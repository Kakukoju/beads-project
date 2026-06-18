# -*- coding: utf-8 -*-
"""
WIP Automation Blueprint (V8 - Fix Date Formats)
檔案名稱: wip_automation_blueprint_1.py

修正重點：
1. 修正 work_orders.db 日期格式混亂問題 ('T' vs ' 'space)
   - SQL 查詢增加 REPLACE 處理
   - Python 解析增加格式統一
2. 維持 V7 的所有邏輯 (WorkOrder 分母 + Dispense_Lot 判定)
"""

import os
import sqlite3
import logging
import re
from datetime import datetime, timedelta, date
from typing import Dict, List, Tuple, Set
import pandas as pd
from flask import Blueprint, request, jsonify

wip_automation_bp = Blueprint("wip_automation", __name__)

# ===================== 路徑設定 =====================
# 1. 入庫資料庫 (WIP)
DB_DIR = "/opt/beadsops/data"
DB_NAME = "Bead_Sort_DB.db"

# 2. 生產紀錄資料庫 (分母來源)
WORK_ORDER_DB_PATH = "/opt/beadsops/data/work_orders.db"

# 3. 配藥排程資料庫 (良率計算仍可能用到)
FORMULATE_DB_PATH = "/opt/beadsops/data/P01_formualte_schedule.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def get_wip_db_path() -> str:
    return os.path.join(DB_DIR, DB_NAME)

class WorkOrderAnalyzer:
    def __init__(self, work_order_db_path: str, wip_db_path: str, formulate_db_path: str):
        self.work_order_db_path = work_order_db_path
        self.wip_db_path = wip_db_path
        self.formulate_db_path = formulate_db_path

    # ------------------------------------------------------------------
    # Helper: 取得所有 WIP 明細表 (跨年搜尋)
    # ------------------------------------------------------------------
    def get_all_wip_tables(self) -> List[str]:
        if not os.path.exists(self.wip_db_path): return []
        try:
            with sqlite3.connect(self.wip_db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [r[0] for r in cur.fetchall()]
                # 篩選 明細_YYYY 格式
                return [t for t in tables if t.startswith("明細_") and t.split("_")[-1].isdigit()]
        except: return []

    # ------------------------------------------------------------------
    # 1. 生產端 (Produced) - work_orders.db (含日期格式修正)
    # ------------------------------------------------------------------
    def get_produced_batches_from_work_orders(self, start_date: datetime, end_date: datetime) -> Dict[str, dict]:
        """
        邏輯：
        1. 讀取 work_orders.db
        2. 針對 '時間_收藥' 進行 REPLACE('T', ' ') 標準化後再篩選區間
        3. 檢查 Dispense_Lot_1~4
        """
        if not os.path.exists(self.work_order_db_path):
            logger.error(f"❌ work_orders DB 不存在: {self.work_order_db_path}")
            return {}

        result = {}
        
        # 轉字串比較 (標準 SQL 格式)
        s_str = start_date.strftime("%Y-%m-%d 00:00:00")
        e_str = end_date.strftime("%Y-%m-%d 23:59:59")
        
        try:
            with sqlite3.connect(self.work_order_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                
                # [修正] SQL 中使用 REPLACE 將 'T' 換成 ' '，確保與 YYYY-MM-DD HH:MM:SS 正確比對
                # 這樣 '2025-08-11T17:33' 變成 '2025-08-11 17:33'，就不會發生 'T' > ' ' 導致的範圍錯誤
                sql = """
                    SELECT 
                        工單號, 
                        bead_name, Dispense_Lot_1, Dispense_Lot_2, Dispense_Lot_3, Dispense_Lot_4,
                        時間_收藥
                    FROM work_orders
                    WHERE 工單號 LIKE 'TMRA%'
                      AND 時間_收藥 IS NOT NULL
                      AND REPLACE("時間_收藥", 'T', ' ') >= ? 
                      AND REPLACE("時間_收藥", 'T', ' ') <= ?
                """
                cur.execute(sql, (s_str, e_str))
                rows = cur.fetchall()
                
                for row in rows:
                    wo = str(row["工單號"]).strip()
                    date_val_raw = str(row["時間_收藥"]).strip()
                    
                    # [修正] Python 端解析日期時，也先移除 'T'，確保 pd.to_datetime 能吃兩種格式
                    clean_date_str = date_val_raw.replace('T', ' ')
                    
                    try:
                        # 再次確認日期區間 (雙重保險)
                        dt_val = pd.to_datetime(clean_date_str, errors='coerce')
                        if pd.isna(dt_val): continue
                        
                        # 比對 (只比對到日期，忽略時間差異)
                        if not (start_date.date() <= dt_val.date() <= end_date.date()):
                            continue
                    except:
                        continue 

                    # 檢查 4 個 Lot 欄位
                    for i in range(1, 5):
                        col_name = f"Dispense_Lot_{i}"
                        lot_val = row[col_name]
                        
                        # 判斷非空字串
                        if lot_val and str(lot_val).strip() not in ["", "None", "nan"]:
                            lot = str(lot_val).strip()
                            key = f"{lot}__{wo}"
                            
                            result[key] = {
                                "WorkOrder": wo,
                                "Lot": lot,
                                "Marker": row["bead_name"],
                                "Date": date_val_raw, # 保留原始字串顯示
                                "SourceCol": col_name
                            }
                            
        except Exception as e:
            logger.error(f"❌ 讀取 work_orders 失敗: {e}")
            
        return result

    # ------------------------------------------------------------------
    # 2. 入庫端 (Packaged)
    # ------------------------------------------------------------------
    def get_packaged_keys_from_wip(self) -> Set[str]:
        """
        從 Bead_Sort_DB.db 取得已入庫清單
        判定：(工單 TMRA) AND (狀態='入庫完成' OR 入庫日期 != '')
        Key = "{LOT NO}__{工單號碼}"
        """
        tables = self.get_all_wip_tables()
        packaged = set()
        
        with sqlite3.connect(self.wip_db_path) as conn:
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
                except Exception as e:
                    pass
        return packaged

    def get_ignored_orders(self) -> Set[str]:
        ignored = set()
        if not os.path.exists(self.wip_db_path): return ignored
        try:
            with sqlite3.connect(self.wip_db_path) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS ignored_orders (work_order TEXT PRIMARY KEY, reason TEXT, created_at TEXT)")
                cursor = conn.execute("SELECT work_order FROM ignored_orders")
                for (wo,) in cursor: ignored.add(wo)
        except: pass
        return ignored

    # ------------------------------------------------------------------
    # 3. 計算核心：未入庫統計
    # ------------------------------------------------------------------
    def calculate_unpackaged_stats(self, start_date: datetime, end_date: datetime) -> Dict:
        # 1. 分母 (work_orders)
        produced_map = self.get_produced_batches_from_work_orders(start_date, end_date)
        produced_keys = set(produced_map.keys())
        
        # 2. 分子 (WIP DB)
        packaged_keys = self.get_packaged_keys_from_wip()
        
        # 3. 忽略清單
        ignored_orders = self.get_ignored_orders()
        
        final_unpackaged = []
        
        for key in produced_keys:
            # 比對：Key = Lot__WorkOrder
            if key in packaged_keys:
                continue
            
            wo_part = key.split("__")[1]
            if wo_part not in ignored_orders:
                final_unpackaged.append(produced_map[key])
        
        # 排序
        final_unpackaged.sort(key=lambda x: x.get("Date", ""))
        
        total_prod = len(produced_keys)
        total_pkg = len(produced_keys & packaged_keys)
        
        ratio = len(final_unpackaged) / total_prod if total_prod > 0 else 0.0
        
        return {
            "produced_count": total_prod,
            "packaged_count": total_pkg,
            "unpackaged_count": len(final_unpackaged),
            "unpackaged_ratio": round(ratio, 4),
            "unpackaged_percentage": round(ratio * 100, 2),
            "unpackaged_details": final_unpackaged
        }

    # ==================================================================
    # 良率計算 (量產良率)
    # ==================================================================
    def get_tmra_yield_data(self) -> pd.DataFrame:
        tables = self.get_all_wip_tables()
        if not tables: return pd.DataFrame()
        all_data = []
        target_cols = {"wo": "工單號碼", "date": "滴定日期", "fill": "分裝數量", "titration": "滴定數(扣除秤重)", "status": "狀態"}
        
        with sqlite3.connect(self.wip_db_path) as conn:
            cur = conn.cursor()
            for table in tables:
                try:
                    cur.execute(f"PRAGMA table_info('{table}')")
                    cols = [r[1] for r in cur.fetchall()]
                    if target_cols["wo"] not in cols: continue

                    sel_cols = [f'"{target_cols[k]}"' for k in target_cols]
                    sql = f'SELECT {", ".join(sel_cols)} FROM "{table}" WHERE "{target_cols["wo"]}" LIKE "TMRA%"'
                    cur.execute(sql)
                    all_data.extend(cur.fetchall())
                except: pass
        
        return pd.DataFrame(all_data, columns=["工單號碼", "滴定日期", "分裝數量", "滴定數(扣除秤重)", "狀態"])

    def calculate_yield_metrics(self, current_date=None, offset_days=7) -> Dict:
        df = self.get_tmra_yield_data()
        
        if current_date is None: 
            current_date = datetime.now()
        else:
            if isinstance(current_date, str):
                current_date = datetime.strptime(current_date, "%Y-%m-%d")

        ref_date = current_date - timedelta(days=offset_days)
        
        if df.empty: 
            return {"ref_date": ref_date.strftime("%Y-%m-%d"), "weekly_yield": 0.0, "monthly_yield": 0.0, "quarterly_yield": 0.0}

        # 1. 數值清洗
        for col in ['分裝數量', '滴定數(扣除秤重)']:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
        # 2. 日期清洗
        df['滴定日期'] = pd.to_datetime(df['滴定日期'], errors='coerce')
        df = df.dropna(subset=['滴定日期'])
        
        # 3. 狀態清洗
        if df['狀態'].dtype == object:
            df['狀態'] = df['狀態'].astype(str).str.strip()
            
        # 非入庫完成，分子歸 0
        mask_fail = df['狀態'] != '入庫完成'
        df.loc[mask_fail, '分裝數量'] = 0

        def calc(days):
            start = ref_date - timedelta(days=days)
            sub = df[(df['滴定日期'] > start) & (df['滴定日期'] <= ref_date)]
            num = sub['分裝數量'].sum()
            den = sub['滴定數(扣除秤重)'].sum()
            return round(num/den, 4) if den > 0 else 0.0

        return {
            "ref_date": ref_date.strftime("%Y-%m-%d"),
            "weekly_yield": calc(7),
            "monthly_yield": calc(28),
            "quarterly_yield": calc(84)
        }

    def calculate_overall_wip_yield_tmr(self) -> Dict:
        tables = self.get_all_wip_tables()
        unique, ok = set(), set()
        latest_date = None
        
        with sqlite3.connect(self.wip_db_path) as conn:
            cur = conn.cursor()
            for table in tables:
                try:
                    cur.execute(f'SELECT TRIM("LOT NO"), TRIM("工單號碼"), TRIM("狀態"), "入庫日期" FROM "{table}" WHERE TRIM("工單號碼") LIKE "TMRA%"')
                    for lot, wo, status, date_val in cur.fetchall():
                        if not lot or not wo: continue
                        key = f"{lot}__{wo}"
                        unique.add(key)
                        
                        #has_date = date_val and str(date_val).strip() not in ['', 'nan', 'None']
                        status_ok = (status and status.strip() == "入庫完成")
                        
                        if status_ok: #and has_date:
                            ok.add(key)
                            if latest_date is None or str(date_val) > str(latest_date): latest_date = str(date_val)
                except: pass
                
        total = len(unique)
        success = len(ok)
        return {
            "overall_yield": round((success/total), 4) if total > 0 else 0.0,
            "total": total, "ok": success, "fail": total - success, "base_date": latest_date
        }

# ===================== API Routes =====================

@wip_automation_bp.route("/api/workorder/unpackaged-ratio-stats", methods=["GET"])
def get_unpackaged_ratio_stats():
    """
    計算未入庫數據
    週定義：前一週 (Previous Week)
    月定義：過去 30 天
    季定義：過去 90 天
    """
    try:
        analyzer = WorkOrderAnalyzer(WORK_ORDER_DB_PATH, get_wip_db_path(), FORMULATE_DB_PATH)
        
        today = date.today()
        
        # 1. 週統計 (前一週)
        curr_monday = today - timedelta(days=today.isoweekday() - 1)
        prev_monday = curr_monday - timedelta(days=7)
        prev_sunday = curr_monday - timedelta(days=1)
        
        w_start = datetime.combine(prev_monday, datetime.min.time())
        w_end = datetime.combine(prev_sunday, datetime.max.time())
        
        # 2. 月統計
        m_start = datetime.now() - timedelta(days=30)
        m_end = datetime.now()
        
        # 3. 季統計
        q_start = datetime.now() - timedelta(days=90)
        q_end = datetime.now()
        
        w_stats = analyzer.calculate_unpackaged_stats(w_start, w_end)
        m_stats = analyzer.calculate_unpackaged_stats(m_start, m_end)
        q_stats = analyzer.calculate_unpackaged_stats(q_start, q_end)
        
        return jsonify({
            "success": True,
            "weekly": {
                "produced": w_stats["produced_count"],
                "packaged": w_stats["packaged_count"],
                "unpackaged": w_stats["unpackaged_count"],
                "details": w_stats["unpackaged_details"],
                "range_desc": f"{prev_monday} ~ {prev_sunday}"
            },
            "monthly": {
                "produced": m_stats["produced_count"],
                "packaged": m_stats["packaged_count"],
                "unpackaged": m_stats["unpackaged_count"],
                "details": m_stats["unpackaged_details"]
            },
            "quarterly": {
                "produced": q_stats["produced_count"],
                "packaged": q_stats["packaged_count"],
                "unpackaged": q_stats["unpackaged_count"],
                "details": q_stats["unpackaged_details"]
            }
        })
        
    except Exception as e:
        logger.error(f"❌ API Error /unpackaged-ratio-stats: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@wip_automation_bp.route("/api/wip/yield-period-stats", methods=["GET"])
def get_yield_period_stats():
    analyzer = WorkOrderAnalyzer(WORK_ORDER_DB_PATH, get_wip_db_path(), FORMULATE_DB_PATH)
    return jsonify({"success": True, "data": analyzer.calculate_yield_metrics()})

@wip_automation_bp.route("/api/wip/yield-overall-tmr", methods=["GET"])
def get_overall_yield():
    analyzer = WorkOrderAnalyzer(WORK_ORDER_DB_PATH, get_wip_db_path(), FORMULATE_DB_PATH)
    res = analyzer.calculate_overall_wip_yield_tmr()
    return jsonify({"success": True, **res})

@wip_automation_bp.route("/api/wip/sync", methods=["POST"])
def manual_sync_dummy():
    return jsonify({"status": "success", "message": "Manual sync via Main Process"})

# ==================== 工單 QR 追蹤 ====================
_STATION_CFG = [
    ("收藥",    "時間_收藥",      "收藥_上傳者",    "收藥_照片"),
    ("滴定準備", "時間_滴定準備",  "滴定準備_上傳者", "滴定準備_照片"),
    ("滴定開始", "時間_滴定開始",  "滴定開始_上傳者", "滴定開始_照片"),
    ("滴定結束", "時間_滴定結束",  "滴定結束_上傳者", "滴定結束_照片"),
    ("凍乾準備", "時間_凍乾準備",  "凍乾準備_上傳者", "凍乾準備_照片"),
    ("凍乾開始", "時間_凍乾開始",  "凍乾開始_上傳者", "凍乾開始_照片"),
    ("凍乾結束", "時間_凍乾結束",  "凍乾結束_上傳者", "凍乾結束_照片"),
]

@wip_automation_bp.route('/api/workorder/qr-tracking', methods=['GET'])
def qr_tracking():
    try:
        start       = request.args.get('start', '')
        end         = request.args.get('end', '')
        wo_filter   = request.args.get('workOrder', '').strip()
        bead_filter = request.args.get('beadName', '').strip()
        incomplete_only = request.args.get('incompleteOnly', '') == '1'

        where, params = [], []
        if start:
            where.append("REPLACE(\"日期\", '/', '-') >= ?"); params.append(start)
        if end:
            where.append("REPLACE(\"日期\", '/', '-') <= ?"); params.append(end)
        if wo_filter:
            where.append("\"工單號\" LIKE ?"); params.append(f'%{wo_filter}%')
        if bead_filter:
            where.append("(bead_name LIKE ? OR \"PN\" LIKE ?)")
            params.extend([f'%{bead_filter}%', f'%{bead_filter}%'])

        cols = '"工單號", "製令數量", bead_name, "PN", "日期"'
        for _, t, u, p in _STATION_CFG:
            cols += f', "{t}", "{u}", "{p}"'
        sql = f"SELECT {cols} FROM work_orders"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY REPLACE(\"日期\", '/', '-') DESC, \"時間_收藥\" DESC"

        with sqlite3.connect(WORK_ORDER_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()

        result = []
        for row in rows:
            stations, progress = [], 0
            for i, (name, t_col, u_col, p_col) in enumerate(_STATION_CFG):
                t = row[t_col] or None
                u = row[u_col] or None
                photos = [x.strip() for x in (row[p_col] or '').split(';') if x.strip()]
                if t:
                    progress = i + 1
                stations.append({'name': name, 'time': t, 'uploader': u, 'photos': photos})

            if incomplete_only and progress == 7:
                continue

            result.append({
                'workOrder':       row['工單號'],
                'quantity':        row['製令數量'],
                'beadName':        row['bead_name'] or '',
                'marker':          row['PN'] or '',
                'date':            row['日期'],
                'stations':        stations,
                'progress':        progress,
                'progressPercent': int(progress / 7 * 100),
                'currentStation':  stations[progress - 1]['name'] if progress > 0 else '未開始',
            })

        return jsonify({'success': True, 'data': result, 'total': len(result)})
    except Exception as e:
        logger.error(f"qr-tracking error: {e}")
        return jsonify({'success': False, 'error': str(e), 'data': [], 'total': 0}), 500


@wip_automation_bp.route('/api/workorder/qr-stats', methods=['GET'])
def qr_stats():
    try:
        period = request.args.get('period', 'week')
        if period == 'week':
            grp = "strftime('%Y-W%W', REPLACE(\"日期\", '/', '-'))"
        elif period == 'month':
            grp = "strftime('%Y-%m', REPLACE(\"日期\", '/', '-'))"
        elif period == 'quarter':
            grp = ("strftime('%Y', REPLACE(\"日期\", '/', '-')) || '-Q' || "
                   "((CAST(strftime('%m', REPLACE(\"日期\", '/', '-')) AS INTEGER) + 2) / 3)")
        else:
            grp = "strftime('%Y', REPLACE(\"日期\", '/', '-'))"

        sql = (f"SELECT bead_name, {grp} AS period, COUNT(*) AS cnt "
               f"FROM work_orders "
               f"WHERE bead_name IS NOT NULL AND bead_name != '' "
               f"  AND \"日期\" IS NOT NULL AND \"日期\" != '' "
               f"GROUP BY bead_name, period ORDER BY period DESC, cnt DESC")

        with sqlite3.connect(WORK_ORDER_DB_PATH) as conn:
            rows = conn.execute(sql).fetchall()

        bead_totals, period_set, cells = {}, set(), []
        for bead, p, cnt in rows:
            bead_totals[bead] = bead_totals.get(bead, 0) + cnt
            period_set.add(p)
            cells.append({'beadName': bead, 'period': p, 'count': cnt})

        top_beads = sorted(bead_totals, key=lambda b: bead_totals[b], reverse=True)[:24]
        top_set   = set(top_beads)
        periods   = sorted(period_set, reverse=True)[:12]
        per_set   = set(periods)

        return jsonify({
            'success': True,
            'periods': periods,
            'beads':   top_beads,
            'cells':   [c for c in cells if c['beadName'] in top_set and c['period'] in per_set],
        })
    except Exception as e:
        logger.error(f"qr-stats error: {e}")
        return jsonify({'success': False, 'error': str(e), 'periods': [], 'beads': [], 'cells': []}), 500


def init_wip_automation(app):
    logger.info("✅ WIP automation blueprint initialized (V8 - Date Fix)")