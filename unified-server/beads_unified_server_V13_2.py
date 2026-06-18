# -*- coding: utf-8 -*-
"""
====================================================================
Beads 統一服務器 V13.2 - 最終整合穩定版
====================================================================
"""
import re, sys, os, time, threading, sqlite3, subprocess, json, mimetypes, urllib.parse
import traceback, tempfile, atexit, logging
import datetime as dt
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pathlib import Path
from dataclasses import dataclass

# --- 強制路徑對齊 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# --- 第三方庫 ---
import pandas as pd
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
from flask import Flask, send_from_directory, request, jsonify, send_file, abort, url_for

# --- 專案模組導入 ---
from api_beads_ipqc_importable import register_beads_ipqc_routes
from wip_automation_blueprint_4 import (wip_automation_bp, init_wip_automation)
from IPQA_db_V1_importable import start_monitoring as start_ipqc_monitoring

# ====================================================================
# ====== 1. 配置與常量 ======
# ====================================================================

BASE_DIR = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定"
APP_DIR = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Bead_auto_update_schedule"
DIST = Path(APP_DIR) / "beads-ui" / "dist"

# 資料庫路徑
MAIN_DB_PATH = os.path.join(BASE_DIR, "資料庫", "beads_sync.db")
DB_PATH = os.path.join(BASE_DIR, "資料庫", "Beads_Schedule.db")
WORK_ORDER_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"
FORMULATE_DB_PATH = r"D:\配藥表\資料庫\P01_formualte_schedule.db"
IPQC_DB_PATH = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Beads_QC\資料庫\P01_Beads_IPQC.db"

# WIP 配置
WIP_EXCEL_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\WIP報表 2025-QR01 NEW (請勿亂動連結).xlsm"
WIP_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\分藥資料庫\Bead_Sort_DB.db"
WIP_TABLE_NAME = "明細_2025"
WIP_HEADER_ROW = 5
WIP_USECOLS = "A:U"
WIP_CHECK_INTERVAL = 15 

TOTAL_TITRATION_CAPACITY = 26
TOTAL_DRYERS = 11

@dataclass
class FileConfig:
    path: str
    sheet: str
    header_row: int
    data_start_row: int
    last_col: str
    lastrow_by_col: str
    table: str
    keys: List[str]
    header_map: Dict[str, str] = None
    def __post_init__(self):
        if self.header_map is None: self.header_map = {}

FILE_A_CONFIG = FileConfig(path=r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\祐銓\★2024-最新版【勿動】-BEADS庫存-20241126.xlsm", sheet="BEADS庫存表(202405~", header_row=5, data_start_row=6, last_col="O", lastrow_by_col="B", table="beads_Inventory", keys=["PN", "Batch"], header_map={"料號": "PN", "批號": "Batch"})
FILE_B_CONFIG = FileConfig(path="", sheet="P_plan Reagent", header_row=2, data_start_row=3, last_col="TT", lastrow_by_col="B", table="production_Plan", keys=["PN"])
FILE_C_CONFIG = FileConfig(path=os.path.join(BASE_DIR, "限制排程表.xlsm"), sheet="限制 OR 插單", header_row=2, data_start_row=3, last_col="M", lastrow_by_col="A", table="限制_OR_插單", keys=[])
FILE_D_CONFIG = FileConfig(path=os.path.join(BASE_DIR, "beads_dry_num_1.xlsm"), sheet="工作表1", header_row=2, data_start_row=3, last_col="D", lastrow_by_col="A", table="Beads_Dry_Count", keys=[])
FILE_E_CONFIG = FileConfig(path=os.path.join(BASE_DIR, "滴定限制.xlsm"), sheet="配藥限制", header_row=1, data_start_row=2, last_col="U", lastrow_by_col="A", table="配藥限制", keys=[])

# ====================================================================
# ====== 2. 狀態與同步工具函數 ======
# ====================================================================

class StateManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._observer = None
        self._watched_folders = set()
        self._last_event_ts = {}
        self._sync_init_done = False
        self._wip_thread = None
        self._wip_stop_event = threading.Event()
    @property
    def observer(self): 
        with self._lock: return self._observer
    @observer.setter
    def observer(self, v): 
        with self._lock: self._observer = v
    def get_last_event_time(self, p): 
        with self._lock: return self._last_event_ts.get(p, 0)
    def set_last_event_time(self, p, ts): 
        with self._lock: self._last_event_ts[p] = ts

state = StateManager()
db_lock = threading.Lock()

def safe_ident(name: str) -> str:
    s = str(name or "").replace('"', '""').strip()
    return s if s else "_col_"

def normalize_df_for_sqlite(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    target_cols = ["PN", "料號", "Lot", "Batch", "工單號碼", "凍乾數"]
    for col_name in out.columns:
        if str(col_name).strip() in target_cols:
            out[col_name] = out[col_name].map(lambda x: str(int(float(x))) if pd.notna(x) and str(x).strip() != "" else "")
    return out

def ensure_table_and_columns(conn, table, df):
    cols_def = ", ".join([f'"{safe_ident(c)}" TEXT' for c in df.columns])
    conn.execute(f'CREATE TABLE IF NOT EXISTS "{safe_ident(table)}" ({cols_def})')

def upsert(conn, table, df, keys):
    ensure_table_and_columns(conn, table, df)
    cols = list(df.columns)
    placeholders = ", ".join(["?"] * len(cols))
    sql = f'REPLACE INTO "{safe_ident(table)}" ({", ".join([f'"{c}"' for c in cols])}) VALUES ({placeholders})'
    conn.executemany(sql, df.itertuples(index=False, name=None))

def sync_file(config: FileConfig, file_key: str):
    if not config.path or not os.path.exists(config.path): return
    with db_lock:
        try:
            df = pd.read_excel(config.path, sheet_name=config.sheet, header=config.header_row-1, engine="openpyxl")
            df = normalize_df_for_sqlite(df.dropna(how="all").fillna(""))
            if config.header_map: df = df.rename(columns=config.header_map)
            with sqlite3.connect(MAIN_DB_PATH) as conn:
                if config.keys: upsert(conn, config.table, df, config.keys)
                else:
                    conn.execute(f'DELETE FROM "{safe_ident(config.table)}"')
                    df.to_sql(config.table, conn, if_exists='append', index=False)
            print(f"✅ {file_key} 檔同步完成")
        except Exception as e: print(f"❌ {file_key} 同步失敗: {e}")

def sync_A(): sync_file(FILE_A_CONFIG, "A")
def sync_B():
    plan_dir = os.path.join(BASE_DIR, "production_plan")
    if os.path.exists(plan_dir):
        files = [f for f in os.listdir(plan_dir) if f.startswith("Production plan-") and f.endswith(".xlsm")]
        if files:
            FILE_B_CONFIG.path = os.path.join(plan_dir, sorted(files)[-1])
            sync_file(FILE_B_CONFIG, "B")
def sync_C(): sync_file(FILE_C_CONFIG, "C")
def sync_D(): sync_file(FILE_D_CONFIG, "D")
def sync_E(): sync_file(FILE_E_CONFIG, "E")

# ====================================================================
# ====== 3. WIP 監控 (Polling) ======
# ====================================================================

def run_wip_sync_once():
    try:
        if not os.path.exists(WIP_EXCEL_PATH): return False
        xls = pd.ExcelFile(WIP_EXCEL_PATH, engine="openpyxl")
        target = next((n for n in xls.sheet_names if "2025" in n and "明細" in n), None)
        if not target: return False
        df = pd.read_excel(WIP_EXCEL_PATH, sheet_name=target, header=4, usecols="A:U", engine="openpyxl", dtype=str).dropna(how="all")
        with sqlite3.connect(WIP_DB_PATH) as conn:
            df.to_sql(WIP_TABLE_NAME, conn, if_exists="replace", index=False)
        return True
    except Exception as e:
        print(f"WIP Sync Error: {e}")
        return False

def wip_monitor_loop(stop_event):
    last_mtime = 0
    while not stop_event.is_set():
        if os.path.exists(WIP_EXCEL_PATH):
            m = os.path.getmtime(WIP_EXCEL_PATH)
            if m > last_mtime:
                if run_wip_sync_once(): last_mtime = m
        stop_event.wait(WIP_CHECK_INTERVAL)

def start_wip_monitor():
    if state._wip_thread and state._wip_thread.is_alive(): return
    state._wip_stop_event.clear()
    state._wip_thread = threading.Thread(target=wip_monitor_loop, args=(state._wip_stop_event,), daemon=True)
    state._wip_thread.start()

# ====================================================================
# ====== 4. Flask API 與 核心路由 ======
# ====================================================================

app = Flask(__name__, static_folder=str(DIST), static_url_path="/")

# 註冊外部 API 模組
try:
    register_beads_ipqc_routes(app)
    app.register_blueprint(wip_automation_bp, url_prefix="")
    print("✅ IPQC 與 WIP 路由註冊完成")
except Exception as e:
    print(f"❌ 路由註冊失敗: {e}")

def initialize_sync_service():
    if state._sync_init_done: return
    print("🔄 執行 A-E 與 WIP 初始同步...")
    sync_A(); sync_B(); sync_C(); sync_D(); sync_E()
    run_wip_sync_once()
    init_wip_automation(app)
    start_wip_monitor()
    
    # 啟動 A-E Watchdog
    state.observer = PollingObserver(timeout=1.0)
    for cfg in [FILE_A_CONFIG, FILE_C_CONFIG, FILE_D_CONFIG, FILE_E_CONFIG]:
        if cfg.path and os.path.exists(os.path.dirname(cfg.path)):
            state.observer.schedule(FileSystemEventHandler(), os.path.dirname(cfg.path), recursive=False)
    state.observer.start()
    state._sync_init_done = True

@app.before_request
def _init_before_request():
    if not state._sync_init_done: initialize_sync_service()

# --- 核心數據統計 API ---

@app.route("/api/schedule/utilization", methods=["GET"])
def api_utilization():
    try:
        date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
        q_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        with sqlite3.connect(FORMULATE_DB_PATH) as conn:
            df = pd.read_sql_query("SELECT Pump, Lyophilizer, Date FROM DropletSchedule", conn)
        df['dt'] = pd.to_datetime(df['Date'], errors='coerce').dt.date
        df = df[df['dt'] == q_date]
        if df.empty: return jsonify({"ok":True, "titration_utilization":0, "dryer_utilization":0})
        titr_used = len(df[df['Pump'].notna()])
        dry_used = df['Lyophilizer'].nunique()
        return jsonify({
            "ok":True, 
            "titration_utilization": round(titr_used/TOTAL_TITRATION_CAPACITY*100, 1), 
            "dryer_utilization": round(dry_used/TOTAL_DRYERS*100, 1)
        })
    except Exception as e: return jsonify({"ok":False, "error":str(e)}), 500

@app.route("/api/schedule/completion-rate", methods=["GET"])
def api_completion_rate():
    try:
        date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
        d_slash = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y/%m/%d")
        with sqlite3.connect(FORMULATE_DB_PATH) as conn:
            res = pd.read_sql_query("SELECT DISTINCT WorkOrder FROM DropletSchedule WHERE Date LIKE ?", conn, params=(f"{d_slash}%",))
        target_os = res['WorkOrder'].dropna().unique().tolist()
        if not target_os: return jsonify({"ok":True, "total_orders":0, "dispensing_rate":0})
        
        placeholders = ','.join(['?']*len(target_os))
        with sqlite3.connect(WORK_ORDER_DB_PATH) as conn:
            df_r = pd.read_sql_query(f"SELECT 工單號, 時間_收藥, 時間_滴定結束, 時間_凍乾開始 FROM work_orders WHERE 工單號 IN ({placeholders})", conn, params=target_os)
        
        def is_d(v): return v and str(v).strip() not in ["","None","nan"]
        disp = df_r[df_r['時間_收藥'].apply(is_d)]['工單號'].nunique()
        titr = df_r[df_r['時間_滴定結束'].apply(is_d)]['工單號'].nunique()
        dry = df_r[df_r['時間_凍乾開始'].apply(is_d)]['工單號'].nunique()
        total = len(target_os)
        return jsonify({
            "ok":True, "total_orders":total, 
            "dispensing_rate":round(disp/total*100,1), 
            "titration_rate":round(titr/total*100,1), 
            "freeze_drying_rate":round(dry/total*100,1)
        })
    except Exception as e: return jsonify({"ok":False, "error":str(e)}), 500

@app.post("/api/wip/sync")
def api_manual_wip_sync():
    run_wip_sync_once()
    return jsonify(ok=True, message="WIP Sync Success")

@app.get("/")
def index(): return send_from_directory(str(DIST), "index.html")

@app.route("/<path:path>")
def static_proxy(path):
    t = DIST / path
    return send_from_directory(str(DIST), path if t.exists() else "index.html")

# ====================================================================
# ====== 5. 主程式啟動 ======
# ====================================================================

if __name__ == "__main__":
    atexit.register(lambda: state.observer.stop() if state.observer else None)
    atexit.register(lambda: state._wip_stop_event.set())
    try:
        # 啟動背景 IPQC Excel 監控 (處理 Excel 自動同步到 IPQC DB)
        beads_observer = start_ipqc_monitoring()
        # 啟動 Flask 並執行首次同步
        app.run(host="0.0.0.0", port=8505, debug=False, threaded=True, use_reloader=False)
    except:
        traceback.print_exc()
    finally:
        if beads_observer: beads_observer.stop()