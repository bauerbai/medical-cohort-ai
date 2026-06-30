from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import close_db_pool, get_db_connection, init_db_pool, release_db_connection


CONCEPTS: list[tuple[str, str, str, str]] = [
    ("demographics", "sex:1", "Male", "男"),
    ("demographics", "sex:0", "Female", "女"),
    ("disease", "I10", "Essential hypertension", "原发性高血压"),
    ("disease", "I10 ESSENTIAL", "Essential hypertension", "原发性高血压"),
    ("disease", "E780", "Pure hypercholesterolaemia", "纯高胆固醇血症"),
    ("disease", "E78.0", "Pure hypercholesterolaemia", "纯高胆固醇血症"),
    ("disease", "E11", "Type 2 diabetes mellitus", "2型糖尿病"),
    ("disease", "I21", "Acute myocardial infarction", "急性心肌梗死"),
    ("disease", "I64", "Stroke", "脑卒中"),
    ("disease", "K219", "Gastro-oesophageal reflux disease", "胃食管反流病"),
    ("disease", "K21.9", "Gastro-oesophageal reflux disease", "胃食管反流病"),
    ("drug", "A10BA02", "Metformin", "二甲双胍"),
    ("drug", "B01AC06", "Aspirin", "阿司匹林"),
    ("drug", "C10AA05", "Atorvastatin", "阿托伐他汀"),
    ("drug", "C07AB07", "Bisoprolol", "比索洛尔"),
    ("drug", "C09AA02", "Enalapril", "依那普利"),
    ("ukb_first_occurrence", "p131286", "Age at hypertension diagnosis", "高血压确诊年龄/首发"),
    ("ukb_first_occurrence", "p131288", "Age at diabetes diagnosis", "糖尿病确诊年龄/首发"),
    ("ukb_first_occurrence", "p131300", "Age at myocardial infarction diagnosis", "心梗确诊年龄/首发"),
]

DISEASE_NAME_FALLBACKS: list[tuple[str, str]] = [
    ("pure hypercholesterolaemia", "纯高胆固醇血症"),
    ("pure hypercholesterolemia", "纯高胆固醇血症"),
    ("acute myocardial infarction", "急性心肌梗死"),
    ("stroke", "脑卒中"),
    ("gastro-oesophageal reflux disease", "胃食管反流病"),
    ("gastroesophageal reflux disease", "胃食管反流病"),
]

DRUG_NAME_FALLBACKS: list[tuple[str, str]] = [
    ("metformin", "二甲双胍"),
    ("aspirin", "阿司匹林"),
    ("atorvastatin", "阿托伐他汀"),
    ("bisoprolol", "比索洛尔"),
    ("enalapril", "依那普利"),
]


def clean_icd10_prefix(raw_icd10: str | None) -> str | None:
    if not raw_icd10:
        return None
    match = re.match(r"^[A-Z]\d{2}\.?\d?", raw_icd10.strip().upper())
    if not match:
        return None
    return match.group(0).replace(".", "")


async def create_dictionary_table(connection: Any) -> None:
    await connection.execute(
        """
        CREATE SCHEMA IF NOT EXISTS ukb_semantic;

        CREATE TABLE IF NOT EXISTS ukb_semantic.concept_dictionary (
            domain VARCHAR(64) NOT NULL,
            concept_code VARCHAR(128) NOT NULL,
            concept_name_en VARCHAR(255) NOT NULL,
            concept_name_cn VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (domain, concept_code)
        );

        CREATE INDEX IF NOT EXISTS idx_concept_dictionary_domain_code
            ON ukb_semantic.concept_dictionary (domain, concept_code);
        """
    )


async def upsert_concepts(connection: Any) -> int:
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
        CONCEPTS,
    )
    return len(CONCEPTS)


async def add_semantic_columns(connection: Any) -> None:
    await connection.execute(
        """
        ALTER TABLE ukb_semantic.patient_master_index
            ADD COLUMN IF NOT EXISTS sex_label VARCHAR(32);

        ALTER TABLE ukb_semantic.unified_diagnoses
            ADD COLUMN IF NOT EXISTS disease_name_cn VARCHAR(255);

        ALTER TABLE ukb_semantic.unified_medications
            ADD COLUMN IF NOT EXISTS drug_name_cn VARCHAR(255);

        ALTER TABLE ukb_semantic.unified_first_occurrences
            ADD COLUMN IF NOT EXISTS event_name_cn VARCHAR(255);
        """
    )


async def update_patient_labels(connection: Any) -> str:
    return await connection.execute(
        """
        UPDATE ukb_semantic.patient_master_index AS p
        SET sex_label = CASE
            WHEN p.sex::text = '1' OR lower(p.sex::text) = 'male' THEN '男'
            WHEN p.sex::text = '0' OR lower(p.sex::text) = 'female' THEN '女'
            ELSE p.sex_label
        END
        WHERE p.sex IS NOT NULL;
        """
    )


async def update_diagnosis_labels(connection: Any) -> str:
    await connection.execute("UPDATE ukb_semantic.unified_diagnoses SET disease_name_cn = NULL;")
    result = await connection.execute(
        """
        WITH diagnosis_clean AS (
            SELECT
                d.ctid AS row_id,
                UPPER(REPLACE(SUBSTRING(d.mapped_icd10 FROM '^[A-Z][0-9]{2}\\.?[0-9A-Z]?'), '.', '')) AS clean_code
            FROM ukb_semantic.unified_diagnoses AS d
            WHERE d.mapped_icd10 IS NOT NULL
        ),
        matched AS (
            SELECT
                x.row_id,
                cd.concept_name_cn
            FROM diagnosis_clean AS x
            JOIN ukb_semantic.concept_dictionary AS cd
                ON cd.domain = 'disease'
               AND (
                    UPPER(REPLACE(cd.concept_code, '.', '')) = x.clean_code
                    OR UPPER(REPLACE(cd.concept_code, '.', '')) = LEFT(x.clean_code, 3)
               )
        )
        UPDATE ukb_semantic.unified_diagnoses AS d
        SET disease_name_cn = m.concept_name_cn
        FROM matched AS m
        WHERE d.ctid = m.row_id;
        """
    )

    for term, name_cn in DISEASE_NAME_FALLBACKS:
        await connection.execute(
            """
            UPDATE ukb_semantic.unified_diagnoses
            SET disease_name_cn = $2
            WHERE disease_name_cn IS NULL
              AND (
                  mapped_icd10 ILIKE '%' || $1 || '%'
                  OR icd10_description ILIKE '%' || $1 || '%'
              );
            """,
            term,
            name_cn,
        )
    return result


async def update_medication_labels(connection: Any) -> str:
    result = await connection.execute(
        """
        UPDATE ukb_semantic.unified_medications AS m
        SET drug_name_cn = cd.concept_name_cn
        FROM ukb_semantic.concept_dictionary AS cd
        WHERE cd.domain = 'drug'
          AND (
              UPPER(m.original_code) = UPPER(cd.concept_code)
              OR m.chemical_substance ILIKE '%' || cd.concept_name_en || '%'
              OR m.product_name ILIKE '%' || cd.concept_name_en || '%'
          );
        """
    )

    for term, name_cn in DRUG_NAME_FALLBACKS:
        await connection.execute(
            """
            UPDATE ukb_semantic.unified_medications
            SET drug_name_cn = $2
            WHERE drug_name_cn IS NULL
              AND (
                  original_code ILIKE '%' || $1 || '%'
                  OR chemical_substance ILIKE '%' || $1 || '%'
                  OR product_name ILIKE '%' || $1 || '%'
              );
            """,
            term,
            name_cn,
        )
    return result


async def update_first_occurrence_labels(connection: Any) -> str:
    return await connection.execute(
        """
        UPDATE ukb_semantic.unified_first_occurrences AS fo
        SET event_name_cn = cd.concept_name_cn
        FROM ukb_semantic.concept_dictionary AS cd
        WHERE cd.domain = 'ukb_first_occurrence'
          AND LOWER(fo.field_id) = LOWER(cd.concept_code);
        """
    )


async def summarize(connection: Any) -> dict[str, Any]:
    return {
        "dictionary_rows": await connection.fetchval("SELECT COUNT(*) FROM ukb_semantic.concept_dictionary;"),
        "sex_labeled": await connection.fetchval(
            "SELECT COUNT(*) FROM ukb_semantic.patient_master_index WHERE sex_label IS NOT NULL;"
        ),
        "diagnoses_labeled": await connection.fetchval(
            "SELECT COUNT(*) FROM ukb_semantic.unified_diagnoses WHERE disease_name_cn IS NOT NULL;"
        ),
        "medications_labeled": await connection.fetchval(
            "SELECT COUNT(*) FROM ukb_semantic.unified_medications WHERE drug_name_cn IS NOT NULL;"
        ),
        "first_occurrences_labeled": await connection.fetchval(
            "SELECT COUNT(*) FROM ukb_semantic.unified_first_occurrences WHERE event_name_cn IS NOT NULL;"
        ),
    }


async def run() -> None:
    await init_db_pool()
    connection = await get_db_connection()
    try:
        async with connection.transaction():
            await create_dictionary_table(connection)
            inserted = await upsert_concepts(connection)
            await add_semantic_columns(connection)
            patient_result = await update_patient_labels(connection)
            diagnosis_result = await update_diagnosis_labels(connection)
            medication_result = await update_medication_labels(connection)
            first_occurrence_result = await update_first_occurrence_labels(connection)
            summary = await summarize(connection)
    finally:
        await release_db_connection(connection)
        await close_db_pool()

    print("Semantic enrichment complete.")
    print(f"Concepts upserted: {inserted}")
    print(f"Patient labels: {patient_result}")
    print(f"Diagnosis labels: {diagnosis_result}")
    print(f"Medication labels: {medication_result}")
    print(f"First occurrence labels: {first_occurrence_result}")
    print(f"Summary: {summary}")


if __name__ == "__main__":
    asyncio.run(run())
