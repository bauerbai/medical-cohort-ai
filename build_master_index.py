import psycopg2
conn = psycopg2.connect(dbname="medical_cohort", user="postgres", password="2022215055", host="127.0.0.1", port="5432")
conn.autocommit = True
cur = conn.cursor()
print("Building Patient Master Index...")
cur.execute("DROP TABLE IF EXISTS ukb_semantic.patient_master_index;")
sql_master = """
CREATE TABLE ukb_semantic.patient_master_index AS
SELECT 
    CAST(p.id AS BIGINT) as patient_id,
    CASE WHEN p.p31 = '1' THEN 'Male' WHEN p.p31 = '0' THEN 'Female' ELSE NULL END as sex,
    CAST(p.p21022 AS INTEGER) as age_at_recruitment,
    CAST(p.p34 AS INTEGER) as year_of_birth,
    CAST(p.p22189 AS NUMERIC) as townsend_deprivation_index,
    MIN(CASE WHEN r.reg_date ~ '^\\d{4}-\\d{1,2}-\\d{1,2}$' THEN CAST(REPLACE(r.reg_date, '/', '-') AS DATE) ELSE NULL END) as observation_start_date,
    MAX(CASE WHEN r.deduct_date ~ '^\\d{4}-\\d{1,2}-\\d{1,2}$' THEN CAST(REPLACE(r.deduct_date, '/', '-') AS DATE) ELSE NULL END) as observation_end_date
FROM ukb_raw."模拟样本1000人_population_characteristics" p
LEFT JOIN ukb_raw."模拟样本1000人_gp_registrations" r ON p.id = r.id
GROUP BY p.id, p.p31, p.p21022, p.p34, p.p22189;
"""
cur.execute(sql_master)
cur.execute("COMMENT ON TABLE ukb_semantic.patient_master_index IS '患者主索引表。包含基线人口学特征和全科注册观察窗口。AI科研必备核心表。';")
cur.execute("COMMENT ON COLUMN ukb_semantic.patient_master_index.patient_id IS '患者唯一标识符';")
cur.execute("COMMENT ON COLUMN ukb_semantic.patient_master_index.sex IS '性别 (Male/Female)';")
cur.execute("COMMENT ON COLUMN ukb_semantic.patient_master_index.age_at_recruitment IS '入组时年龄';")
cur.execute("COMMENT ON COLUMN ukb_semantic.patient_master_index.year_of_birth IS '出生年份';")
cur.execute("COMMENT ON COLUMN ukb_semantic.patient_master_index.townsend_deprivation_index IS '汤森剥夺指数 (社会经济地位指标，值越大越贫困)';")
cur.execute("COMMENT ON COLUMN ukb_semantic.patient_master_index.observation_start_date IS '全科随访开始日期 (注册日期)';")
cur.execute("COMMENT ON COLUMN ukb_semantic.patient_master_index.observation_end_date IS '全科随访结束日期 (注销/死亡日期)';")
print("Master Index DONE.")
print("ALL DONE! Patient Master Index is ready!")