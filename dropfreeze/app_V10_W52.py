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
        now = datetime.now().replace(tzinfo=None).replace(tzinfo=None)
        yest = now - timedelta(days=1)
        today_opts = f"('{now.strftime('%Y/%m/%d')}', '{now.strftime('%Y-%m-%d')}')"
        yest_opts = f"('{yest.strftime('%Y/%m/%d')}', '{yest.strftime('%Y-%m-%d')}')"

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
    """
    成品版 freeze-status：
    - 主狀態（state）來自 work_orders（事實）：running / preparing / finished / idle
    - reserved 子狀態（reserved）來自 DropletSchedule（排程）：今天/昨天是否已排
    - 允許同一台機器同時顯示：
        state = running（昨天工單） + reserved.workOrder（今天工單）
    """
    import traceback

    def _is_blank(v) -> bool:
        return v is None or (isinstance(v, str) and v.strip() == "")

    def _to_naive_dt(dt_like):
        """
        統一把 pandas Timestamp / datetime 轉成 tz-naive python datetime
        """
        if dt_like is None:
            return None
        try:
            # pandas Timestamp
            if hasattr(dt_like, "to_pydatetime"):
                dt_like = dt_like.to_pydatetime()
        except Exception:
            pass

        # tz-aware -> tz-naive
        try:
            if hasattr(dt_like, "tzinfo") and dt_like.tzinfo is not None:
                # datetime tz-aware
                return dt_like.replace(tzinfo=None)
        except Exception:
            pass
        return dt_like

    def _freezer_like_params(search_id: str):
        """
        支援 work_orders.凍乾機_1 的兩種格式：
          - Freezer-05
          - Freezer 05 / Freezer 5 / Freezer 09 / Freezer 9
        """
        if search_id == "Small":
            # 你 DB 同時可能有 Freeze-Small / Freezer Small（以你資料為準可再加）
            return ("%Freeze-Small%", "%Freeze Small%")

        sid2 = str(int(search_id)).zfill(2)   # "09"
        sid1 = str(int(search_id))            # "9"
        # 兩個 pattern：dash版、空白版
        return (f"%Freezer-{sid2}%", f"%Freezer {sid1}%")

    def _pick_actual_row_for_machine(conn_wo, date_strs, search_id):
        """
        從 work_orders 中挑出「最能代表目前狀態」的那一筆（主狀態用）
        規則：
          - 先選 running（有開始、無結束 且未超時）
          - 再選 preparing（有準備、無開始、無結束）
          - 再選 finished（有結束 或 超時完成）
          - 最後才是空白（等同沒有）
        會回傳：row(dict) 或 None
        """
        like_a, like_b = _freezer_like_params(search_id)

        # 注意：日期只查你指定的集合（通常 today+yesterday）
        # 並用 ORDER BY 讓「較新日期」先出來，再由 Python 精選真正狀態
        sql = f"""
        SELECT 工單號, PN, 日期, 凍乾機_1,
               時間_凍乾準備, 時間_凍乾開始, 時間_凍乾結束
        FROM work_orders
        WHERE 日期 IN ({",".join(["?"] * len(date_strs))})
          AND (凍乾機_1 LIKE ? OR 凍乾機_1 LIKE ?)
        ORDER BY 日期 DESC, id DESC
        """
        params = list(date_strs) + [like_a, like_b]
        df = pd.read_sql(sql, conn_wo, params=params)
        if df.empty:
            return None

        # 逐筆評分：running > preparing > finished > none
        best = None
        best_rank = 999
        for _, r in df.iterrows():
            prep = r.get("時間_凍乾準備")
            start = r.get("時間_凍乾開始")
            end = r.get("時間_凍乾結束")

            # 有結束：finished
            if not _is_blank(end):
                rank = 3
            # 有開始無結束：候選 running/finished_by_timeout（需要外部再判）
            elif not _is_blank(start):
                rank = 1
            # 有準備無開始無結束：preparing
            elif not _is_blank(prep) and _is_blank(start) and _is_blank(end):
                rank = 2
            else:
                rank = 9

            if rank < best_rank:
                best_rank = rank
                best = r

        return dict(best) if best is not None else None

    def _calc_state_from_row(monitor, now_dt, row):
        """
        由 work_orders 單筆 row 算主狀態（含 remainMin）
        running：用 PN->凍乾時間，計算剩餘
        finished：有結束 或 超時
        preparing：只有準備
        idle：沒有任何有效時間欄位
        """
        if not row:
            return {"state": "idle", "workOrder": None, "remainMin": None, "pn": None}

        wo = row.get("工單號")
        pn = row.get("PN")
        date_val = row.get("日期")
        prep = row.get("時間_凍乾準備")
        start = row.get("時間_凍乾開始")
        end = row.get("時間_凍乾結束")

        # finished（有結束時間）
        if not _is_blank(end):
            return {"state": "finished", "workOrder": wo, "remainMin": None, "pn": pn}

        # running（有開始無結束） -> 可能超時視為 finished
        if not _is_blank(start):
            start_dt = monitor._str_to_datetime(date_val, start)
            start_dt = _to_naive_dt(start_dt)
            if start_dt is None:
                return {"state": "error", "workOrder": wo, "remainMin": None, "pn": pn}

            duration_hr = float(monitor._get_drying_duration(pn))
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
                # 沒寫結束時間，但已超時 -> 視為 finished
                return {"state": "finished", "workOrder": wo, "remainMin": None, "pn": pn}

        # preparing（有準備、沒開始、沒結束）
        if not _is_blank(prep) and _is_blank(start) and _is_blank(end):
            return {"state": "preparing", "workOrder": wo, "remainMin": None, "pn": pn}

        return {"state": "idle", "workOrder": wo, "remainMin": None, "pn": pn}

    def _get_reserved_from_schedule(conn_sch, date_strs, search_id):
        """
        從 DropletSchedule 取得 reserved 子狀態（今天/昨天排程）
        回傳：{"workOrder": "...", "date": "..."} 或 None
        """
        if search_id == "Small":
            like_val = "%Small%"
        else:
            like_val = f"%{str(int(search_id)).zfill(2)}%"  # 03/09 這種常見表示

        sql = f"""
        SELECT WorkOrder, Date, Lyophilizer
        FROM DropletSchedule
        WHERE Date IN ({",".join(["?"] * len(date_strs))})
          AND Lyophilizer LIKE ?
        ORDER BY Date DESC
        LIMIT 1
        """
        params = list(date_strs) + [like_val]
        df = pd.read_sql(sql, conn_sch, params=params)
        if df.empty:
            return None
        r = df.iloc[0]
        wo = r.get("WorkOrder")
        d = r.get("Date")
        if _is_blank(wo):
            return None
        return {"workOrder": str(wo).strip(), "date": str(d).strip() if not _is_blank(d) else None}

    try:
        monitor = LyophilizerMonitor()

        # 這裡用 tz-naive，並確保 monitor._str_to_datetime 也回 tz-naive（你前面已修過）
        now = datetime.now()

        # 日期格式：DropletSchedule 是 yyyy/mm/dd；work_orders 你目前也用 yyyy/mm/dd（你前面程式如此）
        today_slash = now.strftime("%Y/%m/%d")
        yest_slash = (now - timedelta(days=1)).strftime("%Y/%m/%d")
        date_strs = [today_slash, yest_slash]

        resources = []

        # 連線：每次 endpoint 只開一次，避免頻繁開關造成 IO 負擔
        conn_wo = monitor._get_connection("work_order")
        conn_sch = monitor._get_connection("schedule")

        if conn_wo is None or conn_sch is None:
            # 哪個 DB 不存在就回 error（你也可以改成 partial）
            missing = []
            if conn_wo is None:
                missing.append("work_orders.db")
            if conn_sch is None:
                missing.append("P01_formualte_schedule.db")
            return jsonify({"error": f"DB not found: {', '.join(missing)}"}), 500

        for mid in monitor.TARGET_MACHINES:
            # id / search_id
            rid = "Freeze-Small" if mid == "Small" else f"Freezer-{str(mid).zfill(2)}"
            search_id = "Small" if mid == "Small" else str(int(mid))

            # 1) 主狀態（事實）- work_orders
            row = _pick_actual_row_for_machine(conn_wo, date_strs, search_id)
            actual = _calc_state_from_row(monitor, now, row)

            # 2) reserved 子狀態（排程）- DropletSchedule
            reserved = _get_reserved_from_schedule(conn_sch, date_strs, search_id)

            # 3) 組合：主狀態永遠優先（running/preparing/finished 不會被 reserved 覆蓋）
            #    只有當主狀態 idle 時，才把主狀態提升為 reserved
            state = actual["state"]
            work_order = actual["workOrder"]
            remain_min = actual["remainMin"]

            if state == "idle":
                if reserved:
                    state = "reserved"
                    work_order = reserved["workOrder"]

            # 4) 回傳物件（含 style、reserved 子狀態）
            out = {
                "id": rid,
                "state": state,
                "workOrder": work_order,
                "remainMin": remain_min,
                # 子狀態：當「主狀態不是 reserved」且今天/昨天有排程時，給前端顯示小 badge
                "reserved": None,
                "style": STATUS_STYLE.get(state, STATUS_STYLE["error"]),
            }

            if reserved:
                # 如果主狀態本身就是 reserved，reserved 子狀態可省略或保留（這裡保留，方便 UI 一致）
                out["reserved"] = {
                    **reserved,
                    "style": RESERVED_BADGE_STYLE,
                }

            resources.append(out)

        # 關閉連線
        try:
            conn_wo.close()
        except Exception:
            pass
        try:
            conn_sch.close()
        except Exception:
            pass

        # 統計：主狀態非 idle 視為 in_use（含 reserved / preparing / running / finished）
        total = len(resources)
        in_use = sum(1 for r in resources if r["state"] != "idle")
        free = total - in_use
        next_release = min(
            [r["remainMin"] for r in resources if r["state"] == "running" and r["remainMin"] is not None and r["remainMin"] > 0],
            default=None,
        )

        return jsonify({
            "freezersTotal": total,
            "freezersInUse": in_use,
            "freeFreezers": free,
            "nextReleaseMin": next_release,
            "resources": resources,
            "statusStyle": STATUS_STYLE,            # 前端可選擇用這張表
            "reservedBadgeStyle": RESERVED_BADGE_STYLE,
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        })

    except Exception as e:
        print("🔴 ops_freeze_status error:", e)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500




# 滴定機狀態 API
@app.route("/api/ops/titration-status", methods=["GET"])
def ops_titration_status():
    print("🟢 ops_titration_status CALLED")
    today_slash = datetime.now().strftime("%Y/%m/%d")
    now = datetime.now().replace(tzinfo=None)
    resources = []

    # 初始化 IVEK & Pumps
    ivek_resource = {"id": "IVEK", "type": "IVEK", "todayUsed": False, "state": "unused", "currentJob": None, "remainMin": None}
    resources.append(ivek_resource)
    pump_map = {}
    for i in range(1, 13):
        pid = f"Pump-{str(i).zfill(2)}"
        pump = {"id": pid, "type": "PUMP", "todayUsed": False, "state": "unused", "currentJob": None, "remainMin": None}
        pump_map[pid] = pump
        resources.append(pump)

    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT 工單號, bead_name, 時間_滴定開始
            FROM work_orders
            WHERE 日期 = ? AND 時間_滴定開始 IS NOT NULL AND (時間_滴定結束 IS NULL OR 時間_滴定結束 = '')
        """, (today_slash,))
        running_orders = cur.fetchall()

    jobs = []
    used_pumps = set()

    for row in running_orders:
        wo = row["工單號"]
        marker = row["bead_name"] or ""
        try: start_time = datetime.strptime(row["時間_滴定開始"], "%Y-%m-%d %H:%M:%S")
        except: continue

        pumps, quantity_raw = get_pumps_and_quantity(wo)
        try: quantity = int(quantity_raw)
        except: quantity = 0

        estimate_hours = quantity / 1500 if quantity > 0 else 0
        end_time = start_time + timedelta(minutes=math.ceil(estimate_hours * 60))
        remain_min = max(0, math.ceil((end_time - now).total_seconds() / 60))

        for p in pumps:
            pid = p if p.startswith("Pump") else f"Pump-{str(p).zfill(2)}"
            if pid in pump_map:
                pump_map[pid]["todayUsed"] = True
                pump_map[pid]["state"] = "running"
                pump_map[pid]["currentJob"] = wo
                pump_map[pid]["remainMin"] = remain_min
                used_pumps.add(pid)
        
        ivek_resource["todayUsed"] = True
        ivek_resource["state"] = "running"
        ivek_resource["currentJob"] = wo

        jobs.append({
            "workOrder": wo, "marker": marker, "quantity": quantity,
            "pumps": list(pumps), "estimateHours": round(estimate_hours, 2),
            "estimatedEndTime": end_time.strftime("%Y-%m-%d %H:%M:%S"), "remainMin": remain_min
        })

    # 清理狀態
    for p in pump_map.values():
        if p["todayUsed"] and p["state"] == "unused": p["state"] = "idle"
    if ivek_resource["todayUsed"] and ivek_resource["state"] == "unused": ivek_resource["state"] = "idle"

    pumps_total = 12
    pumps_in_use = len(used_pumps)
    
    return jsonify({
        "pumpsTotal": pumps_total,
        "pumpsInUse": pumps_in_use,
        "freePumps": pumps_total - pumps_in_use,
        "nextReleaseMin": min([j["remainMin"] for j in jobs if j["remainMin"] > 0], default=None),
        "jobs": jobs,
        "resources": resources
    })

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
            
        return jsonify({'ok': True, 'timestamp': cur_time, 'photoName': final_ph})
    except Exception as e: return jsonify({'ok': False, 'error': str(e)}), 500

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