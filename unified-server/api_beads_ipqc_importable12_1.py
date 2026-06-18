import os
import sqlite3
import traceback
from datetime import datetime, timedelta
from flask import request, jsonify
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 資料庫路徑
BEADS_IPQC_DB_PATH = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Beads_QC\資料庫\P01_Beads_IPQC.db"

# ==========================================
#  Helper Functions (輔助函式)
# ==========================================

def get_table_columns(cursor, table_name):
    """獲取表的所有欄位名稱"""
    cursor.execute(f'PRAGMA table_info("{table_name}")')
    return [col[1] for col in cursor.fetchall()]

def get_yield_from_db(cursor, table_name, start_date_str, end_date_str):
    """
    [新增] 計算指定時間範圍內的良率
    Yield = Pass (最終判定 like 'Accept%') / Total
    """
    try:
        # 1. 查詢總生產數 (Total)
        query_total = f"""
            SELECT COUNT(*) FROM "{table_name}" 
            WHERE dD生產日 >= ? AND dD生產日 <= ?
        """
        cursor.execute(query_total, (start_date_str, end_date_str))
        total_prod = cursor.fetchone()[0]

        if total_prod == 0:
            return 0, 0  # 避免除以零

        # 2. 查詢良品數 (Pass: 最終判定 開頭為 Accept)
        query_pass = f"""
            SELECT COUNT(*) FROM "{table_name}" 
            WHERE dD生產日 >= ? AND dD生產日 <= ? 
            AND "最終判定" LIKE 'Accept%'
        """
        cursor.execute(query_pass, (start_date_str, end_date_str))
        pass_count = cursor.fetchone()[0]

        # 3. 計算良率 (回傳百分比整數，例如 95.5)
        yield_rate = round((pass_count / total_prod) * 100, 1)
        return yield_rate, total_prod

    except sqlite3.OperationalError as e:
        # 如果當年度的 table 不存在或欄位不存在，回傳 0
        logger.warning(f"⚠️ 資料庫操作錯誤: {e}")
        return 0, 0
    except Exception as e:
        logger.error(f"❌ 計算錯誤: {e}")
        return 0, 0

# ==========================================
#  Main Registration Function (路由註冊)
# ==========================================

def register_beads_ipqc_routes(app):
    """註冊 Beads IPQC 相關的所有路由到 Flask app"""
    
    @app.route("/api/beads-ipqc/available-years", methods=["GET"])
    def get_available_years():
        """獲取資料庫中可用的年份列表"""
        try:
            if not os.path.exists(BEADS_IPQC_DB_PATH):
                logger.warning(f"⚠️ Beads IPQC 資料庫不存在: {BEADS_IPQC_DB_PATH}")
                return jsonify({
                    "ok": False,
                    "message": "資料庫不存在",
                    "years": []
                }), 404
            
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                
                years = []
                for table in tables:
                    try:
                        if '_IPQC' in table:
                            year_str = table.split('_')[0]
                            if year_str.isdigit() and len(year_str) == 4:
                                years.append(int(year_str))
                    except:
                        continue
                
                years = sorted(list(set(years)), reverse=True)
                logger.info(f"✅ 可用年份: {years}")
                
                return jsonify({
                    "ok": True,
                    "years": years,
                    "current_year": datetime.now().year
                })
                
        except Exception as e:
            logger.error(f"❌ 獲取年份失敗: {e}")
            logger.error(traceback.format_exc())
            return jsonify({
                "ok": False,
                "error": str(e),
                "years": []
            }), 500

    
    @app.route("/api/beads-ipqc/weekly-list", methods=["GET"])
    def get_weekly_list():
        """獲取指定年份的週別列表"""
        try:
            year = request.args.get("year", datetime.now().year, type=int)
            table_name = f"{year}_IPQC"
            
            if not os.path.exists(BEADS_IPQC_DB_PATH):
                return jsonify({
                    "ok": False,
                    "message": "資料庫不存在",
                    "weekly_list": []
                }), 404
            
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                )
                if not cursor.fetchone():
                    logger.warning(f"⚠️ 表 {table_name} 不存在")
                    return jsonify({
                        "ok": True,
                        "weekly_list": [],
                        "message": f"表 {table_name} 不存在"
                    })
                
                query = f'SELECT DISTINCT Weekly FROM "{table_name}" WHERE Weekly IS NOT NULL ORDER BY Weekly'
                cursor.execute(query)
                weekly_list = [row[0] for row in cursor.fetchall()]
                
                logger.info(f"✅ {year} 年週別列表: {len(weekly_list)} 週")
                
                return jsonify({
                    "ok": True,
                    "weekly_list": weekly_list,
                    "year": year
                })
                
        except Exception as e:
            logger.error(f"❌ 獲取週別列表失敗: {e}")
            logger.error(traceback.format_exc())
            return jsonify({
                "ok": False,
                "error": str(e),
                "weekly_list": []
            }), 500

    
    @app.route("/api/beads-ipqc/marker-list", methods=["GET"])
    def get_marker_list():
        """獲取指定年份的 Marker 列表"""
        try:
            year = request.args.get("year", datetime.now().year, type=int)
            table_name = f"{year}_IPQC"
            
            if not os.path.exists(BEADS_IPQC_DB_PATH):
                return jsonify({
                    "ok": False,
                    "message": "資料庫不存在",
                    "marker_list": []
                }), 404
            
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                )
                if not cursor.fetchone():
                    logger.warning(f"⚠️ 表 {table_name} 不存在")
                    return jsonify({
                        "ok": True,
                        "marker_list": [],
                        "message": f"表 {table_name} 不存在"
                    })
                
                query = f'SELECT DISTINCT Marker FROM "{table_name}" WHERE Marker IS NOT NULL ORDER BY Marker'
                cursor.execute(query)
                marker_list = [row[0] for row in cursor.fetchall()]
                
                logger.info(f"✅ {year} 年 Marker 列表: {marker_list}")
                
                return jsonify({
                    "ok": True,
                    "marker_list": marker_list,
                    "year": year
                })
                
        except Exception as e:
            logger.error(f"❌ 獲取 Marker 列表失敗: {e}")
            logger.error(traceback.format_exc())
            return jsonify({
                "ok": False,
                "error": str(e),
                "marker_list": []
            }), 500

    
    # -------------------------------------------------------
    # [新增] 生產良率 API
    # -------------------------------------------------------
    @app.route('/api/dashboard/yield-stats', methods=['GET'])
    def get_yield_stats():
        try:
            now = datetime.now()
            current_year = now.year
            table_name = f"{current_year}_IPQC" # 例如: 2025_IPQC
            
            date_fmt = "%Y-%m-%d %H:%M:%S"
            end_date_str = now.strftime(date_fmt)

            # 計算時間範圍
            start_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            quarter_month = ((now.month - 1) // 3) * 3 + 1
            start_quarter = now.replace(month=quarter_month, day=1, hour=0, minute=0, second=0, microsecond=0)
            start_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

            # --- DEBUG LOG (除錯訊息) ---
            print(f"----- DEBUG START -----")
            print(f"資料庫路徑: {BEADS_IPQC_DB_PATH}")
            print(f"目標 Table: {table_name}")
            print(f"本周查詢範圍: {start_week} ~ {end_date_str}")
            # ---------------------------

            if not os.path.exists(BEADS_IPQC_DB_PATH):
                print("❌ 錯誤: 資料庫檔案找不到！")
                return jsonify({"ok": False, "message": "資料庫不存在"}), 404

            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()

                # 檢查 Table 是否存在
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                if not cursor.fetchone():
                    print(f"❌ 錯誤: 資料表 {table_name} 不存在！")
                    # 嘗試列出所有 tables
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    print(f"ℹ️ 現有 Tables: {[row[0] for row in cursor.fetchall()]}")
                    # 回傳空數據避免前端報錯
                    return jsonify({"ok": True, "overall": 0, "total_year": 0, "items": []})

                # 執行查詢
                yield_week, total_week = get_yield_from_db(cursor, table_name, start_week.strftime(date_fmt), end_date_str)
                yield_month, total_month = get_yield_from_db(cursor, table_name, start_month.strftime(date_fmt), end_date_str)
                yield_quarter, total_quarter = get_yield_from_db(cursor, table_name, start_quarter.strftime(date_fmt), end_date_str)
                yield_year, total_year = get_yield_from_db(cursor, table_name, start_year.strftime(date_fmt), end_date_str)

                print(f"查詢結果 (Year): Total={total_year}, Yield={yield_year}%")

            return jsonify({
                "ok": True,
                "overall": yield_year,
                "total_year": total_year,
                "items": [
                    { "label": "周良率", "value": yield_week, "total": total_week, "color": "bg-sky-500" },
                    { "label": "月良率", "value": yield_month, "total": total_month, "color": "bg-teal-500" },
                    { "label": "季良率", "value": yield_quarter, "total": total_quarter, "color": "bg-purple-500" },
                ]
            })

        except Exception as e:
            logger.error(f"❌ 計算良率失敗: {e}")
            logger.error(traceback.format_exc())
            return jsonify({"ok": False, "error": str(e)}), 500