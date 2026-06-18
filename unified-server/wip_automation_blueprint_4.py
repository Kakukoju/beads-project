# -*- coding: utf-8 -*-
"""
WIP Automation Blueprint (V8.8 - 解決 500 錯誤與欄位對齊)
"""
import os, sqlite3, logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Set
import pandas as pd
from flask import Blueprint, jsonify

wip_automation_bp = Blueprint("wip_automation", __name__)

# 路徑設定
DB_DIR = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\分藥資料庫"
DB_NAME = "Bead_Sort_DB.db"
WORK_ORDER_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"
FORMULATE_DB_PATH = r"D:\配藥表\資料庫\P01_formualte_schedule.db"

logger = logging.getLogger(__name__)

class WorkOrderAnalyzer:
    def __init__(self, work_order_db_path, wip_db_path):
        self.work_order_db_path = work_order_db_path
        self.wip_db_path = wip_db_path
        self.db_timeout = 20

    def get_produced_batches_from_work_orders(self, start_date, end_date):
        """生產端數據抓取 (增加欄位自動偵測)"""
        if not os.path.exists(self.work_order_db_path): return {}
        result = {}
        s_str = start_date.strftime("%Y-%m-%d 00:00:00")
        e_str = end_date.strftime("%Y-%m-%d 23:59:59")
        
        try:
            with sqlite3.connect(self.work_order_db_path, timeout=self.db_timeout) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                # 偵測欄位名稱 (解決 bead_name 可能不存在的問題)
                cur.execute("PRAGMA table_info(work_orders)")
                cols = [r[1] for r in cur.fetchall()]
                name_col = "bead_name" if "bead_name" in cols else ("藥名" if "藥名" in cols else "品名")
                wo_col = "工單號碼" if "工單號碼" in cols else "工單號"

                sql = f"""
                    SELECT "{wo_col}", "{name_col}", "Dispense_Lot_1", "Dispense_Lot_2", 
                           "Dispense_Lot_3", "Dispense_Lot_4", "時間_收藥"
                    FROM work_orders
                    WHERE "{wo_col}" LIKE 'TMRA%' AND "時間_收藥" IS NOT NULL
                      AND REPLACE("時間_收藥", 'T', ' ') BETWEEN ? AND ?
                """
                cur.execute(sql, (s_str, e_str))
                for row in cur.fetchall():
                    wo = str(row[wo_col]).strip()
                    marker = str(row[name_col]).strip() if row[name_col] else "-"
                    raw_date = str(row["時間_收藥"]).strip()
                    
                    for i in range(1, 5):
                        lot = row[f"Dispense_Lot_{i}"]
                        if lot and str(lot).strip() not in ["", "None", "nan"]:
                            key = f"{str(lot).strip()}__{wo}"
                            result[key] = {"WorkOrder": wo, "Lot": str(lot).strip(), "Marker": marker, "Date": raw_date}
        except Exception as e:
            logger.error(f"生產端讀取異常: {e}")
        return result

    def get_packaged_keys_from_wip(self):
        """入庫端數據抓取 (智慧比對)"""
        packaged = set()
        if not os.path.exists(self.wip_db_path): return packaged
        try:
            with sqlite3.connect(self.wip_db_path, timeout=self.db_timeout) as conn:
                cur = conn.cursor()
                # 遍歷所有 2025 明細表
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '明細_%'")
                tables = [r[0] for r in cur.fetchall()]
                for t in tables:
                    cur.execute(f"PRAGMA table_info('{t}')")
                    t_cols = [r[1] for r in cur.fetchall()]
                    lot_col = "LOT NO" if "LOT NO" in t_cols else "批號"
                    wo_col = "工單號碼" if "工單號碼" in t_cols else "工單"
                    sql = f"SELECT TRIM(\"{lot_col}\"), TRIM(\"{wo_col}\") FROM \"{t}\" WHERE \"狀態\" = '入庫完成' OR \"入庫日期\" != ''"
                    cur.execute(sql)
                    for lot, wo in cur.fetchall():
                        if lot and wo: packaged.add(f"{lot}__{wo}")
        except Exception as e:
            logger.error(f"入庫端讀取異常: {e}")
        return packaged

    def calculate_unpackaged_stats(self, start_date, end_date):
        """核心統計 (修正 500 錯誤與被省略的邏輯)"""
        produced_map = self.get_produced_batches_from_work_orders(start_date, end_date)
        packaged_keys = self.get_packaged_keys_from_wip()
        
        final_list = []
        for k, v in produced_map.items():
            if k not in packaged_keys:
                final_list.append(v)
        
        final_list.sort(key=lambda x: x.get("Date", ""), reverse=True)
        return {
            "produced_count": len(produced_map),
            "unpackaged_count": len(final_list),
            "unpackaged_details": final_list
        }

@wip_automation_bp.route("/api/workorder/unpackaged-ratio-stats", methods=["GET"])
def get_stats_api():
    try:
        analyzer = WorkOrderAnalyzer(WORK_ORDER_DB_PATH, os.path.join(DB_DIR, DB_NAME))
        # 預設查詢過去 30 天數據
        s = datetime.now() - timedelta(days=30)
        e = datetime.now()
        data = analyzer.calculate_unpackaged_stats(s, e)
        return jsonify({"success": True, "weekly": data, "monthly": data, "quarterly": data})
    except Exception as e:
        logger.error(f"500 錯誤詳情: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

def init_wip_automation(app):
    logger.info("✅ WIP 藍圖註冊成功 (V8.8)")