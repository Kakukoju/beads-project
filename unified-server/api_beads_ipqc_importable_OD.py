"""
Beads IPQC API - 使用資料庫的「月份」欄位
不再從批號提取月份，直接使用資料庫的月份欄位
"""

import os
import sqlite3
import traceback
from datetime import datetime
from flask import request, jsonify
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BEADS_IPQC_DB_PATH = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Beads_QC\資料庫\P01_Beads_IPQC.db"


def get_table_columns(cursor, table_name):
    """獲取表的所有欄位名稱"""
    cursor.execute(f'PRAGMA table_info("{table_name}")')
    return [col[1] for col in cursor.fetchall()]


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

    
    @app.route("/api/beads-ipqc/od-trend-data", methods=["GET"])
    def get_od_trend_data():
        """獲取 OD 趨勢數據 - 使用資料庫的月份欄位"""
        try:
            year = request.args.get("year", type=int)
            month = request.args.get("month", type=int)
            weekly = request.args.get("weekly")
            marker = request.args.get("marker")
            
            if not year or not marker:
                return jsonify({
                    "ok": False,
                    "message": "缺少必要參數: year 或 marker"
                }), 400
            
            table_name = f"{year}_IPQC"
            
            if not os.path.exists(BEADS_IPQC_DB_PATH):
                return jsonify({
                    "ok": False,
                    "message": "資料庫不存在",
                    "data": []
                }), 404
            
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                )
                if not cursor.fetchone():
                    return jsonify({
                        "ok": True,
                        "data": [],
                        "message": f"表 {table_name} 不存在"
                    })
                
                # 動態檢查欄位
                available_columns = get_table_columns(cursor, table_name)
                
                # 檢查是否有「月份」欄位
                has_month_column = '月份' in available_columns
                
                possible_od_fields = ['L1_Mean_OD', 'L2_Mean_OD', 'N1_OD', 'N3_OD']
                od_fields = [field for field in possible_od_fields if field in available_columns]
                
                if not od_fields:
                    logger.warning(f"⚠️ 表 {table_name} 中沒有找到任何 OD 欄位")
                    return jsonify({
                        "ok": True,
                        "data": [],
                        "message": f"表 {table_name} 中沒有 OD 欄位"
                    })
                
                logger.info(f"✅ {table_name} 可用 OD 欄位: {od_fields}")
                logger.info(f"✅ 月份欄位存在: {has_month_column}")
                
                # 構建查詢條件
                where_conditions = ["Marker = ?"]
                params = [marker]
                
                # ✅ 關鍵修改：使用資料庫的「月份」欄位
                if month and has_month_column:
                    where_conditions.append("月份 = ?")
                    params.append(month)
                    logger.info(f"✅ 使用資料庫月份欄位過濾: {month}")
                elif month and not has_month_column:
                    logger.warning(f"⚠️ 表中沒有「月份」欄位，無法使用月份過濾")
                
                if weekly:
                    where_conditions.append("Weekly = ?")
                    params.append(weekly)
                
                # 構建查詢
                select_fields = ["匹配批號"] + od_fields
                query = f'''
                    SELECT {", ".join(select_fields)}
                    FROM "{table_name}"
                    WHERE {" AND ".join(where_conditions)}
                    ORDER BY 匹配批號
                '''
                
                logger.info(f"SQL: {query}")
                logger.info(f"參數: {params}")
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                # 構建結果
                data = []
                for row in rows:
                    result = {"batch": row[0]}
                    for i, field in enumerate(od_fields, 1):
                        result[field] = float(row[i]) if row[i] is not None else None
                    data.append(result)
                
                logger.info(f"✅ 查詢到 {len(data)} 筆 OD 趨勢數據")
                
                return jsonify({
                    "ok": True,
                    "data": data,
                    "fields": od_fields,
                    "filters": {
                        "year": year,
                        "month": month,
                        "weekly": weekly,
                        "marker": marker
                    }
                })
                
        except Exception as e:
            logger.error(f"❌ 獲取 OD 趨勢數據失敗: {e}")
            logger.error(traceback.format_exc())
            return jsonify({
                "ok": False,
                "error": str(e),
                "data": []
            }), 500

    
    @app.route("/api/beads-ipqc/cv-trend-data", methods=["GET"])
    def get_cv_trend_data():
        """獲取 CV 趨勢數據 - 使用資料庫的月份欄位"""
        try:
            year = request.args.get("year", type=int)
            month = request.args.get("month", type=int)
            weekly = request.args.get("weekly")
            marker = request.args.get("marker")
            
            if not year or not marker:
                return jsonify({
                    "ok": False,
                    "message": "缺少必要參數: year 或 marker"
                }), 400
            
            table_name = f"{year}_IPQC"
            
            if not os.path.exists(BEADS_IPQC_DB_PATH):
                return jsonify({
                    "ok": False,
                    "message": "資料庫不存在",
                    "data": []
                }), 404
            
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                )
                if not cursor.fetchone():
                    return jsonify({
                        "ok": True,
                        "data": [],
                        "message": f"表 {table_name} 不存在"
                    })
                
                # 動態檢查欄位
                available_columns = get_table_columns(cursor, table_name)
                
                # 檢查是否有「月份」欄位
                has_month_column = '月份' in available_columns
                
                possible_cv_fields = ['L1_CV', 'L2_CV', 'N1_CV', 'N3_CV']
                cv_fields = [field for field in possible_cv_fields if field in available_columns]
                
                if not cv_fields:
                    logger.warning(f"⚠️ 表 {table_name} 中沒有找到任何 CV 欄位")
                    return jsonify({
                        "ok": True,
                        "data": [],
                        "message": f"表 {table_name} 中沒有 CV 欄位"
                    })
                
                logger.info(f"✅ {table_name} 可用 CV 欄位: {cv_fields}")
                logger.info(f"✅ 月份欄位存在: {has_month_column}")
                
                # 構建查詢條件
                where_conditions = ["Marker = ?"]
                params = [marker]
                
                # ✅ 關鍵修改：使用資料庫的「月份」欄位
                if month and has_month_column:
                    where_conditions.append("月份 = ?")
                    params.append(month)
                    logger.info(f"✅ 使用資料庫月份欄位過濾: {month}")
                elif month and not has_month_column:
                    logger.warning(f"⚠️ 表中沒有「月份」欄位，無法使用月份過濾")
                
                if weekly:
                    where_conditions.append("Weekly = ?")
                    params.append(weekly)
                
                # 構建查詢
                select_fields = ["匹配批號"] + cv_fields
                query = f'''
                    SELECT {", ".join(select_fields)}
                    FROM "{table_name}"
                    WHERE {" AND ".join(where_conditions)}
                    ORDER BY 匹配批號
                '''
                
                logger.info(f"SQL: {query}")
                logger.info(f"參數: {params}")
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                # 構建結果
                data = []
                for row in rows:
                    result = {"batch": row[0]}
                    for i, field in enumerate(cv_fields, 1):
                        result[field] = float(row[i]) if row[i] is not None else None
                    data.append(result)
                
                logger.info(f"✅ 查詢到 {len(data)} 筆 CV 趨勢數據")
                
                return jsonify({
                    "ok": True,
                    "data": data,
                    "fields": cv_fields,
                    "filters": {
                        "year": year,
                        "month": month,
                        "weekly": weekly,
                        "marker": marker
                    }
                })
                
        except Exception as e:
            logger.error(f"❌ 獲取 CV 趨勢數據失敗: {e}")
            logger.error(traceback.format_exc())
            return jsonify({
                "ok": False,
                "error": str(e),
                "data": []
            }), 500

    
    @app.route("/api/beads-ipqc/test-db", methods=["GET"])
    def test_beads_ipqc_db():
        """測試 Beads IPQC 資料庫連線和結構"""
        try:
            if not os.path.exists(BEADS_IPQC_DB_PATH):
                return jsonify({
                    "ok": False,
                    "message": f"資料庫不存在: {BEADS_IPQC_DB_PATH}"
                }), 404
            
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                
                table_info = {}
                for table in tables:
                    cursor.execute(f'PRAGMA table_info("{table}")')
                    columns = cursor.fetchall()
                    
                    cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                    row_count = cursor.fetchone()[0]
                    
                    table_info[table] = {
                        "columns": [col[1] for col in columns],
                        "column_details": columns,
                        "row_count": row_count
                    }
                
                return jsonify({
                    "ok": True,
                    "database_path": BEADS_IPQC_DB_PATH,
                    "tables": tables,
                    "table_info": table_info
                })
                
        except Exception as e:
            logger.error(f"❌ 測試資料庫失敗: {e}")
            logger.error(traceback.format_exc())
            return jsonify({
                "ok": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }), 500
    
    logger.info("✅ Beads IPQC 路由已註冊（使用資料庫月份欄位）")