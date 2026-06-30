from __future__ import annotations

import math
from typing import Any, ClassVar

import pandas as pd
import statsmodels.api as sm

from engine.base import AnalysisResult, AnalysisValidationError, BaseAnalysis, register_analysis


def _wald_ci(log_estimate: float, se: float) -> tuple[float, float]:
    return math.exp(log_estimate - 1.96 * se), math.exp(log_estimate + 1.96 * se)


@register_analysis("epidemiology.binary_measure")
class BinaryEpidemiologyMeasure(BaseAnalysis):
    analysis_id: ClassVar[str] = "epidemiology.binary_measure"
    title: ClassVar[str] = "Classical binary epidemiology measures"
    description: ClassVar[str] = "Computes POR, RR, or OR from exposure/outcome 2x2 table."

    def validate_data(self) -> None:
        exposure = self.parameters.get("exposure_col")
        outcome = self.parameters.get("outcome_col")
        self.required_columns = [exposure, outcome]
        super().validate_data()

    def _execute_sync(self) -> AnalysisResult:
        exposure = self.parameters["exposure_col"]
        outcome = self.parameters["outcome_col"]
        measure = self.parameters.get("measure", "OR").upper()
        df = self.data[[exposure, outcome]].dropna().copy()
        e = df[exposure].astype(int)
        y = df[outcome].astype(int)
        a = int(((e == 1) & (y == 1)).sum())
        b = int(((e == 1) & (y == 0)).sum())
        c = int(((e == 0) & (y == 1)).sum())
        d = int(((e == 0) & (y == 0)).sum())
        aa, bb, cc, dd = a + 0.5, b + 0.5, c + 0.5, d + 0.5
        if measure in {"OR", "POR"}:
            estimate = (aa * dd) / (bb * cc)
            se = math.sqrt(1 / aa + 1 / bb + 1 / cc + 1 / dd)
        elif measure == "RR":
            estimate = (aa / (aa + bb)) / (cc / (cc + dd))
            se = math.sqrt((1 / aa) - (1 / (aa + bb)) + (1 / cc) - (1 / (cc + dd)))
        else:
            raise AnalysisValidationError("measure must be OR, POR, or RR")
        ci_low, ci_high = _wald_ci(math.log(estimate), se)
        result = self._base_result(len(df))
        result.estimates = [{"measure": measure, "estimate": estimate, "ci_lower": ci_low, "ci_upper": ci_high, "a": a, "b": b, "c": c, "d": d}]
        result.tables = {"two_by_two": {"exposed_cases": a, "exposed_non_cases": b, "unexposed_cases": c, "unexposed_non_cases": d}}
        result.interpretation = f"{measure} compares outcome frequency between exposed and unexposed groups."
        return result

    def generate_report(self, result: AnalysisResult) -> dict[str, Any]:
        return {"title": result.title, "estimates": result.estimates, "tables": result.tables}


@register_analysis("epidemiology.logistic_regression")
class LogisticRegressionAnalysis(BaseAnalysis):
    analysis_id: ClassVar[str] = "epidemiology.logistic_regression"
    title: ClassVar[str] = "Multivariable logistic regression"
    description: ClassVar[str] = "Adjusted OR model for binary outcomes, including 30-day readmission models."

    def validate_data(self) -> None:
        outcome = self.parameters.get("outcome_col")
        predictors = self.parameters.get("predictors", [])
        self.required_columns = [outcome, *predictors]
        super().validate_data()

    def _execute_sync(self) -> AnalysisResult:
        outcome = self.parameters["outcome_col"]
        predictors = self.parameters["predictors"]
        df = self.data[[outcome, *predictors]].dropna().copy()
        x = pd.get_dummies(df[predictors], drop_first=True)
        x = sm.add_constant(x.astype(float), has_constant="add")
        y = df[outcome].astype(int)
        model = sm.Logit(y, x).fit(disp=False)
        rows = []
        for term in model.params.index:
            coef = float(model.params[term])
            se = float(model.bse[term])
            ci_low, ci_high = _wald_ci(coef, se)
            rows.append({"term": term, "odds_ratio": math.exp(coef), "ci_lower": ci_low, "ci_upper": ci_high, "p_value": float(model.pvalues[term])})
        result = self._base_result(len(df))
        result.estimates = rows
        result.diagnostics = {"aic": float(model.aic), "bic": float(model.bic)}
        return result

    def generate_report(self, result: AnalysisResult) -> dict[str, Any]:
        return {"title": result.title, "estimates": result.estimates, "diagnostics": result.diagnostics}
