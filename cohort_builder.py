from textwrap import dedent
from typing import Any


EXPOSURE_DEFINITIONS: dict[str, dict[str, str | None]] = {
    "LDL-C": {
        "label": "LDL-C",
        "source_table": "unified_vitals",
        "source_column": None,
        "description": "低密度脂蛋白胆固醇；当前语义层尚未发现对应字段。",
    },
    "SBP": {
        "label": "SBP",
        "source_table": "unified_vitals",
        "source_column": "systolic_bp",
        "description": "基线收缩压，来自 unified_vitals.systolic_bp。",
    },
    "DBP": {
        "label": "DBP",
        "source_table": "unified_vitals",
        "source_column": "diastolic_bp",
        "description": "基线舒张压，来自 unified_vitals.diastolic_bp。",
    },
}


OUTCOME_DEFINITIONS: dict[str, dict[str, str]] = {
    "G30": {"label": "G30 阿尔茨海默病", "icd_code": "G30", "description_terms": "alzheimer,dementia,阿尔茨海默"},
    "I10": {"label": "I10 原发性高血压", "icd_code": "I10", "description_terms": "hypertension,essential,primary,高血压"},
    "E78": {"label": "E78 高脂血症", "icd_code": "E78", "description_terms": "hyperlipidemia,cholesterol,lipid,高血脂,高脂血症"},
    "E11": {"label": "E11 2型糖尿病", "icd_code": "E11", "description_terms": "diabetes,type 2,糖尿病"},
    "I25": {"label": "I25 慢性缺血性心脏病", "icd_code": "I25", "description_terms": "ischemic heart,ischaemic heart,coronary,冠心病"},
    "J45": {"label": "J45 哮喘", "icd_code": "J45", "description_terms": "asthma,哮喘"},
    "I21": {"label": "I21 急性心肌梗死", "icd_code": "I21", "description_terms": "myocardial infarction,心梗,心肌梗死"},
    "I64": {"label": "I64 脑卒中", "icd_code": "I64", "description_terms": "stroke,脑卒中,中风"},
    "K21": {"label": "K21 胃食管反流病", "icd_code": "K21", "description_terms": "gastro-oesophageal reflux,gastroesophageal reflux,胃食管反流,反流"},
}


def get_common_exposures(metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    vitals_columns = set()
    if metadata:
        vitals_columns = {
            column["name"]
            for column in metadata.get("tables", {})
            .get("unified_vitals", {})
            .get("columns", [])
        }

    options: list[dict[str, Any]] = []
    for key, definition in EXPOSURE_DEFINITIONS.items():
        source_column = definition["source_column"]
        available = source_column is None or source_column in vitals_columns
        options.append(
            {
                "value": key,
                "label": definition["label"],
                "description": definition["description"],
                "available": available,
            }
        )
    return options


def get_common_outcomes() -> list[dict[str, str]]:
    return [
        {
            "value": key,
            "label": definition["label"],
            "icd_code": definition["icd_code"],
        }
        for key, definition in OUTCOME_DEFINITIONS.items()
    ]


def normalize_exposure(value: str) -> str | None:
    normalized = value.strip().upper().replace(" ", "")
    aliases = {
        "LDLC": "LDL-C",
        "LDL-C": "LDL-C",
        "LDL": "LDL-C",
        "SBP": "SBP",
        "收缩压": "SBP",
        "DBP": "DBP",
        "舒张压": "DBP",
    }
    return aliases.get(normalized)


def normalize_outcome(value: str) -> str | None:
    normalized = value.strip().upper()
    aliases = {
        "高血压": "I10",
        "HYPERTENSION": "I10",
        "高血脂": "E78",
        "高脂血症": "E78",
        "HYPERLIPIDEMIA": "E78",
        "糖尿病": "E11",
        "DIABETES": "E11",
        "阿尔茨海默": "G30",
        "ALZHEIMER": "G30",
        "冠心病": "I25",
        "哮喘": "J45",
    }
    for term, outcome_key in aliases.items():
        if term in normalized:
            return outcome_key
    if normalized in OUTCOME_DEFINITIONS:
        return normalized
    for key, definition in OUTCOME_DEFINITIONS.items():
        if definition["icd_code"] == normalized:
            return key
    return None


def build_cohort_sql(params: dict[str, Any]) -> dict[str, Any]:
    exposure = params.get("exposure")
    outcome = params.get("outcome")
    if exposure not in EXPOSURE_DEFINITIONS:
        raise ValueError(f"Unsupported exposure: {exposure}")
    if outcome not in OUTCOME_DEFINITIONS:
        raise ValueError(f"Unsupported outcome: {outcome}")

    exposure_definition = EXPOSURE_DEFINITIONS[exposure]
    outcome_definition = OUTCOME_DEFINITIONS[outcome]
    exposure_column = exposure_definition["source_column"]
    icd_code = outcome_definition["icd_code"]
    description_terms = [
        term.strip().replace("'", "''")
        for term in outcome_definition.get("description_terms", "").split(",")
        if term.strip()
    ]
    description_filters = "\n                OR ".join(
        f"d.icd10_description ILIKE '%{term}%'" for term in description_terms
    )
    diagnosis_filter = f"d.mapped_icd10 ILIKE '%{icd_code}%'"
    if description_filters:
        diagnosis_filter = f"({diagnosis_filter}\n                OR {description_filters})"

    warnings: list[str] = []
    if exposure_column is None:
        exposure_expr = "NULL::numeric"
        warnings.append(
            f"当前数据库语义层未发现 {exposure} 的真实字段，SQL 中 exposure_value 暂以 NULL::numeric 占位。"
        )
    else:
        exposure_expr = f"v.{exposure_column}"

    sql = dedent(
        f"""
        WITH baseline AS (
            SELECT
                p.patient_id,
                p.age_at_recruitment,
                p.sex,
                p.townsend_deprivation_index,
                make_date(
                    (p.birth_year + floor(p.age_at_recruitment)::int),
                    COALESCE(NULLIF(p.birth_month, 0), 7),
                    1
                ) AS baseline_date
            FROM ukb_semantic.patient_master_index AS p
        ),
        outcome_events AS (
            SELECT
                d.patient_id,
                MIN(d.event_date) AS first_outcome_date,
                COUNT(*) AS outcome_record_count
            FROM ukb_semantic.unified_diagnoses AS d
            WHERE {diagnosis_filter}
            GROUP BY d.patient_id
        )
        SELECT
            b.patient_id,
            b.age_at_recruitment,
            b.sex,
            b.townsend_deprivation_index,
            b.baseline_date,
            '{exposure}' AS exposure_name,
            {exposure_expr} AS exposure_value,
            '{icd_code}' AS outcome_icd10,
            oe.first_outcome_date,
            NULL::date AS first_occurrence_date,
            CASE WHEN oe.patient_id IS NULL THEN 0 ELSE 1 END AS outcome_status,
            oe.outcome_record_count
        FROM baseline AS b
        LEFT JOIN ukb_semantic.unified_vitals AS v
            ON v.patient_id = b.patient_id
        LEFT JOIN outcome_events AS oe
            ON oe.patient_id = b.patient_id
        WHERE oe.first_outcome_date IS NULL
           OR oe.first_outcome_date >= b.baseline_date
        ORDER BY b.patient_id;
        """
    ).strip()

    return {
        "sql": sql,
        "warnings": warnings,
        "params": {
            "analysis_type": params.get("analysis_type"),
            "mr_type": params.get("mr_type"),
            "exposure": exposure,
            "outcome": outcome,
            "icd_code": icd_code,
        },
    }

