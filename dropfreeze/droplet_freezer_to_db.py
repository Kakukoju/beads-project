import sqlite3
import pandas as pd
from pathlib import Path


# ===============================
# 路徑設定
# ===============================
EXCEL_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\凍乾機限制表-自動化流程用-V6 1.xlsx"
DB_PATH = r"D:\配藥表\資料庫\P01_formualte_schedule.db"


# ===============================
# 建立 table（依 Excel 欄位）
# ===============================
def ensure_table_from_df(conn, table_name, df):
    col_defs = []

    for col in df.columns:
        col_name = str(col).replace('"', '').strip()
        col_defs.append(f'"{col_name}" TEXT')

    # 系統欄位
    col_defs.append('"record_time" TEXT DEFAULT (datetime(\'now\',\'localtime\'))')
    col_defs.append('"id" INTEGER PRIMARY KEY AUTOINCREMENT')

    sql = f'''
    CREATE TABLE IF NOT EXISTS "{table_name}" (
        {", ".join(col_defs)}
    );
    '''
    conn.execute(sql)


# ===============================
# 主流程：Excel → SQLite
# ===============================
def upload_excel():
    if not Path(EXCEL_PATH).exists():
        raise FileNotFoundError(f"Excel not found: {EXCEL_PATH}")

    # 確保 DB 資料夾存在
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    xl = pd.ExcelFile(EXCEL_PATH)

    print("📘 開始處理 Excel 上傳")

    for sheet_name in xl.sheet_names:
        print(f"\n▶ Sheet: {sheet_name}")

        # 🔑 header=1 → 第 2 列是欄位名稱
        df = xl.parse(sheet_name, header=1)

        # 1. 去掉全空列 (既有的邏輯)
        df = df.dropna(how="all")

        # ==========================================
        # 🔥【新增修正】清理無效欄位
        # ==========================================
        # 移除欄位名稱包含 "Unnamed" 的欄位 (通常是 Excel 右側的空欄)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        
        # 移除欄位名稱是空白的
        df = df.loc[:, df.columns.str.strip() != ""]
        # ==========================================

        if df.empty:
            print("  ⏭ 無資料，跳過")
            continue

        # 清理欄位名稱 (去除前後空白)
        df.columns = [str(c).strip() for c in df.columns]

        # 建立 table (如果不存在)
        ensure_table_from_df(conn, sheet_name, df)

        # 寫入 DB
        try:
            df.to_sql(
                sheet_name,
                conn,
                if_exists="replace", # 如果你是要更新規則，建議考慮用 "replace"
                index=False
            )
            print(f"  ✅ Inserted {len(df)} rows")
        except Exception as e:
            print(f"  ❌ 寫入失敗: {e}")

    conn.commit()
    conn.close()
    print("\n🎉 Excel 全部上傳完成")

if __name__ == "__main__":
    upload_excel()