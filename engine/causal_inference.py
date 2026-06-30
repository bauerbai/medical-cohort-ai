from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pandas as pd

from engine.base import AnalysisResult, AnalysisValidationError, BaseAnalysis, register_analysis


@register_analysis("causal.psm")
class PropensityScoreMatching(BaseAnalysis):
    analysis_id: ClassVar[str] = "causal.psm"
    title: ClassVar[str] = "Propensity score matching"
    description: ClassVar[str] = "1:1 nearest-neighbor PSM with caliper and standardized mean difference diagnostics."
    required_columns: ClassVar[list[str]] = []
    assumptions: ClassVar[list[str]] = [
        "Conditional exchangeability after measured covariate adjustment",
        "Positivity: overlap in propensity scores between treated and control patients",
        "Stable unit treatment value assumption",
        "No immortal time bias in treatment/exposure definition",
    ]
    bias_checks: ClassVar[list[str]] = [
        "Use new-user design for medication exposures where possible",
        "Define index date consistently for treated and control groups",
        "Inspect covariate balance before and after matching",
        "Avoid adjusting for mediators measured after exposure",
    ]

    def validate_data(self) -> None:
        treatment_col = self.parameters.get("treatment_col")
        covariates = self.parameters.get("covariates", [])
        if not treatment_col or not covariates:
            raise AnalysisValidationError("treatment_col and covariates are required")
        self.required_columns = [treatment_col, *covariates]
        super().validate_data()

        treatment_values = set(self.data[treatment_col].dropna().unique().tolist())
        if not treatment_values.issubset({0, 1, False, True}):
            raise AnalysisValidationError("Treatment column must be binary 0/1")
        if self.data[treatment_col].nunique(dropna=True) != 2:
            raise AnalysisValidationError("Treatment column must include both treated and control subjects")

    def _prepare_frame(self) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
        treatment_col = self.parameters["treatment_col"]
        covariates = self.parameters["covariates"]
        categorical_covariates = set(self.parameters.get("categorical_covariates", []))

        df = self.data[[treatment_col, *covariates]].copy().dropna(subset=[treatment_col])
        y = df[treatment_col].astype(int)
        x = df[covariates].copy()
        for col in x.columns:
            if col in categorical_covariates or not pd.api.types.is_numeric_dtype(x[col]):
                x[col] = x[col].astype("category")
        x = pd.get_dummies(x, drop_first=True)
        x = x.apply(pd.to_numeric, errors="coerce")
        keep = x.notna().all(axis=1)
        return df.loc[keep].copy(), y.loc[keep].copy(), x.loc[keep].copy()

    def _execute_sync(self) -> AnalysisResult:
        from sklearn.linear_model import LogisticRegression
        from sklearn.neighbors import NearestNeighbors
        from sklearn.preprocessing import StandardScaler

        treatment_col = self.parameters["treatment_col"]
        caliper = float(self.parameters.get("caliper", 0.2))
        covariates = self.parameters["covariates"]

        original_df, y, x = self._prepare_frame()
        scaler = StandardScaler()
        x_scaled = scaler.fit_transform(x)

        ps_model = LogisticRegression(max_iter=2000, solver="lbfgs")
        ps_model.fit(x_scaled, y)
        propensity = ps_model.predict_proba(x_scaled)[:, 1]
        logit_ps = np.log(propensity / (1 - propensity))
        original_df["propensity_score"] = propensity
        original_df["logit_ps"] = logit_ps

        matched_pairs = self._match_1_to_1(original_df, treatment_col, caliper, NearestNeighbors)
        matched_df = self._build_matched_frame(original_df, matched_pairs)

        balance_before = self._compute_smd(original_df, treatment_col, covariates)
        balance_after = self._compute_smd(matched_df, treatment_col, covariates) if not matched_df.empty else {}

        result = self._base_result(n_used=len(matched_df))
        result.estimates = [
            {
                "matched_pairs": len(matched_pairs),
                "treated_total": int((original_df[treatment_col] == 1).sum()),
                "control_total": int((original_df[treatment_col] == 0).sum()),
                "caliper": caliper,
                "propensity_mean_treated": float(original_df.loc[original_df[treatment_col] == 1, "propensity_score"].mean()),
                "propensity_mean_control": float(original_df.loc[original_df[treatment_col] == 0, "propensity_score"].mean()),
            }
        ]
        result.diagnostics = {
            "balance_before": balance_before,
            "balance_after": balance_after,
            "max_abs_smd_before": self._max_abs_smd(balance_before),
            "max_abs_smd_after": self._max_abs_smd(balance_after),
            "common_support": {
                "treated_min": float(original_df.loc[original_df[treatment_col] == 1, "propensity_score"].min()),
                "treated_max": float(original_df.loc[original_df[treatment_col] == 1, "propensity_score"].max()),
                "control_min": float(original_df.loc[original_df[treatment_col] == 0, "propensity_score"].min()),
                "control_max": float(original_df.loc[original_df[treatment_col] == 0, "propensity_score"].max()),
            },
        }
        result.tables = {
            "matched_pairs": matched_pairs,
            "balance_before": balance_before,
            "balance_after": balance_after,
        }
        result.plots = {"love_plot_plotly": self._build_love_plot(balance_before, balance_after)}
        result.interpretation = (
            "SMD values below 0.1 are commonly treated as acceptable balance. "
            "PSM only addresses measured confounding; residual and unmeasured confounding remain possible."
        )
        result.warnings = self.warnings
        if len(matched_pairs) == 0:
            result.warnings.append("No matched pairs found; relax caliper or inspect overlap.")
        return result

    def _match_1_to_1(self, df: pd.DataFrame, treatment_col: str, caliper: float, nn_cls: Any) -> list[dict[str, Any]]:
        treated = df[df[treatment_col] == 1].copy()
        controls = df[df[treatment_col] == 0].copy()
        if treated.empty or controls.empty:
            return []

        logit_sd = float(df["logit_ps"].std())
        caliper_width = caliper * logit_sd if logit_sd > 0 else caliper
        nn = nn_cls(n_neighbors=1, algorithm="auto")
        nn.fit(controls[["logit_ps"]])
        distances, indices = nn.kneighbors(treated[["logit_ps"]])

        available_controls = set(range(len(controls)))
        pairs: list[dict[str, Any]] = []
        controls_index = controls.index.to_list()
        treated_index = treated.index.to_list()
        for i, distance in enumerate(distances[:, 0]):
            control_pos = int(indices[i, 0])
            if distance > caliper_width or control_pos not in available_controls:
                continue
            available_controls.remove(control_pos)
            pairs.append(
                {
                    "treated_index": int(treated_index[i]) if isinstance(treated_index[i], (int, np.integer)) else str(treated_index[i]),
                    "control_index": int(controls_index[control_pos]) if isinstance(controls_index[control_pos], (int, np.integer)) else str(controls_index[control_pos]),
                    "distance": float(distance),
                }
            )
        return pairs

    def _build_matched_frame(self, df: pd.DataFrame, pairs: list[dict[str, Any]]) -> pd.DataFrame:
        if not pairs:
            return df.iloc[0:0].copy()
        matched_indices: list[Any] = []
        for pair in pairs:
            matched_indices.extend([pair["treated_index"], pair["control_index"]])
        return df.loc[matched_indices].copy()

    def _compute_smd(self, df: pd.DataFrame, treatment_col: str, covariates: list[str]) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        treated = df[df[treatment_col] == 1]
        controls = df[df[treatment_col] == 0]
        for covariate in covariates:
            if covariate not in df.columns:
                continue
            if pd.api.types.is_numeric_dtype(df[covariate]):
                smd = self._numeric_smd(treated[covariate], controls[covariate])
                results[covariate] = {"type": "continuous", "smd": smd}
            else:
                levels = sorted(df[covariate].dropna().astype(str).unique().tolist())
                level_smd = {}
                for level in levels:
                    treated_prop = (treated[covariate].astype(str) == level).mean()
                    control_prop = (controls[covariate].astype(str) == level).mean()
                    pooled = (treated_prop * (1 - treated_prop) + control_prop * (1 - control_prop)) / 2
                    level_smd[level] = float((treated_prop - control_prop) / np.sqrt(pooled)) if pooled > 0 else 0.0
                results[covariate] = {"type": "categorical", "levels": level_smd, "smd": max([abs(v) for v in level_smd.values()] or [0.0])}
        return results

    def _numeric_smd(self, treated: pd.Series, controls: pd.Series) -> float:
        treated = pd.to_numeric(treated, errors="coerce").dropna()
        controls = pd.to_numeric(controls, errors="coerce").dropna()
        pooled_sd = np.sqrt((treated.var(ddof=1) + controls.var(ddof=1)) / 2)
        if pooled_sd == 0 or np.isnan(pooled_sd):
            return 0.0
        return float((treated.mean() - controls.mean()) / pooled_sd)

    def _max_abs_smd(self, balance: dict[str, dict[str, Any]]) -> float | None:
        if not balance:
            return None
        return float(max(abs(item.get("smd", 0.0)) for item in balance.values()))

    def _build_love_plot(self, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        covariates = list(before.keys())
        return {
            "data": [
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "Before matching",
                    "x": [abs(before[cov].get("smd", 0.0)) for cov in covariates],
                    "y": covariates,
                },
                {
                    "type": "scatter",
                    "mode": "markers",
                    "name": "After matching",
                    "x": [abs(after.get(cov, {}).get("smd", 0.0)) for cov in covariates],
                    "y": covariates,
                },
            ],
            "layout": {
                "title": "Covariate balance Love plot",
                "xaxis": {"title": "Absolute standardized mean difference"},
                "yaxis": {"title": "Covariate"},
                "shapes": [{"type": "line", "x0": 0.1, "x1": 0.1, "y0": -0.5, "y1": len(covariates) - 0.5, "line": {"dash": "dash", "color": "red"}}],
                "template": "plotly_white",
            },
        }

    def generate_report(self, result: AnalysisResult) -> dict[str, Any]:
        return {
            "title": result.title,
            "sections": [
                {"heading": "Matching summary", "table": result.estimates},
                {"heading": "Balance before matching", "table": result.tables.get("balance_before", {})},
                {"heading": "Balance after matching", "table": result.tables.get("balance_after", {})},
                {"heading": "Interpretation", "text": result.interpretation},
            ],
            "plots": result.plots,
            "warnings": result.warnings,
        }
