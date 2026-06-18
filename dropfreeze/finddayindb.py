import sqlite3
import pandas as pd

db_path = "\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db" # 請確認路徑
conn = sqlite3.connect(db_path)

# 查詢 1/21 的資料 (考慮不同日期格式)
query = """
SELECT * FROM work_orders 
WHERE 日期 LIKE '%2026/01/21%' 
   OR 日期 LIKE '%2026-01-21%'
   OR 日期 LIKE '%2026/1/21%'
"""
df = pd.read_sql(query, conn)
print(f"找到 {len(df)} 筆 1/21 的資料：")
print(df)
conn.close()