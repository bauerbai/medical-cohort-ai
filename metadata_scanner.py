from typing import Any

from database import get_db_connection, release_db_connection


SCHEMA_NAME = "ukb_semantic"

_metadata_cache: dict[str, Any] | None = None


def is_metadata_cached() -> bool:
    return _metadata_cache is not None


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def scan_schema() -> dict[str, Any]:
    global _metadata_cache
    if _metadata_cache is not None:
        return _metadata_cache

    connection = await get_db_connection()
    try:
        table_rows = await connection.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = $1
              AND table_type = 'BASE TABLE'
            ORDER BY table_name;
            """,
            SCHEMA_NAME,
        )

        tables: dict[str, Any] = {}
        total_rows = 0
        for table_row in table_rows:
            table_name = table_row["table_name"]
            column_rows = await connection.fetch(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = $1
                  AND table_name = $2
                ORDER BY ordinal_position;
                """,
                SCHEMA_NAME,
                table_name,
            )

            qualified_table = (
                f"{_quote_identifier(SCHEMA_NAME)}.{_quote_identifier(table_name)}"
            )
            row_count = await connection.fetchval(f"SELECT COUNT(*) FROM {qualified_table};")
            row_count = int(row_count or 0)
            total_rows += row_count

            tables[table_name] = {
                "row_count": row_count,
                "columns": [
                    {
                        "name": column_row["column_name"],
                        "data_type": column_row["data_type"],
                    }
                    for column_row in column_rows
                ],
            }

        patient_count = None
        if "patient_master_index" in tables:
            patient_count = tables["patient_master_index"]["row_count"]

        icd10_top_codes: list[dict[str, Any]] = []
        diagnoses_columns = {
            column["name"]
            for column in tables.get("unified_diagnoses", {}).get("columns", [])
        }
        if {"mapped_icd10", "icd10_description"}.issubset(diagnoses_columns):
            icd10_top_codes = [
                {
                    "code": row["mapped_icd10"],
                    "description": row["icd10_description"],
                    "count": int(row["code_count"]),
                }
                for row in await connection.fetch(
                    """
                    SELECT
                        mapped_icd10,
                        COALESCE(MAX(icd10_description), '') AS icd10_description,
                        COUNT(*) AS code_count
                    FROM ukb_semantic.unified_diagnoses
                    WHERE mapped_icd10 IS NOT NULL
                    GROUP BY mapped_icd10
                    ORDER BY code_count DESC
                    LIMIT 10;
                    """
                )
            ]

        _metadata_cache = {
            "schema": SCHEMA_NAME,
            "table_count": len(tables),
            "total_rows": total_rows,
            "patient_count": patient_count,
            "tables": tables,
            "icd10_top_codes": icd10_top_codes,
        }
        return _metadata_cache
    finally:
        await release_db_connection(connection)
