import sqlite3
import pandas as pd
from pathlib import Path

# =====================================================
# 路徑設定
# =====================================================
EXCEL_PATH = Path(r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\滴定針頭號數表.xlsx")
DB_PATH = Path(r"D:\配藥表\資料庫\P01_formualte_schedule.db")

TABLE_NAME = "滴定針頭號數表"   # SQLite table name

# =====================================================
# 讀取 Excel
# =====================================================
df = pd.read_excel(EXCEL_PATH, sheet_name=0)

# 去掉全空欄（保險）
df = df.dropna(axis=1, how="all")

print("📄 Excel 欄位：")
print(df.columns.tolist())
print(f"📊 筆數：{len(df)}")

# =====================================================
# 寫入 SQLite
# =====================================================
conn = sqlite3.connect(DB_PATH)

try:
    # 若表已存在 → 覆寫（你之後也可以改成 append）
    df.to_sql(
        TABLE_NAME,
        conn,
        if_exists="replace",   # replace / append
        index=False
    )

    print(f"✅ 已成功上傳至資料庫")
    print(f"📦 DB : {DB_PATH}")
    print(f"📑 Table : {TABLE_NAME}")

finally:
    conn.close()
