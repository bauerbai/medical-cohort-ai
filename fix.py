import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.types import VARCHAR

engine = create_engine("postgresql+psycopg2://postgres:2022215055@127.0.0.1:5432/medical_cohort")
df = pd.read_csv(r"C:\bauer\BY3rd\all\模拟样本1000人_gp_scripts.csv", encoding='gbk', sep=None, engine='python')
df.columns = [str(c).replace(" ", "_").replace("-", "_").replace(".", "_").lower() for c in df.columns]
df.to_sql("模拟样本1000人_gp_scripts", engine, schema='ukb_raw', if_exists='replace', index=False, dtype={col: VARCHAR for col in df.columns})
print("✅ gp_scripts 处方表补救成功！")