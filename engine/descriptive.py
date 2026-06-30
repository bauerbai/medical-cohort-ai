from __future__ import annotations

from typing import Any, ClassVar

import numpy as np
import pandas as pd

from engine.base import AnalysisResult, AnalysisValidationError, BaseAnalysis, register_analysis


@register_analysis("descriptive.table1")
class TableOneAnalysis(BaseAnalysis):
    analysis_id: ClassVar[str] = "descriptive.table1"
    title: ClassVar[str] = "Table 1 baseline characteristics"
    description: ClassVar[str] = "Publication-style baseline Table 1 by optional group variable."

    def validate_data(self) -> None:
        variables = self.parameters.get("variables", [])
        group_col = self.parameters.get("group_col")
        self.required_columns = [*variables, *([group_col] if group_col else [])]
        super().validate_data()
        if not variables:
            raise AnalysisValidationError("variables is required")

    def _execute_sync(self) -> AnalysisResult:
        variables = self.parameters["variables"]
        group_col = self.parameters.get("group_col")
        df = self.data.dropna(how="all", subset=variables).copy()
        groups = [("Overall", df)] if not group_col else [(str(k), v) for k, v in df.groupby(group_col, dropna=False)]
        rows = []
        for variable in variables:
            for group, item in groups:
                series = item[variable]
                if pd.api.types.is_numeric_dtype(series):
                    clean = pd.to_numeric(series, errors="coerce").dropna()
                    rows.append({"variable": variable, "group": group, "n": int(clean.size), "summary": f"{clean.mean():.3g} ({clean.std(ddof=1):.3g})" if clean.size > 1 else "NA"})
                else:
                    counts = series.astype("string").fillna("Missing").value_counts().to_dict()
                    rows.append({"variable": variable, "group": group, "n": int(series.notna().sum()), "summary": counts})
        result = self._base_result(len(df))
        result.tables = {"table1": rows}
        result.interpretation = "Continuous variables are shown as mean (SD); categorical variables as level counts."
        return result

    def generate_report(self, result: AnalysisResult) -> dict[str, Any]:
        return {"title": result.title, "tables": result.tables, "warnings": result.warnings}


@register_analysis("descriptive.multimorbidity")
class MultimorbidityPatternAnalysis(BaseAnalysis):
    analysis_id: ClassVar[str] = "descriptive.multimorbidity"
    title: ClassVar[str] = "Multimorbidity pattern analysis"
    description: ClassVar[str] = "Counts disease-code co-occurrence patterns by patient."

    def validate_data(self) -> None:
        patient_col = self.parameters.get("patient_col", "patient_id")
        code_col = self.parameters.get("code_col")
        self.required_columns = [patient_col, code_col]
        super().validate_data()

    def _execute_sync(self) -> AnalysisResult:
        patient_col = self.parameters.get("patient_col", "patient_id")
        code_col = self.parameters["code_col"]
        min_count = int(self.parameters.get("min_count", 2))
        top_n = int(self.parameters.get("top_n", 30))
        df = self.data[[patient_col, code_col]].dropna().copy()
        df[code_col] = df[code_col].astype(str).str.slice(0, self.parameters.get("code_prefix_length", 3))
        patient_codes = df.groupby(patient_col)[code_col].apply(lambda s: tuple(sorted(set(s))))
        burden = patient_codes.apply(len)
        patterns = patient_codes[patient_codes.apply(len) >= min_count].value_counts().head(top_n)
        result = self._base_result(len(patient_codes))
        result.tables = {
            "burden_distribution": burden.value_counts().sort_index().to_dict(),
            "top_patterns": [{"pattern": list(k), "count": int(v)} for k, v in patterns.items()],
        }
        result.interpretation = "Patterns are unordered co-occurring disease-code prefixes within patient."
        return result

    def generate_report(self, result: AnalysisResult) -> dict[str, Any]:
        return {"title": result.title, "tables": result.tables}
