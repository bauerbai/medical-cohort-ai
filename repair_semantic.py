import psycopg2
conn = psycopg2.connect(dbname="medical_cohort", user="postgres", password="2022215055", host="127.0.0.1", port="5432")
conn.autocommit = True
cur = conn.cursor()
print("Rebuilding Diagnoses with fixed dates...")
cur.execute("DROP TABLE IF EXISTS ukb_semantic.unified_diagnoses;")
sql_diag = """
CREATE TABLE ukb_semantic.unified_diagnoses AS
SELECT CAST(c.id AS BIGINT) as patient_id, CAST(c.event_dt AS DATE) as event_date, 'GP_CLINICAL' as source_system, COALESCE(c.read_2, c.read_3) as original_code, CASE WHEN c.read_2 IS NOT NULL AND c.read_2 != '' THEN 'Read_v2' ELSE 'Read_CTV3' END as code_system, COALESCE(v2.term_description, ctv3.term_description) as standardized_disease_name
FROM ukb_raw."模拟样本1000人_gp_clinical" c
LEFT JOIN ukb_raw.lkp_read_v2_lkp v2 ON c.read_2 = v2.read_code
LEFT JOIN ukb_raw.lkp_read_ctv3_lkp ctv3 ON c.read_3 = ctv3.read_code
WHERE (c.read_2 IS NOT NULL AND c.read_2 != '') OR (c.read_3 IS NOT NULL AND c.read_3 != '')
UNION ALL
SELECT CAST(d.id AS BIGINT), CAST(r.epistart AS DATE), 'HES_INPATIENT', COALESCE(d.diag_icd10, d.diag_icd9), CASE WHEN d.diag_icd10 IS NOT NULL AND d.diag_icd10 != '' THEN 'ICD-10' ELSE 'ICD-9' END, COALESCE(icd10.description, icd9.description_icd9)
FROM ukb_raw."模拟样本1000人_hesin_diag" d
LEFT JOIN ukb_raw."模拟样本1000人_hesin_record" r ON d.id = r.id AND d.ins_index = r.ins_index
LEFT JOIN ukb_raw.lkp_icd10_lkp icd10 ON d.diag_icd10 = icd10.icd10_code
LEFT JOIN ukb_raw.lkp_icd9_lkp icd9 ON d.diag_icd9 = icd9.icd9
WHERE (d.diag_icd10 IS NOT NULL AND d.diag_icd10 != '') OR (d.diag_icd9 IS NOT NULL AND d.diag_icd9 != '');
"""
cur.execute(sql_diag)
cur.execute("COMMENT ON TABLE ukb_semantic.unified_diagnoses IS '统一疾病诊断语义表。整合全科和住院诊断，翻译为标准疾病名。AI核心表。';")
print("Diagnoses DONE.")
print("Rebuilding Medications with native drug names...")
cur.execute("DROP TABLE IF EXISTS ukb_semantic.unified_medications;")
sql_meds = """
CREATE TABLE ukb_semantic.unified_medications AS
SELECT CAST(s.id AS BIGINT) as patient_id, CAST(s.issue_date AS DATE) as prescription_date, COALESCE(s.bnf_code, s.dmd_code) as original_code, COALESCE(b.bnf_chemical_substance, s.drug_name) as chemical_substance, COALESCE(b.bnf_product, s.drug_name) as product_name, b.bnf_chapter as therapeutic_chapter, s.quantity
FROM ukb_raw."模拟样本1000人_gp_scripts" s
LEFT JOIN ukb_raw.lkp_bnf_lkp b ON s.bnf_code = b.bnf_presentation_code
WHERE s.bnf_code IS NOT NULL OR s.dmd_code IS NOT NULL OR s.drug_name IS NOT NULL;
"""
cur.execute(sql_meds)
cur.execute("COMMENT ON TABLE ukb_semantic.unified_medications IS '统一药品处方语义表。整合全科处方记录，翻译为标准药品成分和治疗分类。AI核心表。';")
print("Medications DONE.")
print("ALL REPAIRED! Semantic layer is fully operational!")