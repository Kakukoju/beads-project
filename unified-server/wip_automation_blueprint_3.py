# -*- coding: utf-8 -*-
"""
WIP Automation Blueprint (V8.3 - Final Column Mapping)
檔案名稱: wip_automation_blueprint_1.py

修正重點：
1. 修正生產端欄位名：工單號碼, bead_name (對應前端 Marker)。
2. 維持日期相容性處理 (REPLACE 'T')。
3. 強化跨網路路徑 (UNC Path) 的存取穩定性。
"""

import os
import sqlite3
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Set
import pandas as pd
from flask import Blueprint, jsonify

wip_automation_bp = Blueprint("wip_automation", __name__)

# ===================== 路徑設定 =====================
# 入庫資料庫 (WIP)
DB_DIR = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\分藥資料庫"
DB_NAME = "Bead_Sort_DB.db"

# 生產紀錄資料庫 (分母來源)
WORK_ORDER_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"

# 配藥排程資料庫
FORMULATE_DB_PATH = r"D:\配藥表\資料庫\P01_formualte_schedule.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def get_wip_db_path() -> str:
    return os.path.join(DB_DIR, DB_NAME)

class WorkOrderAnalyzer:
    def __init__(self, work_order_db_path: str, wip_db_path: str, formulate_db_path: str):
        self.work_order_db_path = work_order_db_path
        self.wip_db_path = wip_db_path
        self.formulate_db_path = formulate_db_path
        self.db_timeout = 15  # 考量網絡路徑，設定較長的超時

    def get_all_wip_tables(self) -> List[str]:
        if not os.path.exists(self.wip_db_path): return []
        try:
            with sqlite3.connect(self.wip_db_path, timeout=self.db_timeout) as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [r[0] for r in cur.fetchall()]
                # 篩選 明細_YYYY 格式
                return [t for t in tables if t.startswith("明細_") and t.split("_")[-1].isdigit()]
        except: return []

    # ------------------------------------------------------------------
    # 1. 生產端 (Produced) - 欄位：工單號碼, bead_name
    # ------------------------------------------------------------------
    def get_produced_batches_from_work_orders(self, start_date: datetime, end_date: datetime) -> Dict[str, dict]:
        if not os.path.exists(self.work_order_db_path):
            logger.error(f"❌ work_orders DB 不存在: {self.work_order_db_path}")
            return {}

        result = {}
        s_str = start_date.strftime("%Y-%m-%d 00:00:00")
        e_str = end_date.strftime("%Y-%m-%d 23:59:59")
        
        try:
            with sqlite3.connect(self.work_order_db_path, timeout=self.db_timeout) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                
                # [修正] 欄位名：工單號碼, bead_name
                sql = """
                    SELECT 
                        "工單號碼", 
                        "bead_name",
                        "Dispense_Lot_1", "Dispense_Lot_2", "Dispense_Lot_3", "Dispense_Lot_4",
                        "時間_收藥"
                    FROM work_orders
                    WHERE "工單號碼" LIKE 'TMRA%'
                      AND "時間_收藥" IS NOT NULL
                      AND REPLACE("時間_收藥", 'T', ' ') >= ? 
                      AND REPLACE("時間_收藥", 'T', ' ') <= ?
                """
                cur.execute(sql, (s_str, e_str))
                rows = cur.fetchall()
                
                for row in rows:
                    wo = str(row["工單號碼"]).strip()
                    # 將 bead_name 對應到前端顯示的 Marker
                    marker = str(row["bead_name"]).strip() if row["bead_name"] else "-"
                    date_val_raw = str(row["時間_收藥"]).strip()
                    clean_date_str = date_val_raw.replace('T', ' ')
                    
                    try:
                        dt_val = pd.to_datetime(clean_date_str, errors='coerce')
                        if pd.isna(dt_val) or not (start_date.date() <= dt_val.date() <= end_date.date()):
                            continue
                    except:
                        continue 

                    for i in range(1, 5):
                        col_name = f"Dispense_Lot_{i}"
                        lot_val = row[col_name]
                        
                        if lot_val and str(lot_val).strip() not in ["", "None", "nan"]:
                            lot = str(lot_val).strip()
                            key = f"{lot}__{wo}"
                            
                            result[key] = {
                                "WorkOrder": wo,
                                "Lot": lot,
                                "Marker": marker, # 👈 這裡傳給前端
                                "Date": date_val_raw,
                                "SourceCol": col_name
                            }
        except Exception as e:
            logger.error(f"❌ 讀取 work_orders 失敗: {e}")
            
        return result

    # ------------------------------------------------------------------
    # 2. 入庫端 (Packaged) - 欄位：工單號碼, LOT NO
    # ------------------------------------------------------------------
    def get_packaged_keys_from_wip(self) -> Set[str]:
        tables = self.get_all_wip_tables()
        packaged = set()
        
        with sqlite3.connect(self.wip_db_path, timeout=self.db_timeout) as conn:
            cur = conn.cursor()
            for table in tables:
                try:
                    cur.execute(f"PRAGMA table_info('{table}')")
                    cols = [r[1] for r in cur.fetchall()]
                    
                    has_status = "狀態" in cols
                    has_date = "入庫日期" in cols
                    
                    conditions = []
                    if has_date:
                        conditions.append("(\"入庫日期\" IS NOT NULL AND TRIM(\"入庫日期\") != '')")
                    if has_status:
                        conditions.append("(\"狀態\" = '入庫完成')")
                    
                    if not conditions: continue 
                    where_clause = " OR ".join(conditions)
                    
                    sql = f"""
                        SELECT TRIM("LOT NO"), TRIM("工單號碼") 
                        FROM "{table}" 
                        WHERE TRIM("工單號碼") LIKE 'TMRA%'
                          AND ({where_clause})
                    """
                    cur.execute(sql)
                    for lot, wo in cur.fetchall():
                        if lot and wo: 
                            packaged.add(f"{lot}__{wo}")
                except: continue
        return packaged

    # ... (其餘 calculate_unpackaged_stats 等邏輯維持不變) ...

# ===================== API Routes =====================

@wip_automation_bp.route("/api/workorder/unpackaged-ratio-stats", methods=["GET"])
def get_unpackaged_ratio_stats():
    try:
        analyzer = WorkOrderAnalyzer(WORK_ORDER_DB_PATH, get_wip_db_path(), FORMULATE_DB_PATH)
        today = date.today()
        # 範圍計算邏輯
        curr_monday = today - timedelta(days=today.isoweekday() - 1)
        prev_monday = curr_monday - timedelta(days=7)
        prev_sunday = curr_monday - timedelta(days=1)
        w_start, w_end = datetime.combine(prev_monday, datetime.min.time()), datetime.combine(prev_sunday, datetime.max.time())
        m_start, m_end = datetime.now() - timedelta(days=30), datetime.now()
        q_start, q_end = datetime.now() - timedelta(days=90), datetime.now()
        
        return jsonify({
            "success": True,
            "weekly": analyzer.calculate_unpackaged_stats(w_start, w_end),
            "monthly": analyzer.calculate_unpackaged_stats(m_start, m_end),
            "quarterly": analyzer.calculate_unpackaged_stats(q_start, q_end)
        })
    except Exception as e:
        logger.error(f"❌ API Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

def init_wip_automation(app):
    logger.info("✅ WIP automation blueprint initialized (V8.3 - bead_name Mapping)")