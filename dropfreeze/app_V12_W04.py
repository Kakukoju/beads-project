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
import math
import traceback
import requests
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!' 
CORS(app)

socketio = SocketIO(app, cors_allowed_origins="*") 

# ==========================================
# 1. 全域配置 (Configuration)
# ==========================================
DB_TIMEOUT = 5.0
ADMIN_PIN = "36121288" # 主管簽核密碼

# Teams Webhook
TEAMS_WEBHOOK_URL = "https://skylamb.webhook.office.com/webhookb2/721d0e06-4ea4-429c-a0f0-f0c6a8b6f9a2@15d82f97-4f15-4ead-9ab6-18aa0cd45388/IncomingWebhook/88dbd64b37de41cf8c542382204e6ae7/7731650f-a7d2-4b94-ad86-14e06a65ea2e/V2zdLMPmpiBguJzF9o1Y5rv0kEMSW9R9SfE-FCZy_Zdd01"

# 資料庫路徑 (統一在此管理)
DB_SCHEDULE = r"D:\配藥表\資料庫\P01_formualte_schedule.db"
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"
DB_BEADS_SYNC = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\beads_sync.db"
UPLOAD_FOLDER = Path(r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\Photos")
LOCAL_CACHE_DIR = Path("D:/BeadRecord_Cache") 

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOCAL_CACHE_DIR, exist_ok=True)

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
    """
    產生三種日期格式，確保能抓到資料庫中不同寫法的日期
    1. 2026/1/19 (單碼不補零)
    2. 2026/01/19 (補零)
    3. 2026-01-19 (ISO)
    """
    return [
        f"{dt.year}/{dt.month}/{dt.day}",  # 關鍵：解決 2026/1/19
        dt.strftime("%Y/%m/%d"),           # 解決 2026/01/19
        dt.strftime("%Y-%m-%d")            # 解決 2026-01-19
    ]
# ==========================================
# 2. 核心監控類別 (LyophilizerMonitor)
# ==========================================
class LyophilizerMonitor:
    def __init__(self):
        # 直接使用全域變數，確保路徑一致
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
        """
        支援三種情況：
        1. 日期 + 時間（2025/12/04 + 13:50:51）
        2. 時間欄位本身就是完整 datetime（2025-12-04 13:50:51）
        3. 任一缺失 → None
        回傳 tz-naive datetime
        """
        if not time_val or str(time_val).strip() == "":
            return None

        # Case 1：time_val 本身已是完整 datetime
        try:
            dt = pd.to_datetime(time_val, errors="coerce")
            if pd.notna(dt):
                # 移除 timezone（若有）
                try:
                    dt = dt.tz_localize(None)
                except Exception:
                    pass
                return dt
        except Exception:
            pass

        # Case 2：日期 + 時間 分開儲存
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
        # 建立符合前端格式的物件
        status_info = {
            "id": f"Freeze-{freezer_id}" if freezer_id == "Small" else f"Freezer-{freezer_id}", 
            "state": "idle",   # idle, preparing, running, finished, error
            "workOrder": None,
            "remainMin": None
        }
        # 為了 SQL 查詢方便，轉換 ID 格式
        search_id = "Small" if freezer_id == "Small" else str(freezer_id).zfill(2)
        search_name = f"Freeze-Small" if freezer_id == "Small" else f"Freezer-{str(freezer_id).zfill(2)}"

        try:
            conn_wo = self._get_connection("work_order")
            if not conn_wo:
                status_info["state"] = "error" 
                return status_info

            # --- 步驟 1: 檢查今日 (使用 work_orders) ---
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

                # A: 預冷中
                if raw_prep and str(raw_prep).strip() and (not raw_start or not str(raw_start).strip()):
                    status_info["state"] = "preparing"
                    conn_wo.close()
                    return status_info

                # B: 凍乾中
                if raw_start and str(raw_start).strip() and (not raw_end or not str(raw_end).strip()):
                    start_dt = self._str_to_datetime(raw_date, raw_start)
                    if start_dt:
                        duration = self._get_drying_duration(pn)
                        elapsed_hrs = (now - start_dt).total_seconds() / 3600
                        remaining = duration - elapsed_hrs
                        
                        if remaining > 0:
                            status_info["state"] = "running"
                            status_info["remainMin"] = int(remaining * 60)
                        else:
                            status_info["state"] = "running"
                            status_info["remainMin"] = 0 
                    
                    conn_wo.close()
                    return status_info

                # C: 已完成
                if raw_end and str(raw_end).strip():
                    status_info["state"] = "finished"
                    conn_wo.close()
                    return status_info

            # --- 步驟 2: 檢查跨日 ---
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
        """抓取所有機台資料"""
        now = datetime.now().replace(tzinfo=None)
        yest = now - timedelta(days=1)
        
        # --- 🔥 修改開始：使用 Helper 函式產生 SQL IN 的字串 ---
        today_list = get_all_date_formats(now)
        yest_list = get_all_date_formats(yest)
        
        # 轉換成 SQL 語法: ('2026/1/19', '2026/01/19', '2026-01-19')
        today_opts = f"({', '.join(repr(d) for d in today_list)})"
        yest_opts = f"({', '.join(repr(d) for d in yest_list)})"
        # --- 🔥 修改結束 ---

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

# 工單同步邏輯
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
            # 統一存為 Freezer-0X 格式，方便後續查詢
            if s_lyo.lower() == "small":
                formatted_freezer = "Freeze-Small"
            else:
                formatted_freezer = f"Freezer-{s_lyo.zfill(2)}" if s_lyo.isdigit() else s_lyo

        # ... (省略中間詳細查詢 5714/QC 資料的邏輯，保持原樣即可) ...
        # 這裡為了簡化顯示，假設中間邏輯不變
        
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
            # ... 其他欄位保持原樣
        ]

        # 執行 Update
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

def get_abnormal_stats():
    try:
        now = datetime.now().replace(tzinfo=None)
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

    estimate_hours = qty / 1500 if qty > 0 else 0
    end_time = start + timedelta(hours=estimate_hours)
    remain_min = max(0, int((end_time - datetime.now()).total_seconds() / 60))

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
from pathlib import Path
import time

SYNC_SCRIPT = Path(
    r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Bead-record AN\WebApp\dropfreeze\sync_droplet_record.py"
)
SYNC_LOCK = Path(r"D:\temp\droplet_sync.lock")

def trigger_droplet_sync_safe():
    """
    work_orders 寫完後呼叫
    只負責觸發同步，不處理任何資料
    """
    if SYNC_LOCK.exists():
        return

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
    try:
        local_file = LOCAL_CACHE_DIR / filename
        if local_file.exists():
            return send_from_directory(LOCAL_CACHE_DIR, filename)
        return send_from_directory(UPLOAD_FOLDER, filename)
    except Exception as e:
        return jsonify({'error': 'Photo not found'}), 404
    
# =========================
# 凍乾機狀態顏色定義（主狀態）
# =========================
STATUS_STYLE = {
    "idle":      {"label": "IDLE",      "color": "#22c55e", "bg": "#052e16"},
    "reserved":  {"label": "RESERVED",  "color": "#eab308", "bg": "#422006"},
    "preparing": {"label": "PREPARING", "color": "#38bdf8", "bg": "#082f49"},
    "running":   {"label": "RUNNING",   "color": "#ef4444", "bg": "#450a0a"},
    "finished":  {"label": "FINISHED",  "color": "#a855f7", "bg": "#2e1065"},
    "error":     {"label": "ERROR",     "color": "#f97316", "bg": "#431407"},
}

# =========================
# Reserved 子狀態顏色（右上小 badge 用）
# =========================
RESERVED_BADGE_STYLE = {"label": "RESERVED", "color": "#eab308", "bg": "#422006"}


@app.route("/api/ops/freeze-status", methods=["GET"])
def ops_freeze_status():
    print("❄️ ops_freeze_status CALLED")
    
    # ----------------------------------------------------
    # Helper: 狀態計算 (保持原樣)
    # ----------------------------------------------------
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

        # Finished
        if not _is_blank(end):
            return {"state": "finished", "workOrder": wo, "remainMin": None, "pn": pn}

        # Running
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
                return {
                    "state": "running",
                    "workOrder": wo,
                    "remainMin": int(remain_hr * 60),
                    "pn": pn,
                }
            else:
                return {"state": "finished", "workOrder": wo, "remainMin": None, "pn": pn}

        # Preparing
        if not _is_blank(prep):
            return {"state": "preparing", "workOrder": wo, "remainMin": None, "pn": pn}

        return {"state": "idle", "workOrder": wo, "remainMin": None, "pn": pn}

    try:
        monitor = LyophilizerMonitor()
        now = datetime.now().replace(tzinfo=None)

        # ==========================================
        # 🔥 修改區域：產生三種日期格式
        # ==========================================
        def get_date_variants(dt):
            return [
                f"{dt.year}/{dt.month}/{dt.day}",   # 2026/1/9 (單碼)
                dt.strftime("%Y/%m/%d"),            # 2026/01/09 (補零)
                dt.strftime("%Y-%m-%d")             # 2026-01-09 (ISO)
            ]

        today_dates = get_date_variants(now)
        yest = now - timedelta(days=1)
        yest_dates = get_date_variants(yest)

        # 合併今天與昨天所有可能的格式，並去重
        date_strs = list(set(today_dates + yest_dates))
        
        # 建立 SQL 動態佔位符 (例如: ?,?,?,?,?)
        placeholders = ','.join(['?'] * len(date_strs))
        # ==========================================

        conn_wo = monitor._get_connection("work_order")
        conn_sch = monitor._get_connection("schedule")

        if not conn_wo or not conn_sch:
            return jsonify({"error": "DB connection failed"}), 500

        # ----------------------------------------------------
        # 1️⃣ 一次抓今天 / 昨天的排程
        #    使用動態佔位符
        # ----------------------------------------------------
        df_sch = pd.read_sql(
            f"""
            SELECT WorkOrder, Lyophilizer, Date  -- 🔥 新增 Date
            FROM DropletSchedule
            WHERE Date IN ({placeholders})
            """,
            conn_sch,
            params=date_strs
        )

        # 2️⃣ 修改 Map 結構：同時儲存日期
        schedule_map = {}
        for _, r in df_sch.iterrows():
            ly = r["Lyophilizer"]
            wo = r["WorkOrder"]
            raw_date = r["Date"]

            # 🛑 防呆：如果 凍乾機 或 工單 是空的，直接跳過
            if not ly or str(ly).strip() == "" or not wo or str(wo).strip() == "":
                continue

            fid = str(ly).strip()
            
            if fid not in schedule_map:
                schedule_map[fid] = {"date": raw_date, "orders": []}
            
            schedule_map[fid]["orders"].append(str(wo).strip())

        resources = []

        # ----------------------------------------------------
        # 2️⃣ 每一台凍乾機
        # ----------------------------------------------------
        for mid in monitor.TARGET_MACHINES:
            rid = "Freeze-Small" if mid == "Small" else f"Freezer-{str(mid).zfill(2)}"
            fid = "Small" if mid == "Small" else str(int(mid))

            # --- Step A: work_orders 判斷 (SQL 也需更新佔位符) ---
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
                # 注意參數順序：先放日期列表，再放凍乾機條件
                params = date_strs + [f"%Freezer-{num}%", f"%Freezer {num}%"]
                df = pd.read_sql(sql, conn_wo, params=params)

            if not df.empty:
                row = dict(df.iloc[0])

            actual = _calc_state_from_row(monitor, now, row)
            state = actual["state"]
            work_order = actual["workOrder"]
            remain_min = actual["remainMin"]

            # ------------------------------------------------
            # Step B: RESERVED (修正版 - 防呆)
            # ------------------------------------------------
            reserved_info = None
            
            # 1. 確保 fid 存在
            # 2. 確保 orders 列表不是空的 (防呆)
            if state == "idle" and fid in schedule_map and schedule_map[fid]["orders"]:
                
                sch_data = schedule_map[fid]
                sch_date = sch_data.get("date", "")
                sch_orders = sch_data.get("orders", [])

                # --- 檢查日期是否為今天 ---
                is_today_schedule = False
                for t_str in today_dates:
                    if t_str in str(sch_date):
                        is_today_schedule = True
                        break
                
                # --- 只有今天的排程才顯示 RESERVED ---
                if is_today_schedule:
                    state = "reserved"
                    work_order = sch_orders[0]  # ✅ 安全：因為前面已檢查過列表不為空
                    reserved_info = {"workOrder": work_order}

            # ------------------------------------------------
            # Step C: hover
            # ------------------------------------------------
            hover = {
                "running": [],
                "nextSchedule": None
            }

            if fid in schedule_map:
                db_date_str = schedule_map[fid]["date"]
                
                # 嘗試格式化日期 (可選，視 DB 存的格式而定)
                display_date = db_date_str
                try:
                    # 如果 DB 存的是 2026-01-20，轉成 2026/01/20 統一格式
                    d_obj = pd.to_datetime(db_date_str)
                    display_date = d_obj.strftime('%Y/%m/%d')
                except:
                    pass

                hover["nextSchedule"] = {
                    "date": display_date, # 顯示用的格式維持統一即可
                    "workOrders": schedule_map[fid]["orders"]
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

    now = datetime.now().replace(tzinfo=None)

    # ==========================================
    # 🔥 修改區域：產生三種今日日期格式
    # ==========================================
    today_formats = [
        f"{now.year}/{now.month}/{now.day}",   # 2026/1/9
        now.strftime("%Y/%m/%d"),             # 2026/01/09
        now.strftime("%Y-%m-%d")              # 2026-01-09
    ]
    # 建立 IN (?,?,?) 佔位符
    placeholders = ','.join(['?'] * len(today_formats))
    # ==========================================

    # -----------------------------
    # 初始化資源
    # -----------------------------
    ivek = {
        "id": "IVEK",
        "type": "IVEK",
        "state": "idle",
        "currentJob": None,
        "remainMin": None,
        "todayUsed": False,
    }

    port_map = {}
    for i in range(1, 13):
        pid = f"Port-{i:02d}"
        port_map[pid] = {
            "id": pid,
            "type": "PORT",
            "state": "idle",
            "currentJob": None,
            "remainMin": None,
        }

    jobs = []
    used_ports = set()

    # -----------------------------
    # 1. 找出正在滴定中的工單 (使用三種日期格式查詢)
    # -----------------------------
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # SQL 使用動態 placeholders
        sql = f"""
            SELECT 工單號, bead_name, 時間_滴定開始
            FROM work_orders
            WHERE 日期 IN ({placeholders})
              AND 時間_滴定開始 IS NOT NULL
              AND (時間_滴定結束 IS NULL OR 時間_滴定結束 = '')
        """
        cur.execute(sql, today_formats)
        running_orders = cur.fetchall()

    # -----------------------------
    # 2. 對每一張工單，回查 DropletSchedule.Pump
    # -----------------------------
    with sqlite3.connect(DB_SCHEDULE) as conn_sch:
        cur_sch = conn_sch.cursor()

        for row in running_orders:
            wo = row["工單號"]
            marker = row["bead_name"] or ""

            # 解析開始時間
            try:
                start_time = datetime.strptime(
                    row["時間_滴定開始"], "%Y-%m-%d %H:%M:%S"
                )
            except Exception:
                continue

            # 👉 只查 Pump（位置）
            cur_sch.execute(
                """
                SELECT Pump, Quantity
                FROM DropletSchedule
                WHERE WorkOrder = ?
                """,
                (wo,),
            )
            sch_rows = cur_sch.fetchall()
            
            if not sch_rows:
                continue

            # 用來收集這張工單用到的所有 Pump 名稱
            job_pumps_list = []
            
            # 初始化變數
            job_display_quantity = 0 
            max_remain_min = 0      
            final_end_time = start_time
            
            # --- 迴圈處理每一個 Port ---
            for sch in sch_rows:
                pump_raw, quantity_raw = sch
                
                try:
                    q = int(quantity_raw or 0)
                except:
                    q = 0
                
                job_display_quantity = max(job_display_quantity, q)

                # 假設速度固定 1500/hr
                estimate_hours = q / 1500 if q > 0 else 0
                
                # 計算該 Port 的結束時間
                port_end_time = start_time + timedelta(hours=estimate_hours)
                r_min = max(0, int((port_end_time - now).total_seconds() / 60))
                
                if r_min > max_remain_min:
                    max_remain_min = r_min
                    final_end_time = port_end_time

                # --- 標記資源狀態 ---
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

            # -----------------------------
            # 4. 加入 Jobs 清單
            # -----------------------------
            jobs.append(
                {
                    "workOrder": wo,
                    "marker": marker,
                    "quantity": job_display_quantity,
                    "pumps": list(set(job_pumps_list)), 
                    "estimateHours": round(max_remain_min / 60, 2),
                    "estimatedEndTime": final_end_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "remainMin": max_remain_min, 
                }
            )

    # -----------------------------
    # 統計
    # -----------------------------
    ports_total = 12
    ports_in_use = len(used_ports)
    next_release = min(
        [j["remainMin"] for j in jobs if j["remainMin"] > 0],
        default=None,
    )

    resources = [ivek] + list(port_map.values())

    return jsonify(
        {
            "portsTotal": ports_total,
            "portsInUse": ports_in_use,
            "freePorts": ports_total - ports_in_use,
            "nextReleaseMin": next_release,
            "jobs": jobs,
            "resources": resources,
        }
    )



# 異常相關 API
@app.route('/api/latest_abnormal', methods=['GET'])
def get_latest_abnormal():
    try:
        stats = get_abnormal_stats()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, station, machine_id, description, created_at, user, photos, is_resolved, resolution_note, status, signer FROM abnormal_history ORDER BY created_at DESC LIMIT 1")
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

@app.route('/api/resolve_abnormal', methods=['POST'])
def resolve_abnormal():
    try:
        data = request.get_json()
        record_id, action = data.get('id'), data.get('action')
        note, signer, pin = data.get('note', ''), data.get('signer', ''), data.get('pin', '')

        with get_db_connection() as conn:
            cursor = conn.cursor()
            if action == 'resolve':
                cursor.execute("UPDATE abnormal_history SET status=1, is_resolved=1, resolution_note=? WHERE id=?", (note, record_id))
            elif action == 'signoff':
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

# ==========================================
# 5. Mobile / App APIs (補回)
# ==========================================
@app.route('/api/mobile/work-orders', methods=['GET'])
def mobile_get_orders():
    try:
        if not os.path.exists(DB_SCHEDULE): return jsonify({'ok': False, 'error': "DB Not Found"}), 500
        
        today = datetime.now()
        
        # --- 🔥 修改開始：產生過去3天，每天都有3種格式 ---
        all_dates = []
        for i in range(3):
            target_day = today - timedelta(days=i)
            all_dates.extend(get_all_date_formats(target_day))
        
        # 去重，避免重複查詢
        all_dates = list(set(all_dates))
        
        # 加上 % 用於 SQL LIKE 查詢
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
    # 🔥 新增這兩行：如果是 UMRZ 開頭，直接放行，不查資料庫
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
    print("🔔 [Mobile] Photo Upload Called...")
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
            trigger_droplet_sync_safe() 

        return jsonify({'ok': True, 'timestamp': cur_time, 'photoName': final_ph})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)}), 500

# ==========================================
# 1. 定義 AI 提示詞模板 (PROMPT_TEMPLATES)
# ==========================================
PROMPT_TEMPLATES = {
    "receive": """
        請讀取照片中所有的 QR Code。
        預期格式為 "Name,Lot" (例如 "Ba-BU,20926041")。
        請回傳一個 JSON 物件，包含一個陣列 "codes":
        [ {"marker": "Ba-BU", "lot": "20926041"}, ... ]
        如果沒找到 QR Code，回傳 {"codes": []}。
    """,
    
    "titration_prep": """
        請讀取照片中的 QR Code (例如 "P-IVEK" 或 "P-106")。
        請去除前綴 "P-"，只回傳內容。
        回傳 JSON: {"port_code": "IVEK"} 或 {"port_code": "106"}。
        如果沒找到，回傳 null。
    """,

    "titration_start": """
        請分析機台螢幕 (OCR)。
        1. 橘色區域文字 (Beads Name)。
        2. 滴定體積數值 (Titration Volume)。
        回傳 JSON: {"beads_name": "HDL-D", "volume": "6.00"}
        如果無法辨識，對應欄位回傳 null。
    """,

    "titration_end": """
        請分析機台螢幕。
        1. 橘色區域文字 (Beads Name)。
        2. 尋找 "目前滴定數量" 或 "Current Count" 右邊的數值 X。
        回傳 JSON: {"beads_name": "HDL-D", "current_count": 1234}
        如果無法辨識，對應欄位回傳 null。
    """,

    # 凍乾三步驟共用類似邏輯，但為了精確，分開定義
    "fd_prep": """
        請分析凍乾機螢幕。
        1. 右上角 "NO.X" 的數字 X (例如 3~15) 或 "凍乾機 X" 右邊的數值 X。
        2. 藍色區域上端真空度 (W mTorr)，只取數字 W。
        3. 藍色區域中間層板溫度 (Shelf Temp = -Z)，只取數字 Z。
        回傳 JSON: {"machine_no": "11", "vacuum": "120", "shelf_temp": "40.5"}
    """,
    "fd_start": """
        請分析凍乾機螢幕。
        1. 右上角 "NO.X" 的數字 X。
        2. 藍色區域上端真空度 (W mTorr)。
        3. 藍色區域中間層板溫度 (Shelf Temp)。
        回傳 JSON: {"machine_no": "11", "vacuum": "120", "shelf_temp": "40.5"}
    """,
    "fd_end": """
        請分析凍乾機螢幕。
        1. 右上角 "NO.X" 的數字 X。
        2. 藍色區域上端真空度 (W mTorr)。
        3. 藍色區域中間層板溫度 (Shelf Temp)。
        回傳 JSON: {"machine_no": "11", "vacuum": "120", "shelf_temp": "40.5"}
    """
}

# ==========================================
# 2. 資料庫 Helper
# ==========================================
def get_schedule_row(work_order):
    """根據工單號取得 dropletRecord 的資料"""
    try:
        with sqlite3.connect(DB_SCHEDULE) as conn:
            conn.row_factory = sqlite3.Row # 讓我們可以用欄位名稱存取
            cursor = conn.cursor()
            # 這裡假設 table 名稱是 dropletRecord，且欄位包含 marker, lot, titration_port, syringe, titration_volume, quanity, lyophilizer 等
            cursor.execute("SELECT * FROM dropletRecord WHERE WorkOrder = ?", (work_order,))
            return cursor.fetchone() # 回傳第一筆符合的資料
    except Exception as e:
        print(f"DB Error: {e}")
        return None

def update_schedule_column(work_order, col_name, value):
    """更新 dropletRecord 的特定欄位"""
    try:
        with sqlite3.connect(DB_SCHEDULE) as conn:
            sql = f"UPDATE dropletRecord SET {col_name} = ? WHERE WorkOrder = ?"
            conn.execute(sql, (value, work_order))
            conn.commit()
            return True
    except Exception as e:
        print(f"DB Update Error: {e}")
        return False

# ==========================================
# 3. 核心分析 API
# ==========================================
@app.route('/api/analyze-image', methods=['POST'])
def analyze_image():
    print("🤖 [AI] Analyzing Image & Verifying DB...")
    try:
        data = request.get_json()
        base64_image = data.get('image')
        step_id = data.get('step_id')
        work_order = data.get('work_order') # 前端必須傳這個來

        if not all([base64_image, step_id, work_order]):
            return jsonify({'pass': False, 'msg': '缺少必要參數 (image, step_id, work_order)'}), 400

        # 1. 取得 DB 資料
        db_row = get_schedule_row(work_order)
        if not db_row:
            return jsonify({'pass': False, 'msg': f'資料庫找不到工單: {work_order}'}), 404

        # 2. 呼叫 Gemini AI
        prompt = PROMPT_TEMPLATES.get(step_id, PROMPT_TEMPLATES['receive']) # 預設 fallback
        API_KEY = "AIzaSyBmeZUbPalPxeag9VAsKRNKXg33oIoZwxc"
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }

        response = requests.post(url, headers=headers, data=json.dumps(payload))
        if response.status_code != 200:
            return jsonify({'pass': False, 'msg': 'AI API 連線失敗'}), 500
        
        ai_result = json.loads(response.json()['candidates'][0]['content']['parts'][0]['text'])
        print(f"🤖 AI Result: {ai_result}")

        # ==========================================
        # 3. 執行比對邏輯 (Python Side)
        # ==========================================
        result = {'pass': False, 'msg': '未知錯誤', 'action': 'none'}

        # --- Case 2: Receive (收藥) ---
        if step_id == 'receive':
            codes = ai_result.get('codes', [])
            if not codes:
                return jsonify({'pass': False, 'msg': '❌ 未偵測到 QR Code，請重拍'})
            
            # 比對邏輯：只要有一個 QR Code 符合 DB 的 marker 和 lot 就算過
            db_marker = str(db_row['marker']).strip()
            db_lot = str(db_row['lot']).strip()
            
            match = False
            for code in codes:
                if code.get('marker') == db_marker and code.get('lot') == db_lot:
                    match = True
                    break
            
            if match:
                result = {'pass': True, 'msg': '✅ 收藥確認正確'}
            else:
                result = {'pass': False, 'msg': f'❌ 比對錯誤\n預期: {db_marker}, {db_lot}\n偵測到: {codes}'}

        # --- Case 3: Titration Prep (滴定準備) ---
        elif step_id == 'titration_prep':
            port_code = str(ai_result.get('port_code', '')).strip()
            if not port_code:
                return jsonify({'pass': False, 'msg': '❌ 未偵測到 P-Code，請重拍'})

            if port_code == 'IVEK':
                db_port = str(db_row['titration_port']).strip()
                if db_port == 'IVEK':
                    result = {'pass': True, 'msg': '✅ IVEK 確認正確'}
                else:
                    result = {'pass': False, 'msg': f'❌ 比對錯誤 (預期: {db_port})'}
            else:
                # 數字比對 logic: column.syringe 格式如 "28-29-31-35"
                db_syringe = str(db_row['syringe']).strip()
                # 檢查 port_code 是否存在於 db_syringe 分割後的清單中
                if port_code in db_syringe.split('-'):
                    result = {'pass': True, 'msg': f'✅ Syringe {port_code} 確認正確'}
                else:
                    result = {'pass': False, 'msg': f'❌ 比對錯誤\n掃描: {port_code}\n允許列表: {db_syringe}'}

        # --- Case 4: Titration Start (滴定開始) ---
        elif step_id == 'titration_start':
            ai_name = str(ai_result.get('beads_name', '')).strip()
            ai_vol = str(ai_result.get('volume', '')).strip()
            
            db_marker = str(db_row['marker']).strip()
            db_vol = str(db_row['titration_volume']).strip()

            # 寬鬆比對數值 (例如 6.00 vs 6)
            try:
                vol_match = float(ai_vol) == float(db_vol)
            except:
                vol_match = False

            if ai_name == db_marker and vol_match:
                result = {'pass': True, 'msg': '✅ 參數正確'}
            else:
                result = {'pass': False, 'msg': f'❌ 參數錯誤\n預期: {db_marker}, {db_vol}\n偵測: {ai_name}, {ai_vol}'}

        # --- Case 5: Titration End (滴定結束) ---
        elif step_id == 'titration_end':
            ai_name = str(ai_result.get('beads_name', '')).strip()
            try:
                current_count = int(ai_result.get('current_count', -1))
            except:
                current_count = -1
            
            db_marker = str(db_row['marker']).strip()
            db_qty = int(db_row['quantity'] or 0) 

            if ai_name != db_marker:
                 return jsonify({'pass': False, 'msg': f'❌ Beads Name 錯誤 ({ai_name})'})

            # 寫入 DB (Tri_numbers)
            if current_count > 0:
                update_schedule_column(work_order, 'Tri_numbers', current_count)

            if current_count > db_qty:
                result = {'pass': True, 'msg': f'✅ 數量正確 (目前: {current_count})'}
            else:
                # 數量不足，顯示錯誤但允許通過 (特殊邏輯)
                result = {'pass': True, 'msg': f'⚠️ 警告: 數量不足 ({current_count} < {db_qty})，已記錄數據。', 'warning': True}

        # --- Case 6: FD Prep (凍乾準備) ---
        elif step_id == 'fd_prep':
            # 1. 比對機台號碼
            ai_no = str(ai_result.get('machine_no', '')).strip()
            db_lyo = str(db_row['lyophilizer']).strip()
            
            # 寫入數據 (VACUUM_pre, Temp_pre)
            vac = ai_result.get('vacuum')
            temp = ai_result.get('shelf_temp')
            if vac: update_schedule_column(work_order, 'VACUUM_pre', vac)
            if temp: update_schedule_column(work_order, 'Temp_pre', f"-{temp}") # 存負號

            if ai_no == db_lyo:
                result = {'pass': True, 'msg': '✅ 機台設定正確'}
            else:
                # 異常流程：要求使用者確認
                result = {
                    'pass': False, 
                    'msg': f'❌ 機台不符！(偵測: {ai_no}, 預期: {db_lyo})', 
                    'action': 'ABNORMAL_CONFIRM_REQUIRED' # 告訴前端要跳轉異常單
                }

        # --- Case 7: FD Start ---
        elif step_id == 'fd_start':
            ai_no = str(ai_result.get('machine_no', '')).strip()
            db_lyo = str(db_row['lyophilizer']).strip()
            
            if vac := ai_result.get('vacuum'): update_schedule_column(work_order, 'VACUUM_use', vac)
            if temp := ai_result.get('shelf_temp'): update_schedule_column(work_order, 'Temp_use', f"-{temp}")

            if ai_no == db_lyo:
                result = {'pass': True, 'msg': '✅ 凍乾開始確認'}
            else:
                result = {'pass': False, 'msg': f'❌ 機台不符 (偵測: {ai_no})'}

        # --- Case 8: FD End ---
        elif step_id == 'fd_end':
            ai_no = str(ai_result.get('machine_no', '')).strip()
            db_lyo = str(db_row['lyophilizer']).strip()
            
            if vac := ai_result.get('vacuum'): update_schedule_column(work_order, 'VACUUM_end', vac)
            if temp := ai_result.get('shelf_temp'): update_schedule_column(work_order, 'Temp_end', f"-{temp}")

            if ai_no == db_lyo:
                result = {'pass': True, 'msg': '✅ 凍乾結束確認'}
            else:
                result = {'pass': False, 'msg': f'❌ 機台不符 (偵測: {ai_no})'}

        return jsonify(result)

    except Exception as e:
        print(f"❌ System Error: {e}")
        return jsonify({'pass': False, 'msg': f'系統錯誤: {str(e)}'}), 500
# ==========================================
# 6. Main Execution
# ==========================================
if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    
    init_db()          # 確保工單表存在
    init_abnormal_db() # 確保異常表存在

    port = int(os.environ.get("PORT", 5100))
    print(f"🚀 Flask-SocketIO Server Running on http://0.0.0.0:{port}")
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)