import psycopg2
conn = psycopg2.connect(dbname="medical_cohort", user="postgres", password="2022215055", host="127.0.0.1", port="5432")
conn.autocommit = True
cur = conn.cursor()
cur.execute("DROP TABLE IF EXISTS ukb_semantic.unified_diagnoses;")
sql_create = """
CREATE TABLE ukb_semantic.unified_diagnoses (
    patient_id BIGINT, event_date DATE, source_system TEXT,
    original_code TEXT, code_system TEXT, standardized_disease_name TEXT
);
COMMENT ON TABLE ukb_semantic.unified_diagnoses IS '统一疾病诊断语义表。整合全科和住院诊断，翻译为标准疾病名。AI核心表。';
COMMENT ON COLUMN ukb_semantic.unified_diagnoses.patient_id IS '患者唯一标识符 (UKB eid)';
COMMENT ON COLUMN ukb_semantic.unified_diagnoses.event_date IS '诊断发生日期';
COMMENT ON COLUMN ukb_semantic.unified_diagnoses.source_system IS '数据来源: GP_CLINICAL 或 HES_INPATIENT';
COMMENT ON COLUMN ukb_semantic.unified_diagnoses.original_code IS '原始临床编码';
COMMENT ON COLUMN ukb_semantic.unified_diagnoses.code_system IS '编码体系: Read_v2, Read_CTV3, ICD-10, ICD-9';
COMMENT ON COLUMN ukb_semantic.unified_diagnoses.standardized_disease_name IS '翻译后的标准疾病名称';
"""
cur.execute(sql_create)
print("Table recreated with TEXT. Translating GP records...")
sql_gp = """
INSERT INTO ukb_semantic.unified_diagnoses
SELECT CAST(c.id AS BIGINT), CASE WHEN c.event_dt ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN TO_DATE(c.event_dt, 'YYYY-MM-DD') ELSE NULL END, 'GP_CLINICAL', COALESCE(c.read_2, c.read_3), CASE WHEN c.read_2 IS NOT NULL AND c.read_2 != '' THEN 'Read_v2' ELSE 'Read_CTV3' END, COALESCE(v2.term_description, ctv3.term_description)
FROM ukb_raw."模拟样本1000人_gp_clinical" c
LEFT JOIN ukb_raw.lkp_read_v2_lkp v2 ON c.read_2 = v2.read_code
LEFT JOIN ukb_raw.lkp_read_ctv3_lkp ctv3 ON c.read_3 = ctv3.read_code
WHERE (c.read_2 IS NOT NULL AND c.read_2 != '') OR (c.read_3 IS NOT NULL AND c.read_3 != '');
"""
cur.execute(sql_gp)
print("GP done:", cur.rowcount)
print("Translating HES records...")
sql_hes = """
INSERT INTO ukb_semantic.unified_diagnoses
SELECT CAST(d.id AS BIGINT), CASE WHEN r.epistart ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN TO_DATE(r.epistart, 'YYYY-MM-DD') ELSE NULL END, 'HES_INPATIENT', COALESCE(d.diag_icd10, d.diag_icd9), CASE WHEN d.diag_icd10 IS NOT NULL AND d.diag_icd10 != '' THEN 'ICD-10' ELSE 'ICD-9' END, COALESCE(icd10.description, icd9.description_icd9)
FROM ukb_raw."模拟样本1000人_hesin_diag" d
LEFT JOIN ukb_raw."模拟样本1000人_hesin_record" r ON d.id = r.id AND d.ins_index = r.ins_index
LEFT JOIN ukb_raw.lkp_icd10_lkp icd10 ON d.diag_icd10 = icd10.icd10_code
LEFT JOIN ukb_raw.lkp_icd9_lkp icd9 ON d.diag_icd9 = icd9.icd9
WHERE (d.diag_icd10 IS NOT NULL AND d.diag_icd10 != '') OR (d.diag_icd9 IS NOT NULL AND d.diag_icd9 != '');
"""
cur.execute(sql_hes)
print("HES done:", cur.rowcount)
print("ALL DONE! Semantic layer is ready!")