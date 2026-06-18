# -*- coding: utf-8 -*-
"""
api_beads_ipqc_importable.py
功能：封裝 IPQC 趨勢圖、生管查詢與 WIP 良率 API
"""
import os
import sqlite3
import traceback
import re
import logging
from datetime import datetime, timedelta
from flask import request, jsonify

# 設定 Logging
logger = logging.getLogger(__name__)

# ===== 資料庫路徑配置 (需與主程式 main.py 同步) =====
BEADS_IPQC_DB_PATH = "/opt/beadsops/data/P01_Beads_IPQC.db"
WIP_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\分藥資料庫\Bead_Sort_DB.db"

# ==========================================
#  Helper Functions
# ==========================================

def get_table_columns(cursor, table_name):
    """獲取表的所有欄位名稱"""
    cursor.execute(f'PRAGMA table_info("{table_name}")')
    return [col[1] for col in cursor.fetchall()]

def normalize_col(name):
    """正規化欄位名稱以利比對"""
    return re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())

def map_db_columns(target_fields, db_cols):
    """智慧欄位對應邏輯"""
    field_map = {}
    db_cols_norm = {normalize_col(c): c for c in db_cols}
    for target in target_fields:
        target_norm = normalize_col(target)
        if target_norm in db_cols_norm:
            field_map[target] = db_cols_norm[target_norm]
    return field_map

def find_date_column(cols):
    """智慧搜尋日期欄位名稱"""
    for c in cols:
        if '檢驗日期' in c: return c
    for c in cols:
        if '日期' in c: return c
    for c in cols:
        if 'date' in c.lower(): return c
    return None

# ==========================================
#  WIP / Yield 計算相關邏輯
# ==========================================

def calculate_yield_from_wip(cursor, table_name, start_date_str, end_date_str):
    """從 WIP 資料庫計算良率數據"""
    try:
        query = f"""
            SELECT "LOT NO", "工單號碼", "品名", "滴定數(扣除秤重)", "實際入庫數量", "入庫日期", "狀態"
            FROM "{table_name}"
            WHERE "入庫日期" >= ? AND "入庫日期" <= ?
              AND "LOT NO" IS NOT NULL AND "LOT NO" != ''
              AND CAST("滴定數(扣除秤重)" AS REAL) > 0
        """
        cursor.execute(query, (start_date_str, end_date_str))
        rows = cursor.fetchall()
        if not rows: return 0.0, 0
        
        yield_list = []
        for row in rows:
            try:
                titr = float(row[3]) if row[3] else 0
                act = float(row[4]) if row[4] else 0
                if titr > 0:
                    y = (act / titr) * 100
                    yield_list.append(max(0, min(100, y)))
            except: continue
        
        if not yield_list: return 0.0, 0
        return round(sum(yield_list) / len(yield_list), 1), len(yield_list)
    except:
        return 0.0, 0

# ==========================================
#  Main Registration Function
# ==========================================

def register_beads_ipqc_routes(app):
    """註冊所有 IPQC 與 Dashboard API 路由"""

    @app.route("/api/beads-ipqc/available-years", methods=["GET"])
    def get_ipqc_years():
        try:
            if not os.path.exists(BEADS_IPQC_DB_PATH): return jsonify({"ok": False, "years": []}), 404
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                # 取得 2025_IPQC 格式中的年份
                years = sorted(list(set([int(t.split('_')[0]) for t in tables if '_IPQC' in t and t.split('_')[0].isdigit()])), reverse=True)
                return jsonify({"ok": True, "years": years})
        except Exception as e: return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/beads-ipqc/marker-list", methods=["GET"])
    def get_ipqc_markers():
        try:
            year = request.args.get("year", datetime.now().year, type=int)
            table_name = f"{year}_IPQC"
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(f'SELECT DISTINCT Marker FROM "{table_name}" WHERE Marker IS NOT NULL ORDER BY Marker')
                return jsonify({"ok": True, "marker_list": [row[0] for row in cursor.fetchall()]})
        except: return jsonify({"ok": True, "marker_list": []})

    @app.route("/api/beads-ipqc/od-trend-data", methods=["GET"])
    def get_od_trend():
        """獲取趨勢圖資料 (支援智慧欄位對應)"""
        try:
            year = request.args.get("year", type=int)
            marker = request.args.get("marker")
            table_name = f"{year}_IPQC"
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                cols = get_table_columns(cursor, table_name)
                field_map = map_db_columns(['L1_Mean_OD', 'L2_Mean_OD', 'N1_OD', 'N3_OD'], cols)
                
                if not field_map: return jsonify({"ok": True, "data": []})
                
                sel_cols = [f'"{v}"' for v in field_map.values()]
                query = f'SELECT "匹配批號", {", ".join(sel_cols)} FROM "{table_name}" WHERE Marker = ? ORDER BY 匹配批號'
                cursor.execute(query, (marker,))
                
                data = []
                for row in cursor.fetchall():
                    item = {"batch": row[0]}
                    for idx, key in enumerate(field_map.keys()):
                        item[key] = float(row[idx+1]) if row[idx+1] else None
                    data.append(item)
                return jsonify({"ok": True, "data": data})
        except Exception as e: return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/beads-ipqc/weekly-list", methods=["GET"])
    def get_ipqc_weekly_list():
        """回傳指定年份的週別清單"""
        try:
            year = request.args.get("year", datetime.now().year, type=int)
            table_name = f"{year}_IPQC"
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                cols = get_table_columns(cursor, table_name)
                # 找 Weekly 欄位 (大小寫不敏感)
                weekly_col = next((c for c in cols if c.lower() == 'weekly'), None)
                if not weekly_col:
                    return jsonify({"ok": True, "weekly_list": []})
                cursor.execute(
                    f'SELECT DISTINCT CAST(CAST("{weekly_col}" AS REAL) AS INTEGER) '
                    f'FROM "{table_name}" '
                    f'WHERE "{weekly_col}" IS NOT NULL AND "{weekly_col}" != "" '
                    f'ORDER BY CAST(CAST("{weekly_col}" AS REAL) AS INTEGER)'
                )
                weekly_list = [str(row[0]) for row in cursor.fetchall() if row[0] is not None]
                return jsonify({"ok": True, "weekly_list": weekly_list})
        except Exception as e:
            return jsonify({"ok": True, "weekly_list": []})

    @app.route("/api/beads-ipqc/cv-trend-data", methods=["GET"])
    def get_cv_trend():
        """獲取 CV 趨勢圖資料，支援 cv_type, month, weekly 篩選"""
        try:
            year = request.args.get("year", datetime.now().year, type=int)
            marker = request.args.get("marker")
            cv_type = request.args.get("cv_type", "OD_CV")   # OD_CV or Conc_CV
            month = request.args.get("month", type=int)
            weekly = request.args.get("weekly")

            table_name = f"{year}_IPQC"
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                cols = get_table_columns(cursor, table_name)

                # CV 欄位對應
                target_cv = ['L1_OD_CV', 'L2_OD_CV', 'N1_OD_CV', 'N3_OD_CV',
                             'L1_Conc_CV', 'L2_Conc_CV', 'N1_Conc_CV', 'N3_Conc_CV']
                target_spec = ['L1_SPEC', 'L2_SPEC']
                cv_map   = map_db_columns(target_cv, cols)
                spec_map = map_db_columns(target_spec, cols)

                if not cv_map:
                    return jsonify({"ok": True, "data": [], "spec_data": {}})

                # 找月份 / Weekly 欄位
                month_col  = next((c for c in cols if '月份' in c), None)
                weekly_col = next((c for c in cols if c.lower() == 'weekly'), None)

                # 決定查詢欄位
                if cv_type == "Conc_CV":
                    want_keys = ['L1_Conc_CV', 'L2_Conc_CV', 'N1_Conc_CV', 'N3_Conc_CV']
                else:
                    want_keys = ['L1_OD_CV', 'L2_OD_CV', 'N1_OD_CV', 'N3_OD_CV']

                sel_map = {k: cv_map[k] for k in want_keys if k in cv_map}
                spec_cols = [f'"{v}"' for v in spec_map.values()]

                sel_list = [f'"{v}" AS "{k}"' for k, v in sel_map.items()]
                if spec_cols:
                    sel_list += spec_cols

                # 組 WHERE 條件
                where_clauses = ["Marker = ?"]
                params = [marker]
                if month and month_col:
                    where_clauses.append(f'CAST(CAST("{month_col}" AS REAL) AS INTEGER) = ?')
                    params.append(int(month))
                if weekly and weekly_col:
                    where_clauses.append(f'CAST(CAST("{weekly_col}" AS REAL) AS INTEGER) = ?')
                    params.append(int(weekly))

                where_sql = " AND ".join(where_clauses)
                query = (
                    f'SELECT "匹配批號", {", ".join(sel_list)} '
                    f'FROM "{table_name}" WHERE {where_sql} ORDER BY 匹配批號'
                )
                cursor.execute(query, params)
                rows = cursor.fetchall()

                col_names = ['batch'] + list(sel_map.keys()) + list(spec_map.keys())
                data = []
                spec_data = {}
                for row in rows:
                    item = {}
                    for i, name in enumerate(col_names):
                        val = row[i]
                        fval = None if (val is None or str(val).strip() == '') else val
                        item[name] = fval
                    # 提取 spec (取第一筆非空)
                    for sk in spec_map.keys():
                        if sk not in spec_data and item.get(sk) is not None:
                            spec_data[sk] = item[sk]
                    # 保留 CV 欄位 + batch
                    cv_item = {"batch": item["batch"]}
                    for k in target_cv:
                        cv_item[k] = item.get(k)
                    data.append(cv_item)

                return jsonify({"ok": True, "data": data, "spec_data": spec_data})
        except Exception as e:
            logger.error(f"cv-trend-data error: {traceback.format_exc()}")
            return jsonify({"ok": False, "error": str(e)}), 500

    # --- WIP Dashboard API (良率趨勢) ---
    @app.route('/api/dashboard/yield-stats', methods=['GET'])
    def get_dashboard_yield_stats():
        """計算儀表板顯示的週、月、季良率"""
        try:
            if not os.path.exists(WIP_DB_PATH): return jsonify({"ok": True, "items": []})
            
            now = datetime.now()
            # 基準日：往前推兩天 (確保資料已入庫)
            base_date = (now - timedelta(days=2)).replace(hour=0, minute=0, second=0)
            
            items = []
            with sqlite3.connect(WIP_DB_PATH) as conn:
                cursor = conn.cursor()
                for label, days, color in [("2周良率", 14, "bg-sky-500"), ("月良率", 30, "bg-teal-500"), ("季良率", 90, "bg-purple-500")]:
                    start_d = (base_date - timedelta(days=days)).strftime("%Y-%m-%d")
                    # 簡單化處理：僅查詢 2025 明細表
                    yld, count = calculate_yield_from_wip(cursor, "明細_2025", start_d, base_date.strftime("%Y-%m-%d"))
                    items.append({"label": label, "value": yld, "total": count, "color": color, "period": f"{days}天"})
            
            return jsonify({"ok": True, "overall": items[0]['value'], "items": items, "base_date": base_date.strftime("%Y-%m-%d")})
        except Exception as e: return jsonify({"ok": False, "error": str(e)}), 500

    logger.info("✅ api_beads_ipqc_importable 路由註冊函式載入完畢")