from flask import Flask, request, jsonify, send_from_directory, redirect
from flask_cors import CORS
from flask_socketio import SocketIO, emit 
import sqlite3
import os
from pathlib import Path
import boto3

# === S3 Config ===
S3_BUCKET = "beads-photos-harry"
S3_REGION = "ap-northeast-1"
s3_client = boto3.client("s3", region_name=S3_REGION)

def upload_to_s3(file_bytes, s3_key):
    s3_client.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=file_bytes, ContentType="image/jpeg")
    return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{s3_key}"

def get_s3_url(s3_key):
    return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{s3_key}" 
from datetime import datetime, timedelta, timezone

TZ_TW = timezone(timedelta(hours=8))
def now_tw():
    return datetime.now(TZ_TW).replace(tzinfo=None)
import threading
import shutil
import pandas as pd
import requests
import json
import re
import math
import traceback

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!' 
CORS(app)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')
MOBILE_WEB_DIR = Path(__file__).resolve().parent / "Web"

# ==========================================
# 1. 全域配置 (Configuration)
# ==========================================
DB_TIMEOUT = 5.0
ADMIN_PIN = "36121288" # 主管簽核密碼

# Teams Webhook
TEAMS_WEBHOOK_URL = "https://skylamb.webhook.office.com/webhookb2/721d0e06-4ea4-429c-a0f0-f0c6a8b6f9a2@15d82f97-4f15-4ead-9ab6-18aa0cd45388/IncomingWebhook/88dbd64b37de41cf8c542382204e6ae7/7731650f-a7d2-4b94-ad86-14e06a65ea2e/V2zdLMPmpiBguJzF9o1Y5rv0kEMSW9R9SfE-FCZy_Zdd01"

# 資料庫路徑 (統一在此管理)
DB_SCHEDULE = "/opt/beadsops/data/P01_formualte_schedule.db"
DB_PATH = "/opt/beadsops/data/work_orders.db"
DB_BEADS_SYNC = "/opt/beadsops/data/beads_sync.db"
UPLOAD_FOLDER = Path(r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\Photos")
LOCAL_CACHE_DIR = Path("D:/BeadRecord_Cache") 

try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
except Exception as e:
    print(f"⚠️ NAS UPLOAD_FOLDER not available: {e}")

try:
    os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)
except Exception as e:
    print(f"⚠️ LOCAL_CACHE_DIR not available: {e}")

# 欄位定義
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

# 步驟設定
STEP_CONFIG = {
    'receive':          ('時間_收藥',      '收藥_上傳者',      '收藥_照片'),
    'titration_prep':   ('時間_滴定準備',  '滴定準備_上傳者',  '滴定準備_照片'),
    'titration_start':  ('時間_滴定開始',  '滴定開始_上傳者',  '滴定開始_照片'),
    'titration_end':    ('時間_滴定結束',  '滴定結束_上傳者',  '滴定結束_照片'),
    'fd_prep':          ('時間_凍乾準備',  '凍乾準備_上傳者',  '凍乾準備_照片'),
    'fd_start':         ('時間_凍乾開始',  '凍乾開始_上傳者',  '凍乾開始_照片'),
    'fd_end':           ('時間_凍乾結束',  '凍乾結束_上傳者',  '凍乾結束_照片')
}

def get_all_date_formats(dt):
    return [
        f"{dt.year}/{dt.month}/{dt.day}",
        dt.strftime("%Y/%m/%d"),
        dt.strftime("%Y-%m-%d")
    ]

@app.route('/mobile')
@app.route('/mobile/')
def mobile_page():
    return send_from_directory(MOBILE_WEB_DIR, "index.html")

@app.route('/mobile/<path:path>')
def mobile_assets(path):
    target = MOBILE_WEB_DIR / path
    if target.exists() and target.is_file():
        return send_from_directory(MOBILE_WEB_DIR, path)
    if path == "config.js":
        return app.response_class(
            'window.API_BASE = window.location.origin;\n',
            mimetype="application/javascript",
        )
    return jsonify({'ok': False, 'error': 'Mobile asset not found', 'path': path}), 404

# ==========================================
# 2. 核心監控類別 (LyophilizerMonitor)
# ==========================================
class LyophilizerMonitor:
    def __init__(self):
        self.DB_PATHS = {
            "schedule": DB_SCHEDULE,
            "work_order": DB_PATH,
            "limit": DB_BEADS_SYNC
        }
        self.TARGET_MACHINES = [
            "03", "04", "05", "06", "07", 
            "08", "09", "10", "11", "12", "Small"
        ]

    def _get_connection(self, db_key):
        path = self.DB_PATHS.get(db_key)
        if not path or not os.path.exists(path):
            return None
        return sqlite3.connect(path)

    def _str_to_datetime(self, date_val, time_val):
        if not time_val or str(time_val).strip() == "":
            return None
        try:
            dt = pd.to_datetime(time_val, errors="coerce")
            if pd.notna(dt):
                try:
                    dt = dt.tz_localize(None)
                except Exception:
                    pass
                return dt
        except Exception:
            pass
        if not date_val or str(date_val).strip() == "":
            return None
        try:
            d_str = str(date_val).strip().replace("-", "/")
            t_str = str(time_val).strip()
            dt = pd.to_datetime(f"{d_str} {t_str}", errors="coerce")
            if pd.notna(dt):
                try:
                    dt = dt.tz_localize(None)
                except Exception:
                    pass
                return dt
        except Exception:
            pass
        return None

    def _get_drying_duration(self, pn):
        default_duration = 24.0
        try:
            conn = self._get_connection("limit")
            if not conn: return default_duration
            df = pd.read_sql("SELECT [凍乾時間] FROM [配藥限制] WHERE PN=?", conn, params=(pn,))
            conn.close()
            if not df.empty:
                val = df.iloc[0, 0]
                return float(val) if val and str(val).strip() else default_duration
            return default_duration
        except Exception as e:
            print(f"DB Error (Duration): {e}")
            return default_duration

    def _get_status_single(self, freezer_id, now, today_opts, yest_opts):
        status_info = {
            "id": f"Freeze-{freezer_id}" if freezer_id == "Small" else f"Freezer-{freezer_id}", 
            "state": "idle",
            "workOrder": None,
            "remainMin": None
        }
        search_id = "Small" if freezer_id == "Small" else str(freezer_id).zfill(2)
        search_name = f"Freeze-Small" if freezer_id == "Small" else f"Freezer-{str(freezer_id).zfill(2)}"

        try:
            conn_wo = self._get_connection("work_order")
            if not conn_wo:
                status_info["state"] = "error" 
                return status_info

            query_today = f"SELECT * FROM work_orders WHERE [日期] IN {today_opts} AND [凍乾機_1] LIKE ?"
            df_today = pd.read_sql(query_today, conn_wo, params=(f'%{search_name}%',))

            if not df_today.empty:
                row = df_today.iloc[0]
                status_info["workOrder"] = row.get("工單號", row.get("PN", "N/A"))
                pn = row.get("PN")
                raw_date = row.get("日期")
                raw_start = row.get("時間_凍乾開始")
                raw_end = row.get("時間_凍乾結束")
                raw_prep = row.get("時間_凍乾準備")

                if raw_prep and str(raw_prep).strip() and (not raw_start or not str(raw_start).strip()):
                    status_info["state"] = "preparing"
                    conn_wo.close()
                    return status_info

                if raw_start and str(raw_start).strip() and (not raw_end or not str(raw_end).strip()):
                    start_dt = self._str_to_datetime(raw_date, raw_start)
                    if start_dt:
                        duration = self._get_drying_duration(pn)
                        elapsed_hrs = (now - start_dt).total_seconds() / 3600
                        remaining = duration - elapsed_hrs
                        status_info["state"] = "running"
                        status_info["remainMin"] = int(remaining * 60) if remaining > 0 else 0
                    conn_wo.close()
                    return status_info

                if raw_end and str(raw_end).strip():
                    status_info["state"] = "finished"
                    conn_wo.close()
                    return status_info

            conn_sch = self._get_connection("schedule")
            if conn_sch:
                query_sch = f"SELECT * FROM DropletSchedule WHERE [Date] IN {yest_opts} AND [Lyophilizer] LIKE ?"
                df_sch = pd.read_sql(query_sch, conn_sch, params=(f'%{search_id}%',))
                conn_sch.close()

                if not df_sch.empty:
                    query_yest = f"SELECT * FROM work_orders WHERE [日期] IN {yest_opts} AND [凍乾機_1] LIKE ?"
                    df_yest = pd.read_sql(query_yest, conn_wo, params=(f'%{search_name}%',))
                    if not df_yest.empty:
                        row = df_yest.iloc[0]
                        status_info["workOrder"] = row.get("工單號", row.get("PN", "N/A"))
                        raw_date = row.get("日期")
                        raw_start = row.get("時間_凍乾開始")
                        raw_end = row.get("時間_凍乾結束")
                        if raw_end and str(raw_end).strip():
                            status_info["state"] = "idle"
                        elif raw_start and str(raw_start).strip():
                            start_dt = self._str_to_datetime(raw_date, raw_start)
                            if start_dt:
                                duration = self._get_drying_duration(row.get("PN"))
                                elapsed_hrs = (now - start_dt).total_seconds() / 3600
                                remaining = duration - elapsed_hrs
                                if remaining > 0:
                                    status_info["state"] = "running"
                                    status_info["remainMin"] = int(remaining * 60)
                                else:
                                    status_info["state"] = "idle"

            conn_wo.close()
            return status_info

        except Exception as e:
            print(f"Error checking {freezer_id}: {e}")
            status_info["state"] = "error"
            return status_info

    def get_dashboard_data(self):
        now = now_tw()
        yest = now - timedelta(days=1)
        today_list = get_all_date_formats(now)
        yest_list = get_all_date_formats(yest)
        today_opts = f"({', '.join(repr(d) for d in today_list)})"
        yest_opts = f"({', '.join(repr(d) for d in yest_list)})"
        results = []
        for mid in self.TARGET_MACHINES:
            results.append(self._get_status_single(mid, now, today_opts, yest_opts))
        return results

# ==========================================
# 3. 一般 Helper Functions
# ==========================================
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
            conn.commit()
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
    if not os.path.exists(DB_SCHEDULE): return
    try:
        conn_src = sqlite3.connect(DB_SCHEDULE)
        sql_src = "SELECT WorkOrder, Marker, Quantity, Date, Lot, Pump, Lyophilizer FROM DropletSchedule WHERE WorkOrder = ?"
        df_src = pd.read_sql(sql_src, conn_src, params=(target_order_id,))
        if df_src.empty:
            conn_src.close()
            return

        # 優先取有 Pump 的滴定日記錄（配藥日 Pump 為空）
        df_with_pump = df_src[df_src['Pump'].fillna('').str.strip() != '']
        ref_row = df_with_pump.iloc[0] if not df_with_pump.empty else df_src.iloc[0]
        first_row = df_src.iloc[0]
        marker = first_row['Marker']
        qty = first_row['Quantity']
        date = ref_row['Date']
        pump = ref_row['Pump']
        lyo = ref_row['Lyophilizer']

        lots = df_src['Lot'].dropna().tolist()
        lots = [str(x) for x in lots if str(x).strip()]
        lots += [None] * (4 - len(lots))

        formatted_freezer = None
        if lyo and str(lyo).strip():
            s_lyo = str(lyo).strip()
            if s_lyo.lower() == "small":
                formatted_freezer = "Freeze-Small"
            else:
                formatted_freezer = f"Freezer-{s_lyo.zfill(2)}" if s_lyo.isdigit() else s_lyo

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
            ('凍乾機_1', formatted_freezer), ('凍乾機_2', formatted_freezer),
            ('凍乾機_3', formatted_freezer), ('凍乾機_4', formatted_freezer),
            ('Dispense_Lot_1', lots[0]), ('Dispense_Lot_2', lots[1]),
            ('Dispense_Lot_3', lots[2]), ('Dispense_Lot_4', lots[3]),
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

def send_teams_alert(data):
    if not TEAMS_WEBHOOK_URL: return
    try:
        card = {
            "@type": "MessageCard",
            "summary": "異常通報",
            "sections": [{
                "activityTitle": f"🚨 產線異常通報: {data['station']}",
                "facts": [
                    {"name": "描述", "value": data['description']},
                    {"name": "通報人", "value": data['user']},
                    {"name": "時間", "value": data['created_at']}
                ],
                "markdown": True
            }]
        }
        requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=5)
    except Exception as e:
        print(f"❌ Teams send failed: {e}")

def send_teams_resolve_alert(data):
    if not TEAMS_WEBHOOK_URL: return
    try:
        action = data.get('action')
        if action == 'resolve':
            title = f"✅ 異常已處置: {data['station']} {data.get('machine_id','') or ''}".strip()
            extra_fact = {"name": "處置說明", "value": data.get('note', '')}
            color = "00b300"
        else:
            title = f"🔒 異常已簽核結案: {data['station']} {data.get('machine_id','') or ''}".strip()
            extra_fact = {"name": "簽核人", "value": data.get('signer', '')}
            color = "0078d4"
        card = {
            "@type": "MessageCard",
            "themeColor": color,
            "summary": "異常處置通知",
            "sections": [{
                "activityTitle": title,
                "facts": [
                    {"name": "異常描述", "value": data['description']},
                    {"name": "通報人", "value": data['reporter']},
                    {"name": "通報時間", "value": data['created_at']},
                    extra_fact
                ],
                "markdown": True
            }]
        }
        requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=5)
    except Exception as e:
        print(f"❌ Teams resolve alert failed: {e}")

def get_abnormal_stats():
    try:
        now = now_tw()
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

def calc_titration_remaining(start_time_str, quantity):
    try:
        start = datetime.fromisoformat(start_time_str)
    except:
        start = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
    try: qty = float(quantity)
    except: qty = 0
    estimate_hours = qty / 1900 if qty > 0 else 0
    end_time = start + timedelta(hours=estimate_hours)
    remain_min = max(0, int((end_time - now_tw()).total_seconds() / 60))
    return {
        "estimateHours": round(estimate_hours, 2),
        "estimatedEndTime": end_time.strftime("%Y-%m-%d %H:%M"),
        "remainMin": remain_min
    }

def get_pumps_and_quantity(work_order):
    with sqlite3.connect(DB_SCHEDULE) as conn:
        cur = conn.cursor()
        cur.execute("SELECT Pump, Quantity FROM DropletSchedule WHERE WorkOrder = ?", (work_order,))
        rows = cur.fetchall()
    pumps = []
    quantity = 0
    for pump, qty in rows:
        if pump: pumps.append(pump)
        if qty: quantity = qty
    return pumps, quantity

# ==========================================
# 同步手機時間 Helper Functions
# ==========================================
import subprocess
import sys
import time

SYNC_SCRIPT = Path("/opt/beadsops/dropfreeze/sync_droplet_record.py")
SYNC_LOCK = Path("/tmp/droplet_sync.lock")

SYNC_LOCK_TTL = 120  # seconds

def trigger_droplet_sync_safe():
    if SYNC_LOCK.exists():
        age = time.time() - SYNC_LOCK.stat().st_mtime
        if age < SYNC_LOCK_TTL:
            return
        SYNC_LOCK.unlink(missing_ok=True)
    try:
        SYNC_LOCK.parent.mkdir(parents=True, exist_ok=True)
        SYNC_LOCK.write_text(str(time.time()))
        subprocess.Popen(
            [sys.executable, str(SYNC_SCRIPT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"⚠️ Sync trigger failed: {e}")

# ==========================================
# 4. API Routes
# ==========================================

@app.route('/photos/<path:filename>')
def serve_photo(filename):
    # Try workorder_photo first, then abnormal_photo
    for prefix in ["workorder_photo", "abnormal_photo"]:
        s3_key = f"{prefix}/{filename}"
        try:
            s3_client.head_object(Bucket=S3_BUCKET, Key=s3_key)
            return redirect(get_s3_url(s3_key))
        except:
            continue
    # Fallback: try direct S3 key
    return redirect(get_s3_url(f"workorder_photo/{filename}"))


STATUS_STYLE = {
    "idle": {"bg": "#052e16", "color": "#22c55e", "label": "IDLE"},
    "preparing": {"bg": "#082f49", "color": "#38bdf8", "label": "PREPARING"},
    "running": {"bg": "#450a0a", "color": "#ef4444", "label": "RUNNING"},
    "finished": {"bg": "#2e1065", "color": "#a855f7", "label": "FINISHED"},
    "reserved": {"bg": "#422006", "color": "#eab308", "label": "RESERVED"},
    "error": {"bg": "#431407", "color": "#f97316", "label": "ERROR"},
}

@app.route("/api/ops/freeze-status", methods=["GET"])
def ops_freeze_status():
    print("❄️ ops_freeze_status CALLED")

    def _calc_state_from_row(monitor, now_dt, row):
        if not row:
            return {"state": "idle", "workOrder": None, "remainMin": None, "pn": None}

        def _is_blank(v):
            return v is None or (isinstance(v, str) and v.strip() == "")

        wo = row.get("工單號")
        pn = row.get("PN")
        date_val = row.get("日期")
        prep = row.get("時間_凍乾準備")
        start = row.get("時間_凍乾開始")
        end = row.get("時間_凍乾結束")

        if not _is_blank(end):
            return {"state": "finished", "workOrder": wo, "remainMin": None, "pn": pn}

        if not _is_blank(start):
            start_dt = monitor._str_to_datetime(date_val, start)
            if start_dt is None:
                return {"state": "running", "workOrder": wo, "remainMin": None, "pn": pn}
            try:
                duration_hr = float(monitor._get_drying_duration(pn))
            except:
                duration_hr = 24.0
            elapsed_hr = (now_dt - start_dt).total_seconds() / 3600.0
            remain_hr = duration_hr - elapsed_hr
            if remain_hr > 0:
                return {"state": "running", "workOrder": wo, "remainMin": int(remain_hr * 60), "pn": pn}
            else:
                return {"state": "finished", "workOrder": wo, "remainMin": None, "pn": pn}

        if not _is_blank(prep):
            return {"state": "preparing", "workOrder": wo, "remainMin": None, "pn": pn}

        return {"state": "idle", "workOrder": wo, "remainMin": None, "pn": pn}

    try:
        monitor = LyophilizerMonitor()
        now = now_tw()

        def get_date_variants(dt):
            return [
                f"{dt.year}/{dt.month}/{dt.day}",
                dt.strftime("%Y/%m/%d"),
                dt.strftime("%Y-%m-%d")
            ]

        today_dates = get_date_variants(now)
        yest = now - timedelta(days=1)
        yest_dates = get_date_variants(yest)
        date_strs = list(set(today_dates + yest_dates))
        placeholders = ','.join(['?'] * len(date_strs))

        conn_wo = monitor._get_connection("work_order")
        conn_sch = monitor._get_connection("schedule")

        if not conn_wo or not conn_sch:
            return jsonify({"error": "DB connection failed"}), 500

        df_sch = pd.read_sql(
            f"SELECT WorkOrder, Lyophilizer FROM DropletSchedule WHERE Date IN ({placeholders})",
            conn_sch, params=date_strs
        )

        schedule_map = {}
        for _, r in df_sch.iterrows():
            ly = r["Lyophilizer"]
            wo = r["WorkOrder"]
            if ly is None or wo is None:
                continue
            fid = str(ly).strip()
            schedule_map.setdefault(fid, []).append(str(wo).strip())

        resources = []

        for mid in monitor.TARGET_MACHINES:
            rid = "Freeze-Small" if mid == "Small" else f"Freezer-{str(mid).zfill(2)}"
            fid = "Small" if mid == "Small" else str(int(mid))

            row = None
            if fid == "Small":
                sql = f"""
                    SELECT 工單號, PN, 日期, 凍乾機_1,
                           時間_凍乾準備, 時間_凍乾開始, 時間_凍乾結束
                    FROM work_orders
                    WHERE 日期 IN ({placeholders})
                    AND 凍乾機_1 LIKE '%Small%'
                    ORDER BY 日期 DESC, id DESC
                """
                df = pd.read_sql(sql, conn_wo, params=date_strs)
            else:
                num = str(fid).zfill(2)
                sql = f"""
                    SELECT 工單號, PN, 日期, 凍乾機_1,
                           時間_凍乾準備, 時間_凍乾開始, 時間_凍乾結束
                    FROM work_orders
                    WHERE 日期 IN ({placeholders})
                    AND (凍乾機_1 LIKE ? OR 凍乾機_1 LIKE ?)
                    ORDER BY 日期 DESC, id DESC
                """
                params = date_strs + [f"%Freezer-{num}%", f"%Freezer {num}%"]
                df = pd.read_sql(sql, conn_wo, params=params)

            if not df.empty:
                row = dict(df.iloc[0])

            actual = _calc_state_from_row(monitor, now, row)
            state = actual["state"]
            work_order = actual["workOrder"]
            remain_min = actual["remainMin"]

            reserved_info = None
            if state == "idle" and fid in schedule_map:
                state = "reserved"
                work_order = schedule_map[fid][0]
                reserved_info = {"workOrder": work_order}

            hover = {"running": [], "nextSchedule": None}
            if fid in schedule_map:
                hover["nextSchedule"] = {
                    "date": now.strftime('%Y/%m/%d'),
                    "workOrders": schedule_map[fid]
                }

            resources.append({
                "id": rid,
                "state": state,
                "workOrder": work_order,
                "remainMin": remain_min,
                "hover": hover,
                "reserved": reserved_info,
                "style": STATUS_STYLE.get(state, STATUS_STYLE["error"]),
            })

        conn_wo.close()
        conn_sch.close()

        total = len(resources)
        in_use = sum(1 for r in resources if r["state"] != "idle")

        return jsonify({
            "freezersTotal": total,
            "freezersInUse": in_use,
            "freeFreezers": total - in_use,
            "resources": resources,
            "statusStyle": STATUS_STYLE,
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S")
        })

    except Exception as e:
        print("🔴 ops_freeze_status error:", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/ops/titration-status", methods=["GET"])
def ops_titration_status():
    print("🟢 ops_titration_status CALLED")

    now = now_tw()
    today_str = now.strftime("%Y-%m-%d")

    ivek = {
        "id": "IVEK", "type": "IVEK", "state": "idle",
        "currentJob": None, "remainMin": None, "todayUsed": False,
    }

    port_map = {}
    for i in range(1, 13):
        pid = f"Port-{i:02d}"
        port_map[pid] = {"id": pid, "type": "PORT", "state": "idle", "currentJob": None, "remainMin": None}

    jobs = []
    used_ports = set()

    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # 用 時間_滴定開始 的日期判斷，不依賴 日期 欄位（日期欄位可能因配藥日/滴定日落差而錯誤）
        sql = """
            SELECT 工單號, bead_name, 時間_滴定開始
            FROM work_orders
            WHERE 時間_滴定開始 IS NOT NULL
              AND (時間_滴定結束 IS NULL OR 時間_滴定結束 = '')
              AND substr(時間_滴定開始, 1, 10) = ?
        """
        cur.execute(sql, (today_str,))
        running_orders = cur.fetchall()

    with sqlite3.connect(DB_SCHEDULE) as conn_sch:
        cur_sch = conn_sch.cursor()
        for row in running_orders:
            wo = row["工單號"]
            marker = row["bead_name"] or ""
            try:
                start_time = datetime.strptime(row["時間_滴定開始"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

            cur_sch.execute("SELECT Pump, Quantity FROM DropletSchedule WHERE WorkOrder = ?", (wo,))
            sch_rows = cur_sch.fetchall()
            if not sch_rows:
                continue

            job_pumps_list = []
            job_display_quantity = 0
            max_remain_min = 0
            final_end_time = start_time

            for sch in sch_rows:
                pump_raw, quantity_raw = sch
                try: q = int(quantity_raw or 0)
                except: q = 0

                job_display_quantity = max(job_display_quantity, q)
                estimate_hours = q / 1900 if q > 0 else 0
                port_end_time = start_time + timedelta(hours=estimate_hours)
                r_min = max(0, int((port_end_time - now).total_seconds() / 60))

                if r_min > max_remain_min:
                    max_remain_min = r_min
                    final_end_time = port_end_time

                raw_pump_str = str(pump_raw).strip() if pump_raw else ""
                current_pumps = [p.strip() for p in raw_pump_str.split(',') if p.strip()]

                for single_pump in current_pumps:
                    u_pump = single_pump.upper()
                    if "IVEK" in u_pump:
                        ivek["state"] = "running"
                        ivek["currentJob"] = wo
                        ivek["remainMin"] = r_min
                        ivek["todayUsed"] = True
                        job_pumps_list.append("IVEK")
                    elif "PORT" in u_pump:
                        m = re.search(r"(\d+)", single_pump)
                        if m:
                            p_num = int(m.group(1))
                            pid = f"Port-{p_num:02d}"
                            if pid in port_map:
                                port_map[pid]["state"] = "running"
                                port_map[pid]["currentJob"] = wo
                                port_map[pid]["remainMin"] = r_min
                                used_ports.add(pid)
                            job_pumps_list.append(pid)

            jobs.append({
                "workOrder": wo,
                "marker": marker,
                "quantity": job_display_quantity,
                "pumps": list(set(job_pumps_list)),
                "estimateHours": round(max_remain_min / 60, 2),
                "estimatedEndTime": final_end_time.strftime("%Y-%m-%d %H:%M:%S"),
                "remainMin": max_remain_min,
            })

    ports_total = 12
    ports_in_use = len(used_ports)
    next_release = min([j["remainMin"] for j in jobs if j["remainMin"] > 0], default=None)
    resources = [ivek] + list(port_map.values())

    return jsonify({
        "portsTotal": ports_total,
        "portsInUse": ports_in_use,
        "freePorts": ports_total - ports_in_use,
        "nextReleaseMin": next_release,
        "jobs": jobs,
        "resources": resources,
    })

@app.route('/ping')
def ping():
    return jsonify({'ok': True, 'msg': 'pong'})

# 異常相關 API
@app.route('/api/latest_abnormal', methods=['GET'])
def get_latest_abnormal():
    try:
        stats = get_abnormal_stats()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, station, machine_id, description, created_at, user, photos, is_resolved, resolution_note, status, signer FROM abnormal_history WHERE status = 0 ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            abnormal_data = None
            if row:
                abnormal_data = {
                    'id': row[0], 'station': row[1], 'machine_id': row[2], 'description': row[3],
                    'created_at': row[4], 'user': row[5], 'photos': row[6], 'status': row[9] if len(row) > 9 else 0
                }
            return jsonify({'ok': True, 'stats': stats, 'abnormal': abnormal_data})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/today_abnormals', methods=['GET'])
def get_today_abnormals():
    try:
        today_str = now_tw().strftime('%Y-%m-%d')
        with get_db_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM abnormal_history WHERE created_at LIKE ? ORDER BY created_at DESC", (f"{today_str}%",))
            return jsonify({'ok': True, 'data': [dict(r) for r in cursor.fetchall()]})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/resolve_abnormal', methods=['POST'])
def resolve_abnormal():
    try:
        data = request.get_json()
        record_id, action = data.get('id'), data.get('action')
        note, signer, pin = data.get('note', ''), data.get('signer', ''), data.get('pin', '')
        orig = None
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT station, machine_id, description, user, created_at FROM abnormal_history WHERE id=?", (record_id,))
            orig = cursor.fetchone()
            if action == 'resolve':
                cursor.execute("UPDATE abnormal_history SET status=1, is_resolved=1, resolution_note=? WHERE id=?", (note, record_id))
            elif action == 'signoff':
                if pin != ADMIN_PIN: return jsonify({'ok': False, 'error': 'PIN碼錯誤'}), 403
                cursor.execute("UPDATE abnormal_history SET status=2, signer=? WHERE id=?", (signer, record_id))
            conn.commit()
        if orig:
            resolve_msg = {'station': orig[0], 'machine_id': orig[1], 'description': orig[2],
                           'reporter': orig[3], 'created_at': orig[4],
                           'action': action, 'note': note, 'signer': signer}
            threading.Thread(target=send_teams_resolve_alert, args=(resolve_msg,)).start()
        stats = get_abnormal_stats()
        socketio.emit('count_update', {'stats': stats})
        # Emit current unresolved alert so dashboard updates/clears immediately
        with get_db_connection() as conn2:
            cur2 = conn2.cursor()
            cur2.execute(
                "SELECT id, station, machine_id, description, created_at, user, photos, status "
                "FROM abnormal_history WHERE status = 0 ORDER BY id DESC LIMIT 1"
            )
            next_row = cur2.fetchone()
        next_abnormal = None
        if next_row:
            next_abnormal = {
                'id': next_row[0], 'station': next_row[1], 'machine_id': next_row[2],
                'description': next_row[3], 'created_at': next_row[4],
                'user': next_row[5], 'photos': next_row[6], 'status': next_row[7]
            }
        socketio.emit('latest_abnormal', {'abnormal': next_abnormal, 'stats': stats})
        return jsonify({'ok': True, 'stats': stats})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/abnormal_record', methods=['POST'])
def add_abnormal_record():
    try:
        station = request.form.get('station')
        machine_id = request.form.get('machine_id')
        description = request.form.get('description')
        user = request.form.get('user', 'Unknown')
        created_at = request.form.get('created_at') or now_tw().strftime('%Y-%m-%d %H:%M')

        if not station or not description:
            return jsonify({'ok': False, 'error': 'Missing fields'}), 400

        files = request.files.getlist('photos')
        saved_filenames = []
        if files:
            for idx, file in enumerate(files):
                if file:
                    _station = re.sub(r"[\\w]", "", str(station))
                    _ts = now_tw().strftime("%Y%m%d_%H%M%S")
                    fname = f"Abnormal_{_station}_{_ts}_{idx}.jpg"
                    try:
                        file_bytes = file.read()
                        s3_key = f"abnormal_photo/{fname}"
                        upload_to_s3(file_bytes, s3_key)
                        saved_filenames.append(fname)
                        print(f"  S3 uploaded: {s3_key}")
                    except Exception as e:
                        print(f"  S3 upload failed: {e}")

        photo_str = ";".join(saved_filenames)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO abnormal_history (station, machine_id, description, created_at, user, photos, status, is_resolved) VALUES (?, ?, ?, ?, ?, ?, 0, 0)",
                (station, machine_id, description, created_at, user, photo_str)
            )
            conn.commit()
            new_id = cursor.lastrowid

        threading.Thread(target=send_teams_alert, args=({'station': station, 'machine_id': machine_id, 'description': description, 'user': user, 'created_at': created_at},)).start()

        stats = get_abnormal_stats()
        socketio.emit('new_abnormal', {
            'id': new_id, 'station': station, 'machine_id': machine_id,
            'description': description, 'created_at': created_at,
            'user': user, 'photos': photo_str, 'stats': stats
        })
        return jsonify({'ok': True, 'msg': 'Record saved'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

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
    except:
        return jsonify({'ok': True, 'issues': defs})

# ==========================================
# 5. Mobile / App APIs
# ==========================================
@app.route('/api/mobile/work-orders', methods=['GET'])
def mobile_get_orders():
    try:
        if not os.path.exists(DB_SCHEDULE):
            return jsonify({'ok': False, 'error': "DB Not Found"}), 500

        today = now_tw()
        all_dates = []
        for i in range(3):
            target_day = today - timedelta(days=i)
            all_dates.extend(get_all_date_formats(target_day))
        all_dates = list(set(all_dates))
        sql_params = [f"{d}%" for d in all_dates]

        with sqlite3.connect(DB_SCHEDULE) as conn:
            cursor = conn.cursor()
            conds = " OR ".join(["Date LIKE ?" for _ in sql_params])
            sql = f"SELECT WorkOrder, Marker, Date, Pump, DrugGivenAt FROM DropletSchedule WHERE WorkOrder IS NOT NULL AND WorkOrder != '' AND ({conds})"
            cursor.execute(sql, sql_params)

            orders_map = {}
            for row in cursor.fetchall():
                wo, marker, date_str, pump, time_str = row
                if not (wo.startswith("TMRA") or wo.startswith("UMR")): continue

                pump = str(pump).upper() if pump else ""
                # 跳過沒有 Pump 的配藥日記錄（手機端只顯示滴定日）
                if not pump:
                    continue
                try: hour = int(str(time_str).split(':')[0])
                except: hour = 0

                score = 999
                if "IVEK" in pump:
                    score = 0
                elif "PORT" in pump:
                    try: port_num = int(re.search(r'\d+', pump).group())
                    except: port_num = 99
                    score = (200 if hour >= 12 else 100) + port_num

                if wo not in orders_map or score < orders_map[wo]['best_score']:
                    orders_map[wo] = {
                        'work_order': wo, 'marker': marker or '', 'date': date_str,
                        'best_score': score, 'pump_info': pump, 'time_info': time_str or "00:00"
                    }

        def _parse_date(date_str):
            try:
                parts = str(date_str).strip().replace('-', '/').split('/')
                return datetime(int(parts[0]), int(parts[1]), int(parts[2]))
            except:
                return datetime.min

        orders = sorted(
            list(orders_map.values()),
            key=lambda x: (x['best_score'], -_parse_date(x['date']).timestamp())
        )
        return jsonify({'ok': True, 'orders': orders})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/mobile/check-access', methods=['GET'])
def mobile_check_access():
    work_order = request.args.get('work_order')
    if not work_order:
        return jsonify({'ok': False, 'msg': 'Missing Work Order'}), 400
    if work_order.startswith("UMRZ"):
        return jsonify({'ok': True, 'allowed': True})
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
                    if cursor.fetchone():
                        return jsonify({'ok': True, 'allowed': True})
            return jsonify({'ok': True, 'allowed': False, 'msg': '5714 Prep not completed'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

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
                    steps[step_id] = {
                        'timestamp': data.get(t_col),
                        'user': data.get(u_col),
                        'photoName': data.get(p_col)
                    }

            return jsonify({
                'ok': True,
                'steps': steps,
                'details': {**data, 'freezer_plan': data.get('凍乾機_1', '未指定')}
            })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/mobile/update-freezer', methods=['POST'])
def mobile_update_freezer():
    try:
        d = request.get_json()
        with get_db_connection() as conn:
            conn.execute('UPDATE work_orders SET "凍乾機_1" = ? WHERE 工單號 = ?', (d.get('freezer'), d.get('work_order')))
            conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/mobile/upload', methods=['POST'])
def mobile_upload():
    print("🔔 [Mobile] Photo Upload Called...")
    try:
        order = request.form.get('work_order')
        step_id = request.form.get('step_id')
        user = request.form.get('user')
        file = request.files.get('photo')

        if not all([order, step_id, user]):
            return jsonify({'ok': False, 'msg': 'Params missing'}), 400

        config = STEP_CONFIG.get(step_id)
        if not config:
            return jsonify({'ok': False, 'msg': 'Invalid step'}), 400
        t_col, u_col, p_col = config

        filename = ""
        if file:
            fname = f"{order}_{step_id}_{now_tw().strftime('%Y%m%d_%H%M%S')}.jpg"
            try:
                file_bytes = file.read()
                s3_key = f"workorder_photo/{fname}"
                upload_to_s3(file_bytes, s3_key)
                filename = fname
                print(f"  S3 uploaded: {s3_key}")
            except Exception as e:
                print(f"  S3 upload failed: {e}")

        cur_time = now_tw().strftime('%Y-%m-%d %H:%M:%S')
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM work_orders WHERE 工單號 = ?", (order,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO work_orders (工單號) VALUES (?)", (order,))

            cursor.execute(f'SELECT "{p_col}" FROM work_orders WHERE 工單號 = ?', (order,))
            row = cursor.fetchone()
            exist_ph = row[0] if row else ""
            final_ph = f"{exist_ph};{filename}" if exist_ph and filename else (filename or exist_ph)

            cursor.execute(
                f'UPDATE work_orders SET "{t_col}"=?, "{u_col}"=?, "{p_col}"=? WHERE 工單號=?',
                (cur_time, user, final_ph, order)
            )
            conn.commit()
            trigger_droplet_sync_safe()

        return jsonify({'ok': True, 'timestamp': cur_time, 'photoName': final_ph})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/mobile/delete-photo', methods=['POST'])
def delete_photo():
    """Delete a photo from S3 and remove from work_orders DB"""
    try:
        data = request.get_json(force=True)
        work_order = data.get('work_order')
        step_id = data.get('step_id')
        filename = data.get('filename')

        if not all([work_order, step_id, filename]):
            return jsonify({'ok': False, 'msg': 'Missing params'}), 400

        config = STEP_CONFIG.get(step_id)
        if not config:
            return jsonify({'ok': False, 'msg': 'Invalid step'}), 400
        t_col, u_col, p_col = config

        # Delete from S3
        for prefix in ["workorder_photo", "abnormal_photo"]:
            try:
                s3_client.delete_object(Bucket=S3_BUCKET, Key=f"{prefix}/{filename}")
            except:
                pass

        # Remove filename from DB
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f'SELECT "{p_col}" FROM work_orders WHERE 工單號 = ?', (work_order,))
            row = cursor.fetchone()
            if row and row[0]:
                photos = [p.strip() for p in row[0].split(';') if p.strip() and p.strip() != filename]
                new_photo_str = ';'.join(photos)
                cursor.execute(f'UPDATE work_orders SET "{p_col}" = ? WHERE 工單號 = ?', (new_photo_str, work_order))
                conn.commit()

        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/analyze-image', methods=['POST', 'OPTIONS'])
def analyze_image():
    """
    AI 圖片檢查端點。
    目前版本：直接放行（pass=True），不做實際 AI 判讀。
    日後可接 Claude / Azure Vision API 做真正的機台設定驗證。
    """
    if request.method == 'OPTIONS':
        return '', 204

    try:
        data = request.get_json(force=True)
        step_id   = data.get('step_id', '')
        work_order = data.get('work_order', '')
        # image = data.get('image', '')  # base64，留待日後使用

        # ---- 預留：日後在此呼叫 Vision API ----
        # 目前直接放行
        return jsonify({
            'pass': True,
            'warning': False,
            'action': None,
            'msg': ''          # 空字串 → handleUpload 不會跳 alert
        })

    except Exception as e:
        return jsonify({'pass': False, 'msg': f'Server error: {e}'}), 500

# ==========================================
# 6. Main Execution
# ==========================================
if __name__ == "__main__":
    init_db()
    init_abnormal_db()
    port = int(os.environ.get("PORT", 5100))
    print(f"🚀 Flask-SocketIO Server Running on http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, threaded=True, debug=False)
