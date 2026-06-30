import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.types import VARCHAR

folder_path = r"C:\bauer\BY3rd\all"
db_user = "postgres"       
db_password = "2022215055"
db_host = "127.0.0.1"      
db_port = "5432"           
db_name = "medical_cohort" 

print("🚀 正在连接数据库...")
engine = create_engine(f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}")

with engine.connect() as conn:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS ukb_raw;"))
    conn.commit()
print("✅ 数据空间 ukb_raw 准备就绪")

supported_files = [f for f in os.listdir(folder_path) if f.endswith(('.csv', '.xlsx', '.xls', '.tab', '.txt'))]
print(f"🔍 发现 {len(supported_files)} 个文件，开始导入...")

for file_name in supported_files:
    file_path = os.path.join(folder_path, file_name)
    table_name = os.path.splitext(file_name)[0].replace(" ", "_").replace("-", "_").lower()
    if table_name and table_name[0].isdigit():
        table_name = "t_" + table_name
        
    try:
        print(f"\n⏳ 正在读取: {file_name} ...")
        if file_name.endswith(('.csv', '.tab', '.txt')):
            df = pd.read_csv(file_path, sep=None, engine='python') 
        else:
            df = pd.read_excel(file_path)
            
        df.columns = [str(c).replace(" ", "_").replace("-", "_").replace(".", "_").lower() for c in df.columns]
        df = df.replace(['NA', 'na', 'N/A', ''], np.nan)
        df = df.where(pd.notnull(df), None)
        for col in df.columns:
            df[col] = df[col].apply(lambda x: str(x) if x is not None else None)

        print(f"  -> 正在写入: ukb_raw.{table_name} (共 {len(df)} 行)...")
        df.to_sql(
            table_name, engine, schema='ukb_raw', if_exists='replace', 
            index=False, chunksize=10000, dtype={col: VARCHAR for col in df.columns} 
        )
        print(f"  ✅ {table_name} 完美入库！({len(df)} 行)")
    except Exception as e:
        print(f"  ❌ {file_name} 遇到意外: {e}")

print("\n🎉 全部完成！请去 Chat2DB 刷新查看 ukb_raw 模式！")