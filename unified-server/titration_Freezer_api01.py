from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

app = Flask(__name__)
# 啟用 CORS，允許所有來源呼叫 (開發環境方便)，或指定 React 的 URL
CORS(app)

# =================設定區=================
# 使用 raw string (r"") 避免路徑反斜線問題
SCHEDULE_DB_PATH = "/opt/beadsops/data/P01_formualte_schedule.db"
RECORD_DB_PATH = "/opt/beadsops/data/work_orders.db"
API_PORT = 5001  # 設定獨立的 Port，避免與主程式衝突
# =======================================

# 定義機台列表 (Port 1~12 + IVEK = 13台)
MACHINES = [f"Port-{str(i).zfill(2)}" for i in range(1, 13)] + ["IVEK"]

def get_db_connection(db_path):
    # 設定 timeout 防止網路磁碟機鎖定
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

# 🟢 新增：日期變體產生器
def get_date_variants(date_obj):
    """
    輸入 datetime 物件，回傳三種常見的日期字串格式列表。
    例如輸入 2026年1月19日：
    1. '2026/01/19' (標準補零)
    2. '2026/1/19'  (Excel常見，不補零)
    3. '2026-01-19' (ISO 格式)
    """
    return [
        date_obj.strftime('%Y/%m/%d'),           # 2026/01/19
        f"{date_obj.year}/{date_obj.month}/{date_obj.day}", # 2026/1/19
        date_obj.strftime('%Y-%m-%d')            # 2026-01-19
    ]

@app.route('/api/titration/stats', methods=['GET'])
def get_titration_stats():
    # 1. 取得查詢日期 (預設昨日)
    default_date = (datetime.now() - timedelta(days=1)).strftime('%Y/%m/%d')
    target_date_str = request.args.get('date', default_date)
    
    # 用於儲存要查詢的所有日期格式
    search_dates = []
    display_date = target_date_str # 用於 print 顯示

    try:
        clean_date_str = target_date_str.strip()
        
        # 解析日期
        if '-' in clean_date_str:
            dt_obj = datetime.strptime(clean_date_str, '%Y-%m-%d')
        else:
            dt_obj = datetime.strptime(clean_date_str, '%Y/%m/%d')
            
        # 🟢 產生三種格式的日期列表
        search_dates = get_date_variants(dt_obj)
        # 去除重複 (例如 10月10日時，補零與不補零是一樣的)
        search_dates = list(set(search_dates))
        
        display_date = dt_obj.strftime('%Y/%m/%d')
        
    except ValueError:
        return jsonify({"ok": False, "error": f"日期格式錯誤: {target_date_str}"}), 400
    
    stats_data = []
    total_usage_hours = 0
    in_use_count = 0
    
    try:
        print(f"正在查詢日期 (包含變體): {search_dates}")

        # 🟢 動態產生 SQL 佔位符 (?,?,?)
        placeholders = ','.join(['?'] * len(search_dates))

        # --- 步驟 A: 從排程表 (Schedule) 找出當日工單 ---
        with get_db_connection(SCHEDULE_DB_PATH) as conn_sch:
            # 修改為 IN 查詢
            query_sch = f"SELECT WorkOrder, Pump FROM DropletSchedule WHERE Date IN ({placeholders})"
            # params 必須是 tuple
            df_sch = pd.read_sql_query(query_sch, conn_sch, params=tuple(search_dates))
        
        # --- 步驟 B: 從紀錄表 (Record) 找出工單的時間 ---
        with get_db_connection(RECORD_DB_PATH) as conn_rec:
            # 檢查並建立欄位
            try:
                conn_rec.execute("SELECT `滴定機閒置時間(hrs)` FROM work_orders LIMIT 1")
            except sqlite3.OperationalError:
                print("欄位不存在，正在新增 '滴定機閒置時間(hrs)'...")
                conn_rec.execute("ALTER TABLE work_orders ADD COLUMN `滴定機閒置時間(hrs)` REAL")
                conn_rec.commit()

            # 修改為 IN 查詢
            query_rec = f"""
            SELECT "工單號" as WorkOrder, "日期", "時間_滴定準備", "時間_滴定結束" 
            FROM work_orders 
            WHERE "日期" IN ({placeholders})
            """
            df_rec = pd.read_sql_query(query_rec, conn_rec, params=tuple(search_dates))

       # --- 步驟 C: 資料合併與計算 ---
        if not df_sch.empty and not df_rec.empty:
            merged_df = pd.merge(df_sch, df_rec, on="WorkOrder", how="inner")
        else:
            merged_df = pd.DataFrame(columns=["Pump", "WorkOrder", "時間_滴定準備", "時間_滴定結束"])

        # 初始化每台機器的統計
        machine_stats = {m: {"usage_sec": 0, "status": "Idle"} for m in MACHINES}

        # 計算每張工單的使用時間
        for index, row in merged_df.iterrows():
            pump_raw = row['Pump']
            start_str = row['時間_滴定準備']
            end_str = row['時間_滴定結束']
            
            # 正規化機台名稱
            pump_name = pump_raw
            if pump_raw and "Port" in str(pump_raw): # 修正：加 str() 防止 None 報錯
                try:
                    p_num = int(''.join(filter(str.isdigit, str(pump_raw))))
                    pump_name = f"Port-{str(p_num).zfill(2)}"
                except:
                    pass
            
            # IVEK 處理
            if "IVEK" in str(pump_raw).upper():
                pump_name = "IVEK"

            if pump_name not in machine_stats:
                continue

            # 狀態判斷與時間計算
            if start_str and (not end_str or str(end_str).strip() == ""):
                machine_stats[pump_name]["status"] = "Running"
                in_use_count += 1
            elif start_str and end_str:
                try:
                    fmt_list = ['%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M:%S']
                    t_start = None
                    t_end = None
                    
                    for fmt in fmt_list:
                        try:
                            t_start = datetime.strptime(str(start_str), fmt)
                            break
                        except ValueError: continue
                            
                    for fmt in fmt_list:
                        try:
                            t_end = datetime.strptime(str(end_str), fmt)
                            break
                        except ValueError: continue

                    if t_start and t_end:
                        duration = (t_end - t_start).total_seconds()
                        if duration > 0:
                            machine_stats[pump_name]["usage_sec"] += duration
                except Exception as e:
                    print(f"Time parse error for {row['WorkOrder']}: {e}")

        # --- 步驟 D: 彙整最終數據 ---
        AVAILABLE_HOURS = 15.0
        updates_for_db = [] 

        for machine in MACHINES:
            usage_hours = machine_stats[machine]["usage_sec"] / 3600
            total_usage_hours += usage_hours
            
            idle_hours = max(0, AVAILABLE_HOURS - usage_hours)
            utilization_rate = (usage_hours / AVAILABLE_HOURS) * 100

            stats_data.append({
                "name": machine,
                "utilization": round(utilization_rate, 1),
                "idleHours": round(idle_hours, 1),
                "status": machine_stats[machine]["status"]
            })
            
            # 準備寫回資料
            for idx, row in merged_df.iterrows():
                p_raw = row['Pump']
                current_p_name = p_raw
                if "Port" in str(p_raw):
                      try:
                        num = int(''.join(filter(str.isdigit, str(p_raw))))
                        current_p_name = f"Port-{str(num).zfill(2)}"
                      except: pass
                elif "IVEK" in str(p_raw).upper():
                    current_p_name = "IVEK"

                if current_p_name == machine:
                    updates_for_db.append((round(idle_hours, 1), row['WorkOrder']))

        # --- 步驟 E: 寫回資料庫 ---
        if updates_for_db:
            print(f"正在更新 {len(updates_for_db)} 筆工單的閒置時間...")
            with get_db_connection(RECORD_DB_PATH) as conn_rec:
                conn_rec.executemany(
                    "UPDATE work_orders SET `滴定機閒置時間(hrs)` = ? WHERE \"工單號\" = ?",
                    updates_for_db
                )
                conn_rec.commit()
            print("更新完成。")

        # 計算當日不重複工單數
        daily_batches = 0
        if not df_rec.empty:
            daily_batches = int(df_rec['WorkOrder'].nunique())

        # 計算 KPI
        avg_utilization = sum([d['utilization'] for d in stats_data]) / 13
        
        return jsonify({
            "ok": True,
            "data": stats_data,
            "kpi": {
                "total_machines": 13,
                "avg_utilization": round(avg_utilization, 1),
                "in_use_count": in_use_count,
                "daily_batches": daily_batches
            }
        })

    except Exception as e:
        print(f"API Error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500
    
@app.route('/api/titration/period_stats', methods=['GET'])
def get_period_stats():
    # 設定基準日為昨天
    yesterday = datetime.now() - timedelta(days=1)
    
    def calculate_split_stats(days_back):
        start_date = yesterday - timedelta(days=days_back-1)
        start_str = start_date.strftime('%Y/%m/%d')
        end_str = yesterday.strftime('%Y/%m/%d')
        
        try:
            # 1. 撈取區間排程
            with get_db_connection(SCHEDULE_DB_PATH) as conn_sch:
                query_sch = f"SELECT WorkOrder, Pump FROM DropletSchedule WHERE Date BETWEEN ? AND ?"
                df_sch = pd.read_sql_query(query_sch, conn_sch, params=(start_str, end_str))
                
            # 2. 撈取區間紀錄
            with get_db_connection(RECORD_DB_PATH) as conn_rec:
                query_rec = f"""
                SELECT "工單號" as WorkOrder, "日期", "時間_滴定準備", "時間_滴定結束" 
                FROM work_orders 
                WHERE "日期" BETWEEN ? AND ?
                """
                df_rec = pd.read_sql_query(query_rec, conn_rec, params=(start_str, end_str))

            if df_sch.empty or df_rec.empty:
                return {
                    "ports": {"util": 0, "idle": 15},
                    "ivek": {"util": 0, "idle": 15},
                    "active_days": 0
                }

            # 合併資料
            merged_df = pd.merge(df_sch, df_rec, on="WorkOrder", how="inner")
            
            # 🔴 重點 1: 計算「有效工作天數」 (不重複的日期數)
            # 只有實際有生產紀錄的日期才算入分母
            active_days = merged_df['日期'].nunique()
            if active_days == 0:
                active_days = 1 # 避免除以零 (雖前面判斷過 empty，防呆)

            # 初始化累積秒數
            total_sec_ports = 0
            total_sec_ivek = 0
            
            # 遍歷計算工時
            for _, row in merged_df.iterrows():
                pump_raw = str(row['Pump']).upper()
                
                # 計算單張工單時長
                duration = 0
                start_str_time = row['時間_滴定準備']
                end_str_time = row['時間_滴定結束']
                
                if start_str_time and end_str_time:
                    try:
                        fmt_list = ['%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M:%S']
                        t_start, t_end = None, None
                        for fmt in fmt_list:
                            try:
                                if not t_start: t_start = datetime.strptime(str(start_str_time), fmt)
                            except: pass
                            try:
                                if not t_end: t_end = datetime.strptime(str(end_str_time), fmt)
                            except: pass
                            
                            if t_start and t_end:
                                d = (t_end - t_start).total_seconds()
                                if d > 0: duration = d
                    except: pass
                
                # 🔴 重點 2: 分類累加 (Ports vs IVEK)
                if "IVEK" in pump_raw:
                    total_sec_ivek += duration
                elif "PORT" in pump_raw:
                    total_sec_ports += duration

            # 🔴 重點 3: 計算平均值
            # 每日可用 15 小時 (秒數 = 15 * 3600 = 54000)
            DAILY_SEC = 15.0 * 3600
            
            # Ports (12台)
            # 平均稼動 = 總秒數 / (12台 * 有效天數 * 每日秒數)
            ports_capacity = 12 * active_days * DAILY_SEC
            ports_util = (total_sec_ports / ports_capacity) * 100 if ports_capacity > 0 else 0
            # 平均閒置 = 15小時 - (總秒數 / 3600 / 12台 / 有效天數)
            ports_avg_usage_hours = (total_sec_ports / 3600) / (12 * active_days)
            ports_idle = max(0, 15.0 - ports_avg_usage_hours)

            # IVEK (1台)
            ivek_capacity = 1 * active_days * DAILY_SEC
            ivek_util = (total_sec_ivek / ivek_capacity) * 100 if ivek_capacity > 0 else 0
            ivek_avg_usage_hours = (total_sec_ivek / 3600) / (1 * active_days)
            ivek_idle = max(0, 15.0 - ivek_avg_usage_hours)

            return {
                "active_days": active_days,
                "ports": {
                    "util": round(ports_util, 1),
                    "idle": round(ports_idle, 1)
                },
                "ivek": {
                    "util": round(ivek_util, 1),
                    "idle": round(ivek_idle, 1)
                }
            }
            
        except Exception as e:
            print(f"Period stats error: {e}")
            return {
                "ports": {"util": 0, "idle": 0},
                "ivek": {"util": 0, "idle": 0},
                "active_days": 0
            }

    return jsonify({
        "ok": True,
        "weekly": calculate_split_stats(7),
        "monthly": calculate_split_stats(30)
    })

if __name__ == '__main__':
    print(f"🚀 Titration Statistics Service running on port {API_PORT}...")
    # debug=True 方便開發時看到錯誤訊息，host='0.0.0.0' 允許區網訪問
    app.run(debug=True, port=API_PORT, host='0.0.0.0')