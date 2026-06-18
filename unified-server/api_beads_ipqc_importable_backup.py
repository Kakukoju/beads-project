import os
import sqlite3
import traceback
import re
from datetime import datetime, timedelta
from flask import request, jsonify
import logging

# 設定 Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ===== 資料庫路徑配置 =====
BEADS_IPQC_DB_PATH = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Beads_QC\資料庫\P01_Beads_IPQC.db"
WIP_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\分藥資料庫\Bead_Sort_DB.db"

# ==========================================
#  Helper Functions
# ==========================================

def get_table_columns(cursor, table_name):
    """獲取表的所有欄位名稱"""
    cursor.execute(f'PRAGMA table_info("{table_name}")')
    return [col[1] for col in cursor.fetchall()]

def normalize_col(name):
    """將欄位名稱正規化：轉小寫、移除底線與空格，用於比對"""
    return re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())

def map_db_columns(target_fields, db_cols):
    """
    智慧欄位對應
    input: target_fields (前端要的欄位, e.g., ['L1_Mean_OD'])
    input: db_cols (資料庫實際欄位, e.g., ['L1MeanOD'])
    output: field_map (字典, {'L1_Mean_OD': 'L1MeanOD'})
    """
    field_map = {}
    db_cols_norm = {normalize_col(c): c for c in db_cols} # 建立索引: l1meanod -> L1MeanOD
    
    for target in target_fields:
        target_norm = normalize_col(target)
        if target_norm in db_cols_norm:
            field_map[target] = db_cols_norm[target_norm]
        else:
            # 如果真的找不到，試著找完全一樣的(雖然正規化已經涵蓋)
            if target in db_cols:
                field_map[target] = target
                
    return field_map

def find_date_column(cols):
    """智慧搜尋日期欄位名稱 (優先順序：'檢驗日期' -> 含 '日期' -> 含 'Date')"""
    for c in cols:
        if '檢驗日期' in c: return c
    for c in cols:
        if '日期' in c: return c
    for c in cols:
        if 'date' in c.lower(): return c
    return None

# --- WIP Dashboard Helper Functions ---
def create_ignored_items_table(conn):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ignored_yield_items (
                key TEXT PRIMARY KEY,
                lot_no TEXT,
                work_order TEXT,
                reason TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
    except Exception as e:
        logger.error(f"建立忽略項目表失敗: {e}")

def get_ignored_items(conn):
    try:
        create_ignored_items_table(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT key FROM ignored_yield_items")
        return {row[0] for row in cursor.fetchall()}
    except Exception as e:
        return set()

def toggle_ignore_item(conn, key, lot_no, work_order, ignore):
    try:
        create_ignored_items_table(conn)
        cursor = conn.cursor()
        if ignore:
            cursor.execute(
                """INSERT OR REPLACE INTO ignored_yield_items 
                   (key, lot_no, work_order, created_at) VALUES (?, ?, ?, ?)""",
                (key, lot_no, work_order, datetime.now().isoformat())
            )
        else:
            cursor.execute("DELETE FROM ignored_yield_items WHERE key = ?", (key,))
        conn.commit()
        return True
    except Exception as e:
        return False

def calculate_yield_from_wip(cursor, table_name, start_date_str, end_date_str):
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
        
        yields = []
        for row in rows:
            try:
                titr = float(row[3]) if row[3] else 0
                act = float(row[4]) if row[4] else 0
                if titr > 0:
                    y = (act / titr) * 100
                    yields.append(max(0, min(100, y)))
            except: continue
        
        if not yields: return 0.0, 0
        return round(sum(yields) / len(yields), 1), len(yields)
    except:
        return 0.0, 0

# ==========================================
#  Main Registration Function
# ==========================================

def register_beads_ipqc_routes(app):
    """註冊路由"""
    
    # 1. IPQC 基礎資料
    @app.route("/api/beads-ipqc/available-years", methods=["GET"])
    def get_ipqc_years():
        try:
            if not os.path.exists(BEADS_IPQC_DB_PATH): return jsonify({"ok": False, "years": []}), 404
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                years = sorted([int(t.split('_')[0]) for t in tables if '_IPQC' in t and t.split('_')[0].isdigit()], reverse=True)
                return jsonify({"ok": True, "years": years})
        except Exception as e: return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/beads-ipqc/weekly-list", methods=["GET"])
    def get_ipqc_weekly():
        try:
            year = request.args.get("year", datetime.now().year, type=int)
            table_name = f"{year}_IPQC"
            if not os.path.exists(BEADS_IPQC_DB_PATH): return jsonify({"ok": False, "weekly_list": []}), 404
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if not cursor.fetchone(): return jsonify({"ok": True, "weekly_list": []})
                cursor.execute(f'SELECT DISTINCT CAST(Weekly AS INT) FROM "{table_name}" WHERE Weekly IS NOT NULL ORDER BY Weekly')
                return jsonify({"ok": True, "weekly_list": [row[0] for row in cursor.fetchall()]})
        except Exception as e: return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/beads-ipqc/marker-list", methods=["GET"])
    def get_ipqc_markers():
        try:
            year = request.args.get("year", datetime.now().year, type=int)
            table_name = f"{year}_IPQC"
            if not os.path.exists(BEADS_IPQC_DB_PATH): return jsonify({"ok": False, "marker_list": []}), 404
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if not cursor.fetchone(): return jsonify({"ok": True, "marker_list": []})
                cursor.execute(f'SELECT DISTINCT Marker FROM "{table_name}" WHERE Marker IS NOT NULL ORDER BY Marker')
                return jsonify({"ok": True, "marker_list": [row[0] for row in cursor.fetchall()]})
        except Exception as e: return jsonify({"ok": False, "error": str(e)}), 500

    # 2. IPQC OD 趨勢 (修正版)
    @app.route("/api/beads-ipqc/od-trend-data", methods=["GET"])
    def get_od_trend():
        try:
            year = request.args.get("year", type=int)
            month = request.args.get("month", type=int)
            weekly = request.args.get("weekly")
            marker = request.args.get("marker")
            if not year or not marker: return jsonify({"ok": False, "message": "缺少參數"}), 400
            
            table_name = f"{year}_IPQC"
            if not os.path.exists(BEADS_IPQC_DB_PATH): return jsonify({"ok": False, "data": []}), 404
            
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if not cursor.fetchone(): return jsonify({"ok": True, "data": []})
                
                cols = get_table_columns(cursor, table_name)
                
                # --- 智慧對應欄位 ---
                target_fields = ['L1_Mean_OD', 'L2_Mean_OD', 'N1_OD', 'N3_OD']
                field_map = map_db_columns(target_fields, cols)
                
                if not field_map:
                    logger.error(f"[OD] 無法找到對應欄位. DB Cols: {cols}")
                    return jsonify({"ok": True, "data": [], "message": "無 OD 欄位"})
                
                logger.info(f"[OD] Mapped Fields: {field_map}") # Debug Log

                where = ["Marker = ?"]
                params = [marker]
                
                date_col = find_date_column(cols)
                if month:
                    if date_col:
                        where.append(f"strftime('%m', \"{date_col}\") = ?")
                        params.append(f"{month:02d}")
                    elif '月份' in cols:
                        where.append('CAST("月份" AS INT) = ?')
                        params.append(month)

                if weekly:
                    where.append('CAST("Weekly" AS INT) = ?')
                    params.append(weekly)
                
                # 組裝 SQL: 使用 DB 的實際欄位名 (value)，但在回傳時我們會對應回前端要的 key
                db_fields_to_select = [f'"{v}"' for v in field_map.values()]
                query = f'SELECT "匹配批號", {", ".join(db_fields_to_select)} FROM "{table_name}" WHERE {" AND ".join(where)} ORDER BY 匹配批號'
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                data = []
                for row in rows:
                    item = {"batch": row[0]}
                    # row[1] 開始是數據，順序對應 field_map.values()
                    # 但我們需要把這些數據塞回 item[target_key]
                    for idx, target_key in enumerate(field_map.keys()):
                        val = row[idx+1]
                        item[target_key] = float(val) if val not in [None, ''] else None
                    data.append(item)
                
                # 回傳給前端的 fields 必須是前端認識的 key
                return jsonify({"ok": True, "data": data, "fields": list(field_map.keys())})
        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify({"ok": False, "error": str(e)}), 500

    # 3. IPQC CV 趨勢 (修正版)
    @app.route("/api/beads-ipqc/cv-trend-data", methods=["GET"])
    def get_cv_trend():
        try:
            year = request.args.get("year", type=int)
            marker = request.args.get("marker")
            cv_type = request.args.get("cv_type", "OD_CV")
            month = request.args.get("month", type=int)
            weekly = request.args.get("weekly")
            if not year or not marker: return jsonify({"ok": False}), 400
            
            table_name = f"{year}_IPQC"
            if not os.path.exists(BEADS_IPQC_DB_PATH): return jsonify({"ok": False, "data": []}), 404
            
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if not cursor.fetchone(): return jsonify({"ok": True, "data": []})
                
                cols = get_table_columns(cursor, table_name)
                
                # 定義目標欄位
                if cv_type == "OD_CV":
                    target_cv = ['L1_OD_CV', 'L2_OD_CV', 'N1_OD_CV', 'N3_OD_CV']
                else:
                    target_cv = ['L1_Conc_CV', 'L2_Conc_CV', 'N1_Conc_CV', 'N3_Conc_CV']
                target_spec = ['L1_SPEC', 'L2_SPEC']
                
                # 進行對應
                cv_map = map_db_columns(target_cv, cols)
                spec_map = map_db_columns(target_spec, cols)
                
                if not cv_map: return jsonify({"ok": True, "data": []})
                
                where = ["Marker = ?"]
                params = [marker]
                
                date_col = find_date_column(cols)
                if month:
                    if date_col:
                        where.append(f"strftime('%m', \"{date_col}\") = ?")
                        params.append(f"{month:02d}")
                    elif '月份' in cols:
                        where.append('CAST("月份" AS INT) = ?')
                        params.append(month)

                if weekly:
                    where.append('CAST("Weekly" AS INT) = ?')
                    params.append(weekly)
                
                # 組裝 SQL
                select_db_cols = [f'"{v}"' for v in cv_map.values()] + [f'"{v}"' for v in spec_map.values()]
                query = f'SELECT "匹配批號", {", ".join(select_db_cols)} FROM "{table_name}" WHERE {" AND ".join(where)} ORDER BY 匹配批號'
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                data = []
                spec_data = {}
                for row in rows:
                    item = {"batch": row[0]}
                    
                    # 處理 CV
                    for idx, target_key in enumerate(cv_map.keys()):
                        val = row[idx+1]
                        item[target_key] = float(val) if val not in [None, ''] else None
                        
                    # 處理 SPEC (只需要取一次有效值)
                    spec_start_idx = 1 + len(cv_map)
                    for idx, target_key in enumerate(spec_map.keys()):
                        val = row[spec_start_idx + idx]
                        if target_key not in spec_data and val not in [None, '']:
                            try: spec_data[target_key] = float(val)
                            except: pass
                            
                    data.append(item)
                
                return jsonify({"ok": True, "data": data, "spec_data": spec_data, "fields": list(cv_map.keys())})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    # 4. WIP Dashboard (保持不變)
    @app.route('/api/dashboard/yield-stats', methods=['GET'])
    def get_dashboard_yield_stats():
        try:
            now = datetime.now()
            base_date = (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
            base_date_str = base_date.strftime("%Y-%m-%d")

            # 取得日期範圍
            ranges = [
                ("2周良率", 14, "bg-sky-500"),
                ("月良率", 30, "bg-teal-500"),
                ("季良率", 90, "bg-purple-500")
            ]

            if not os.path.exists(WIP_DB_PATH):
                return jsonify({"ok": True, "overall": 0, "total_year": 0, "items": []})

            with sqlite3.connect(WIP_DB_PATH) as conn:
                cursor = conn.cursor()

                ignored_keys = get_ignored_items(conn)

                items = []
                yield_2week = 0

                for label, days, color in ranges:

                    start_date = base_date - timedelta(days=days)
                    start_d = start_date.strftime("%Y-%m-%d")

                    # -------- 跨年關鍵：依日期動態找 tables --------
                    tables = set()

                    for y in range(start_date.year, base_date.year + 1):
                        table = f"明細_{y}"
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                        if cursor.fetchone():
                            tables.add(table)

                    total_batches = 0
                    period_yields = []

                    for t in tables:
                        y, total = calculate_yield_from_wip(cursor, t, start_d, base_date_str)
                        if total > 0:
                            total_batches += total
                            total_batches += total
                            
                            # 收集該表區間 yield 明細
                            query = f'SELECT "實際入庫數量", "滴定數(扣除秤重)" FROM "{t}" WHERE "入庫日期" BETWEEN ? AND ?'
                            cursor.execute(query, (start_d, base_date_str))
                            for act, titr in cursor.fetchall():
                                try:
                                    act = float(act)
                                    titr = float(titr)
                                    if titr > 0:
                                        period_yields.append((act/titr)*100)
                                except:
                                    continue

                    overall_val = round(sum(period_yields)/len(period_yields), 1) if period_yields else 0.0

                    items.append({
                        "label": label,
                        "value": overall_val,
                        "total": total_batches,
                        "color": color,
                        "period": f"{days}天"
                    })

                    if days == 14:
                        yield_2week = overall_val

                # -------- 年良率：同樣跨年查所有 tables --------
                year_tables = set()
                start_y = base_date.replace(month=1, day=1).strftime("%Y-%m-%d")

                for y in range(2025, base_date.year + 1):
                    table = f"明細_{y}"
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
                    if cursor.fetchone():
                        year_tables.add(table)

                total_year = 0
                year_yields = []

                for t in year_tables:
                    y, total = calculate_yield_from_wip(cursor, t, start_y, base_date_str)
                    total_year += total

                    # 依日期範圍收集明細
                    cursor.execute(f'SELECT "實際入庫數量", "滴定數(扣除秤重)" FROM "{t}" WHERE "入庫日期" BETWEEN ? AND ?', (start_y, base_date_str))
                    for act, titr in cursor.fetchall():
                        try:
                            act = float(act)
                            titr = float(titr)
                            if titr > 0:
                                year_yields.append((act/titr)*100)
                        except:
                            continue

                overall_year = round(sum(year_yields)/len(year_yields), 1) if year_yields else 0.0

            # 前端需要的結構
            return jsonify({
                "ok": True,
                "overall": overall_year,
                "total_year": total_year,
                "items": items,
                "has_low_yield_alert": yield_2week < 95.0,
                "base_date": base_date_str
            })

        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify({"ok": False, "error": str(e)}), 500


    @app.route('/api/dashboard/low-yield-items', methods=['GET'])
    def get_low_yield_items_crossyear():
        try:
            now = datetime.now()

            # 基準日：沿用你原本邏輯往前 2 天
            base_date = (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
            end_date_str = base_date.strftime("%Y-%m-%d")

            # 低良率警示區間：14 天
            start_date = base_date - timedelta(days=14)
            start_date_str = start_date.strftime("%Y-%m-%d")

            if not os.path.exists(WIP_DB_PATH):
                return jsonify({"ok": False, "items": []}), 404

            with sqlite3.connect(WIP_DB_PATH) as conn:
                cursor = conn.cursor()

                # 先取得 ignored keys（你已有 helper）
                ignored_keys = get_ignored_items(conn)

                # -------- 跨年關鍵邏輯 --------
                # 依日期範圍找出可能涵蓋的 tables
                candidate_tables = set()

                for y in range(start_date.year, base_date.year + 1):
                    table = f"明細_{y}"
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                        (table,)
                    )
                    if cursor.fetchone():
                        candidate_tables.add(table)

                rows = []

                # 組裝跨年查詢：對每個 table 取得 LOT 與工單相關資料
                for table_name in candidate_tables:
                    query = f"""
                        SELECT "LOT NO", "工單號碼", "品名",
                            "滴定數(扣除秤重)", "實際入庫數量",
                            "入庫日期", "狀態"
                        FROM "{table_name}"
                        WHERE "入庫日期" >= ? AND "入庫日期" <= ?
                        AND "LOT NO" IS NOT NULL AND "LOT NO" != ''
                        AND CAST("滴定數(扣除秤重)" AS REAL) > 0
                        ORDER BY "入庫日期" DESC
                    """
                    cursor.execute(query, (start_date_str, end_date_str))
                    rows += cursor.fetchall()

            items = []

            for row in rows:
                try:
                    lot_no = str(row[0]).strip()
                    work_order = str(row[1]).strip()

                    titr = float(row[3]) if row[3] not in [None, ''] else 0.0
                    act = float(row[4]) if row[4] not in [None, ''] else 0.0

                    if titr > 0:
                        yld = round((act / titr) * 100, 1)

                        if yld < 95.0:
                            key = f"{lot_no}_{work_order}"

                            items.append({
                                "key": key,
                                "lot_no": lot_no,
                                "work_order": work_order,
                                "product_name": row[2],
                                "titration_qty": int(titr),
                                "actual_qty": int(act),
                                "warehouse_date": row[5],
                                "status": row[6],
                                "yield": yld,
                                "ignored": key in ignored_keys
                            })

                except:
                    continue

            return jsonify({"ok": True, "items": items})

        except Exception as e:
            logger.error(traceback.format_exc())
            return jsonify({"ok": False, "error": str(e)}), 500


    @app.route('/api/dashboard/toggle-yield-ignore', methods=['POST'])
    def toggle_yield_ignore():
        try:
            data = request.json
            with sqlite3.connect(WIP_DB_PATH) as conn:
                toggle_ignore_item(conn, data.get('key'), data.get('lot_no'), data.get('work_order'), data.get('ignore'))
            return jsonify({'ok': True})
        except Exception as e: return jsonify({'ok': False, 'error': str(e)}), 500

    logger.info("✅ Beads IPQC & WIP Dashboard Routes Fully Registered.")