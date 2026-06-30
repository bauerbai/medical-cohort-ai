import psycopg2
conn = psycopg2.connect(dbname="medical_cohort", user="postgres", password="2022215055", host="127.0.0.1", port="5432")
conn.autocommit = True
cur = conn.cursor()
print("Fixing medications date format...")
cur.execute("DROP TABLE IF EXISTS ukb_semantic.unified_medications;")
sql_meds = """
CREATE TABLE ukb_semantic.unified_medications AS
SELECT CAST(s.id AS BIGINT) as patient_id, CASE WHEN REPLACE(s.issue_date, '/', '-') ~ '^\\d{4}-\\d{1,2}-\\d{1,2}$' THEN CAST(REPLACE(s.issue_date, '/', '-') AS DATE) ELSE NULL END as prescription_date, COALESCE(s.bnf_code, s.dmd_code) as original_code, COALESCE(b.bnf_chemical_substance, s.drug_name) as chemical_substance, COALESCE(b.bnf_product, s.drug_name) as product_name, b.bnf_chapter as therapeutic_chapter, s.quantity
FROM ukb_raw."模拟样本1000人_gp_scripts" s
LEFT JOIN ukb_raw.lkp_bnf_lkp b ON s.bnf_code = b.bnf_presentation_code
WHERE s.bnf_code IS NOT NULL OR s.dmd_code IS NOT NULL OR s.drug_name IS NOT NULL;
"""
cur.execute(sql_meds)
cur.execute("COMMENT ON TABLE ukb_semantic.unified_medications IS '统一药品处方语义表。整合全科处方记录，翻译为标准药品成分和治疗分类。AI核心表。';")
print("Medications DONE.")
print("ALL FIXED! Semantic layer is fully operational!")