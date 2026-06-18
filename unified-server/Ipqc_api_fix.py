# ====================================================================
# ====== IPQC 表單專用 API (完整修復版) ======
# ====================================================================
# 問題診斷與修復清單：
# 1. ✅ DATE() 函數語法錯誤 → 改用字串比較
# 2. ✅ 日期格式混亂 (YYYY/MM/DD vs YYYY-MM-DD) → 統一轉換
# 3. ✅ 欄位名稱不一致 → 使用更靈活的欄位偵測
# 4. ✅ 缺少錯誤處理 → 加入 try-catch 與日誌
# 5. ✅ SQL 注入風險 → 使用參數化查詢
# ====================================================================

import logging
import sqlite3
import os
from datetime import datetime
from flask import request, jsonify

logger = logging.getLogger('IPQC_API')

# 輔助函式：取得所有 IPQC 資料表名稱
def get_all_ipqc_tables(cursor):
    """取得資料庫中所有 YYYY_IPQC 格式的資料表，並由新到舊排序"""
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        # 篩選出格式為 "YYYY_IPQC" 的表 (例如 2025_IPQC, 2026_IPQC)
        ipqc_tables = [t for t in tables if t.endswith("_IPQC")]
        # 排序：由新到舊
        ipqc_tables.sort(reverse=True)
        logger.info(f"✅ 找到 {len(ipqc_tables)} 個 IPQC 表: {ipqc_tables}")
        return ipqc_tables
    except Exception as e:
        logger.error(f"❌ 取得 IPQC 表清單失敗: {e}")
        return []

def normalize_date_str(date_str):
    """
    將日期字串統一轉為 YYYY-MM-DD 格式
    支援: YYYY-MM-DD, YYYY/MM/DD, YYYYMMDD
    """
    if not date_str or not str(date_str).strip():
        return None
    
    s = str(date_str).strip()
    
    # 嘗試多種格式
    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y.%m.%d"]:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except:
            continue
    
    logger.warning(f"⚠️ 日期格式無法解析: {date_str}")
    return None

def find_column(columns, *possible_names):
    """從可能的欄位名列表中找到實際存在的欄位"""
    for name in possible_names:
        if name in columns:
            return name
    return None

# ====================================================================
# API 1: 取得篩選選項
# ====================================================================

def api_get_options_impl(ipqc_db_path):
    """
    取得篩選選項 (Marker 與 併批狀態)
    邏輯：掃描所有 IPQC 資料表，合併去重後回傳給前端下拉選單使用
    """
    response_data = {"makers": [], "batch_options": []}

    if not os.path.exists(ipqc_db_path):
        logger.warning(f"❌ IPQC DB 路徑不存在: {ipqc_db_path}")
        return response_data

    try:
        with sqlite3.connect(ipqc_db_path) as conn:
            cursor = conn.cursor()
            
            # 1. 取得所有 IPQC 資料表
            tables = get_all_ipqc_tables(cursor)
            
            if not tables:
                logger.warning("❌ 沒有找到任何 IPQC 資料表")
                return response_data

            all_markers = set()
            all_batches = set()

            # 2. 迴圈掃描每一張表
            for table in tables:
                try:
                    # 取得該表的欄位
                    cursor.execute(f'PRAGMA table_info("{table}")')
                    columns_info = cursor.fetchall()
                    column_names = {row[1] for row in columns_info}
                    
                    logger.debug(f"📋 表 {table} 的欄位: {column_names}")

                    # --- 找 Marker 欄位 (相容不同命名) ---
                    marker_col = find_column(
                        column_names,
                        'Marker', 'marker', 'Maker', 'maker',
                        '廠商', '牌號', '品牌'
                    )
                    
                    if marker_col:
                        try:
                            cursor.execute(f'SELECT DISTINCT "{marker_col}" FROM "{table}" WHERE "{marker_col}" IS NOT NULL AND "{marker_col}" != ""')
                            for r in cursor.fetchall():
                                val = str(r[0]).strip() if r[0] else ""
                                if val and val not in ["None", "null"]:
                                    all_markers.add(val)
                            logger.debug(f"   ✅ 從 {table} 取得 {len(all_markers)} 個 Marker")
                        except Exception as e:
                            logger.warning(f"   ⚠️ 讀取 {marker_col} 欄位失敗: {e}")

                    # --- 找 併批 欄位 ---
                    batch_col = find_column(
                        column_names,
                        '併批', '批號', 'Batch', 'batch',
                        '批處理', 'Batch_Number'
                    )
                    
                    if batch_col:
                        try:
                            cursor.execute(f'SELECT DISTINCT "{batch_col}" FROM "{table}" WHERE "{batch_col}" IS NOT NULL AND "{batch_col}" != ""')
                            for r in cursor.fetchall():
                                val = str(r[0]).strip() if r[0] else ""
                                if val and val not in ["None", "null"]:
                                    all_batches.add(val)
                            logger.debug(f"   ✅ 從 {table} 取得 {len(all_batches)} 個併批狀態")
                        except Exception as e:
                            logger.warning(f"   ⚠️ 讀取 {batch_col} 欄位失敗: {e}")

                except Exception as table_err:
                    logger.warning(f"❌ 讀取表 {table} 時錯誤: {table_err}")
                    continue

            # 3. 轉換回 List 並排序
            response_data["makers"] = sorted(list(all_markers))
            response_data["batch_options"] = sorted(list(all_batches))
            
            logger.info(f"✅ 選項取得成功: {len(response_data['makers'])} 個 Marker, {len(response_data['batch_options'])} 個批狀態")
            return response_data

    except Exception as e:
        logger.error(f"❌ 取得選項失敗: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return response_data

# ====================================================================
# API 2: 主要查詢
# ====================================================================

def api_get_qc_table_impl(ipqc_db_path):
    """
    主要查詢 API (跨年度搜尋)
    根據前端傳來的條件，搜尋所有年份的 IPQC 表並回傳結果
    """
    logger.info("=" * 60)
    logger.info("🔍 IPQC 查詢開始")
    
    # 取得前端參數
    marker = request.args.get("marker", "").strip()
    prod_start = request.args.get("prod_start", "").strip()
    prod_end = request.args.get("prod_end", "").strip()
    insp_start = request.args.get("insp_start", "").strip()
    insp_end = request.args.get("insp_end", "").strip()
    batchable = request.args.get("batchable", "").strip()
    
    logger.info(f"📋 查詢條件:")
    logger.info(f"   - Marker: {marker or '(無)'}")
    logger.info(f"   - 生產日: {prod_start} ~ {prod_end}")
    logger.info(f"   - 檢驗日: {insp_start} ~ {insp_end}")
    logger.info(f"   - 併批: {batchable or '(無)'}")
    
    if not os.path.exists(ipqc_db_path):
        logger.error(f"❌ IPQC DB 不存在: {ipqc_db_path}")
        return []

    final_results = []

    try:
        with sqlite3.connect(ipqc_db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 1. 取得所有年份資料表
            tables = get_all_ipqc_tables(cursor)
            
            if not tables:
                logger.warning("⚠️ 沒有找到任何 IPQC 表")
                return []
            
            # 2. 迴圈查詢每一個表
            for table_name in tables:
                logger.info(f"📊 查詢表: {table_name}")
                
                try:
                    # 取得該表的欄位結構
                    cursor.execute(f'PRAGMA table_info("{table_name}")')
                    columns_info = cursor.fetchall()
                    column_names = {row[1] for row in columns_info}
                    
                    logger.debug(f"   欄位數: {len(column_names)}")

                    # ========== 欄位偵測 ==========
                    
                    # 生產日欄位
                    prod_col = find_column(
                        column_names,
                        'dD生產日', '生產日', 'ProductionDate', 
                        'prod_date', '製造日期'
                    )
                    
                    # 檢驗日欄位
                    insp_col = find_column(
                        column_names,
                        '檢驗日期', '驗收日期', 'InspectionDate',
                        'insp_date', '檢測日期'
                    )
                    
                    # Marker 欄位
                    marker_col = find_column(
                        column_names,
                        'Marker', 'marker', 'Maker', 'maker',
                        '廠商', '牌號', '品牌'
                    )
                    
                    # 併批欄位
                    batch_col = find_column(
                        column_names,
                        '併批', '批號', 'Batch', 'batch',
                        '批處理', 'Batch_Number'
                    )

                    logger.debug(f"   欄位對應:")
                    logger.debug(f"      生產日: {prod_col}")
                    logger.debug(f"      檢驗日: {insp_col}")
                    logger.debug(f"      Marker: {marker_col}")
                    logger.debug(f"      併批: {batch_col}")

                    # 如果連基本欄位都沒有，跳過
                    if not prod_col and not insp_col:
                        logger.warning(f"   ⚠️ 跳過: 缺少生產日或檢驗日欄位")
                        continue

                    # ========== 組建查詢 ==========
                    
                    query_parts = [f'SELECT *']
                    where_parts = []
                    params = []

                    # --- 條件 1: Marker ---
                    if marker and marker_col:
                        where_parts.append(f'"{marker_col}" = ?')
                        params.append(marker)
                        logger.debug(f"   + Marker 篩選: {marker}")

                    # --- 條件 2: 生產日範圍 ---
                    if prod_col:
                        # 轉換參數格式
                        norm_prod_start = normalize_date_str(prod_start) if prod_start else None
                        norm_prod_end = normalize_date_str(prod_end) if prod_end else None
                        
                        if norm_prod_start and norm_prod_end:
                            # 將 DB 欄位轉為標準格式後比較
                            where_parts.append(f'REPLACE("{prod_col}", "/", "-") >= ? AND REPLACE("{prod_col}", "/", "-") <= ?')
                            params.extend([norm_prod_start, norm_prod_end])
                            logger.debug(f"   + 生產日範圍: {norm_prod_start} ~ {norm_prod_end}")
                        elif norm_prod_start:
                            where_parts.append(f'REPLACE("{prod_col}", "/", "-") >= ?')
                            params.append(norm_prod_start)
                            logger.debug(f"   + 生產日開始: {norm_prod_start}")

                    # --- 條件 3: 檢驗日範圍 ---
                    if insp_col:
                        norm_insp_start = normalize_date_str(insp_start) if insp_start else None
                        norm_insp_end = normalize_date_str(insp_end) if insp_end else None
                        
                        if norm_insp_start and norm_insp_end:
                            where_parts.append(f'REPLACE("{insp_col}", "/", "-") >= ? AND REPLACE("{insp_col}", "/", "-") <= ?')
                            params.extend([norm_insp_start, norm_insp_end])
                            logger.debug(f"   + 檢驗日範圍: {norm_insp_start} ~ {norm_insp_end}")
                        elif norm_insp_start:
                            where_parts.append(f'REPLACE("{insp_col}", "/", "-") >= ?')
                            params.append(norm_insp_start)
                            logger.debug(f"   + 檢驗日開始: {norm_insp_start}")

                    # --- 條件 4: 併批 ---
                    if batchable and batch_col:
                        where_parts.append(f'"{batch_col}" = ?')
                        params.append(batchable)
                        logger.debug(f"   + 併批篩選: {batchable}")

                    # 組合最終 SQL
                    final_sql = f'SELECT * FROM "{table_name}"'
                    if where_parts:
                        final_sql += ' WHERE ' + ' AND '.join(where_parts)

                    logger.debug(f"   🔧 SQL: {final_sql}")
                    logger.debug(f"   📌 參數: {params}")

                    # 執行查詢
                    cursor.execute(final_sql, params)
                    rows = cursor.fetchall()
                    
                    table_results = [dict(row) for row in rows]
                    final_results.extend(table_results)
                    
                    logger.info(f"   ✅ 找到 {len(table_results)} 筆資料")

                except Exception as e:
                    logger.error(f"   ❌ 查詢表 {table_name} 時發生錯誤: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    continue

            # 3. 排序 (由新到舊，嘗試多個日期欄位)
            def sort_key(item):
                for key in ['dD生產日', '生產日', 'ProductionDate', '檢驗日期', '驗收日期']:
                    if key in item and item[key]:
                        return str(item[key])
                return ""
            
            final_results.sort(key=sort_key, reverse=True)
            
            logger.info(f"=" * 60)
            logger.info(f"✅ 總計找到 {len(final_results)} 筆資料")
            logger.info(f"=" * 60)
            
            # 限制回傳筆數 (防止前端炸裂，最多 2000 筆)
            if len(final_results) > 2000:
                logger.warning(f"⚠️ 結果超過 2000 筆，僅返回前 2000 筆")
                final_results = final_results[:2000]
            
            return final_results

    except Exception as e:
        logger.error(f"❌ 跨年度查詢失敗: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []

# ====================================================================
# Flask 路由包裝
# ====================================================================

def register_ipqc_routes(app, ipqc_db_path):
    """
    將 IPQC API 路由註冊到 Flask App
    
    使用方式:
    ```python
    from ipqc_api_fix import register_ipqc_routes
    
    IPQC_DB_PATH = r"D:\OneDrive - ...\Beads_QC\資料庫\P01_Beads_IPQC.db"
    register_ipqc_routes(app, IPQC_DB_PATH)
    ```
    """
    
    @app.route("/api/options", methods=["GET"])
    def api_get_options():
        try:
            result = api_get_options_impl(ipqc_db_path)
            return jsonify(result)
        except Exception as e:
            logger.error(f"❌ API /api/options 異常: {e}")
            return jsonify({"makers": [], "batch_options": [], "error": str(e)}), 500

    @app.route("/api/qc_table", methods=["GET"])
    def api_get_qc_table():
        try:
            result = api_get_qc_table_impl(ipqc_db_path)
            return jsonify(result)
        except Exception as e:
            logger.error(f"❌ API /api/qc_table 異常: {e}")
            return jsonify({"error": str(e), "data": []}), 500
    
    logger.info(f"✅ IPQC API 路由已註冊")
    logger.info(f"   📍 /api/options - 取得下拉選項")
    logger.info(f"   📍 /api/qc_table - 查詢資料 (支援日期、Marker、併批篩選)")

if __name__ == "__main__":
    print("這是一個模組，請在 main.py 中匯入使用")