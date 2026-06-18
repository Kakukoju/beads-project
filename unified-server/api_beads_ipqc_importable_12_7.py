import os
import sqlite3
import traceback
from datetime import datetime, timedelta
from flask import request, jsonify
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== 資料庫路徑配置 =====
BEADS_IPQC_DB_PATH = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Beads_QC\資料庫\P01_Beads_IPQC.db"

# 🆕 WIP 資料庫路徑（用於生產良率）
WIP_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\分藥資料庫\Bead_Sort_DB.db"

# ==========================================
#  Helper Functions (輔助函式)
# ==========================================

def get_table_columns(cursor, table_name):
    """獲取表的所有欄位名稱"""
    cursor.execute(f'PRAGMA table_info("{table_name}")')
    return [col[1] for col in cursor.fetchall()]

# 🆕 忽略清單管理
def create_ignored_items_table(conn):
    """建立忽略項目表"""
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
    """取得所有被忽略的項目"""
    try:
        create_ignored_items_table(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT key FROM ignored_yield_items")
        return {row[0] for row in cursor.fetchall()}
    except Exception as e:
        logger.error(f"讀取忽略清單失敗: {e}")
        return set()

def toggle_ignore_item(conn, key, lot_no, work_order, ignore):
    """切換項目忽略狀態"""
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
        logger.error(f"切換忽略狀態失敗: {e}")
        return False

# 🆕 WIP 良率計算核心函數
def calculate_yield_from_wip(cursor, table_name, start_date_str, end_date_str):
    """從 WIP 資料庫計算生產良率"""
    try:
        query = f"""
            SELECT 
                "LOT NO", "工單號碼", "品名", "滴定數(扣除秤重)", "實際入庫數量", "入庫日期", "狀態"
            FROM "{table_name}"
            WHERE "入庫日期" >= ? AND "入庫日期" <= ?
              AND "LOT NO" IS NOT NULL AND "LOT NO" != ''
              AND "工單號碼" IS NOT NULL AND "工單號碼" != ''
              AND "滴定數(扣除秤重)" IS NOT NULL AND "滴定數(扣除秤重)" != ''
              AND CAST("滴定數(扣除秤重)" AS REAL) > 0
        """
        
        cursor.execute(query, (start_date_str, end_date_str))
        rows = cursor.fetchall()
        
        if not rows:
            return 0.0, 0
        
        yields = []
        for row in rows:
            lot_no = str(row[0]).strip()
            work_order = str(row[1]).strip()
            key = f"{lot_no}_{work_order}"
            
            try:
                titration_qty = float(row[3]) if row[3] else 0
                actual_qty = float(row[4]) if row[4] else 0
                
                if titration_qty > 0:
                    item_yield = (actual_qty / titration_qty) * 100
                    item_yield = max(0, min(100, item_yield))
                    yields.append(item_yield)
            except (ValueError, TypeError):
                continue
        
        if not yields:
            return 0.0, 0
        
        avg_yield = sum(yields) / len(yields)
        return round(avg_yield, 1), len(yields)
        
    except Exception as e:
        logger.error(f"❌ 計算良率失敗: {e}")
        return 0.0, 0

# ==========================================
#  Main Registration Function (路由註冊)
# ==========================================

def register_beads_ipqc_routes(app):
    """註冊 Beads IPQC 相關的所有路由到 Flask app"""
    
    # =====================================================
    # 1. 基礎 IPQC 選單 API (修復 404 錯誤)
    # =====================================================
    
    @app.route('/api/beads-ipqc/available-years', methods=['GET'])
    def get_ipqc_years():
        """取得 IPQC 可用年份"""
        try:
            # 這裡可以連接 BEADS_IPQC_DB_PATH 查詢實際年份
            # 目前回傳預設值以確保前端能運作
            return jsonify([2023, 2024, 2025])
        except Exception as e:
            logger.error(f"取得年份失敗: {e}")
            return jsonify([2025]), 200

    @app.route('/api/beads-ipqc/weekly-list', methods=['GET'])
    def get_ipqc_weekly_list():
        """取得指定年份的週次列表"""
        year = request.args.get('year', '2025')
        try:
            # 模擬回傳，實際應查詢 DB
            return jsonify([
                {"week": f"{year}_W01", "label": "第 01 週"},
                {"week": f"{year}_W02", "label": "第 02 週"},
                {"week": f"{year}_W50", "label": "第 50 週"}
            ])
        except Exception as e:
            logger.error(f"取得週次失敗: {e}")
            return jsonify([]), 200

    @app.route('/api/beads-ipqc/marker-list', methods=['GET'])
    def get_ipqc_marker_list():
        """取得指定年份的 Marker 列表"""
        year = request.args.get('year', '2025')
        try:
            return jsonify(["Ca-B", "NH3", "MG-AD", "CRP-U", "TEST-MARKER"])
        except Exception as e:
            logger.error(f"取得 Marker 失敗: {e}")
            return jsonify([]), 200

    # =====================================================
    # 2. 生產良率 API（使用 WIP 資料庫）
    # =====================================================
    @app.route('/api/dashboard/yield-stats', methods=['GET'])
    def get_yield_stats():
        try:
            now = datetime.now()
            base_date = (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
            base_date_str = base_date.strftime("%Y-%m-%d")
            
            year = base_date.year
            table_name = f"明細_{year}"
            
            logger.info(f"📊 生產良率查詢 - 基準日期: {base_date_str}, 資料表: {table_name}")
            
            if not os.path.exists(WIP_DB_PATH):
                return jsonify({"ok": True, "overall": 0, "total_year": 0, "items": [], "message": "資料庫不存在"})
            
            with sqlite3.connect(WIP_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if not cursor.fetchone():
                    return jsonify({"ok": True, "overall": 0, "total_year": 0, "items": []})
                
                # 計算各時段
                start_2week = (base_date - timedelta(days=14)).strftime("%Y-%m-%d")
                yield_2week, total_2week = calculate_yield_from_wip(cursor, table_name, start_2week, base_date_str)
                
                start_month = (base_date - timedelta(days=30)).strftime("%Y-%m-%d")
                yield_month, total_month = calculate_yield_from_wip(cursor, table_name, start_month, base_date_str)
                
                start_quarter = (base_date - timedelta(days=90)).strftime("%Y-%m-%d")
                yield_quarter, total_quarter = calculate_yield_from_wip(cursor, table_name, start_quarter, base_date_str)
                
                start_year = base_date.replace(month=1, day=1).strftime("%Y-%m-%d")
                yield_year, total_year = calculate_yield_from_wip(cursor, table_name, start_year, base_date_str)
            
            return jsonify({
                "ok": True,
                "overall": yield_year,
                "total_year": total_year,
                "items": [
                    {"label": "2周良率", "value": yield_2week, "total": total_2week, "color": "bg-sky-500", "period": "14天"},
                    {"label": "月良率", "value": yield_month, "total": total_month, "color": "bg-teal-500", "period": "30天"},
                    {"label": "季良率", "value": yield_quarter, "total": total_quarter, "color": "bg-purple-500", "period": "90天"}
                ],
                "base_date": base_date_str,
                "has_low_yield_alert": yield_2week < 95.0
            })
            
        except Exception as e:
            logger.error(f"❌ 計算良率失敗: {e}")
            logger.error(traceback.format_exc())
            return jsonify({"ok": False, "error": str(e), "overall": 0, "items": []}), 500
    
    # =====================================================
    # 3. 低良率項目列表 API
    # =====================================================
    @app.route('/api/dashboard/low-yield-items', methods=['GET'])
    def get_low_yield_items():
        try:
            now = datetime.now()
            base_date = (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
            start_date = (base_date - timedelta(days=14)).strftime("%Y-%m-%d")
            end_date = base_date.strftime("%Y-%m-%d")
            year = base_date.year
            table_name = f"明細_{year}"
            
            if not os.path.exists(WIP_DB_PATH):
                return jsonify({"ok": False, "message": "資料庫不存在", "items": []}), 404
            
            with sqlite3.connect(WIP_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if not cursor.fetchone():
                    return jsonify({"ok": True, "items": [], "message": f"資料表 {table_name} 不存在"})
                
                ignored_keys = get_ignored_items(conn)
                
                query = f"""
                    SELECT "LOT NO", "工單號碼", "品名", "滴定數(扣除秤重)", "實際入庫數量", "入庫日期", "狀態"
                    FROM "{table_name}"
                    WHERE "入庫日期" >= ? AND "入庫日期" <= ?
                      AND "LOT NO" IS NOT NULL AND "LOT NO" != ''
                      AND "工單號碼" IS NOT NULL AND "工單號碼" != ''
                      AND "滴定數(扣除秤重)" IS NOT NULL AND "滴定數(扣除秤重)" != ''
                      AND CAST("滴定數(扣除秤重)" AS REAL) > 0
                    ORDER BY "入庫日期" DESC
                """
                cursor.execute(query, (start_date, end_date))
                rows = cursor.fetchall()
            
            low_yield_items = []
            for row in rows:
                try:
                    lot_no = str(row[0]).strip()
                    work_order = str(row[1]).strip()
                    key = f"{lot_no}_{work_order}"
                    titration_qty = float(row[3]) if row[3] else 0
                    actual_qty = float(row[4]) if row[4] else 0
                    
                    if titration_qty > 0:
                        item_yield = (actual_qty / titration_qty) * 100
                        item_yield = max(0, min(100, item_yield))
                        
                        if item_yield < 95.0:
                            low_yield_items.append({
                                "key": key,
                                "lot_no": lot_no,
                                "work_order": work_order,
                                "product_name": str(row[2]).strip() if row[2] else "",
                                "titration_qty": int(titration_qty),
                                "actual_qty": int(actual_qty),
                                "warehouse_date": str(row[5]) if row[5] else "",
                                "status": str(row[6]).strip() if row[6] else "",
                                "yield": round(item_yield, 1),
                                "ignored": key in ignored_keys
                            })
                except Exception:
                    continue
            
            return jsonify({
                "ok": True,
                "items": low_yield_items,
                "period": f"{start_date} ~ {end_date}",
                "threshold": 95.0
            })
            
        except Exception as e:
            logger.error(f"❌ 取得低良率項目失敗: {e}")
            return jsonify({"ok": False, "error": str(e), "items": []}), 500
    
    # =====================================================
    # 4. 切換忽略狀態 API
    # =====================================================
    @app.route('/api/dashboard/toggle-yield-ignore', methods=['POST'])
    def toggle_yield_ignore():
        try:
            data = request.json
            key = data.get('key')
            lot_no = data.get('lot_no')
            work_order = data.get('work_order')
            ignore = data.get('ignore', True)
            
            if not key or not lot_no or not work_order:
                return jsonify({'ok': False, 'error': '缺少必要參數'}), 400
            
            if not os.path.exists(WIP_DB_PATH):
                return jsonify({'ok': False, 'error': '資料庫不存在'}), 404
            
            with sqlite3.connect(WIP_DB_PATH) as conn:
                success = toggle_ignore_item(conn, key, lot_no, work_order, ignore)
            
            if success:
                return jsonify({'ok': True, 'message': f"項目 {key} {'已忽略' if ignore else '已恢復'}"})
            else:
                return jsonify({'ok': False, 'error': '操作失敗'}), 500
                
        except Exception as e:
            logger.error(f"❌ 切換忽略狀態失敗: {e}")
            return jsonify({'ok': False, 'error': str(e)}), 500
    
    logger.info("✅ Beads IPQC & Dashboard Routes Registered")