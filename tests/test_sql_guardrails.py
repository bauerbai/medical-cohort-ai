from __future__ import annotations

import unittest

from sql_guardrails import SQLGuardrailError, assert_sql_safe, validate_sql_guardrails


class SQLGuardrailTests(unittest.TestCase):
    def test_blocks_read_exact_match(self) -> None:
        sql = "SELECT COUNT(*) FROM gp_diagnoses WHERE read2_code = 'G3...';"
        violations = validate_sql_guardrails(sql)
        self.assertTrue(any(v.rule_id == "READ_PREFIX_MATCH_REQUIRED" for v in violations))
        self.assertTrue(any(v.rule_id == "DIAGNOSIS_COUNT_DISTINCT_REQUIRED" for v in violations))
        with self.assertRaises(SQLGuardrailError):
            assert_sql_safe(sql)

    def test_allows_read_prefix_with_distinct(self) -> None:
        sql = """
        SELECT COUNT(DISTINCT patient_id)
        FROM gp_diagnoses
        WHERE read2_code LIKE 'G3%';
        """
        self.assertEqual(validate_sql_guardrails(sql), [])

    def test_blocks_lab_threshold_without_unit(self) -> None:
        sql = "SELECT patient_id FROM lab_results WHERE creatinine > 150;"
        violations = validate_sql_guardrails(sql)
        self.assertTrue(any(v.rule_id == "LAB_UNIT_HARMONIZATION_REQUIRED" for v in violations))

    def test_blocks_survival_end_date_without_least(self) -> None:
        sql = "SELECT death_date, last_visit_date FROM cohort_survival;"
        violations = validate_sql_guardrails(sql)
        self.assertTrue(any(v.rule_id == "CENSORING_LEAST_REQUIRED" for v in violations))


if __name__ == "__main__":
    unittest.main()
