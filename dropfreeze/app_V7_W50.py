from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
from pathlib import Path
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from PIL import Image
import re
from waitress import serve
import threading
import shutil
import pandas as pd  # ⚠️ 必須引用 pandas，否則同步會失敗

app = Flask(__name__)
CORS(app)

# === Configuration ===
DB_TIMEOUT = 5.0
ADMIN_PIN = "36121288"

# === Database Paths ===
# 1. Schedule & 5714 DB (排程來源)
DB_SCHEDULE = r"D:\配藥表\資料庫\P01_formualte_schedule.db"

# 2. Production Record & Photo DB (紀錄存檔位置)
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"
UPLOAD_FOLDER = Path(r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\Photos")

# Ensure photo directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 本機快取路徑 (加速上傳用)
LOCAL_CACHE_DIR = Path("D:/BeadRecord_Cache") 
os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)

# === Field Definitions ===
QR_FIELDS = [
    "工單號", "製令數量", "bead_name", "PN", "是否懸浮", "日期",
    "L1_反應_OD", "L1_起始_OD", "L2_反應_OD", "L2_起始_OD",
    "liquid_storge_避光", "liquid_storge_冰浴",
    "滴定_避光", "滴定_冰浴", "滴定_攪拌",
    "Dispense_Lot_1", "port_1", "pump_1", "凍乾機_1",
    "Dispense_Lot_2", "port_2", "pump_2", "凍乾機_2",
    "Dispense_Lot_3", "port_3", "pump_3", "凍乾機_3",
    "Dispense_Lot_4", "port_4", "pump_4", "凍乾機_4",
    "淨重g", "時間_收藥", "時間_滴定準備", "時間_滴定開始",
    "時間_滴定結束", "時間_凍乾準備", "時間_凍乾開始", "時間_凍乾結束",
    "收藥_上傳者", "滴定準備_上傳者", "滴定開始_上傳者",
    "滴定結束_上傳者", "凍乾準備_上傳者", "凍乾開始_上傳者", "凍乾結束_上傳者"
]
PHOTO_FIELDS = [
    "收藥_照片", "滴定準備_照片", "滴定開始_照片",
    "滴定結束_照片", "凍乾準備_照片", "凍乾開始_照片", "凍乾結束_照片"
]
ALL_FIELDS = QR_FIELDS + PHOTO_FIELDS

# === 步驟設定 ===
STEP_CONFIG = {
    'receive':          ('時間_收藥',      '收藥_上傳者',      '收藥_照片'),
    'titration_prep':   ('時間_滴定準備',  '滴定準備_上傳者',  '滴定準備_照片'),
    'titration_start':  ('時間_滴定開始',  '滴定開始_上傳者',  '滴定開始_照片'),
    'titration_end':    ('時間_滴定結束',  '滴定結束_上傳者',  '滴定結束_照片'),
    'fd_prep':          ('時間_凍乾準備',  '凍乾準備_上傳者',  '凍乾準備_照片'),
    'fd_start':         ('時間_凍乾開始',  '凍乾開始_上傳者',  '凍乾開始_照片'),
    'fd_end':           ('時間_凍乾結束',  '凍乾結束_上傳者',  '凍乾結束_照片')
}

# === Helper Functions ===
def get_db_connection():
    return sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT)

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='work_orders'")
        if not cursor.fetchone():
            col_defs = ", ".join([f'"{col}" TEXT' for col in ALL_FIELDS])
            cursor.execute(f"""
                CREATE TABLE work_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    {col_defs}
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_orders_order_no ON work_orders (工單號)")
            print("✅ Database initialized: work_orders table created.")

def init_abnormal_db():
    """ 初始化異常紀錄表格 (Abnormal History) """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 建立基本表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS abnormal_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station TEXT,
                    machine_id TEXT,
                    description TEXT,
                    created_at TEXT,
                    user TEXT
                )
            """)
            
            # 檢查並補足欄位
            cursor.execute(f"PRAGMA table_info(abnormal_history)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'photos' not in columns:
                cursor.execute('ALTER TABLE abnormal_history ADD COLUMN photos TEXT')
                print("⚠️ [DB Upgrade] Added 'photos' column to abnormal_history")
            
            if 'user' not in columns:
                cursor.execute('ALTER TABLE abnormal_history ADD COLUMN user TEXT')
                print("⚠️ [DB Upgrade] Added 'user' column to abnormal_history")

            conn.commit()
            print("✅ Database initialized: abnormal_history table checked.")
    except Exception as e:
        print(f"❌ Init Abnormal DB Failed: {e}")

def background_move_to_nas(local_path, nas_path):
    try:
        shutil.copy2(local_path, nas_path)
        os.remove(local_path)
        print(f"✅ [背景任務] 照片已搬移至 NAS: {nas_path}")
    except Exception as e:
        print(f"❌ [背景任務] 搬移失敗: {e}")

def sync_single_order_logic(target_order_id):
    """
    [補回] 同步單一工單邏輯
    從排程表抓取 Lot, Pump, Freezer, OD, PN 等資訊寫入 work_orders.db
    """
    if not os.path.exists(DB_SCHEDULE):
        print(f"❌ [Sync] 找不到來源資料庫: {DB_SCHEDULE}")
        return

    try:
        conn_src = sqlite3.connect(DB_SCHEDULE)
        cursor_src = conn_src.cursor()
        
        extra_data = {}

        # Phase 1: DropletSchedule
        sql_src = """
            SELECT WorkOrder, Marker, Quantity, Date, Lot, Pump, Lyophilizer 
            FROM DropletSchedule 
            WHERE WorkOrder = ?
        """
        df_src = pd.read_sql(sql_src, conn_src, params=(target_order_id,))
        
        if df_src.empty:
            conn_src.close()
            return

        first_row = df_src.iloc[0]
        marker = first_row['Marker']
        qty = first_row['Quantity']
        date = first_row['Date']
        pump = first_row['Pump']
        lyo = first_row['Lyophilizer']
        
        lots = df_src['Lot'].dropna().tolist()
        lots = [str(x) for x in lots if str(x).strip()]
        lots += [None] * (4 - len(lots))
        
        formatted_freezer = None
        if lyo and str(lyo).strip():
            s_lyo = str(lyo).strip()
            formatted_freezer = f"Freezer {s_lyo.zfill(2)}" if s_lyo.isdigit() else s_lyo

        # Phase 2: 571 Table
        if marker:
            try:
                cursor_src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%571%'")
                tables_571 = [r[0] for r in cursor_src.fetchall()]
                
                target_table_571 = None
                search_marker = str(marker).lower()
                
                for t_name in tables_571:
                    if search_marker in t_name.lower():
                        target_table_571 = t_name
                        break
                
                if target_table_571:
                    sql_571 = f"""
                        SELECT "L1OD", "L2OD", "起始L1OD", "起始L2OD", "總重量"
                        FROM "{target_table_571}"
                        WHERE "工單號碼" = ? LIMIT 1
                    """
                    cursor_src.execute(sql_571, (target_order_id,))
                    row_571 = cursor_src.fetchone()
                    if row_571:
                        extra_data['L1_反應_OD'] = row_571[0]
                        extra_data['L2_反應_OD'] = row_571[1]
                        extra_data['L1_起始_OD'] = row_571[2]
                        extra_data['L2_起始_OD'] = row_571[3]
                        extra_data['淨重g']      = row_571[4]
            except Exception:
                pass

        # Phase 3: Liquid form QC
        found_pn = None
        if marker:
            try:
                sql_qc = 'SELECT "PN", "懸浮物" FROM "Liquid form QC" WHERE LOWER("Marker name") = ? LIMIT 1'
                cursor_src.execute(sql_qc, (marker.lower(),))
                row_qc = cursor_src.fetchone()
                
                if row_qc:
                    found_pn = row_qc[0]
                    suspension_val = row_qc[1]
                    extra_data['PN'] = found_pn
                    is_suspension = "True" if "cloudy" in str(suspension_val).lower() else "False"
                    extra_data['是否懸浮'] = is_suspension
            except Exception:
                pass

        # Phase 4: 滴定條件
        if found_pn:
            try:
                sql_cond = """
                    SELECT "儲存時避光", "儲存時冰浴", "滴定時避光", "滴定時冰浴", "滴定時攪拌"
                    FROM "滴定條件" WHERE "PN" = ? LIMIT 1
                """
                cursor_src.execute(sql_cond, (found_pn,))
                row_cond = cursor_src.fetchone()
                
                if row_cond:
                    def check_cond(val):
                        if val and "no" in str(val).lower():
                            return "False"
                        return "True"

                    extra_data['liquid_storge_避光'] = check_cond(row_cond[0])
                    extra_data['liquid_storge_冰浴'] = check_cond(row_cond[1])
                    extra_data['滴定_避光'] = check_cond(row_cond[2])
                    extra_data['滴定_冰浴'] = check_cond(row_cond[3])
                    extra_data['滴定_攪拌'] = check_cond(row_cond[4])
            except Exception:
                pass

        conn_src.close()

        # Phase 5: Update Target DB
        conn_target = get_db_connection()
        cursor = conn_target.cursor()

        cursor.execute("SELECT id FROM work_orders WHERE 工單號 = ?", (target_order_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO work_orders (工單號) VALUES (?)", (target_order_id,))
            order_db_id = cursor.lastrowid
        else:
            order_db_id = row[0]

        updates = [
            ('bead_name', marker),
            ('製令數量', qty),
            ('日期', date),
            ('port_1', pump), ('port_2', pump), ('port_3', pump), ('port_4', pump),
            ('凍乾機_1', formatted_freezer), ('凍乾機_2', formatted_freezer), 
            ('凍乾機_3', formatted_freezer), ('凍乾機_4', formatted_freezer),
            ('Dispense_Lot_1', lots[0]), ('Dispense_Lot_2', lots[1]), 
            ('Dispense_Lot_3', lots[2]), ('Dispense_Lot_4', lots[3]),
            ('L1_反應_OD', extra_data.get('L1_反應_OD')),
            ('L2_反應_OD', extra_data.get('L2_反應_OD')),
            ('L1_起始_OD', extra_data.get('L1_起始_OD')),
            ('L2_起始_OD', extra_data.get('L2_起始_OD')),
            ('淨重g', extra_data.get('淨重g')),
            ('PN', extra_data.get('PN')),
            ('是否懸浮', extra_data.get('是否懸浮')),
            ('liquid_storge_避光', extra_data.get('liquid_storge_避光')),
            ('liquid_storge_冰浴', extra_data.get('liquid_storge_冰浴')),
            ('滴定_避光', extra_data.get('滴定_避光')),
            ('滴定_冰浴', extra_data.get('滴定_冰浴')),
            ('滴定_攪拌', extra_data.get('滴定_攪拌'))
        ]

        cursor.execute(f"SELECT * FROM work_orders WHERE id = ?", (order_db_id,))
        current_row = cursor.fetchone()
        col_names = [d[0] for d in cursor.description]
        current_data = dict(zip(col_names, current_row))

        final_updates = []
        final_values = []

        for col, new_val in updates:
            curr_val = current_data.get(col)
            is_target_empty = (curr_val is None) or (str(curr_val).strip() == '')
            is_new_valid = (new_val is not None) and (str(new_val).strip() != '')
            
            if is_target_empty and is_new_valid:
                final_updates.append(f'"{col}" = ?')
                final_values.append(str(new_val))

        if final_updates:
            sql = f"UPDATE work_orders SET {', '.join(final_updates)} WHERE id = ?"
            final_values.append(order_db_id)
            cursor.execute(sql, tuple(final_values))
            conn_target.commit()
            print(f"✅ 工單 {target_order_id} 同步完成")
        
        conn_target.close()

    except Exception as e:
        print(f"❌ 同步錯誤: {e}")

# ==================== APIs ====================

# 1. 取得工單列表 (3天 + TMRA/UMRZ 篩選 + IVEK優先排序)
@app.route('/api/mobile/work-orders', methods=['GET'])
def mobile_get_orders():
    try:
        if not os.path.exists(DB_SCHEDULE):
            return jsonify({'ok': False, 'error': f"DB Not Found"}), 500

        today = datetime.now()
        yesterday = today - timedelta(days=1)
        day_before = today - timedelta(days=2) # 3天範圍
        
        target_dates = [
            today.strftime('%Y/%m/%d'),
            yesterday.strftime('%Y/%m/%d'),
            day_before.strftime('%Y/%m/%d')
        ]
        
        sql_params = [f"{d}%" for d in target_dates]

        with sqlite3.connect(DB_SCHEDULE) as conn:
            cursor = conn.cursor()
            date_conditions = " OR ".join(["Date LIKE ?" for _ in sql_params])
            
            sql = f"""
                SELECT WorkOrder, Marker, Date, Pump, DrugGivenAt
                FROM DropletSchedule 
                WHERE WorkOrder IS NOT NULL AND WorkOrder != ''
                AND ({date_conditions})
            """
            cursor.execute(sql, sql_params)
            all_rows = cursor.fetchall()
            
            orders_map = {} 

            for row in all_rows:
                wo, marker, date_str, pump, time_str = row
                
                # 篩選條件
                if not (wo.startswith("TMRA") or wo.startswith("UMRZ")):
                    continue

                pump = str(pump).upper() if pump else ""
                time_str = str(time_str) if time_str else "00:00"
                
                try: hour = int(time_str.split(':')[0])
                except: hour = 0
                is_pm = hour >= 12 

                # 計算權重 (IVEK=0, AM=1xx, PM=2xx)
                sort_score = 999
                if "IVEK" in pump:
                    sort_score = 0
                elif "PORT" in pump:
                    try: port_num = int(re.search(r'\d+', pump).group())
                    except: port_num = 99
                    base_score = 200 if is_pm else 100
                    sort_score = base_score + port_num
                
                if wo not in orders_map:
                    orders_map[wo] = {
                        'work_order': wo,
                        'marker': marker if marker else '',
                        'date': date_str,
                        'best_score': sort_score,
                        'pump_info': pump,
                        'time_info': time_str
                    }
                else:
                    # 保留較高優先級(分數較低)的資訊
                    if sort_score < orders_map[wo]['best_score']:
                        orders_map[wo]['best_score'] = sort_score
                        orders_map[wo]['pump_info'] = pump
                        orders_map[wo]['time_info'] = time_str

            orders_list = list(orders_map.values())

            # 排序：先按權重(小到大)，再按日期(新到舊)
            orders_list.sort(key=lambda x: x['best_score']) 
            orders_list.sort(key=lambda x: x['date'], reverse=True) 

        return jsonify({'ok': True, 'orders': orders_list})
        
    except Exception as e:
        print(f"Fetch Order Error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500

# 2. 權限檢查 & 3. 取得工單狀態
@app.route('/api/mobile/check-access', methods=['GET'])
def mobile_check_access():
    work_order = request.args.get('work_order')
    if not work_order: return jsonify({'ok': False, 'msg': 'Missing Work Order'}), 400
    try:
        with sqlite3.connect(DB_SCHEDULE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%5714%'")
            tables = cursor.fetchall()
            if not tables: return jsonify({'ok': False, 'allowed': False, 'msg': 'No 5714 tables'}), 404

            found_info = None
            for (table_name,) in tables:
                cursor.execute(f"PRAGMA table_info(\"{table_name}\")")
                cols = [c[1] for c in cursor.fetchall()]
                target_col_wo = "工單號碼" if "工單號碼" in cols else ("WorkOrder" if "WorkOrder" in cols else None)
                target_col_date = "試劑配製日期" if "試劑配製日期" in cols else None
                if target_col_wo:
                    select_stmt = f'"{target_col_date}"' if target_col_date else "'Unknown Date'"
                    sql = f'SELECT {select_stmt} FROM "{table_name}" WHERE "{target_col_wo}" = ? LIMIT 1'
                    cursor.execute(sql, (work_order,))
                    row = cursor.fetchone()
                    if row:
                        found_info = { 'table': table_name, 'date': row[0] }
                        break
            if found_info:
                return jsonify({'ok': True, 'allowed': True, 'msg': f"Access Granted", 'meta': found_info})
            else:
                return jsonify({'ok': True, 'allowed': False, 'msg': '5714 Prep not completed'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/mobile/status', methods=['GET'])
def mobile_get_status():
    order = request.args.get('work_order')
    if order:
        # 這裡會用到 sync_single_order_logic，確保它有被定義
        sync_single_order_logic(order)

    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM work_orders WHERE 工單號 = ?", (order,))
            row = cursor.fetchone()
            
            data = dict(row) if row else {}
            
            steps_data = {}
            for step_id, (time_col, user_col, photo_col) in STEP_CONFIG.items():
                time_val = data.get(time_col)
                if time_val:
                    steps_data[step_id] = {
                        'timestamp': time_val,
                        'user': data.get(user_col),
                        'photoName': data.get(photo_col) 
                    }

            freezer_val = data.get('凍乾機_1')
            freezer_plan = freezer_val if freezer_val else "未指定"
            details = data
            details['freezer_plan'] = freezer_plan 

            return jsonify({'ok': True, 'steps': steps_data, 'details': details})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/mobile/update-freezer', methods=['POST'])
def mobile_update_freezer():
    try:
        data = request.get_json()
        order = data.get('work_order')
        freezer = data.get('freezer')
        if not order or not freezer: return jsonify({'ok': False, 'msg': 'Missing params'}), 400
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM work_orders WHERE 工單號 = ?", (order,))
            if not cursor.fetchone(): cursor.execute("INSERT INTO work_orders (工單號) VALUES (?)", (order,))
            cursor.execute('UPDATE work_orders SET "凍乾機_1" = ? WHERE 工單號 = ?', (freezer, order))
            conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# 4. 生產照片上傳 (工單)
@app.route('/api/mobile/upload', methods=['POST'])
def mobile_upload():
    print("🔔 [Production] 收到照片上傳請求...") 
    try:
        order = request.form.get('work_order')
        step_id = request.form.get('step_id')
        user = request.form.get('user')
        file = request.files.get('photo')

        if not all([order, step_id, user]):
            return jsonify({'ok': False, 'msg': '資料不完整'}), 400

        config = STEP_CONFIG.get(step_id)
        if not config: return jsonify({'ok': False, 'msg': '無效步驟'}), 400
        
        time_col, user_col, photo_col = config
        filename = ""
        if file:
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{order}_{step_id}_{timestamp_str}.jpg"
            local_path = LOCAL_CACHE_DIR / filename
            nas_path = UPLOAD_FOLDER / filename
            try:
                file.save(local_path)
                thread = threading.Thread(target=background_move_to_nas, args=(local_path, nas_path))
                thread.start()
            except Exception as e:
                return jsonify({'ok': False, 'msg': f'Save Error: {str(e)}'}), 500
        
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM work_orders WHERE 工單號 = ?", (order,))
            if not cursor.fetchone(): cursor.execute("INSERT INTO work_orders (工單號) VALUES (?)", (order,))

            cursor.execute(f'SELECT "{photo_col}" FROM work_orders WHERE 工單號 = ?', (order,))
            row = cursor.fetchone()
            existing = row[0] if row else ""
            final_str = f"{existing};{filename}" if existing and filename else (filename or existing)
            
            sql = f'UPDATE work_orders SET "{time_col}"=?, "{user_col}"=?, "{photo_col}"=? WHERE 工單號=?'
            cursor.execute(sql, (current_time, user, final_str, order))
            conn.commit()

        return jsonify({'ok': True, 'timestamp': current_time, 'photoName': final_photo_str if 'final_photo_str' in locals() else filename})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# 5. 異常紀錄 API (多圖)
@app.route('/api/abnormal_record', methods=['POST'])
def add_abnormal_record():
    print(f"🔔 [Abnormal] 收到異常請求 IP: {request.remote_addr}")
    try:
        # --- 🔍 加入這兩行來檢查收到的資料 ---
        print(f"🔍 DEBUG Headers: {request.headers}")
        print(f"🔍 DEBUG Form Data: {request.form}")
        # -----------------------------------
        station = request.form.get('station')
        machine_id = request.form.get('machine_id')
        description = request.form.get('description')
        user = request.form.get('user', 'Unknown')
        created_at = request.form.get('created_at') or datetime.now().isoformat()

        if not all([station, machine_id, description]):
            return jsonify({'ok': False, 'error': 'Missing fields'}), 400

        files = request.files.getlist('photos')
        saved_filenames = []

        if files:
            print(f"📸 收到 {len(files)} 張異常照片")
            for idx, file in enumerate(files):
                if file:
                    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
                    safe_station = re.sub(r'[\\/*?:"<>|]', "", station)
                    filename = f"Abnormal_{safe_station}_{timestamp_str}_{idx}.jpg"
                    local_path = LOCAL_CACHE_DIR / filename
                    nas_path = UPLOAD_FOLDER / filename
                    try:
                        file.save(local_path)
                        thread = threading.Thread(target=background_move_to_nas, args=(local_path, nas_path))
                        thread.start()
                        saved_filenames.append(filename)
                    except Exception as e:
                        print(f"❌ Photo Save Error: {e}")

        photo_str = ";".join(saved_filenames)

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO abnormal_history (station, machine_id, description, created_at, user, photos)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (station, machine_id, description, created_at, user, photo_str))
            conn.commit()
        
        print(f"✅ [Abnormal] Saved: {station} - {machine_id}")
        return jsonify({'ok': True, 'msg': 'Record saved'})
    except Exception as e:
        print(f"❌ Abnormal Error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/abnormal_top5', methods=['GET'])
def get_abnormal_top5():
    station = request.args.get('station', '')
    default_suggestions = ["管路阻塞", "感測器異常", "數據未上傳", "緊急停止", "其他"]
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='abnormal_history'")
            if not cursor.fetchone(): return jsonify({'ok': True, 'issues': default_suggestions})

            sql = """
            SELECT description, COUNT(*) as cnt FROM abnormal_history
            WHERE station = ? AND description IS NOT NULL AND description != ''
            GROUP BY description ORDER BY cnt DESC LIMIT 5
            """
            cursor.execute(sql, (station,))
            rows = cursor.fetchall()
            issues = [row[0] for row in rows] if rows else []
            if len(issues) < 5:
                for d in default_suggestions:
                    if d not in issues: issues.append(d)
                    if len(issues) >= 5: break
            return jsonify({'ok': True, 'issues': issues})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/photos/<path:filename>')
def serve_photo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# === Main ===
if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"Initializing DB...")
        init_db()
        init_abnormal_db()
    else:
        print(f"DB Exists: {DB_PATH}")
        init_abnormal_db() # 確保欄位補齊

    port = int(os.environ.get("PORT", 5100))
    print(f"🚀 Flask Backend Running on http://0.0.0.0:{port}")
    serve(app, host='0.0.0.0', port=port, threads=20)