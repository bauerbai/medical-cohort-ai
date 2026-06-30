from __future__ import annotations

from typing import Any, ClassVar

import pandas as pd

from engine.base import AnalysisResult, AnalysisValidationError, BaseAnalysis, register_analysis


@register_analysis("survival.cox")
class CoxRegressionAnalysis(BaseAnalysis):
    analysis_id: ClassVar[str] = "survival.cox"
    title: ClassVar[str] = "Cox proportional hazards regression"
    description: ClassVar[str] = (
        "Multivariable Cox PH model with Schoenfeld residual PH diagnostics "
        "and Kaplan-Meier curve data prepared for Plotly."
    )
    required_columns: ClassVar[list[str]] = []
    assumptions: ClassVar[list[str]] = [
        "Independent censoring",
        "Correct time origin and no immortal time bias",
        "Proportional hazards for modeled covariates",
        "No severe multicollinearity among covariates",
    ]
    bias_checks: ClassVar[list[str]] = [
        "Confirm exposure is measured before follow-up starts",
        "Exclude baseline prevalent outcome cases",
        "Consider confounding by age, sex, socioeconomic status, comorbidity",
        "Assess informative censoring and competing risks",
    ]

    def validate_data(self) -> None:
        time_col = self.parameters.get("time_col")
        event_col = self.parameters.get("event_col")
        exposure = self.parameters.get("exposure")
        covariates = self.parameters.get("covariates", [])
        self.required_columns = [time_col, event_col, exposure, *covariates]
        super().validate_data()

        if not time_col or not event_col or not exposure:
            raise AnalysisValidationError("time_col, event_col and exposure are required")
        if (self.data[time_col] <= 0).any():
            raise AnalysisValidationError("Follow-up time must be positive for Cox regression")
        if self.data[event_col].dropna().nunique() < 2:
            raise AnalysisValidationError("Event column must contain both events and non-events")

    def _prepare_model_frame(self) -> pd.DataFrame:
        time_col = self.parameters["time_col"]
        event_col = self.parameters["event_col"]
        exposure = self.parameters["exposure"]
        covariates = self.parameters.get("covariates", [])
        columns = [time_col, event_col, exposure, *covariates]
        df = self.data.loc[:, columns].copy()
        df = df.dropna(subset=[time_col, event_col, exposure])

        categorical_covariates = self.parameters.get("categorical_covariates", [])
        categorical_covariates = [col for col in categorical_covariates if col in df.columns]
        if categorical_covariates:
            df = pd.get_dummies(df, columns=categorical_covariates, drop_first=True)

        for col in df.columns:
            if col not in {time_col, event_col}:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna()
        return df

    def _execute_sync(self) -> AnalysisResult:
        from lifelines import CoxPHFitter, KaplanMeierFitter
        from lifelines.statistics import proportional_hazard_test

        time_col = self.parameters["time_col"]
        event_col = self.parameters["event_col"]
        exposure = self.parameters["exposure"]
        strata_col = self.parameters.get("km_group_col", exposure)
        alpha = float(self.parameters.get("alpha", 0.05))

        df = self._prepare_model_frame()
        if len(df) < 20:
            self.warnings.append("Small sample size; Cox estimates may be unstable.")

        cph = CoxPHFitter()
        cph.fit(df, duration_col=time_col, event_col=event_col, robust=True)

        summary = cph.summary.reset_index(names="term")
        estimates: list[dict[str, Any]] = []
        for _, row in summary.iterrows():
            estimates.append(
                {
                    "term": row["term"],
                    "hazard_ratio": float(row["exp(coef)"]),
                    "ci_lower": float(row["exp(coef) lower 95%"]),
                    "ci_upper": float(row["exp(coef) upper 95%"]),
                    "p_value": float(row["p"]),
                    "coef": float(row["coef"]),
                    "se": float(row["se(coef)"]),
                }
            )

        ph_test = proportional_hazard_test(cph, df, time_transform="rank")
        ph_table = ph_test.summary.reset_index(names="term")
        ph_diagnostics = {
            str(row["term"]): {
                "test_statistic": float(row["test_statistic"]),
                "p_value": float(row["p"]),
                "violates_ph": bool(row["p"] < alpha),
            }
            for _, row in ph_table.iterrows()
        }
        if any(item["violates_ph"] for item in ph_diagnostics.values()):
            self.warnings.append("One or more covariates may violate the proportional hazards assumption.")

        km_plot = self._build_km_plotly_json(df, time_col, event_col, strata_col, KaplanMeierFitter)

        result = self._base_result(n_used=len(df))
        result.estimates = estimates
        result.diagnostics = {
            "proportional_hazards_schoenfeld": ph_diagnostics,
            "concordance_index": float(cph.concordance_index_),
            "log_likelihood": float(cph.log_likelihood_),
        }
        result.plots = {"kaplan_meier_plotly": km_plot}
        result.tables = {
            "cox_summary": estimates,
            "ph_test": ph_diagnostics,
        }
        result.interpretation = (
            "Hazard ratios above 1 indicate higher instantaneous risk. "
            "Interpret causally only if time zero, confounding control, and censoring assumptions are defensible."
        )
        result.warnings = self.warnings
        return result

    def _build_km_plotly_json(
        self,
        df: pd.DataFrame,
        time_col: str,
        event_col: str,
        strata_col: str,
        km_cls: Any,
    ) -> dict[str, Any]:
        if strata_col not in df.columns:
            strata_col = self.parameters["exposure"]

        plot_df = df.copy()
        if pd.api.types.is_numeric_dtype(plot_df[strata_col]) and plot_df[strata_col].nunique() > 2:
            median_value = plot_df[strata_col].median()
            plot_df["__km_group"] = plot_df[strata_col].apply(lambda value: f">= median ({median_value:.3g})" if value >= median_value else f"< median ({median_value:.3g})")
        else:
            plot_df["__km_group"] = plot_df[strata_col].astype(str)

        traces = []
        kmf = km_cls()
        for group, group_df in plot_df.groupby("__km_group"):
            if group_df.empty:
                continue
            kmf.fit(group_df[time_col], group_df[event_col], label=str(group))
            sf = kmf.survival_function_.reset_index()
            traces.append(
                {
                    "type": "scatter",
                    "mode": "lines",
                    "name": str(group),
                    "x": sf.iloc[:, 0].astype(float).tolist(),
                    "y": sf.iloc[:, 1].astype(float).tolist(),
                    "line": {"shape": "hv"},
                }
            )

        return {
            "data": traces,
            "layout": {
                "title": "Kaplan-Meier survival curve",
                "xaxis": {"title": "Follow-up time"},
                "yaxis": {"title": "Survival probability", "range": [0, 1]},
                "template": "plotly_white",
            },
        }

    def generate_report(self, result: AnalysisResult) -> dict[str, Any]:
        return {
            "title": result.title,
            "sections": [
                {"heading": "Model estimates", "table": result.tables.get("cox_summary", [])},
                {"heading": "PH assumption diagnostics", "table": result.tables.get("ph_test", {})},
                {"heading": "Interpretation", "text": result.interpretation},
            ],
            "plots": result.plots,
            "warnings": result.warnings,
        }
