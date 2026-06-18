from flask import Flask, request, jsonify
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

app = Flask(__name__)
CORS(app)

# === Configuration ===
DB_TIMEOUT = 5.0
ADMIN_PIN = "36121288"

# === Database Paths ===
# 1. Schedule & 5714 DB (Source of Truth for Planning)
DB_SCHEDULE = r"D:\配藥表\資料庫\P01_formualte_schedule.db"

# 2. Production Record & Photo DB (Source of Truth for Execution)
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"
UPLOAD_FOLDER = Path(r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\Photos")

# Ensure photo directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 新增一個本機快速路徑 (例如在程式同目錄下)
LOCAL_CACHE_DIR = Path("D:/BeadRecord_Cache") 
os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)

# === Field Definitions (保留原樣，對應您資料庫真實欄位) ===
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

# === [關鍵修改] 步驟對應表 ===
# 格式: '前端StepID': ('時間欄位', '使用者欄位', '照片欄位')
# 這裡使用了您資料庫中現有的舊欄位名稱
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
        cursor.execute("DROP TABLE IF EXISTS work_orders")
        col_defs = ", ".join([f'"{col}" TEXT' for col in ALL_FIELDS])
        cursor.execute(f"""
            CREATE TABLE work_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {col_defs}
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_orders_order_no ON work_orders (工單號)")
        conn.commit()
        print("✅ Database initialized: work_orders table created.")

def ensure_columns(conn, table, columns):
    cur = conn.cursor()
    cur.execute(f'PRAGMA table_info("{table}")')
    existing = {row[1] for row in cur.fetchall()}
    for col in columns:
        if col not in existing:
            cur.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" TEXT')
    conn.commit()

def compress_image(input_path, output_path, max_width=600, quality=70):
    try:
        img = Image.open(input_path)
        # 修正照片方向 (EXIF Orientation)
        try:
            exif = img._getexif()
            if exif:
                from PIL import ExifTags
                orientation_key = next((k for k, v in ExifTags.TAGS.items() if v == 'Orientation'), None)
                if orientation_key and orientation_key in exif:
                    val = exif[orientation_key]
                    if val == 3: img = img.rotate(180, expand=True)
                    elif val == 6: img = img.rotate(270, expand=True)
                    elif val == 8: img = img.rotate(90, expand=True)
        except:
            pass

        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        
        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
        img.save(output_path, format="JPEG", quality=quality, optimize=True)
    except Exception as e:
        print(f"Compression failed: {e}")

def background_move_to_nas(local_path, nas_path):
    try:
        # 複製過去 (copy2 保留 metadata)
        shutil.copy2(local_path, nas_path)
        # 成功後刪除本機暫存
        os.remove(local_path)
        print(f"✅ [背景任務] 照片已搬移至 NAS: {nas_path}")
    except Exception as e:
        print(f"❌ [背景任務] 搬移失敗: {e}")

# ==================== APIs ====================

# 1. Get Work Orders (Today & Yesterday)
# 修改 app_V6.py 中的 mobile_get_orders 函式

@app.route('/api/mobile/work-orders', methods=['GET'])
def mobile_get_orders():
    try:
        if not os.path.exists(DB_SCHEDULE):
            return jsonify({'ok': False, 'error': f"DB Not Found: {DB_SCHEDULE}"}), 500

        today = datetime.now()
        yesterday = today - timedelta(days=1)
        
        target_dates = [
            f"{today.strftime('%Y/%m/%d')}%",
            f"{yesterday.strftime('%Y/%m/%d')}%"
        ]

        with sqlite3.connect(DB_SCHEDULE) as conn:
            cursor = conn.cursor()
            date_conditions = " OR ".join(["Date LIKE ?" for _ in target_dates])
            
            # [修改 1] 多抓取 Marker 欄位
            sql = f"""
                SELECT DISTINCT WorkOrder, Marker
                FROM DropletSchedule 
                WHERE WorkOrder IS NOT NULL AND WorkOrder != ''
                AND ({date_conditions})
            """
            cursor.execute(sql, target_dates)
            
            # [修改 2] 組裝成物件列表
            orders = []
            for row in cursor.fetchall():
                orders.append({
                    'work_order': row[0],
                    'marker': row[1] if row[1] else '' # 處理 Marker 可能為空的情況
                })
            
            # 排序 (依照工單號由新到舊)
            orders.sort(key=lambda x: x['work_order'], reverse=True)
            
        return jsonify({'ok': True, 'orders': orders})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# 2. Check 5714 Access
@app.route('/api/mobile/check-access', methods=['GET'])
def mobile_check_access():
    work_order = request.args.get('work_order')
    if not work_order: return jsonify({'ok': False, 'msg': 'Missing Work Order'}), 400

    try:
        with sqlite3.connect(DB_SCHEDULE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%5714%'")
            tables = cursor.fetchall()
            
            if not tables:
                return jsonify({'ok': False, 'allowed': False, 'msg': 'No 5714 tables found'}), 404

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
                return jsonify({'ok': True, 'allowed': True, 'msg': f"Access Granted\nPrep Date: {found_info['date']}", 'meta': found_info})
            else:
                return jsonify({'ok': True, 'allowed': False, 'msg': '5714 Prep not completed'})

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# 3. Get Status (Updated to use OLD column names)
# 修改 mobile_get_status 函式
@app.route('/api/mobile/status', methods=['GET'])
def mobile_get_status():
    order = request.args.get('work_order')
    try:
        # 1. 先去排程表抓預計凍乾機 (DropletSchedule)
        freezer_plan = "未指定"
        if os.path.exists(DB_SCHEDULE):
            with sqlite3.connect(DB_SCHEDULE) as conn_sched:
                cursor_sched = conn_sched.cursor()
                # 假設日期格式為 YYYY/MM/DD，抓取 Lyophilizer 欄位
                # 我們不限日期，只對工單號
                cursor_sched.execute("SELECT Lyophilizer FROM DropletSchedule WHERE WorkOrder = ? LIMIT 1", (order,))
                row_sched = cursor_sched.fetchone()
                if row_sched and row_sched[0]:
                    # 格式化: 如果是 "03"，轉成 "Freezer 03"
                    val = str(row_sched[0]).strip()
                    if val.isdigit():
                        freezer_plan = f"Freezer {val.zfill(2)}"
                    else:
                        freezer_plan = val # 如果已經有字(如 F-03)就照舊

        # 2. 再去紀錄表抓進度 (work_orders)
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

            # 回傳 details 時，把預計凍乾機也塞進去
            details = data
            details['freezer_plan'] = freezer_plan # <--- 新增此欄位

            return jsonify({'ok': True, 'steps': steps_data, 'details': details})

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    
# 新增 API: 更新凍乾機欄位
@app.route('/api/mobile/update-freezer', methods=['POST'])
def mobile_update_freezer():
    try:
        data = request.get_json()
        order = data.get('work_order')
        freezer = data.get('freezer') # e.g. "Freezer 03"

        if not order or not freezer:
            return jsonify({'ok': False, 'msg': '缺少參數'}), 400

        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 確保工單存在
            cursor.execute("SELECT 1 FROM work_orders WHERE 工單號 = ?", (order,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO work_orders (工單號) VALUES (?)", (order,))
            
            # 更新 凍乾機_1 欄位
            # 注意：這裡假設您的資料庫有 '凍乾機_1' 這個欄位，如果沒有請先加
            cursor.execute('UPDATE work_orders SET "凍乾機_1" = ? WHERE 工單號 = ?', (freezer, order))
            conn.commit()

        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/mobile/upload', methods=['POST'])
def mobile_upload():
    print("🔔 [1] 收到上傳請求 (多張照片模式)...") 
    try:
        # 1. 獲取參數
        order = request.form.get('work_order')
        step_id = request.form.get('step_id')
        user = request.form.get('user')
        file = request.files.get('photo')

        print(f"📄 [2] 參數: Order={order}, Step={step_id}, User={user}, Photo={file.filename if file else '無'}")

        if not all([order, step_id, user]):
            print("❌ [Error] 參數不完整")
            return jsonify({'ok': False, 'msg': '資料不完整'}), 400

        # 2. 取得欄位設定 (從 STEP_CONFIG 查表)
        config = STEP_CONFIG.get(step_id)
        if not config: 
            print(f"❌ [Error] 無效的步驟 ID: {step_id}")
            return jsonify({'ok': False, 'msg': '無效步驟'}), 400
        
        time_col, user_col, photo_col = config
        
        # 3. 處理照片 (存檔 + 壓縮)
        filename = ""
        if file:
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{order}_{step_id}_{timestamp_str}.jpg"
            
            # 1. 先存到本機 SSD/HDD (速度快)
            local_path = LOCAL_CACHE_DIR / filename
            nas_path = UPLOAD_FOLDER / filename
            
            try:
                file.save(local_path)
                # 這裡也可以做 compress_image，但如果是前端壓縮過就不需要了
                
                # 2. 啟動背景執行緒搬移到 NAS (不卡住 Request)
                thread = threading.Thread(target=background_move_to_nas, args=(local_path, nas_path))
                thread.start()
                
            except Exception as e:
                return jsonify({'ok': False, 'msg': f'Local Save Error: {str(e)}'}), 500
        else:
            print("⚠️ [Warning] 此次請求沒有包含照片檔案")

        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 4. 寫入資料庫 (串接邏輯)
        print(f"🔌 [4] 連接資料庫更新...")
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 4-1. 檢查工單是否存在 (不存在則建立)
            cursor.execute("SELECT 1 FROM work_orders WHERE 工單號 = ?", (order,))
            if not cursor.fetchone():
                print(f"🆕 工單 {order} 不存在，建立新紀錄...")
                cursor.execute("INSERT INTO work_orders (工單號) VALUES (?)", (order,))

            # 4-2. [關鍵] 讀取舊照片欄位
            # 我們需要知道之前已經傳了什麼，才能把新照片接在後面
            cursor.execute(f'SELECT "{photo_col}" FROM work_orders WHERE 工單號 = ?', (order,))
            row = cursor.fetchone()
            existing_photos = row[0] if row else ""
            
            # 4-3. 字串串接 (使用分號 ; 分隔)
            final_photo_str = ""
            
            # 如果資料庫裡原本就有照片字串
            if existing_photos and str(existing_photos).strip():
                if filename: 
                    # 原本有 + 這次有 = 串接 (例如: "a.jpg;b.jpg")
                    final_photo_str = f"{existing_photos};{filename}"
                else:
                    # 原本有 + 這次沒傳 = 保持原樣
                    final_photo_str = existing_photos
            else:
                # 原本沒有 = 直接使用這次的檔名
                final_photo_str = filename
            
            print(f"🔗 [4-3] 照片欄位將更新為: {final_photo_str}")

            # 4-4. 執行 Update
            # 更新：時間、使用者、以及"串接後"的照片字串
            sql = f"""
                UPDATE work_orders 
                SET "{time_col}" = ?, "{user_col}" = ?, "{photo_col}" = ?
                WHERE 工單號 = ?
            """
            cursor.execute(sql, (current_time, user, final_photo_str, order))
            conn.commit()
            print("✅ [5] 資料庫 Commit 成功")

        # 5. 回傳成功
        # photoName 回傳完整的串接字串，讓前端解析後可以顯示所有照片
        return jsonify({'ok': True, 'timestamp': current_time, 'photoName': final_photo_str})

    except Exception as e:
        print(f"🔥 [Fatal Error] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'ok': False, 'error': str(e)}), 500
    
from flask import send_from_directory

@app.route('/photos/<path:filename>')
def serve_photo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# === Main ===
if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"Initializing DB: {DB_PATH} ...")
        init_db()
    else:
        print(f"DB Exists: {DB_PATH}")

    port = int(os.environ.get("PORT", 5100))
    print(f"🚀 Flask Backend Running on http://0.0.0.0:{port}")
    serve(app, host='0.0.0.0', port=port, threads=20)