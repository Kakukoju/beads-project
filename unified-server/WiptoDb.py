# -*- coding: utf-8 -*-
"""
Excel → SQLite（不會卡的安全版）
"""

import os
import sqlite3
from datetime import datetime
import pandas as pd

# ===================== 路徑 =====================
EXCEL_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\WIP報表 2025-QR01 NEW (請勿亂動連結).xlsm"
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\分藥資料庫\Bead_Sort_DB.db"

TABLE_NAME = "明細_2025"
HEADER_ROW = 5
USECOLS = "A:U"

# ===================== STEP 0：找 sheet =====================
def find_target_sheet():
    xls = pd.ExcelFile(EXCEL_PATH, engine="openpyxl")
    for name in xls.sheet_names:
        s = name.strip()
        if "2025" in s and "明細" in s:
            return name
    raise RuntimeError("❌ 找不到包含 2025 + 明細 的 sheet")

# ===================== STEP 1：用 pandas 找 last row（不會卡） =====================
def find_last_row_via_pandas(sheet_name: str) -> int:
    """
    只讀 Column A，用 pandas 在記憶體中找最後一筆
    """
    print("🔍 讀取 Column A 以偵測最後一筆資料（安全模式）")

    col_a = pd.read_excel(
        EXCEL_PATH,
        sheet_name=sheet_name,
        usecols="A",
        header=None,
        engine="openpyxl"
    )

    # 從 header row 後開始
    data = col_a.iloc[HEADER_ROW - 1 :, 0]

    non_empty = data[data.notna() & (data.astype(str).str.strip() != "")]

    if non_empty.empty:
        raise RuntimeError("❌ Column A 沒有任何有效資料")

    last_excel_row = non_empty.index[-1] + 1  # pandas index → Excel row
    return last_excel_row

# ===================== 日期清洗 =====================
def normalize_date(val):
    if pd.isna(val) or str(val).strip() == "":
        return None
    try:
        s = str(val).split(" ")[0]
        dt = pd.to_datetime(s, errors="coerce")
        return dt.strftime("%Y-%m-%d") if pd.notna(dt) else None
    except:
        return None

# ===================== 主流程 =====================
def main():
    print("STEP 0：找 Sheet")
    sheet = find_target_sheet()
    print(f"✅ 使用 Sheet：{sheet}")

    print("STEP 1：找 Column A 最後一筆（不會卡）")
    last_row = find_last_row_via_pandas(sheet)
    print(f"✅ 最後資料列：Row {last_row}")

    print("STEP 2：讀取有效資料")
    nrows = last_row - (HEADER_ROW - 1)

    df = pd.read_excel(
        EXCEL_PATH,
        sheet_name=sheet,
        header=HEADER_ROW - 1,
        usecols=USECOLS,
        nrows=nrows,
        engine="openpyxl",
        dtype=str
    )

    df = df.dropna(how="all")
    print(f"✅ 資料筆數：{len(df)}")

    # 修正日期欄位
    for col in ["滴定日期", "入庫日期", "警示日期", "藥劑效期"]:
        if col in df.columns:
            df[col] = df[col].apply(normalize_date)

    df["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("STEP 3：寫入 DB")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)

    print("🎉 完成，資料已寫入 DB")

if __name__ == "__main__":
    main()
