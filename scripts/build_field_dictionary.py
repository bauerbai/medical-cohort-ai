from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import close_db_pool, get_db_connection, init_db_pool, release_db_connection

SCHEMA = "ukb_semantic"
EXCLUDED_TABLES = {"concept_dictionary"}

FIELD_CN: dict[str, str] = {
    "patient_master_index.patient_id": "受试者唯一标识",
    "patient_master_index.age_at_recruitment": "入组年龄",
    "patient_master_index.sex": "原始性别编码",
    "patient_master_index.birth_year": "出生年份",
    "patient_master_index.birth_month": "出生月份",
    "patient_master_index.townsend_deprivation_index": "Townsend 社会经济剥夺指数",
    "patient_master_index.sex_label": "性别中文标签",
    "unified_diagnoses.patient_id": "受试者唯一标识",
    "unified_diagnoses.event_date": "诊断/事件日期",
    "unified_diagnoses.source": "诊断数据来源",
    "unified_diagnoses.raw_code": "原始诊断编码（GP Read/CTV3 或 HES 原始码）",
    "unified_diagnoses.mapped_icd10": "映射后的 ICD-10 编码/描述",
    "unified_diagnoses.icd10_description": "ICD-10 英文描述",
    "unified_diagnoses.disease_name_cn": "疾病中文名",
    "unified_first_occurrences.patient_id": "受试者唯一标识",
    "unified_first_occurrences.field_id": "UKB 首发事件 Field ID",
    "unified_first_occurrences.first_occurrence_date": "首发事件日期",
    "unified_first_occurrences.event_name_cn": "首发事件中文名",
    "unified_hospitalizations.patient_id": "受试者唯一标识",
    "unified_hospitalizations.ins_index": "住院记录索引",
    "unified_hospitalizations.admission_date": "入院日期",
    "unified_hospitalizations.discharge_date": "出院日期",
    "unified_hospitalizations.length_of_stay_days": "住院天数",
    "unified_hospitalizations.discharge_method": "出院方式",
    "unified_hospitalizations.discharge_destination": "出院去向",
    "unified_medications.patient_id": "受试者唯一标识",
    "unified_medications.prescription_date": "处方/用药日期",
    "unified_medications.original_code": "原始药物编码（当前多为 dm+d/SNOMED 风格数字码）",
    "unified_medications.chemical_substance": "药物成分/处方文本",
    "unified_medications.product_name": "药品商品名/产品名",
    "unified_medications.therapeutic_chapter": "治疗章节/药物章节",
    "unified_medications.quantity": "处方数量",
    "unified_medications.drug_name_cn": "药物中文通用名",
    "unified_vitals.patient_id": "受试者唯一标识",
    "unified_vitals.systolic_bp": "收缩压",
    "unified_vitals.diastolic_bp": "舒张压",
}

TABLE_CN: dict[str, str] = {
    "patient_master_index": "受试者主索引/人口学主表",
    "unified_diagnoses": "统一诊断表",
    "unified_first_occurrences": "统一首发事件表",
    "unified_hospitalizations": "统一住院记录表",
    "unified_medications": "统一用药/处方记录表",
    "unified_vitals": "统一生命体征表",
}

CODE_SYSTEMS: list[tuple[str, str, str]] = [
    ("ICD10", "ICD-10 diagnosis coding", "已结构化：unified_diagnoses.mapped_icd10；但 disease 概念中文映射仍只是核心慢病子集。"),
    ("ICD9", "ICD-9 diagnosis coding", "当前 schema 未发现独立 ICD-9 字段；如源数据含 ICD-9，需要新增标准化列或映射视图。"),
    ("Read2", "Read version 2 GP clinical coding", "仅原始保留：GP_Clinical raw_code 中存在 Read2 风格编码，尚未拆成 read2_code 标准列。"),
    ("Read3_CTV3", "Read v3 / CTV3 GP clinical coding", "仅原始保留：GP_Clinical raw_code 中存在 Xa/XE 等 CTV3 风格编码，尚未拆成 read3_code 标准列。"),
    ("BNF", "British National Formulary medication coding", "当前 schema 未发现独立 BNF code 字段；therapeutic_chapter 可保留章节信息但不能等价于 BNF 编码。"),
    ("DMD", "NHS dm+d medication coding", "部分原始保留：unified_medications.original_code 多为数字药物码，疑似 dm+d/SNOMED 风格；尚未接入完整 dm+d 词表。"),
]


async def ensure_dictionary(connection: Any) -> None:
    await connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ukb_semantic.concept_dictionary (
            domain VARCHAR(64) NOT NULL,
            concept_code VARCHAR(128) NOT NULL,
            concept_name_en VARCHAR(255) NOT NULL,
            concept_name_cn VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (domain, concept_code)
        );
        """
    )


async def fetch_business_columns(connection: Any) -> list[dict[str, Any]]:
    rows = await connection.fetch(
        """
        SELECT table_name, column_name, data_type, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = $1
          AND table_name <> ALL($2::text[])
        ORDER BY table_name, ordinal_position;
        """,
        SCHEMA,
        sorted(EXCLUDED_TABLES),
    )
    return [dict(row) for row in rows]


async def upsert_rows(connection: Any, rows: list[tuple[str, str, str, str]]) -> None:
    await connection.executemany(
        """
        INSERT INTO ukb_semantic.concept_dictionary
            (domain, concept_code, concept_name_en, concept_name_cn)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (domain, concept_code)
        DO UPDATE SET
            concept_name_en = EXCLUDED.concept_name_en,
            concept_name_cn = EXCLUDED.concept_name_cn,
            updated_at = NOW();
        """,
        rows,
    )


async def code_system_audit(connection: Any) -> dict[str, Any]:
    return {
        "distinct_mapped_icd10": await connection.fetchval("SELECT COUNT(DISTINCT mapped_icd10) FROM ukb_semantic.unified_diagnoses WHERE mapped_icd10 IS NOT NULL;"),
        "distinct_diagnosis_raw_code": await connection.fetchval("SELECT COUNT(DISTINCT raw_code) FROM ukb_semantic.unified_diagnoses WHERE raw_code IS NOT NULL;"),
        "distinct_gp_raw_code": await connection.fetchval("SELECT COUNT(DISTINCT raw_code) FROM ukb_semantic.unified_diagnoses WHERE source = 'GP_Clinical' AND raw_code IS NOT NULL;"),
        "distinct_hes_raw_code": await connection.fetchval("SELECT COUNT(DISTINCT raw_code) FROM ukb_semantic.unified_diagnoses WHERE source = 'HESIN' AND raw_code IS NOT NULL;"),
        "distinct_med_original_code": await connection.fetchval("SELECT COUNT(DISTINCT original_code) FROM ukb_semantic.unified_medications WHERE original_code IS NOT NULL;"),
        "distinct_ukb_field_id": await connection.fetchval("SELECT COUNT(DISTINCT field_id) FROM ukb_semantic.unified_first_occurrences WHERE field_id IS NOT NULL;"),
    }


async def run() -> dict[str, Any]:
    await init_db_pool()
    connection = await get_db_connection()
    try:
        await ensure_dictionary(connection)
        columns = await fetch_business_columns(connection)
        field_rows = []
        for col in columns:
            table = col["table_name"]
            column = col["column_name"]
            code = f"{SCHEMA}.{table}.{column}"
            key = f"{table}.{column}"
            field_rows.append((
                "field",
                code,
                f"{table}.{column} ({col['data_type']})",
                FIELD_CN.get(key, f"待补充字段释义：{table}.{column}"),
            ))
        table_rows = [
            ("table", f"{SCHEMA}.{table}", table, label)
            for table, label in sorted(TABLE_CN.items())
        ]
        code_rows = [
            ("code_system", code, name_en, name_cn)
            for code, name_en, name_cn in CODE_SYSTEMS
        ]
        await upsert_rows(connection, field_rows + table_rows + code_rows)
        audit = await code_system_audit(connection)
        field_dictionary_rows = await connection.fetchval(
            "SELECT COUNT(*) FROM ukb_semantic.concept_dictionary WHERE domain = 'field';"
        )
        domain_rows = await connection.fetch(
            """
            SELECT domain, COUNT(*) AS n
            FROM ukb_semantic.concept_dictionary
            GROUP BY domain
            ORDER BY domain;
            """
        )
        return {
            "raw_business_field_count": len(columns),
            "field_dictionary_rows": field_dictionary_rows,
            "field_coverage_percent": field_dictionary_rows / len(columns) if columns else 0,
            "inserted_or_updated_field_rows": len(field_rows),
            "inserted_or_updated_table_rows": len(table_rows),
            "inserted_or_updated_code_system_rows": len(code_rows),
            "domain_counts": [dict(row) for row in domain_rows],
            "code_system_audit": audit,
        }
    finally:
        await release_db_connection(connection)
        await close_db_pool()


if __name__ == "__main__":
    result = asyncio.run(run())
    for key, value in result.items():
        print(f"{key}: {value}")
