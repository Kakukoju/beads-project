# -*- coding: utf-8 -*-
"""
一次性補救 Script（自動偵測明細表）
"""

import os
import sqlite3
import pandas as pd
import openpyxl

# ===== 路徑設定 =====

EXCEL_FILE_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\WIP報表 2025-QR01 NEW (請勿亂動連結).xlsm"
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\分藥資料庫\Bead_Sort_DB.db"
HEADER_ROW = 5
TABLE_NAME = "明細_2025"


# ===== 找出「明細」sheet =====

def find_detail_sheet(excel_path: str) -> str:
    wb = openpyxl.load_workbook(excel_path, read_only=True)
    try:
        for s in wb.sheetnames:
            if "明細" in s:
                return s
        raise RuntimeError("❌ 找不到包含『明細』的工作表")
    finally:
        wb.close()


# ===== 日期轉換 =====

def parse_excel_date(value):
    if pd.isna(value) or value == "" or str(value).lower() == "nan":
        return None

    try:
        if isinstance(value, (int, float)):
            dt = pd.to_datetime(value, unit="D", origin="1899-12-30", errors="coerce")
        else:
            dt = pd.to_datetime(str(value).split(" ")[0], errors="coerce")

        return dt.strftime("%Y-%m-%d") if pd.notna(dt) else None
    except Exception:
        return None


# ===== 主流程 =====

def main():
    print("🔧 開始修復入庫日期")

    # 1️⃣ 找明細表
    sheet_name = find_detail_sheet(EXCEL_FILE_PATH)
    print(f"📄 使用工作表: {sheet_name}")

    # 2️⃣ 讀 Excel
    df = pd.read_excel(
        EXCEL_FILE_PATH,
        sheet_name=sheet_name,
        header=HEADER_ROW - 1,
        engine="openpyxl",
        dtype=object
    )

    df = df.dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]

    if "工單號碼" not in df.columns or "入庫日期" not in df.columns:
        raise RuntimeError("❌ Excel 欄位缺少 工單號碼 / 入庫日期")

    excel_date_map = {}
    for _, row in df.iterrows():
        wo = str(row["工單號碼"]).strip()
        inbound = parse_excel_date(row["入庫日期"])
        if wo and inbound:
            excel_date_map[wo] = inbound

    print(f"✅ Excel 有效入庫日期: {len(excel_date_map)} 筆")

    # 3️⃣ 連 DB
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(f"""
        SELECT 工單號碼
        FROM {TABLE_NAME}
        WHERE 入庫日期 IS NULL
           OR TRIM(入庫日期) = ''
           OR TRIM(入庫日期) = 'nan'
    """)

    targets = [r[0] for r in cur.fetchall()]
    print(f"🔍 DB 需修復筆數: {len(targets)}")

    updated = 0
    for wo in targets:
        wo = str(wo).strip()
        if wo in excel_date_map:
            cur.execute(
                f"""
                UPDATE {TABLE_NAME}
                SET 入庫日期 = ?
                WHERE TRIM(工單號碼) = ?
                """,
                (excel_date_map[wo], wo)
            )
            updated += 1

    conn.commit()
    conn.close()

    print(f"🎉 修復完成，共更新 {updated} 筆")


if __name__ == "__main__":
    main()
