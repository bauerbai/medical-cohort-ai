import psycopg2
conn = psycopg2.connect(dbname="medical_cohort", user="postgres", password="2022215055", host="127.0.0.1", port="5432")
conn.autocommit = True
cur = conn.cursor()
cur.execute("DROP TABLE IF EXISTS ukb_semantic.unified_medications;")
sql_create = """
CREATE TABLE ukb_semantic.unified_medications (
    patient_id BIGINT, prescription_date DATE, original_bnf_code TEXT,
    chemical_substance TEXT, product_name TEXT, therapeutic_chapter TEXT, quantity TEXT
);
COMMENT ON TABLE ukb_semantic.unified_medications IS '统一药品处方语义表。整合全科处方记录，翻译为标准药品成分和治疗分类。AI核心表。';
COMMENT ON COLUMN ukb_semantic.unified_medications.patient_id IS '患者唯一标识符 (UKB eid)';
COMMENT ON COLUMN ukb_semantic.unified_medications.prescription_date IS '处方开具日期';
COMMENT ON COLUMN ukb_semantic.unified_medications.original_bnf_code IS '原始 BNF 处方编码';
COMMENT ON COLUMN ukb_semantic.unified_medications.chemical_substance IS '标准化活性化学成分 (如: Metformin)';
COMMENT ON COLUMN ukb_semantic.unified_medications.product_name IS '药品商品名/产品名';
COMMENT ON COLUMN ukb_semantic.unified_medications.therapeutic_chapter IS 'BNF 治疗学章节 (如: 内分泌系统)';
COMMENT ON COLUMN ukb_semantic.unified_medications.quantity IS '处方开具数量/剂量';
"""
cur.execute(sql_create)
print("Table created. Translating BNF prescriptions...")
sql_bnf = """
INSERT INTO ukb_semantic.unified_medications
SELECT CAST(s.id AS BIGINT), CASE WHEN s.issue_date ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN TO_DATE(s.issue_date, 'YYYY-MM-DD') ELSE NULL END, s.bnf_code, b.bnf_chemical_substance, b.bnf_product, b.bnf_chapter, s.quantity
FROM ukb_raw."模拟样本1000人_gp_scripts" s
LEFT JOIN ukb_raw.lkp_bnf_lkp b ON s.bnf_code = b.bnf_presentation_code
WHERE s.bnf_code IS NOT NULL AND s.bnf_code != '';
"""
cur.execute(sql_bnf)
print("BNF done:", cur.rowcount)
print("ALL DONE! Medication semantic layer is ready!")