from __future__ import annotations

import re
from typing import Any

import pandas as pd
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from database import get_db_connection, release_db_connection
from sql_guardrails import assert_sql_safe
from engine import AnalysisRegistry
from engine.causal_inference import PropensityScoreMatching
from engine.survival import CoxRegressionAnalysis


MAX_TOOL_ROWS = 20000


class CoxToolInput(BaseModel):
    sql: str = Field(..., description="SQL that returns one row per subject with time/event/exposure/covariates")
    time_col: str = Field(..., description="Positive follow-up duration column")
    event_col: str = Field(..., description="Binary event indicator column")
    exposure: str = Field(..., description="Exposure variable name")
    covariates: list[str] = Field(default_factory=list, description="Adjustment covariates")
    categorical_covariates: list[str] = Field(default_factory=list, description="Categorical covariates to one-hot encode")
    km_group_col: str | None = Field(default=None, description="Variable used to stratify KM curves")
    limit: int = Field(default=MAX_TOOL_ROWS, ge=1, le=100000)


class PSMToolInput(BaseModel):
    sql: str = Field(..., description="SQL returning treatment and covariates")
    treatment_col: str = Field(..., description="Binary treatment/exposure indicator")
    covariates: list[str] = Field(..., description="Pre-exposure confounders for PS model")
    categorical_covariates: list[str] = Field(default_factory=list)
    caliper: float = Field(default=0.2, gt=0, le=1)
    limit: int = Field(default=MAX_TOOL_ROWS, ge=1, le=100000)


class RegisteredAnalysisInput(BaseModel):
    analysis_id: str = Field(..., description="Registered analysis key from /api/analyses")
    sql: str = Field(..., description="SQL returning the analysis-ready dataset")
    parameters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=MAX_TOOL_ROWS, ge=1, le=100000)


class FeasibilityInput(BaseModel):
    disease: str | None = Field(
        default=None,
        description="Clinical disease term or ICD-10 prefix, for example 高血压, hypertension, I10, G30.",
    )
    disease_name: str | None = Field(default=None, description="Optional disease name used for fuzzy description matching.")
    icd10_prefix: str | None = Field(default=None, description="Optional ICD-10 prefix, for example I10 or G30.")
    limit: int = Field(default=10, ge=1, le=50, description="Number of top outcomes to return when disease is missing.")


class SemanticOverviewInput(BaseModel):
    disease_limit: int = Field(default=3, ge=1, le=20)
    drug_limit: int = Field(default=5, ge=1, le=20)


class DiseaseCountInput(BaseModel):
    disease: str = Field(..., description="Clinical disease term or ICD-10 prefix, for example 高血压, I10, 糖尿病.")


CLINICAL_TERM_DICTIONARY: dict[str, dict[str, Any]] = {
    "高血压": {
        "icd10_prefix": "I10",
        "label": "原发性高血压",
        "description_terms": ["hypertension", "essential", "primary", "高血压"],
    },
    "hypertension": {
        "icd10_prefix": "I10",
        "label": "原发性高血压",
        "description_terms": ["hypertension", "essential", "primary"],
    },
    "i10": {
        "icd10_prefix": "I10",
        "label": "原发性高血压",
        "description_terms": ["hypertension", "essential", "primary"],
    },
    "高血脂": {
        "icd10_prefix": "E78",
        "label": "脂质代谢异常/高脂血症",
        "description_terms": ["hyperlipidemia", "lipoprotein", "cholesterol", "lipid", "高血脂"],
    },
    "高脂血症": {
        "icd10_prefix": "E78",
        "label": "脂质代谢异常/高脂血症",
        "description_terms": ["hyperlipidemia", "lipoprotein", "cholesterol", "lipid", "高脂血症"],
    },
    "糖尿病": {
        "icd10_prefix": "E11",
        "label": "2型糖尿病",
        "description_terms": ["diabetes", "type 2", "糖尿病"],
    },
    "type 2 diabetes": {
        "icd10_prefix": "E11",
        "label": "2型糖尿病",
        "description_terms": ["diabetes", "type 2"],
    },
    "阿尔茨海默": {
        "icd10_prefix": "G30",
        "label": "阿尔茨海默病",
        "description_terms": ["alzheimer", "dementia", "阿尔茨海默"],
    },
    "alzheimer": {
        "icd10_prefix": "G30",
        "label": "阿尔茨海默病",
        "description_terms": ["alzheimer", "dementia"],
    },
    "冠心病": {
        "icd10_prefix": "I25",
        "label": "慢性缺血性心脏病/冠心病",
        "description_terms": ["ischemic heart", "ischaemic heart", "coronary", "冠心病"],
    },    "心力衰竭": {
        "icd10_prefix": "I50",
        "label": "心力衰竭",
        "description_terms": ["heart failure", "cardiac failure", "心力衰竭", "心衰"],
    },
    "心衰": {
        "icd10_prefix": "I50",
        "label": "心力衰竭",
        "description_terms": ["heart failure", "cardiac failure", "心力衰竭", "心衰"],
    },
    "heart failure": {
        "icd10_prefix": "I50",
        "label": "心力衰竭",
        "description_terms": ["heart failure", "cardiac failure"],
    },
    "i50": {
        "icd10_prefix": "I50",
        "label": "心力衰竭",
        "description_terms": ["heart failure", "cardiac failure"],
    },
    "哮喘": {
        "icd10_prefix": "J45",
        "label": "哮喘",
        "description_terms": ["asthma", "哮喘"],
    },
}


def _extract_icd10_prefix(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"\b([A-Z]\d{2}[A-Z0-9.]*)\b", value.strip().upper())
    return match.group(1).replace(".", "") if match else None


def _resolve_disease(disease: str | None, disease_name: str | None, icd10_prefix: str | None) -> dict[str, Any] | None:
    raw_terms = [term for term in [disease, disease_name, icd10_prefix] if term]
    for raw_term in raw_terms:
        normalized = raw_term.strip().lower()
        if normalized in CLINICAL_TERM_DICTIONARY:
            return {**CLINICAL_TERM_DICTIONARY[normalized], "matched_input": raw_term}
        for key, definition in CLINICAL_TERM_DICTIONARY.items():
            if key in normalized or normalized in key:
                return {**definition, "matched_input": raw_term}

    code = _extract_icd10_prefix(icd10_prefix or disease or disease_name)
    if code:
        return {
            "icd10_prefix": code,
            "label": disease_name or disease or code,
            "description_terms": [disease_name] if disease_name else [],
            "matched_input": disease or disease_name or icd10_prefix,
        }
    return None


def _extract_known_disease_term(text: str) -> str:
    normalized = text.strip().lower()
    for key in sorted(CLINICAL_TERM_DICTIONARY, key=len, reverse=True):
        if key in normalized:
            return key
    return text


def _format_top_outcome_label(row: dict[str, Any]) -> str:
    code = row.get("mapped_icd10") or "未知编码"
    description = row.get("icd10_description") or ""
    if description and description not in str(code):
        return f"{code} {description}"
    return str(code)


async def _fetch_dataframe(sql: str, limit: int) -> pd.DataFrame:
    assert_sql_safe(sql)
    cleaned_sql = sql.strip().rstrip(";")
    limited_sql = f"SELECT * FROM ({cleaned_sql}) AS agent_tool_data LIMIT $1;"
    connection = await get_db_connection()
    try:
        records = await connection.fetch(limited_sql, limit)
    finally:
        await release_db_connection(connection)
    return pd.DataFrame([dict(record) for record in records])


async def _fetch_top_diagnoses(limit: int) -> list[dict[str, Any]]:
    sql = """
        SELECT
            mapped_icd10,
            icd10_description,
            COUNT(DISTINCT patient_id) AS patient_count,
            COUNT(*) AS record_count
        FROM ukb_semantic.unified_diagnoses
        WHERE mapped_icd10 IS NOT NULL
           OR icd10_description IS NOT NULL
        GROUP BY mapped_icd10, icd10_description
        ORDER BY patient_count DESC, record_count DESC
        LIMIT $1;
    """
    connection = await get_db_connection()
    try:
        records = await connection.fetch(sql, limit)
    finally:
        await release_db_connection(connection)
    return [dict(record) for record in records]


async def _evaluate_diagnosis_feasibility(
    disease: str | None = None,
    disease_name: str | None = None,
    icd10_prefix: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    resolved = _resolve_disease(disease, disease_name, icd10_prefix)
    if not resolved:
        top_diagnoses = await _fetch_top_diagnoses(limit)
        readable = [
            {
                "rank": index,
                "label": _format_top_outcome_label(row),
                "mapped_icd10": row.get("mapped_icd10"),
                "icd10_description": row.get("icd10_description"),
                "patient_count": row.get("patient_count"),
                "record_count": row.get("record_count"),
            }
            for index, row in enumerate(top_diagnoses, start=1)
        ]
        top_text = "、".join(f"{item['label']}({item['patient_count']}人)" for item in readable[:5])
        return {
            "status": "needs_outcome_selection",
            "mode": "top_diagnoses",
            "message": "未指定具体疾病，已从 unified_diagnoses 返回真实有数据的 Top 10 诊断。",
            "top_diagnoses": readable,
            "suggested_reply": (
                f"主任，我先查了诊断表 unified_diagnoses。当前数据最充足的结局包括：{top_text}。"
                "您想以哪个疾病作为结局，或者把其中某个疾病作为暴露来设计队列？"
            ),
        }

    prefix = str(resolved["icd10_prefix"]).upper().replace(".", "")
    description_terms = [term for term in resolved.get("description_terms", []) if term]
    if disease_name and disease_name not in description_terms:
        description_terms.append(disease_name)
    if disease and disease not in description_terms and not _extract_icd10_prefix(disease):
        description_terms.append(disease)

    code_pattern = f"%{prefix}%"
    description_patterns = [f"%{term}%" for term in description_terms] or [f"%{resolved['label']}%"]
    sql = """
        SELECT
            COUNT(DISTINCT patient_id) AS patient_count,
            COUNT(*) AS record_count,
            MIN(event_date) AS first_event_date,
            MAX(event_date) AS last_event_date
        FROM ukb_semantic.unified_diagnoses
        WHERE mapped_icd10 ILIKE $1
           OR icd10_description ILIKE ANY($2::text[]);
    """
    top_code_sql = """
        SELECT
            mapped_icd10,
            icd10_description,
            COUNT(DISTINCT patient_id) AS patient_count,
            COUNT(*) AS record_count
        FROM ukb_semantic.unified_diagnoses
        WHERE mapped_icd10 ILIKE $1
           OR icd10_description ILIKE ANY($2::text[])
        GROUP BY mapped_icd10, icd10_description
        ORDER BY patient_count DESC, record_count DESC
        LIMIT $3;
    """
    connection = await get_db_connection()
    try:
        summary = dict(await connection.fetchrow(sql, code_pattern, description_patterns))
        top_codes = [dict(record) for record in await connection.fetch(top_code_sql, code_pattern, description_patterns, limit)]
    finally:
        await release_db_connection(connection)

    patient_count = summary.get("patient_count") or 0
    label = resolved["label"]
    first_event_date = summary.get("first_event_date")
    last_event_date = summary.get("last_event_date")
    return {
        "status": "success" if patient_count else "no_events_found",
        "mode": "diagnosis_feasibility",
        "resolved_disease": {
            "input": resolved.get("matched_input"),
            "label": label,
            "icd10_prefix": prefix,
            "description_terms": description_terms,
        },
        "diagnosis_source": "ukb_semantic.unified_diagnoses",
        "filter_logic": {
            "mapped_icd10": f"ILIKE '{code_pattern}'",
            "icd10_description": [f"ILIKE '{pattern}'" for pattern in description_patterns],
        },
        "patient_count": patient_count,
        "record_count": summary.get("record_count") or 0,
        "first_event_date": first_event_date.isoformat() if first_event_date else None,
        "last_event_date": last_event_date.isoformat() if last_event_date else None,
        "top_matching_codes": top_codes,
        "suggested_reply": (
            f"主任，我用 unified_diagnoses 重新预检了 {label}（ICD-10 前缀 {prefix}），"
            f"匹配逻辑为 mapped_icd10 模糊匹配或 icd10_description 疾病名匹配。"
            f"目前识别到 {patient_count} 名受试者、{summary.get('record_count') or 0} 条诊断记录。"
        ),
    }


async def _get_semantic_data_overview(disease_limit: int = 3, drug_limit: int = 5) -> dict[str, Any]:
    connection = await get_db_connection()
    try:
        sex_rows = await connection.fetch(
            """
            SELECT
                COALESCE(sex_label, sex::text, '未知') AS label,
                COUNT(*) AS n
            FROM ukb_semantic.patient_master_index
            GROUP BY COALESCE(sex_label, sex::text, '未知')
            ORDER BY n DESC;
            """
        )
        disease_rows = await connection.fetch(
            """
            SELECT
                disease_name_cn AS label,
                COUNT(DISTINCT patient_id) AS patient_count
            FROM ukb_semantic.unified_diagnoses
            WHERE disease_name_cn IS NOT NULL
            GROUP BY disease_name_cn
            ORDER BY patient_count DESC
            LIMIT $1;
            """,
            disease_limit,
        )
        drug_rows = await connection.fetch(
            """
            SELECT
                drug_name_cn AS label,
                COUNT(DISTINCT patient_id) AS patient_count
            FROM ukb_semantic.unified_medications
            WHERE drug_name_cn IS NOT NULL
            GROUP BY drug_name_cn
            ORDER BY patient_count DESC
            LIMIT $1;
            """,
            drug_limit,
        )
        first_occurrence_rows = await connection.fetch(
            """
            SELECT
                event_name_cn AS label,
                COUNT(*) AS event_count
            FROM ukb_semantic.unified_first_occurrences
            WHERE event_name_cn IS NOT NULL
            GROUP BY event_name_cn
            ORDER BY event_count DESC
            LIMIT 5;
            """
        )
        total_patients = await connection.fetchval("SELECT COUNT(*) FROM ukb_semantic.patient_master_index;")
    finally:
        await release_db_connection(connection)

    sex_distribution = [dict(row) for row in sex_rows]
    top_diseases = [dict(row) for row in disease_rows]
    top_drugs = [dict(row) for row in drug_rows]
    top_first_occurrences = [dict(row) for row in first_occurrence_rows]
    sex_text = "、".join(
        f"{row['label']} {row['n']}人（{(row['n'] / total_patients):.1%}）"
        for row in sex_distribution
        if total_patients
    )
    disease_text = "、".join(f"{row['label']} {row['patient_count']}人" for row in top_diseases)
    drug_text = "、".join(f"{row['label']} {row['patient_count']}人" for row in top_drugs)

    return {
        "status": "success",
        "total_patients": total_patients,
        "sex_distribution": sex_distribution,
        "top_diseases": top_diseases,
        "top_drugs": top_drugs,
        "top_first_occurrences": top_first_occurrences,
        "suggested_reply": (
            f"主任，语义化数据预检已完成。当前队列共 {total_patients} 人；"
            f"男女比例为：{sex_text}。"
            f"排名靠前的慢性病/诊断是：{disease_text}。"
            f"常见药物包括：{drug_text}。"
            "这些结果已优先使用 sex_label、disease_name_cn、drug_name_cn 等人话列。"
        ),
    }


async def _get_disease_count(disease: str) -> dict[str, Any]:
    disease_term = _extract_known_disease_term(disease)
    feasibility = await _evaluate_diagnosis_feasibility(disease=disease_term, limit=10)
    total_patients = 0
    connection = await get_db_connection()
    try:
        total_patients = await connection.fetchval("SELECT COUNT(*) FROM ukb_semantic.patient_master_index;")
    finally:
        await release_db_connection(connection)

    resolved = feasibility.get("resolved_disease", {})
    label = resolved.get("label") or disease
    patient_count = feasibility.get("patient_count") or 0
    record_count = feasibility.get("record_count") or 0
    prevalence = patient_count / total_patients if total_patients else None
    top_codes = feasibility.get("top_matching_codes", [])
    code_text = "、".join(
        str(item.get("mapped_icd10") or item.get("icd10_description") or "")
        for item in top_codes[:3]
        if item.get("mapped_icd10") or item.get("icd10_description")
    )

    return {
        "status": feasibility.get("status"),
        "disease": label,
        "total_patients": total_patients,
        "patient_count": patient_count,
        "record_count": record_count,
        "prevalence": prevalence,
        "matched_codes": top_codes,
        "filter_logic": feasibility.get("filter_logic"),
        "suggested_reply": (
            f"主任，库里目前识别到 {label} 患者 {patient_count} 人，"
            f"占全部 {total_patients} 人的 {prevalence:.2%}。"
            f"诊断记录共 {record_count} 条。"
            f"我使用的是语义化诊断表 unified_diagnoses，并按疾病中文名/ICD-10 脏数据模糊匹配；"
            f"主要匹配到的原始编码包括：{code_text}。"
        )
        if prevalence is not None
        else f"主任，库里目前识别到 {label} 患者 {patient_count} 人，诊断记录共 {record_count} 条。",
    }


@tool("run_registered_analysis", args_schema=RegisteredAnalysisInput)
async def run_registered_analysis(analysis_id: str, sql: str, parameters: dict[str, Any] | None = None, limit: int = MAX_TOOL_ROWS) -> dict[str, Any]:
    """Run any registered Stats Engine analysis by registry key."""
    df = await _fetch_dataframe(sql, limit)
    analysis = AnalysisRegistry.create(analysis_id, data=df, parameters=parameters or {})
    result = await analysis.execute()
    return result.model_dump(mode="json")


@tool("evaluate_feasibility", args_schema=FeasibilityInput)
async def evaluate_feasibility(
    disease: str | None = None,
    disease_name: str | None = None,
    icd10_prefix: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Evaluate real diagnosis availability from ukb_semantic.unified_diagnoses using dirty ICD-10 and description matching."""
    return await _evaluate_diagnosis_feasibility(disease=disease, disease_name=disease_name, icd10_prefix=icd10_prefix, limit=limit)


@tool("get_semantic_data_overview", args_schema=SemanticOverviewInput)
async def get_semantic_data_overview(disease_limit: int = 3, drug_limit: int = 5) -> dict[str, Any]:
    """Return PI-facing data overview using semantic columns such as sex_label, disease_name_cn, and drug_name_cn."""
    return await _get_semantic_data_overview(disease_limit=disease_limit, drug_limit=drug_limit)


@tool("get_disease_count", args_schema=DiseaseCountInput)
async def get_disease_count(disease: str) -> dict[str, Any]:
    """Return patient count and prevalence for a disease using semantic diagnosis mapping and dirty ICD-10 matching."""
    return await _get_disease_count(disease=disease)


@tool("run_cox_regression", args_schema=CoxToolInput)
async def run_cox_regression(
    sql: str,
    time_col: str,
    event_col: str,
    exposure: str,
    covariates: list[str] | None = None,
    categorical_covariates: list[str] | None = None,
    km_group_col: str | None = None,
    limit: int = MAX_TOOL_ROWS,
) -> dict[str, Any]:
    """Run multivariable Cox PH regression and return HRs, PH diagnostics, and KM Plotly JSON."""
    df = await _fetch_dataframe(sql, limit)
    analysis = CoxRegressionAnalysis(
        data=df,
        parameters={
            "time_col": time_col,
            "event_col": event_col,
            "exposure": exposure,
            "covariates": covariates or [],
            "categorical_covariates": categorical_covariates or [],
            "km_group_col": km_group_col or exposure,
        },
    )
    result = await analysis.execute()
    return result.model_dump(mode="json")


@tool("run_propensity_score_matching", args_schema=PSMToolInput)
async def run_propensity_score_matching(
    sql: str,
    treatment_col: str,
    covariates: list[str],
    categorical_covariates: list[str] | None = None,
    caliper: float = 0.2,
    limit: int = MAX_TOOL_ROWS,
) -> dict[str, Any]:
    """Run 1:1 propensity score matching and return matched pairs plus before/after SMD balance diagnostics."""
    df = await _fetch_dataframe(sql, limit)
    analysis = PropensityScoreMatching(
        data=df,
        parameters={
            "treatment_col": treatment_col,
            "covariates": covariates,
            "categorical_covariates": categorical_covariates or [],
            "caliper": caliper,
        },
    )
    result = await analysis.execute()
    return result.model_dump(mode="json")


RWE_AGENT_TOOLS = [
    evaluate_feasibility,
    get_semantic_data_overview,
    get_disease_count,
    run_registered_analysis,
    run_cox_regression,
    run_propensity_score_matching,
]



