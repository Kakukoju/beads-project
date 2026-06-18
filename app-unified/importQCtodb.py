import pandas as pd
import sqlite3
from pathlib import Path

# ====== 路徑設定 ======
excel_path = Path(r"D:\配藥表\配藥紀錄\PUMP可滴定試劑.xlsx")   # 已上傳檔案
db_path = Path(r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\資料庫\配藥\P01_formualte_schedule.db")  # 目標資料庫

# ====== 建立資料庫連線 ======
conn = sqlite3.connect(db_path)

# ====== 讀取 Excel 所有工作表 ======
xls = pd.ExcelFile(excel_path)

for sheet_name in xls.sheet_names:
    print(f"正在處理工作表：{sheet_name}")

    # 讀取資料，header=2 表示第3列是欄名
    df = pd.read_excel(excel_path, sheet_name=sheet_name, header=4)

    # 移除完全空白的列
    df = df.dropna(how="all")

    # 去除欄名中空白
    df.columns = [str(c).strip() for c in df.columns]

    # 匯入 SQLite（若存在同名表則覆蓋）
    df.to_sql(sheet_name, conn, if_exists="replace", index=False)

print("✅ 匯入完成！")
conn.close()
