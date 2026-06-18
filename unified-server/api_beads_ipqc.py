"""
Beads IPQC 獨立 API 後端
可以直接運行，不需要整合到現有 Flask app

使用方法:
1. 確認資料庫路徑正確
2. 執行: python standalone_beads_ipqc_api.py
3. API 將運行在 http://localhost:5000
"""

import os
import sqlite3
import traceback
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging

# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 創建 Flask app
app = Flask(__name__)
CORS(app)  # 允許跨域請求

# ✅ Beads IPQC 資料庫路徑
BEADS_IPQC_DB_PATH = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Beads_QC\資料庫\P01_Beads_IPQC.db"


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
            
            # 獲取所有表名
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            # 提取年份
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
            
            query = f"SELECT DISTINCT Weekly FROM {table_name} WHERE Weekly IS NOT NULL ORDER BY Weekly"
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
            
            query = f"SELECT DISTINCT Marker FROM {table_name} WHERE Marker IS NOT NULL ORDER BY Marker"
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
    """獲取 OD 趨勢數據"""
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
            
            where_conditions = ["Marker = ?"]
            params = [marker]
            
            if month:
                where_conditions.append("CAST(substr(匹配批號, 5, 2) AS INTEGER) = ?")
                params.append(month)
            
            if weekly:
                where_conditions.append("Weekly = ?")
                params.append(weekly)
            
            query = f'''
                SELECT 
                    匹配批號,
                    L1_Mean_OD,
                    L2_Mean_OD,
                    N1_OD,
                    N3_OD
                FROM {table_name}
                WHERE {" AND ".join(where_conditions)}
                ORDER BY 匹配批號
            '''
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            data = []
            for row in rows:
                data.append({
                    "batch": row[0],
                    "L1_Mean_OD": float(row[1]) if row[1] is not None else None,
                    "L2_Mean_OD": float(row[2]) if row[2] is not None else None,
                    "N1_OD": float(row[3]) if row[3] is not None else None,
                    "N3_OD": float(row[4]) if row[4] is not None else None,
                })
            
            logger.info(f"✅ 查詢到 {len(data)} 筆 OD 趨勢數據")
            
            return jsonify({
                "ok": True,
                "data": data,
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
    """獲取 CV 趨勢數據"""
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
            
            where_conditions = ["Marker = ?"]
            params = [marker]
            
            if month:
                where_conditions.append("CAST(substr(匹配批號, 5, 2) AS INTEGER) = ?")
                params.append(month)
            
            if weekly:
                where_conditions.append("Weekly = ?")
                params.append(weekly)
            
            query = f'''
                SELECT 
                    匹配批號,
                    L1_CV,
                    L2_CV,
                    N1_CV,
                    N3_CV
                FROM {table_name}
                WHERE {" AND ".join(where_conditions)}
                ORDER BY 匹配批號
            '''
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            data = []
            for row in rows:
                data.append({
                    "batch": row[0],
                    "L1_CV": float(row[1]) if row[1] is not None else None,
                    "L2_CV": float(row[2]) if row[2] is not None else None,
                    "N1_CV": float(row[3]) if row[3] is not None else None,
                    "N3_CV": float(row[4]) if row[4] is not None else None,
                })
            
            logger.info(f"✅ 查詢到 {len(data)} 筆 CV 趨勢數據")
            
            return jsonify({
                "ok": True,
                "data": data,
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
                cursor.execute(f"PRAGMA table_info({table})")
                columns = cursor.fetchall()
                
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
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


@app.route("/", methods=["GET"])
def index():
    """根路由 - 顯示 API 資訊"""
    return jsonify({
        "name": "Beads IPQC API",
        "version": "1.0",
        "status": "running",
        "endpoints": [
            "/api/beads-ipqc/available-years",
            "/api/beads-ipqc/weekly-list",
            "/api/beads-ipqc/marker-list",
            "/api/beads-ipqc/od-trend-data",
            "/api/beads-ipqc/cv-trend-data",
            "/api/beads-ipqc/test-db"
        ]
    })


if __name__ == "__main__":
    # 啟動時檢查資料庫
    logger.info("=" * 60)
    logger.info("🚀 Beads IPQC 獨立 API 啟動中...")
    logger.info(f"📂 資料庫路徑: {BEADS_IPQC_DB_PATH}")
    
    if os.path.exists(BEADS_IPQC_DB_PATH):
        logger.info("✅ 資料庫檔案存在")
        try:
            with sqlite3.connect(BEADS_IPQC_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                logger.info(f"✅ 可用資料表: {tables}")
        except Exception as e:
            logger.error(f"❌ 資料庫檢查失敗: {e}")
    else:
        logger.warning(f"⚠️ 資料庫檔案不存在: {BEADS_IPQC_DB_PATH}")
        logger.warning("⚠️ 請確認路徑是否正確")
    
    logger.info("=" * 60)
    logger.info("🌐 API 運行在: http://localhost:5000")
    logger.info("🔧 測試 API: curl http://localhost:5000/api/beads-ipqc/test-db")
    logger.info("=" * 60)
    
    # 在不同的端口運行，避免與現有 Flask app 衝突
    app.run(host="0.0.0.0", port=5000, debug=True)