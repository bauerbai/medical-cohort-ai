from __future__ import annotations

import math
from typing import Any, ClassVar

import pandas as pd
import statsmodels.api as sm

from engine.base import AnalysisResult, BaseAnalysis, register_analysis


@register_analysis("health_economics.length_of_stay_nb")
class LengthOfStayNegativeBinomial(BaseAnalysis):
    analysis_id: ClassVar[str] = "health_economics.length_of_stay_nb"
    title: ClassVar[str] = "Length-of-stay negative binomial regression"
    description: ClassVar[str] = "Models over-dispersed hospitalization length of stay as count outcome."

    def validate_data(self) -> None:
        outcome = self.parameters.get("los_col", "length_of_stay_days")
        predictors = self.parameters.get("predictors", [])
        self.required_columns = [outcome, *predictors]
        super().validate_data()

    def _execute_sync(self) -> AnalysisResult:
        outcome = self.parameters.get("los_col", "length_of_stay_days")
        predictors = self.parameters.get("predictors", [])
        df = self.data[[outcome, *predictors]].dropna().copy()
        df = df[df[outcome] >= 0]
        x = pd.get_dummies(df[predictors], drop_first=True) if predictors else pd.DataFrame(index=df.index)
        x = sm.add_constant(x.astype(float), has_constant="add")
        y = df[outcome].astype(float)
        model = sm.GLM(y, x, family=sm.families.NegativeBinomial()).fit()
        estimates = []
        for term in model.params.index:
            coef = float(model.params[term])
            se = float(model.bse[term])
            estimates.append({"term": term, "incidence_rate_ratio": math.exp(coef), "ci_lower": math.exp(coef - 1.96 * se), "ci_upper": math.exp(coef + 1.96 * se), "p_value": float(model.pvalues[term])})
        result = self._base_result(len(df))
        result.estimates = estimates
        result.diagnostics = {"deviance": float(model.deviance), "pearson_chi2": float(model.pearson_chi2), "aic": float(model.aic)}
        result.interpretation = "IRR > 1 indicates longer expected hospitalization length of stay."
        return result

    def generate_report(self, result: AnalysisResult) -> dict[str, Any]:
        return {"title": result.title, "estimates": result.estimates, "diagnostics": result.diagnostics}


@register_analysis("health_economics.readmission_logistic")
class ReadmissionLogisticRegression(BaseAnalysis):
    analysis_id: ClassVar[str] = "health_economics.readmission_logistic"
    title: ClassVar[str] = "30-day readmission logistic regression"
    description: ClassVar[str] = "Adjusted logistic regression for 30-day readmission outcome."

    def validate_data(self) -> None:
        outcome = self.parameters.get("readmission_col", "readmission_30d")
        predictors = self.parameters.get("predictors", [])
        self.required_columns = [outcome, *predictors]
        super().validate_data()

    def _execute_sync(self) -> AnalysisResult:
        from engine.epidemiology import LogisticRegressionAnalysis
        params = {"outcome_col": self.parameters.get("readmission_col", "readmission_30d"), "predictors": self.parameters.get("predictors", [])}
        analysis = LogisticRegressionAnalysis(self.data, params)
        return analysis._execute_sync()

    def generate_report(self, result: AnalysisResult) -> dict[str, Any]:
        return {"title": self.title, "estimates": result.estimates, "diagnostics": result.diagnostics}
