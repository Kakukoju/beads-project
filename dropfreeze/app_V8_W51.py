from gevent import monkey
monkey.patch_all()

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit 
import sqlite3
import os
from pathlib import Path
from datetime import datetime, timedelta
import threading
import shutil
import pandas as pd
import requests
import json
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!' 
CORS(app)

socketio = SocketIO(app, cors_allowed_origins="*") 

# === Configuration ===
DB_TIMEOUT = 5.0
ADMIN_PIN = "36121288" # 主管簽核密碼

# 🔥 Teams Webhook (請確認這是您的最新網址)
TEAMS_WEBHOOK_URL = "https://skylamb.webhook.office.com/webhookb2/721d0e06-4ea4-429c-a0f0-f0c6a8b6f9a2@15d82f97-4f15-4ead-9ab6-18aa0cd45388/IncomingWebhook/88dbd64b37de41cf8c542382204e6ae7/7731650f-a7d2-4b94-ad86-14e06a65ea2e/V2zdLMPmpiBguJzF9o1Y5rv0kEMSW9R9SfE-FCZy_Zdd01"

# === Database Paths ===
DB_SCHEDULE = r"D:\配藥表\資料庫\P01_formualte_schedule.db"
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"
UPLOAD_FOLDER = Path(r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\Photos")
LOCAL_CACHE_DIR = Path("D:/BeadRecord_Cache") 

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)

# === Field Definitions (工單紀錄用) ===
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
            cursor.execute(f"CREATE TABLE work_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, {col_defs})")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_orders_order_no ON work_orders (工單號)")
            print("✅ Database initialized: work_orders table created.")

def init_abnormal_db():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS abnormal_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station TEXT,
                    machine_id TEXT,
                    description TEXT,
                    created_at TEXT,
                    user TEXT,
                    photos TEXT,
                    is_resolved INTEGER DEFAULT 0,
                    resolution_note TEXT,
                    status INTEGER DEFAULT 0,
                    signer TEXT
                )
            """)
            
            cursor.execute(f"PRAGMA table_info(abnormal_history)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'photos' not in columns: cursor.execute('ALTER TABLE abnormal_history ADD COLUMN photos TEXT')
            if 'is_resolved' not in columns: cursor.execute('ALTER TABLE abnormal_history ADD COLUMN is_resolved INTEGER DEFAULT 0')
            if 'resolution_note' not in columns: cursor.execute('ALTER TABLE abnormal_history ADD COLUMN resolution_note TEXT')
            if 'status' not in columns: cursor.execute('ALTER TABLE abnormal_history ADD COLUMN status INTEGER DEFAULT 0')
            if 'signer' not in columns: cursor.execute('ALTER TABLE abnormal_history ADD COLUMN signer TEXT')

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

# 🔥 [修復 1] 優先讀取本機快取，解決剛上傳看不到照片的問題
@app.route('/photos/<path:filename>')
def serve_photo(filename):
    try:
        local_file = LOCAL_CACHE_DIR / filename
        if local_file.exists():
            return send_from_directory(LOCAL_CACHE_DIR, filename)
        return send_from_directory(UPLOAD_FOLDER, filename)
    except Exception as e:
        return jsonify({'error': 'Photo not found'}), 404

# 🔥 [修復 2] 補回工單同步邏輯，解決工單無資料的問題
def sync_single_order_logic(target_order_id):
    if not os.path.exists(DB_SCHEDULE): return
    try:
        conn_src = sqlite3.connect(DB_SCHEDULE)
        cursor_src = conn_src.cursor()
        extra_data = {}

        sql_src = "SELECT WorkOrder, Marker, Quantity, Date, Lot, Pump, Lyophilizer FROM DropletSchedule WHERE WorkOrder = ?"
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

        if marker:
            try:
                cursor_src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%571%'")
                tables_571 = [r[0] for r in cursor_src.fetchall()]
                target_table_571 = next((t for t in tables_571 if str(marker).lower() in t.lower()), None)
                
                if target_table_571:
                    sql_571 = f'SELECT "L1OD", "L2OD", "起始L1OD", "起始L2OD", "總重量" FROM "{target_table_571}" WHERE "工單號碼" = ? LIMIT 1'
                    cursor_src.execute(sql_571, (target_order_id,))
                    row_571 = cursor_src.fetchone()
                    if row_571:
                        extra_data['L1_反應_OD'] = row_571[0]
                        extra_data['L2_反應_OD'] = row_571[1]
                        extra_data['L1_起始_OD'] = row_571[2]
                        extra_data['L2_起始_OD'] = row_571[3]
                        extra_data['淨重g'] = row_571[4]
            except: pass

        found_pn = None
        if marker:
            try:
                sql_qc = 'SELECT "PN", "懸浮物" FROM "Liquid form QC" WHERE LOWER("Marker name") = ? LIMIT 1'
                cursor_src.execute(sql_qc, (marker.lower(),))
                row_qc = cursor_src.fetchone()
                if row_qc:
                    found_pn = row_qc[0]
                    extra_data['PN'] = found_pn
                    extra_data['是否懸浮'] = "True" if "cloudy" in str(row_qc[1]).lower() else "False"
            except: pass

        if found_pn:
            try:
                sql_cond = 'SELECT "儲存時避光", "儲存時冰浴", "滴定時避光", "滴定時冰浴", "滴定時攪拌" FROM "滴定條件" WHERE "PN" = ? LIMIT 1'
                cursor_src.execute(sql_cond, (found_pn,))
                row_cond = cursor_src.fetchone()
                if row_cond:
                    check_cond = lambda v: "False" if v and "no" in str(v).lower() else "True"
                    extra_data['liquid_storge_避光'] = check_cond(row_cond[0])
                    extra_data['liquid_storge_冰浴'] = check_cond(row_cond[1])
                    extra_data['滴定_避光'] = check_cond(row_cond[2])
                    extra_data['滴定_冰浴'] = check_cond(row_cond[3])
                    extra_data['滴定_攪拌'] = check_cond(row_cond[4])
            except: pass

        conn_src.close()

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
            ('bead_name', marker), ('製令數量', qty), ('日期', date),
            ('port_1', pump), ('port_2', pump), ('port_3', pump), ('port_4', pump),
            ('凍乾機_1', formatted_freezer), ('凍乾機_2', formatted_freezer), ('凍乾機_3', formatted_freezer), ('凍乾機_4', formatted_freezer),
            ('Dispense_Lot_1', lots[0]), ('Dispense_Lot_2', lots[1]), ('Dispense_Lot_3', lots[2]), ('Dispense_Lot_4', lots[3]),
            ('L1_反應_OD', extra_data.get('L1_反應_OD')), ('L2_反應_OD', extra_data.get('L2_反應_OD')),
            ('L1_起始_OD', extra_data.get('L1_起始_OD')), ('L2_起始_OD', extra_data.get('L2_起始_OD')),
            ('淨重g', extra_data.get('淨重g')), ('PN', extra_data.get('PN')),
            ('是否懸浮', extra_data.get('是否懸浮')), ('liquid_storge_避光', extra_data.get('liquid_storge_避光')),
            ('liquid_storge_冰浴', extra_data.get('liquid_storge_冰浴')), ('滴定_避光', extra_data.get('滴定_避光')),
            ('滴定_冰浴', extra_data.get('滴定_冰浴')), ('滴定_攪拌', extra_data.get('滴定_攪拌'))
        ]

        final_updates = []
        final_values = []
        for col, new_val in updates:
            if new_val is not None and str(new_val).strip() != '':
                final_updates.append(f'"{col}" = ?')
                final_values.append(str(new_val))

        if final_updates:
            sql = f"UPDATE work_orders SET {', '.join(final_updates)} WHERE id = ?"
            final_values.append(order_db_id)
            cursor.execute(sql, tuple(final_values))
            conn_target.commit()
        
        conn_target.close()
    except Exception as e:
        print(f"❌ 同步錯誤: {e}")

# Helper: Teams 發送
def send_teams_alert(data):
    if not TEAMS_WEBHOOK_URL: return
    try:
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": "d70000",
            "summary": "異常通報",
            "sections": [{
                "activityTitle": f"🚨 產線異常通報: {data['station']}",
                "activitySubtitle": f"機台: {data['machine_id'] or '無'}",
                "facts": [
                    {"name": "描述", "value": data['description']},
                    {"name": "通報人", "value": data['user']},
                    {"name": "時間", "value": data['created_at']}
                ],
                "markdown": True
            }],
            "potentialAction": [{
                "@type": "OpenUri",
                "name": "開啟儀表板審核",
                # 🔥 請填入您前端 Cloudflare 網址
                "targets": [{"os": "default", "uri": "https://tons-stating-modular-attempting.trycloudflare.com/?view=audit"}] 
            }]
        }
        requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=5)
    except Exception as e:
        print(f"❌ Teams send failed: {e}")

# Helper: 統計
def get_abnormal_stats():
    try:
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        month_str = now.strftime('%Y-%m')
        start_of_week = now - timedelta(days=now.weekday())
        week_str = start_of_week.strftime('%Y-%m-%d')

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM abnormal_history WHERE created_at LIKE ?", (f"{today_str}%",))
            day_cnt = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM abnormal_history WHERE created_at LIKE ?", (f"{month_str}%",))
            month_cnt = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM abnormal_history WHERE created_at >= ?", (f"{week_str} 00:00",))
            week_cnt = cursor.fetchone()[0]
            return {'day': day_cnt, 'week': week_cnt, 'month': month_cnt}
    except:
        return {'day': 0, 'week': 0, 'month': 0}
    
# === Ops Helper: 滴定時間預測 ===
def calc_titration_remaining(start_time_str, quantity):
    try:
        start = datetime.fromisoformat(start_time_str)
    except:
        start = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")

    # 🔥 關鍵修正：Quantity 轉數字
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        qty = 0

    estimate_hours = qty / 1500 if qty > 0 else 0

    end_time = start + timedelta(hours=estimate_hours)
    remain_min = max(
        0,
        int((end_time - datetime.now()).total_seconds() / 60)
    )

    return {
        "estimateHours": round(estimate_hours, 2),
        "estimatedEndTime": end_time.strftime("%Y-%m-%d %H:%M"),
        "remainMin": remain_min
    }



def get_pumps_and_quantity(work_order):
    with sqlite3.connect(DB_SCHEDULE) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT Pump, Quantity
            FROM DropletSchedule
            WHERE WorkOrder = ?
        """, (work_order,))
        rows = cur.fetchall()
        print(f"🔎 滴定中工單數量 = {len(rows)}")

    pumps = []
    quantity = 0
    for pump, qty in rows:
        if pump:
            pumps.append(pump)
        if qty:
            quantity = qty

    return pumps, quantity

def is_ivek_scheduled_today():
    today = datetime.now().strftime("%Y/%m/%d")
    with sqlite3.connect(DB_SCHEDULE) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT 1 FROM DropletSchedule
            WHERE Date = ?
              AND UPPER(Pump) LIKE '%IVEK%'
            LIMIT 1
        """, (today,))
        return cur.fetchone() is not None

def get_ivek_state():
    today = datetime.now().strftime("%Y/%m/%d")

    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT 工單號, 時間_滴定開始, 時間_滴定結束
            FROM work_orders
            WHERE 日期 = ?
              AND (
                port_1 LIKE '%IVEK%' OR
                port_2 LIKE '%IVEK%' OR
                port_3 LIKE '%IVEK%' OR
                port_4 LIKE '%IVEK%'
              )
            ORDER BY 時間_滴定開始 ASC
        """, (today,))
        rows = cur.fetchall()

    if not rows:
        return "idle", None

    for r in rows:
        if r["時間_滴定開始"] and not r["時間_滴定結束"]:
            return "running", r["工單號"]

    return "finished", rows[-1]["工單號"]
def build_pump_resources(rows):
    """
    rows: 滴定中 + 今日排程的 work_orders
    """
    pumps = {f"Pump-{i:02d}": {
        "id": f"Pump-{i:02d}",
        "type": "PUMP",
        "todayUsed": False,
        "state": "unused",
        "currentJob": None,
        "remainMin": None
    } for i in range(1, 13)}

    for r in rows:
        wo = r["工單號"]
        start = r["時間_滴定開始"]
        end = r["時間_滴定結束"]
        pump_list, quantity = get_pumps_and_quantity(wo)
        timing = calc_titration_remaining(start, quantity) if start else None

        for p in pump_list:
            pid = p.replace("Port", "Pump-").zfill(7) if p.startswith("Port") else p
            if pid not in pumps:
                continue

            pumps[pid]["todayUsed"] = True
            pumps[pid]["currentJob"] = wo

            if start and not end:
                pumps[pid]["state"] = "running"
                pumps[pid]["remainMin"] = timing["remainMin"] if timing else None
            elif start and end:
                pumps[pid]["state"] = "finished"
            else:
                pumps[pid]["state"] = "idle"

    return list(pumps.values())


# ==================== APIs ====================

from datetime import datetime, timedelta
import math

@app.route("/api/ops/titration-status", methods=["GET"])
def ops_titration_status():
    print("🟢 ops_titration_status CALLED")

    today_slash = datetime.now().strftime("%Y/%m/%d")
    now = datetime.now()

    # =========================
    # 1️⃣ 先建立所有 Resource
    # =========================
    resources = []

    # IVEK
    ivek_resource = {
        "id": "IVEK",
        "type": "IVEK",
        "todayUsed": False,
        "state": "unused",
        "currentJob": None,
        "remainMin": None
    }
    resources.append(ivek_resource)

    # Pumps 01~12
    pump_map = {}
    for i in range(1, 13):
        pid = f"Pump-{str(i).zfill(2)}"
        pump = {
            "id": pid,
            "type": "PUMP",
            "todayUsed": False,
            "state": "unused",
            "currentJob": None,
            "remainMin": None
        }
        pump_map[pid] = pump
        resources.append(pump)

    # =========================
    # 2️⃣ 讀取「滴定中工單」
    # =========================
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("""
            SELECT 工單號, bead_name, 時間_滴定開始
            FROM work_orders
            WHERE 日期 = ?
              AND 時間_滴定開始 IS NOT NULL
              AND (時間_滴定結束 IS NULL OR 時間_滴定結束 = '')
        """, (today_slash,))

        running_orders = cur.fetchall()

    jobs = []
    used_pumps = set()

    # =========================
    # 3️⃣ 處理每張工單
    # =========================
    for row in running_orders:
        wo = row["工單號"]
        marker = row["bead_name"] or ""
        start_time_str = row["時間_滴定開始"]

        try:
            start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
        except:
            continue

        # 👉 你既有的 helper
        pumps, quantity_raw = get_pumps_and_quantity(wo)

        # ⚠️ 修正 quantity 為字串的問題
        try:
            quantity = int(quantity_raw)
        except:
            quantity = 0

        # =========================
        # 4️⃣ 計算時間
        # =========================
        estimate_hours = quantity / 1500 if quantity > 0 else 0
        estimate_minutes = math.ceil(estimate_hours * 60)
        end_time = start_time + timedelta(minutes=estimate_minutes)
        remain_min = max(0, math.ceil((end_time - now).total_seconds() / 60))

        # =========================
        # 5️⃣ 更新 Pump Resource
        # =========================
        for p in pumps:
            pid = p if p.startswith("Pump") else f"Pump-{str(p).zfill(2)}"
            if pid in pump_map:
                pump_map[pid]["todayUsed"] = True
                pump_map[pid]["state"] = "running"
                pump_map[pid]["currentJob"] = wo
                pump_map[pid]["remainMin"] = remain_min
                used_pumps.add(pid)

        # =========================
        # 6️⃣ IVEK 規則（只要今天有滴定）
        # =========================
        ivek_resource["todayUsed"] = True
        ivek_resource["state"] = "running"
        ivek_resource["currentJob"] = wo

        # =========================
        # 7️⃣ jobs list
        # =========================
        jobs.append({
            "workOrder": wo,
            "marker": marker,
            "quantity": quantity,
            "pumps": list(pumps),
            "estimateHours": round(estimate_hours, 2),
            "estimatedEndTime": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "remainMin": remain_min
        })

    # =========================
    # 8️⃣ 處理 idle / finished / unused
    # =========================
    for p in pump_map.values():
        if p["todayUsed"] and p["state"] == "unused":
            p["state"] = "idle"
        if p["todayUsed"] and p["remainMin"] == 0 and p["state"] == "running":
            p["state"] = "finished"

    if ivek_resource["todayUsed"] and ivek_resource["state"] == "unused":
        ivek_resource["state"] = "idle"

    # =========================
    # 9️⃣ 統計
    # =========================
    pumps_total = 12
    pumps_in_use = len(used_pumps)
    free_pumps = pumps_total - pumps_in_use

    next_release = min(
        [j["remainMin"] for j in jobs if j["remainMin"] > 0],
        default=None
    )

    # =========================
    # 🔟 Response（完全對齊 ops.ts）
    # =========================
    return jsonify({
        "pumpsTotal": pumps_total,
        "pumpsInUse": pumps_in_use,
        "freePumps": free_pumps,
        "nextReleaseMin": next_release,
        "jobs": jobs,
        "resources": resources
    })



@app.route('/api/latest_abnormal', methods=['GET'])
def get_latest_abnormal():
    try:
        stats = get_abnormal_stats()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            sql = "SELECT id, station, machine_id, description, created_at, user, photos, is_resolved, resolution_note, status, signer FROM abnormal_history ORDER BY created_at DESC LIMIT 1"
            cursor.execute(sql)
            row = cursor.fetchone()
            abnormal_data = None
            if row:
                abnormal_data = {
                    'id': row[0], 'station': row[1], 'machine_id': row[2], 'description': row[3],
                    'created_at': row[4], 'user': row[5], 'photos': row[6], 'status': row[9] if len(row)>9 else 0
                }
            return jsonify({'ok': True, 'stats': stats, 'abnormal': abnormal_data})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/today_abnormals', methods=['GET'])
def get_today_abnormals():
    try:
        today_str = datetime.now().strftime('%Y-%m-%d')
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM abnormal_history WHERE created_at LIKE ? ORDER BY created_at DESC", (f"{today_str}%",))
            return jsonify({'ok': True, 'data': [dict(r) for r in cursor.fetchall()]})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)}), 500

# 🔥 [修復 3] 異常處置邏輯：分為 resolve(處置) 和 signoff(簽核)
@app.route('/api/resolve_abnormal', methods=['POST'])
def resolve_abnormal():
    try:
        data = request.get_json()
        record_id = data.get('id')
        action = data.get('action') # 'resolve' or 'signoff'
        note = data.get('note', '')
        signer = data.get('signer', '') 
        pin = data.get('pin', '')       

        with get_db_connection() as conn:
            cursor = conn.cursor()
            if action == 'resolve':
                # 階段一：人員處置 -> 狀態變 1
                cursor.execute("UPDATE abnormal_history SET status=1, is_resolved=1, resolution_note=? WHERE id=?", (note, record_id))
            elif action == 'signoff':
                # 階段二：主管簽核 -> 狀態變 2
                if pin != ADMIN_PIN: return jsonify({'ok': False, 'error': 'PIN碼錯誤'}), 403
                cursor.execute("UPDATE abnormal_history SET status=2, signer=? WHERE id=?", (signer, record_id))
            conn.commit()
            
        stats = get_abnormal_stats()
        socketio.emit('count_update', {'stats': stats})
        return jsonify({'ok': True, 'stats': stats})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/abnormal_record', methods=['POST'])
def add_abnormal_record():
    try:
        station, machine_id = request.form.get('station'), request.form.get('machine_id')
        description, user = request.form.get('description'), request.form.get('user', 'Unknown')
        created_at = request.form.get('created_at') or datetime.now().strftime('%Y-%m-%d %H:%M')

        if not station or not description: return jsonify({'ok': False, 'error': 'Missing fields'}), 400
        if station != "收藥" and not machine_id: return jsonify({'ok': False, 'error': 'Missing machine_id'}), 400

        files = request.files.getlist('photos')
        saved_filenames = []
        if files:
            for idx, file in enumerate(files):
                if file:
                    fname = f"Abnormal_{re.sub(r'[^\w]', '', str(station))}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx}.jpg"
                    l_path, n_path = LOCAL_CACHE_DIR / fname, UPLOAD_FOLDER / fname
                    try:
                        file.save(l_path)
                        threading.Thread(target=background_move_to_nas, args=(l_path, n_path)).start()
                        saved_filenames.append(fname)
                    except: pass
        
        photo_str = ";".join(saved_filenames)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO abnormal_history (station, machine_id, description, created_at, user, photos, status, is_resolved) VALUES (?, ?, ?, ?, ?, ?, 0, 0)", 
                           (station, machine_id, description, created_at, user, photo_str))
            conn.commit()
            new_id = cursor.lastrowid 

        threading.Thread(target=send_teams_alert, args=({'station': station, 'machine_id': machine_id, 'description': description, 'user': user, 'created_at': created_at},)).start()
        
        stats = get_abnormal_stats()
        socketio.emit('new_abnormal', {'id': new_id, 'station': station, 'machine_id': machine_id, 'description': description, 'created_at': created_at, 'user': user, 'photos': photo_str, 'stats': stats})
        return jsonify({'ok': True, 'msg': 'Record saved'})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/abnormal_top5', methods=['GET'])
def get_abnormal_top5():
    st = request.args.get('station', '')
    defs = ["管路阻塞", "感測器異常", "數據未上傳", "緊急停止", "其他"]
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT description, COUNT(*) as c FROM abnormal_history WHERE station=? GROUP BY description ORDER BY c DESC LIMIT 5", (st,))
            issues = [r[0] for r in cur.fetchall()]
            return jsonify({'ok': True, 'issues': list(set(issues + defs))[:8]}) 
    except: return jsonify({'ok': True, 'issues': defs})

@app.route('/api/mobile/work-orders', methods=['GET'])
def mobile_get_orders():
    try:
        if not os.path.exists(DB_SCHEDULE): return jsonify({'ok': False, 'error': "DB Not Found"}), 500
        today = datetime.now()
        dates = [(today - timedelta(days=i)).strftime('%Y/%m/%d') for i in range(3)]
        sql_params = [f"{d}%" for d in dates]
        
        with sqlite3.connect(DB_SCHEDULE) as conn:
            cursor = conn.cursor()
            conds = " OR ".join(["Date LIKE ?" for _ in sql_params])
            sql = f"SELECT WorkOrder, Marker, Date, Pump, DrugGivenAt FROM DropletSchedule WHERE WorkOrder IS NOT NULL AND WorkOrder != '' AND ({conds})"
            cursor.execute(sql, sql_params)
            
            orders_map = {}
            for row in cursor.fetchall():
                wo, marker, date_str, pump, time_str = row
                if not (wo.startswith("TMRA") or wo.startswith("UMRZ")): continue
                
                pump = str(pump).upper() if pump else ""
                try: hour = int(str(time_str).split(':')[0])
                except: hour = 0
                
                score = 999
                if "IVEK" in pump: score = 0
                elif "PORT" in pump:
                    try: port_num = int(re.search(r'\d+', pump).group())
                    except: port_num = 99
                    score = (200 if hour >= 12 else 100) + port_num
                
                if wo not in orders_map or score < orders_map[wo]['best_score']:
                    orders_map[wo] = {'work_order': wo, 'marker': marker or '', 'date': date_str, 'best_score': score, 'pump_info': pump, 'time_info': time_str or "00:00"}

            orders = sorted(list(orders_map.values()), key=lambda x: (x['best_score'], -1 * int(x['date'].replace('/',''))))
            return jsonify({'ok': True, 'orders': orders})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/mobile/check-access', methods=['GET'])
def mobile_check_access():
    work_order = request.args.get('work_order')
    if not work_order: return jsonify({'ok': False, 'msg': 'Missing Work Order'}), 400
    try:
        with sqlite3.connect(DB_SCHEDULE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%5714%'")
            for (tbl,) in cursor.fetchall():
                cursor.execute(f'PRAGMA table_info("{tbl}")')
                cols = [c[1] for c in cursor.fetchall()]
                wo_col = "工單號碼" if "工單號碼" in cols else "WorkOrder"
                if wo_col in cols:
                    cursor.execute(f'SELECT 1 FROM "{tbl}" WHERE "{wo_col}" = ? LIMIT 1', (work_order,))
                    if cursor.fetchone(): return jsonify({'ok': True, 'allowed': True})
            return jsonify({'ok': True, 'allowed': False, 'msg': '5714 Prep not completed'})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/mobile/status', methods=['GET'])
def mobile_get_status():
    order = request.args.get('work_order')
    if order: sync_single_order_logic(order)
    try:
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM work_orders WHERE 工單號 = ?", (order,))
            row = cursor.fetchone()
            data = dict(row) if row else {}
            
            steps = {}
            for step_id, (t_col, u_col, p_col) in STEP_CONFIG.items():
                if data.get(t_col):
                    steps[step_id] = {'timestamp': data.get(t_col), 'user': data.get(u_col), 'photoName': data.get(p_col)}
            
            return jsonify({'ok': True, 'steps': steps, 'details': {**data, 'freezer_plan': data.get('凍乾機_1', '未指定')}})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/mobile/update-freezer', methods=['POST'])
def mobile_update_freezer():
    try:
        d = request.get_json()
        with get_db_connection() as conn:
            conn.execute('UPDATE work_orders SET "凍乾機_1" = ? WHERE 工單號 = ?', (d.get('freezer'), d.get('work_order')))
            conn.commit()
        return jsonify({'ok': True})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/mobile/upload', methods=['POST'])
def mobile_upload():
    print("🔔 [Production] 收到工單照片上傳...")
    try:
        order, step_id, user = request.form.get('work_order'), request.form.get('step_id'), request.form.get('user')
        file = request.files.get('photo')
        if not all([order, step_id, user]): return jsonify({'ok': False, 'msg': 'Params missing'}), 400
        
        config = STEP_CONFIG.get(step_id)
        if not config: return jsonify({'ok': False, 'msg': 'Invalid step'}), 400
        t_col, u_col, p_col = config

        filename = ""
        if file:
            fname = f"{order}_{step_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            l_path, n_path = LOCAL_CACHE_DIR / fname, UPLOAD_FOLDER / fname
            try:
                file.save(l_path)
                threading.Thread(target=background_move_to_nas, args=(l_path, n_path)).start()
                filename = fname
            except: pass

        cur_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM work_orders WHERE 工單號 = ?", (order,))
            if not cursor.fetchone(): cursor.execute("INSERT INTO work_orders (工單號) VALUES (?)", (order,))
            
            cursor.execute(f'SELECT "{p_col}" FROM work_orders WHERE 工單號 = ?', (order,))
            row = cursor.fetchone()
            exist_ph = row[0] if row else ""
            final_ph = f"{exist_ph};{filename}" if exist_ph and filename else (filename or exist_ph)
            
            cursor.execute(f'UPDATE work_orders SET "{t_col}"=?, "{u_col}"=?, "{p_col}"=? WHERE 工單號=?', (cur_time, user, final_ph, order))
            conn.commit()
            
        return jsonify({'ok': True, 'timestamp': cur_time, 'photoName': final_ph})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)}), 500

# === Main ===
if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    
    init_db()          # 確保工單表存在
    init_abnormal_db() # 確保異常表存在

    port = int(os.environ.get("PORT", 5100))
    print(f"🚀 Flask-SocketIO Server Running on http://0.0.0.0:{port}")
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)