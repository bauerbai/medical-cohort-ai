from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class SQLGuardrailViolation:
    rule_id: str
    message: str
    suggestion: str
    evidence: str = ""


class SQLGuardrailError(ValueError):
    def __init__(self, violations: Iterable[SQLGuardrailViolation]):
        self.violations = list(violations)
        detail = "\n".join(f"[{v.rule_id}] {v.message} 建议：{v.suggestion}" for v in self.violations)
        super().__init__(detail)


READ_CODE_COLUMNS = {
    "read2_code",
    "read3_code",
    "read_code",
    "readv2_code",
    "readv3_code",
    "ctv3_code",
}
DIAGNOSIS_TABLE_PATTERNS = {
    "diagnoses",
    "diagnosis",
    "gp_diagnoses",
    "hospital_diagnoses",
    "unified_diagnoses",
    "v_all_diagnoses_standardized",
}
LAB_TABLE_PATTERNS = {"lab", "labs", "laboratory", "measurements", "observations"}
LAB_VALUE_COLUMNS = {"creatinine", "hba1c", "glucose", "ldl", "hdl", "cholesterol", "egfr"}


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql


def _uses_any_table(sql_lower: str, table_terms: set[str]) -> bool:
    return any(re.search(rf"\b{re.escape(term)}\w*\b", sql_lower) for term in table_terms)


def _has_read_exact_match(sql: str) -> re.Match[str] | None:
    column_pattern = "|".join(re.escape(column) for column in sorted(READ_CODE_COLUMNS))
    return re.search(rf"\b(?:{column_pattern})\b\s*=\s*'[^']+'", sql, flags=re.IGNORECASE)


def _has_read_prefix_or_mapping(sql_lower: str) -> bool:
    return bool(
        re.search(r"\bread(?:2|3|v2|v3)?_?code\b\s+(?:i?like|similar\s+to)\s*'[^']*%'", sql_lower)
        or "mapped_standard_code" in sql_lower
        or "standard_disease" in sql_lower
        or "v_all_diagnoses_standardized" in sql_lower
    )


def _has_count_star(sql_lower: str) -> bool:
    return bool(re.search(r"\bcount\s*\(\s*\*\s*\)", sql_lower))


def _has_count_distinct_patient(sql_lower: str) -> bool:
    return bool(re.search(r"\bcount\s*\(\s*distinct\s+[^)]*patient_id", sql_lower))


def _groups_by_patient_id(sql_lower: str) -> bool:
    return bool(re.search(r"\bgroup\s+by\b[^;]*\bpatient_id\b", sql_lower, flags=re.DOTALL))


def _has_unit_filter(sql_lower: str) -> bool:
    return bool(re.search(r"\bunit\b\s*(=|in\s*\(|ilike|like)", sql_lower)) or "unit_harmon" in sql_lower


def _has_lab_value_filter_without_unit(sql_lower: str) -> bool:
    if not _uses_any_table(sql_lower, LAB_TABLE_PATTERNS):
        return False
    if _has_unit_filter(sql_lower):
        return False
    for column in LAB_VALUE_COLUMNS:
        if re.search(rf"\b{re.escape(column)}\b\s*(>=|<=|>|<|between)", sql_lower):
            return True
    return False


def _has_invalid_censoring_pattern(sql_lower: str) -> bool:
    mentions_survival_dates = any(term in sql_lower for term in {"death_date", "last_visit", "last_follow", "censor"})
    if not mentions_survival_dates:
        return False
    return "least(" not in sql_lower and "death_date" in sql_lower and ("last_visit" in sql_lower or "last_follow" in sql_lower)


def validate_sql_guardrails(sql: str) -> list[SQLGuardrailViolation]:
    cleaned = _strip_sql_comments(sql)
    lowered = cleaned.lower()
    violations: list[SQLGuardrailViolation] = []

    read_exact = _has_read_exact_match(cleaned)
    if read_exact:
        violations.append(
            SQLGuardrailViolation(
                rule_id="READ_PREFIX_MATCH_REQUIRED",
                message="检测到 Read2/Read3 编码精确匹配，这会漏掉层级子分类。",
                suggestion="将 read2/read3 条件改为 LIKE 'prefix%'，或改查 v_all_diagnoses_standardized.mapped_standard_code。",
                evidence=read_exact.group(0),
            )
        )

    if re.search(r"\bread(?:2|3|v2|v3)?_?code\b", lowered) and not _has_read_prefix_or_mapping(lowered):
        violations.append(
            SQLGuardrailViolation(
                rule_id="READ_MAPPING_OR_PREFIX_REQUIRED",
                message="检测到 Read 编码查询，但未看到前缀匹配或标准语义映射。",
                suggestion="使用 read2_code LIKE 'G3%'，或先通过标准诊断视图查询 mapped_standard_code。",
            )
        )

    if _uses_any_table(lowered, DIAGNOSIS_TABLE_PATTERNS) and _has_count_star(lowered) and not _has_count_distinct_patient(lowered) and not _groups_by_patient_id(lowered):
        violations.append(
            SQLGuardrailViolation(
                rule_id="DIAGNOSIS_COUNT_DISTINCT_REQUIRED",
                message="诊断/疾病统计使用 COUNT(*)，可能被重复就诊或重复诊断记录放大发病率。",
                suggestion="统计患者人数请使用 COUNT(DISTINCT patient_id)；统计事件还应按 visit_id/episode_id 去重。",
            )
        )

    if _has_lab_value_filter_without_unit(lowered):
        violations.append(
            SQLGuardrailViolation(
                rule_id="LAB_UNIT_HARMONIZATION_REQUIRED",
                message="检测到检验指标阈值筛选，但未限定或统一 unit 字段。",
                suggestion="先进行单位统一，或在 WHERE 中同时限定 unit，例如 unit='umol/L'。",
            )
        )

    if _has_invalid_censoring_pattern(lowered):
        violations.append(
            SQLGuardrailViolation(
                rule_id="CENSORING_LEAST_REQUIRED",
                message="检测到生存/随访终点计算涉及死亡日期和末次随访，但未使用 LEAST() 防止死亡后记录延长随访。",
                suggestion="end_date 应使用 LEAST(death_date, last_visit_date, database_lock_date)。",
            )
        )

    return violations


def assert_sql_safe(sql: str) -> None:
    violations = validate_sql_guardrails(sql)
    if violations:
        raise SQLGuardrailError(violations)



