import pandas as pd
import re
from sqlalchemy import create_engine
from sqlalchemy.types import VARCHAR

engine = create_engine("postgresql+psycopg2://postgres:2022215055@127.0.0.1:5432/medical_cohort")
xls = pd.ExcelFile(r"C:\bauer\BY3rd\all\all_lkps_maps_v4.xlsx")
print("Found " + str(len(xls.sheet_names)) + " sheets")

for s in xls.sheet_names:
    n = re.sub(r'[^a-zA-Z0-9_]', '_', s).lower().strip('_')
    if not n:
        n = "sheet"
    if n[0].isdigit():
        n = "t_" + n
    t = "lkp_" + n
    try:
        df = pd.read_excel(xls, sheet_name=s, dtype=str)
        df.columns = [re.sub(r'[^a-zA-Z0-9_]', '_', str(c)).lower() for c in df.columns]
        df.to_sql(t, engine, schema='ukb_raw', if_exists='replace', index=False, chunksize=5000, dtype={c: VARCHAR for c in df.columns})
        print("OK: " + t + " (" + str(len(df)) + " rows)")
    except Exception as e:
        print("FAIL: " + s + " -> " + str(e))
print("ALL DONE")