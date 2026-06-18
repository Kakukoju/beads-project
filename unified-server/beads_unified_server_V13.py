# -*- coding: utf-8 -*-
"""
====================================================================
Beads 統一服務器 V6 - WIP 整合終極版
====================================================================
功能：
1. Excel ↔ SQLite 同步服務 (A/B/C/D/E 五個檔案 - Watchdog 模式)
2. WIP Excel ↔ SQLite 同步服務 (WIP 報表 - Polling 模式 [新增])
3. Flask Web API 服務
4. 排程管理與查詢
5. 需求統計模組
==================================================================
"""
print("🔥 IMPORTED wip_automation_blueprint FROM:", __file__)
import re
import sys
import os
import time
import threading
import sqlite3
import subprocess
import json
import mimetypes
import urllib.parse
import traceback
import tempfile
import atexit
import logging
import datetime as dt
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pathlib import Path
from dataclasses import dataclass

# --- 強制加入當前目錄到系統路徑 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# --- 第三方庫 ---
import pandas as pd
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
from pandas.api.types import is_datetime64_any_dtype as is_datetime
from flask import Flask, send_from_directory, request, jsonify, send_file, abort, url_for

# --- 專案模組 ---
from api_beads_ipqc_importable import register_beads_ipqc_routes
from wip_automation_blueprint_1 import (wip_automation_bp, init_wip_automation)
from IPQA_db_V1_importable import start_monitoring as start_ipqc_monitoring

# ====================================================================
# ====== 配置與常量 ======
# ====================================================================

# === 路徑配置 ===
BASE_DIR = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定"
APP_DIR = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Bead_auto_update_schedule"
DIST = Path(APP_DIR) / "beads-ui" / "dist"
SCRIPT = Path(APP_DIR) / "plan_to_bead_requirements_1.py"
SCHEDULER_SCRIPT = Path(APP_DIR) / "beads_Scheduler_V9_9_7.py"

# === 資料庫路徑 ===
MAIN_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\beads_sync.db"
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\Beads_Schedule.db"
WORK_ORDER_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"
FORMULATE_DB_PATH = r"D:\配藥表\資料庫\P01_formualte_schedule.db"
IPQC_DB_PATH = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Beads_QC\資料庫\P01_Beads_IPQC.db"

# === [新增] WIP 監控配置 ===
WIP_EXCEL_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\WIP報表 2025-QR01 NEW (請勿亂動連結).xlsm"
WIP_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\分藥資料庫\Bead_Sort_DB.db"
WIP_TABLE_NAME = "明細_2025"
WIP_HEADER_ROW = 5
WIP_USECOLS = "A:U"
WIP_CHECK_INTERVAL = 15  # WIP 輪詢間隔(秒)

# === Excel 檔案配置 (原有 A-E) ===
@dataclass
class FileConfig:
    """檔案配置類"""
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
        if self.header_map is None:
            self.header_map = {}

# A 檔：庫存檔
FILE_A_CONFIG = FileConfig(
    path=r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\祐銓\★2024-最新版【勿動】-BEADS庫存-20241126.xlsm",
    sheet="BEADS庫存表(202405~",
    header_row=5,
    data_start_row=6,
    last_col="O",
    lastrow_by_col="B",
    table="beads_Inventory",
    keys=["PN", "Batch"],
    header_map={"料號": "PN", "批號": "Batch", "PN ": "PN", "PN": "PN", "Batch No.": "Batch", "Batch": "Batch"}
)

# B 檔：生產計畫檔
FILE_B_CONFIG = FileConfig(
    path="",  # 動態選擇
    sheet="P_plan Reagent",
    header_row=2,
    data_start_row=3,
    last_col="TT",
    lastrow_by_col="B",
    table="production_Plan",
    keys=["PN"]
)

# C 檔：限制排程表
FILE_C_CONFIG = FileConfig(
    path=r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\限制排程表.xlsm",
    sheet="限制 OR 插單",
    header_row=2,
    data_start_row=3,
    last_col="M",
    lastrow_by_col="A",
    table="限制_OR_插單",
    keys=[]
)

# D 檔：凍乾數量
FILE_D_CONFIG = FileConfig(
    path=r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\beads_dry_num_1.xlsm",
    sheet="工作表1",
    header_row=2,
    data_start_row=3,
    last_col="D",
    lastrow_by_col="A",
    table="Beads_Dry_Count",
    keys=[]
)

# E 檔：配藥限制
FILE_E_CONFIG = FileConfig(
    path=r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\滴定限制.xlsm",
    sheet="配藥限制",
    header_row=1,
    data_start_row=2,
    last_col="U",
    lastrow_by_col="A",
    table="配藥限制",
    keys=[]
)

# === 同步配置 ===
DEBOUNCE_SECONDS = 2.0
READ_RETRY = 4
READ_RETRY_SLEEP = 0.6
TIME_COLUMNS = ["RD給藥時間", "預計滴定時間", "預計結束"]
NO_DECIMAL_COLUMNS = ["PN", "料號", "Lot", "Batch", "Batch No.", "工單號", "工單號碼", "凍乾數"]

# === 設備容量常量 ===
PORTS_PER_MACHINE = 12
SHIFTS_PER_DAY = 2 
TOTAL_TITRATION_CAPACITY = 26
TOTAL_DRYERS = 11

# === Flask 配置 ===
DEFAULT_TEMPLATE = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\空白排程.xlsm"
DEFAULT_OUTDIR = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\beadsSchedule"
ALLOWED_ROOTS = [r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定"]

# ====================================================================
# ====== 日誌配置 ======
# ====================================================================

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(APP_DIR, 'beads_sync.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def get_logger(name: str):
    return logging.getLogger(name)

logger = get_logger('SYNC_SVC')
wip_logger = get_logger('WIP_MONITOR')

# ====================================================================
# ====== 全局狀態管理 ======
# ====================================================================

class StateManager:
    """線程安全的狀態管理器"""
    def __init__(self):
        self._lock = threading.Lock()
        self._observer = None
        self._watched_folders: set = set()
        self._last_event_ts: Dict[str, float] = {}
        self._sync_init_done = False
        self._sched_proc = None
        self._demand_proc = None
        # [新增] WIP 監控線程控制
        self._wip_thread = None
        self._wip_stop_event = threading.Event()
    
    @property
    def observer(self):
        with self._lock: return self._observer
    
    @observer.setter
    def observer(self, value):
        with self._lock: self._observer = value
    
    @property
    def watched_folders(self):
        with self._lock: return self._watched_folders.copy()
    
    def add_watched_folder(self, folder: str):
        with self._lock: self._watched_folders.add(folder)
    
    def get_last_event_time(self, path: str) -> float:
        with self._lock: return self._last_event_ts.get(path, 0)
    
    def set_last_event_time(self, path: str, ts: float):
        with self._lock: self._last_event_ts[path] = ts
    
    @property
    def sync_init_done(self):
        with self._lock: return self._sync_init_done
    
    @sync_init_done.setter
    def sync_init_done(self, value):
        with self._lock: self._sync_init_done = value

    @property
    def sched_proc(self):
        with self._lock: return self._sched_proc
    
    @sched_proc.setter
    def sched_proc(self, value):
        with self._lock: self._sched_proc = value

    @property
    def demand_proc(self):
        with self._lock: return self._demand_proc
    
    @demand_proc.setter
    def demand_proc(self, value):
        with self._lock: self._demand_proc = value

state = StateManager()
db_lock = threading.Lock()

# ====================================================================
# ====== [新增] WIP Excel 同步模組 (Polling 模式) ======
# ====================================================================

def wip_find_target_sheet():
    """WIP: 找尋包含 2025 和 明細 的 sheet"""
    try:
        xls = pd.ExcelFile(WIP_EXCEL_PATH, engine="openpyxl")
        for name in xls.sheet_names:
            s = name.strip()
            if "2025" in s and "明細" in s:
                return name
        raise RuntimeError("❌ 找不到包含 2025 + 明細 的 sheet")
    except Exception as e:
        raise RuntimeError(f"讀取 Excel Sheet 失敗: {e}")

def wip_find_last_row(sheet_name: str) -> int:
    """WIP: 只讀 Column A 偵測最後一筆"""
    col_a = pd.read_excel(
        WIP_EXCEL_PATH, sheet_name=sheet_name, usecols="A", header=None, engine="openpyxl"
    )
    # 從 header row 後開始
    data = col_a.iloc[WIP_HEADER_ROW - 1 :, 0]
    non_empty = data[data.notna() & (data.astype(str).str.strip() != "")]
    if non_empty.empty:
        raise RuntimeError("❌ Column A 沒有任何有效資料")
    return non_empty.index[-1] + 1

def wip_normalize_date(val):
    """WIP: 日期清洗"""
    if pd.isna(val) or str(val).strip() == "": return None
    try:
        s = str(val).split(" ")[0]
        dt = pd.to_datetime(s, errors="coerce")
        return dt.strftime("%Y-%m-%d") if pd.notna(dt) else None
    except: return None

def run_wip_sync_once():
    """WIP: 執行一次完整的同步"""
    try:
        wip_logger.info("🔄 [WIP] 開始執行同步作業...")
        if not os.path.exists(WIP_EXCEL_PATH):
             wip_logger.warning("⚠️ [WIP] 檔案不存在，跳過同步")
             return False

        # 1. 找 Sheet
        sheet = wip_find_target_sheet()
        
        # 2. 找最後一行
        last_row = wip_find_last_row(sheet)
        nrows = last_row - (WIP_HEADER_ROW - 1)
        
        # 3. 讀取資料
        wip_logger.info(f"📥 [WIP] 正在讀取 {nrows} 筆資料 (Sheet: {sheet})")
        df = pd.read_excel(
            WIP_EXCEL_PATH, sheet_name=sheet, header=WIP_HEADER_ROW - 1,
            usecols=WIP_USECOLS, nrows=nrows, engine="openpyxl", dtype=str
        )
        df = df.dropna(how="all")

        # 4. 修正日期
        for col in ["滴定日期", "入庫日期", "警示日期", "藥劑效期"]:
            if col in df.columns:
                df[col] = df[col].apply(wip_normalize_date)
        
        df["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 5. 寫入 DB
        os.makedirs(os.path.dirname(WIP_DB_PATH), exist_ok=True)
        with sqlite3.connect(WIP_DB_PATH) as conn:
            df.to_sql(WIP_TABLE_NAME, conn, if_exists="replace", index=False)
        
        wip_logger.info(f"🎉 [WIP] 同步成功！共寫入 {len(df)} 筆資料。")
        return True

    except Exception as e:
        wip_logger.error(f"❌ [WIP] 同步失敗: {e}")
        return False

def wip_monitor_loop(stop_event: threading.Event):
    """WIP: 背景監控迴圈"""
    wip_logger.info(f"🚀 [WIP] 監控線程啟動 (間隔: {WIP_CHECK_INTERVAL}s)")
    wip_logger.info(f"📂 [WIP] 目標: {WIP_EXCEL_PATH}")
    
    last_mtime = 0
    
    # 初始同步嘗試
    try:
        if os.path.exists(WIP_EXCEL_PATH):
            last_mtime = os.path.getmtime(WIP_EXCEL_PATH)
            run_wip_sync_once()
    except Exception as e:
        wip_logger.warning(f"⚠️ [WIP] 初始同步跳過: {e}")

    while not stop_event.is_set():
        try:
            if not os.path.exists(WIP_EXCEL_PATH):
                # wip_logger.warning("⚠️ [WIP] 找不到 Excel 檔案，等待連線...")
                pass # 避免洗版
            else:
                current_mtime = os.path.getmtime(WIP_EXCEL_PATH)
                
                if current_mtime > last_mtime:
                    wip_logger.info("🔔 [WIP] 偵測到檔案變更！準備同步...")
                    time.sleep(2) # 等待寫入完成
                    
                    try:
                        if run_wip_sync_once():
                            last_mtime = current_mtime
                    except PermissionError:
                        wip_logger.warning("🔒 [WIP] 檔案鎖定中，稍後重試")
                    except Exception as e:
                        wip_logger.error(f"❌ [WIP] 未預期錯誤: {e}")
            
        except Exception as e:
            wip_logger.error(f"💥 [WIP] 監控迴圈錯誤: {e}")
        
        if stop_event.wait(WIP_CHECK_INTERVAL):
            break
            
    wip_logger.info("🛑 [WIP] 監控線程已停止")

def start_wip_monitor():
    """啟動 WIP 監控"""
    if state._wip_thread and state._wip_thread.is_alive():
        logger.warning("⚠️ WIP Monitor 已經在運行")
        return

    state._wip_stop_event.clear()
    state._wip_thread = threading.Thread(
        target=wip_monitor_loop,
        args=(state._wip_stop_event,),
        daemon=True,
        name="WipMonitorThread"
    )
    state._wip_thread.start()

def stop_wip_monitor():
    """停止 WIP 監控"""
    if state._wip_thread:
        logger.info("正在停止 WIP Monitor...")
        state._wip_stop_event.set()
        state._wip_thread.join(timeout=5)
        state._wip_thread = None

# ====================================================================
# ====== 工具函數 (原有 A-E 檔邏輯) ======
# ====================================================================

def safe_ident(name: str) -> str:
    if name is None: name = ""
    s = str(name).replace('"', '""').strip()
    return s if s else "_col_"

def col_to_index(col: str) -> int:
    col = col.upper()
    s = 0
    for ch in col:
        s = s * 26 + (ord(ch) - 64)
    return s

def get_plan_dir() -> str:
    candidates = [
        os.path.join(BASE_DIR, "production_plan"),
        os.path.join(BASE_DIR, "paoduction_plan"),
    ]
    for d in candidates:
        if os.path.isdir(d): return d
    return BASE_DIR

def pick_latest_plan_file() -> Optional[str]:
    files = []
    today = date.today()
    rx = re.compile(r"Production plan-(\d{8})\.xlsm$", re.IGNORECASE)
    base = get_plan_dir()
    
    try:
        names = os.listdir(base)
    except FileNotFoundError:
        return None

    for name in names:
        m = rx.match(name)
        if not m: continue
        ymd = m.group(1)
        try:
            d = datetime.strptime(ymd, "%Y%m%d").date()
        except Exception: continue
        if d <= today:
            files.append((d, os.path.join(base, name)))

    if not files: return None
    files.sort(key=lambda x: (today - x[0]))
    return files[0][1]

def normalize_df_for_sqlite(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col_name in out.columns:
        col_name_str = str(col_name).strip()
        s = out[col_name]

        if col_name_str in NO_DECIMAL_COLUMNS:
            def remove_decimal(x):
                if pd.isna(x): return ""
                if isinstance(x, (int, float)):
                    try: return str(int(float(x)))
                    except: return str(x)
                x_str = str(x).strip()
                if '.' in x_str:
                    try: return str(int(float(x_str)))
                    except: return x_str.split('.')[0]
                return x_str
            
            out[col_name] = s.map(remove_decimal)
        
        elif col_name_str in TIME_COLUMNS:
            def convert_excel_time(x):
                if pd.isna(x): return ""
                if isinstance(x, (dt.time, dt.datetime, pd.Timestamp)):
                    return x.strftime("%H:%M")
                if isinstance(x, (int, float)):
                    try:
                        total_seconds = int(float(x) * 86400)
                        hours = (total_seconds // 3600) % 24
                        minutes = (total_seconds % 3600) // 60
                        return f"{hours:02d}:{minutes:02d}"
                    except: return str(x)
                return str(x)
            out[col_name] = s.map(convert_excel_time)
        
        elif is_datetime(s): 
            out[col_name] = s.dt.strftime("%Y-%m-%d").fillna("")
        
        else:
            out[col_name] = s.map(lambda x: (
                x.strftime("%Y-%m-%d") if isinstance(x, (dt.date, dt.datetime, pd.Timestamp))
                else x.strftime("%H:%M") if isinstance(x, dt.time)
                else ("" if pd.isna(x) else str(x))
            ))
    return out

def read_range_df(xl_path: str, sheet: str, header_row: int, data_start_row: int, 
                  last_col_letter: str, lastrow_by_col_letter: str) -> pd.DataFrame:
    for i in range(READ_RETRY):
        try:
            df = pd.read_excel(xl_path, sheet_name=sheet, header=header_row - 1, engine="openpyxl")
            break
        except Exception as e:
            if i < READ_RETRY - 1:
                time.sleep(READ_RETRY_SLEEP)
            else:
                raise e

    last_col_idx = min(col_to_index(last_col_letter), df.shape[1])
    lastrow_col_idx = col_to_index(lastrow_by_col_letter)
    target_col_pos = max(0, min(lastrow_col_idx - 1, df.shape[1] - 1))

    iloc_start = max(0, data_start_row - header_row - 1)
    sub = df.iloc[iloc_start:, :]

    nonempty = sub.iloc[:, target_col_pos].astype(str).str.strip() != ""
    if not nonempty.any():
        return df.iloc[0:0, :last_col_idx].fillna("")

    last_rel_idx = nonempty[nonempty].index[-1]
    iloc_end = df.index.get_loc(last_rel_idx) + 1

    df2 = df.iloc[iloc_start:iloc_end, :last_col_idx].copy()
    df2.columns = [str(c).replace("\n", " ").strip() for c in df2.columns]
    df2 = df2.dropna(how="all").fillna("")
    df2 = normalize_df_for_sqlite(df2)
    return df2

def normalize_b_headers(cols: list) -> list:
    out = []
    for c in cols:
        s = str(c).strip()
        m = re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+\d{2}:\d{2}:\d{2})?\s*$", s)
        if m:
            y, mo, da = map(int, m.groups())
            out.append(f"{y:04d}-{mo:02d}-{da:02d}")
        else:
            out.append(s)
    return out

def normalize_columns(df: pd.DataFrame, header_map: Dict[str, str]) -> pd.DataFrame:
    cols = []
    seen = {}
    for c in df.columns:
        s = str(c).replace("\n", " ").replace("\u3000", " ").strip()
        s = header_map.get(s, s)
        if s in seen:
            seen[s] += 1
            s = f"{s}__{seen[s]}"
        else:
            seen[s] = 1
        cols.append(s)
    df.columns = cols
    return df

def drop_rows_with_empty_keys(df: pd.DataFrame, keys: List[str]) -> pd.DataFrame:
    for k in keys:
        if k not in df.columns:
            return df.iloc[0:0]
        df[k] = df[k].map(lambda x: str(x).strip())
    mask = df[keys].apply(lambda s: s.str.len() > 0).all(axis=1)
    return df[mask].copy()

# ====================================================================
# ====== 資料庫操作函數 ======
# ====================================================================

def ensure_table_and_columns(conn: sqlite3.Connection, table: str, df: pd.DataFrame):
    table_q = safe_ident(table)
    cols = [f'"{safe_ident(c)}" TEXT' for c in df.columns]
    with conn:
        conn.execute(f'CREATE TABLE IF NOT EXISTS "{table_q}" ({", ".join(cols)});')
        cur = conn.execute(f'PRAGMA table_info("{table_q}")')
        existing = {row[1] for row in cur.fetchall()}
        for c in df.columns:
            cq = safe_ident(c)
            if cq not in existing:
                conn.execute(f'ALTER TABLE "{table_q}" ADD COLUMN "{cq}" TEXT;')

def ensure_unique_index(conn: sqlite3.Connection, table: str, keys: List[str]):
    if not keys: return
    table_q = safe_ident(table)
    idx_name = f'ux_{table_q}_' + "_".join([safe_ident(k).lower() for k in keys])
    cols = ",".join([f'"{safe_ident(k)}"' for k in keys])
    with conn:
        conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "{idx_name}" ON "{table_q}" ({cols});')

def upsert(conn: sqlite3.Connection, table: str, df: pd.DataFrame, keys: List[str]):
    ensure_table_and_columns(conn, table, df)
    ensure_unique_index(conn, table, keys)

    cols = list(df.columns)
    cols_q = [safe_ident(c) for c in cols]
    keys_q = [safe_ident(k) for k in keys]
    nonkeys = [c for c in cols_q if c not in set(keys_q)]

    col_list = ", ".join([f'"{c}"' for c in cols_q])
    placeholders = ", ".join(["?"] * len(cols_q))
    conflict = ", ".join([f'"{k}"' for k in keys_q])

    if keys and nonkeys:
        set_clause = ", ".join([f'"{c}"=excluded."{c}"' for c in nonkeys])
        sql = (f'INSERT INTO "{safe_ident(table)}" ({col_list}) VALUES ({placeholders}) '
               f'ON CONFLICT ({conflict}) DO UPDATE SET {set_clause};')
    elif keys:
        sql = (f'INSERT INTO "{safe_ident(table)}" ({col_list}) VALUES ({placeholders}) '
               f'ON CONFLICT ({conflict}) DO NOTHING;')
    else:
        sql = f'REPLACE INTO "{safe_ident(table)}" ({col_list}) VALUES ({placeholders});'

    with conn:
        conn.executemany(sql, df.itertuples(index=False, name=None))

# ====================================================================
# ====== Excel 重算函數 (完整版) ======
# ====================================================================

def recalc_and_make_temp_copy(filepath: str, timeout_sec: int = 30) -> str:
    """重算 Excel 檔案並建立暫存副本"""
    tmp = None
    # 方案1：pywin32 COM
    try:
        import pythoncom
        import win32com.client
        try:
            win32com.client.gencache.is_readonly = True
        except Exception:
            pass

        def _com_job():
            nonlocal tmp
            pythoncom.CoInitialize()
            xl = None
            wb = None
            try:
                xl = win32com.client.DispatchEx("Excel.Application")
                for attr, val in (("Visible", False), ("DisplayAlerts", False)):
                    try:
                        setattr(xl, attr, val)
                    except Exception:
                        pass
                try:
                    xl.AutoRecover.Enabled = False
                except Exception:
                    pass

                try:
                    wb = xl.Workbooks.Open(filepath, 0, False, None, None, None, True)
                except Exception:
                    wb = xl.Workbooks.Open(filepath, 0, False)

                for f in (
                    lambda: xl.CalculateFullRebuild(),
                    lambda: xl.CalculateFull(),
                    lambda: wb.Application.CalculateFullRebuild(),
                    lambda: wb.Application.CalculateFull(),
                ):
                    try:
                        f()
                        break
                    except Exception:
                        continue

                fd, tmp = tempfile.mkstemp(suffix=".xlsx")
                os.close(fd)
                try:
                    wb.SaveCopyAs(tmp)
                except Exception:
                    base, _ = os.path.splitext(tmp)
                    tmp = base + ".xlsm"
                    wb.SaveCopyAs(tmp)
            finally:
                if wb:
                    try: wb.Close(False)
                    except Exception: pass
                if xl:
                    try: xl.Quit()
                    except Exception: pass
                pythoncom.CoUninitialize()

        t = threading.Thread(target=_com_job, daemon=True)
        t.start()
        t.join(timeout_sec)
        if t.is_alive():
            raise TimeoutError("COM recalc timeout")
        return tmp or filepath
    except Exception as e:
        logger.warning(f"A 檔重算：COM 失敗（{e}），改用 VBScript")

    # 方案2：VBScript
    try:
        import textwrap
        fd, tmp = tempfile.mkstemp(suffix=".xlsm")
        os.close(fd)
        vbs = textwrap.dedent(f"""
        On Error Resume Next
        Dim xl, wb
        Set xl = CreateObject("Excel.Application")
        If Not xl Is Nothing Then
            xl.DisplayAlerts = False
            xl.Visible = False
            On Error Resume Next
            Set wb = xl.Workbooks.Open("{filepath.replace('"','""')}", 0, False, , , , True)
            If Not wb Is Nothing Then
                Err.Clear
                xl.CalculateFullRebuild
                If Err.Number <> 0 Then
                    Err.Clear
                    xl.CalculateFull
                End If
                wb.SaveCopyAs "{tmp.replace('"','""')}"
                wb.Close False
            End If
            xl.Quit
        End If
        """)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".vbs") as f:
            f.write(vbs.encode("utf-8-sig"))
            vbs_path = f.name
        try:
            p = subprocess.Popen(
                ["cscript.exe", "//nologo", vbs_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            waited = 0.0
            while p.poll() is None and waited < timeout_sec:
                time.sleep(0.5)
                waited += 0.5
            if p.poll() is None:
                try: p.terminate()
                except Exception: pass
        finally:
            try: os.unlink(vbs_path)
            except Exception: pass
        return tmp or filepath
    except Exception as e:
        logger.warning(f"A 檔重算：VBScript 也失敗（{e}），改讀原檔")
        return filepath

# ====================================================================
# ====== A-E 檔同步核心函數 ======
# ====================================================================

def sync_file(config: FileConfig, file_key: str):
    global MAIN_DB_PATH
    filepath = config.path
    if not filepath or not os.path.exists(filepath):
        logger.warning(f"{file_key} 檔不存在或路徑為空")
        return
    
    tmp_to_delete = None
    with db_lock:
        logger.info(f"🔄 同步 {file_key} 檔開始（{config.table}）")
        
        # A 檔需要重算
        if file_key == "A":
            try:
                calc_path = recalc_and_make_temp_copy(filepath)
                if os.path.abspath(calc_path) != os.path.abspath(filepath):
                    tmp_to_delete = calc_path
                    filepath = calc_path
            except Exception as e:
                logger.warning(f"{file_key} 檔重算警告：{e}（將直接讀原檔）")

        try:
            df = read_range_df(filepath, config.sheet, config.header_row, config.data_start_row,
                               config.last_col, config.lastrow_by_col)
            
            if file_key == "B":
                df.columns = normalize_b_headers(list(df.columns))
            elif config.header_map:
                df = normalize_columns(df, config.header_map)
            
            if config.keys:
                df = drop_rows_with_empty_keys(df, config.keys)
            
            if len(df) == 0:
                logger.warning(f"{file_key} 檔有效資料為 0 列")
                return
            
            with sqlite3.connect(MAIN_DB_PATH) as conn:
                if config.keys: upsert(conn, config.table, df, config.keys)
                else:
                    ensure_table_and_columns(conn, config.table, df)
                    conn.execute(f'DELETE FROM "{safe_ident(config.table)}"')
                    df.to_sql(config.table, conn, if_exists='append', index=False)
            
            logger.info(f"✅ {file_key} 檔同步完成：{len(df)} 筆")
        except Exception as e:
            logger.error(f"❌ {file_key} 檔同步失敗：{e}")
            logger.error(traceback.format_exc())
        finally:
            if tmp_to_delete and os.path.exists(tmp_to_delete):
                try: os.remove(tmp_to_delete)
                except Exception: pass

def sync_A(): sync_file(FILE_A_CONFIG, "A")
def sync_B():
    file_b = pick_latest_plan_file()
    if not file_b:
        logger.warning("找不到合法的 Production plan-YYYYMMDD.xlsm")
        return
    config = FileConfig(path=file_b, sheet=FILE_B_CONFIG.sheet, header_row=FILE_B_CONFIG.header_row,
                        data_start_row=FILE_B_CONFIG.data_start_row, last_col=FILE_B_CONFIG.last_col,
                        lastrow_by_col=FILE_B_CONFIG.lastrow_by_col, table=FILE_B_CONFIG.table, keys=FILE_B_CONFIG.keys)
    sync_file(config, "B")
def sync_C(): sync_file(FILE_C_CONFIG, "C")
def sync_D(): sync_file(FILE_D_CONFIG, "D")
def sync_E(): sync_file(FILE_E_CONFIG, "E")

# ====================================================================
# ====== Watchdog 監控 (原有 A-E 檔) ======
# ====================================================================

class Handler(FileSystemEventHandler):
    def on_any_event(self, event):
        if event.is_directory: return
        path = os.path.abspath(event.src_path)
        filename = os.path.basename(path)
        if filename.startswith('~$') or filename.endswith('.tmp'): return

        now = time.time()
        last = state.get_last_event_time(path)
        if now - last < DEBOUNCE_SECONDS: return
        state.set_last_event_time(path, now)

        try:
            if os.path.abspath(FILE_A_CONFIG.path).lower() == path.lower():
                logger.info("🎯 偵測到 A 檔變更"); sync_A(); return
            
            current_b = pick_latest_plan_file()
            if current_b and os.path.abspath(current_b).lower() == path.lower():
                logger.info("🎯 偵測到 B 檔變更"); sync_B(); return

            for key, config in [("C", FILE_C_CONFIG), ("D", FILE_D_CONFIG), ("E", FILE_E_CONFIG)]:
                if os.path.abspath(config.path).lower() == path.lower():
                    logger.info(f"🎯 偵測到 {key} 檔變更"); sync_file(config, key); return
            
            plan_dir = get_plan_dir()
            if os.path.dirname(path).lower() == plan_dir.lower() and re.search(r"Production plan-\d{8}\.xlsm$", filename, re.I):
                logger.info("🎯 偵測到新的 B 檔"); sync_B(); return

        except Exception as e:
            logger.error(f"❌ 事件處理錯誤: {e}")

def start_watch():
    if state.observer and state.observer.is_alive(): return
    
    logger.info("🔍 啟動 Watchdog 監控 (A/B/C/D/E)")
    try:
        state.observer = PollingObserver(timeout=0.5)
        handler = Handler()
        
        # 監控 A/C/D/E
        for _, config in [("A", FILE_A_CONFIG), ("C", FILE_C_CONFIG), ("D", FILE_D_CONFIG), ("E", FILE_E_CONFIG)]:
            if os.path.exists(config.path):
                folder = os.path.dirname(config.path)
                if folder not in state.watched_folders:
                    state.observer.schedule(handler, folder, recursive=False)
                    state.add_watched_folder(folder)

        # 監控 B
        bfile = pick_latest_plan_file()
        if bfile and os.path.exists(bfile):
            folder = os.path.dirname(bfile)
            if folder not in state.watched_folders:
                state.observer.schedule(handler, folder, recursive=False)
                state.add_watched_folder(folder)
        
        if not state.watched_folders:
            logger.error("❌ 沒有任何檔案被監控！")
            return

        state.observer.start()
        logger.info(f"✅ Watchdog 啟動成功，監控 {len(state.watched_folders)} 個資料夾")
    except Exception as e:
        logger.error(f"❌ Watchdog 啟動異常: {e}")

def stop_watch():
    if state.observer:
        state.observer.stop()
        state.observer.join(timeout=5)
        state.observer = None

# ====================================================================
# ====== 初始化與清理 ======
# ====================================================================

def initialize_sync_service():
    if state.sync_init_done: return
    logger.info("🚀 初始化同步服務")
    
    # 1. 初始同步 A-E
    sync_A(); sync_B(); sync_C(); sync_D(); sync_E()
    
    # 2. 啟動 A-E Watchdog
    start_watch()

    # 3. [新增] 啟動 WIP 監控
    start_wip_monitor()

    # 4. 初始化 WIP Blueprint
    try:
        init_wip_automation(app)
    except Exception as e:
        logger.error(f"❌ WIP Blueprint 初始化異常: {e}")

    state.sync_init_done = True

def final_sync_before_exit():
    logger.info("🔄 關閉前最終同步")
    sync_A(); sync_B(); sync_C(); sync_D(); sync_E()
    run_wip_sync_once()

# ====================================================================
# ====== Flask 應用程式 ======
# ====================================================================

app = Flask(__name__, static_folder=str(DIST), static_url_path="/")

# 註冊 Blueprints
register_beads_ipqc_routes(app)
app.register_blueprint(wip_automation_bp, url_prefix="")

@app.before_request
def _init_before_request():
    if not state.sync_init_done:
        initialize_sync_service()

# --- API 路由 ---

# ==========================================
# 請將以下完整程式碼覆蓋 main.py 中對應的 API 區塊
# ==========================================

@app.route("/api/schedule/utilization", methods=["GET"])
def api_utilization():
    """稼動率計算（完整修復版）"""
    try:
        mode = request.args.get("mode", "day")
        date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
        query_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        if not os.path.exists(FORMULATE_DB_PATH):
            return jsonify({"ok": True, "titration_utilization": 0, "dryer_utilization": 0})

        with sqlite3.connect(FORMULATE_DB_PATH) as conn:
            # 依據模式建立 SQL
            if mode == "day":
                d_slash = query_date.strftime("%Y/%m/%d")
                d_dash = query_date.strftime("%Y-%m-%d")
                query = "SELECT Pump, Lyophilizer, Date FROM DropletSchedule WHERE Date LIKE ? OR Date LIKE ?"
                params = (f"{d_slash}%", f"{d_dash}%")
                period_desc = d_dash
            elif mode == "week":
                iso_weekday = query_date.isoweekday()
                start = query_date - dt.timedelta(days=iso_weekday - 1)
                end = start + dt.timedelta(days=6)
                s_slash, s_dash = start.strftime("%Y/%m/%d"), start.strftime("%Y-%m-%d")
                e_slash, e_dash = end.strftime("%Y/%m/%d"), end.strftime("%Y-%m-%d")
                # 簡化查詢：使用字串比較 (注意格式需統一，此處假設 DB 格式混亂，用 OR 條件較安全但較長，這裡用範圍近似)
                query = "SELECT Pump, Lyophilizer, Date FROM DropletSchedule" # 全撈再用 Pandas 過濾比較穩
                params = ()
                period_desc = f"{start} ~ {end}"
            else: # month
                query = "SELECT Pump, Lyophilizer, Date FROM DropletSchedule"
                params = ()
                period_desc = query_date.strftime("%Y-%m")

            df = pd.read_sql_query(query, conn, params=params)

        if df.empty:
            return jsonify({"ok": True, "titration_utilization": 0, "dryer_utilization": 0})

        # Pandas 過濾日期 (解決 SQLite 日期格式不一問題)
        df['dt'] = pd.to_datetime(df['Date'], errors='coerce')
        if mode == "week":
            df = df[(df['dt'].dt.date >= start) & (df['dt'].dt.date <= end)]
        elif mode == "month":
            df = df[(df['dt'].dt.year == query_date.year) & (df['dt'].dt.month == query_date.month) & (df['dt'].dt.date <= query_date)]

        if df.empty:
            return jsonify({"ok": True, "titration_utilization": 0, "dryer_utilization": 0})

        work_days = df['dt'].dt.date.nunique() or 1
        
        # 滴定計算
        machines = df["Pump"].dropna().astype(str).str.strip()
        machines = machines[machines != ""]
        ivek_count = machines.str.contains("IVEK", case=False, na=False).sum()
        port_count = len(machines) - ivek_count
        titration_used = port_count + ivek_count
        titration_capacity = work_days * TOTAL_TITRATION_CAPACITY
        titration_util = round((titration_used / titration_capacity) * 100, 1) if titration_capacity > 0 else 0

        # 凍乾計算
        if mode == "day":
            dryer_used = df["Lyophilizer"].dropna().nunique()
        else:
            # 週/月: 每日加總
            dryer_used = df.groupby(df['dt'].dt.date)['Lyophilizer'].nunique().sum()
            
        dryer_capacity = work_days * TOTAL_DRYERS
        dryer_util = round((dryer_used / dryer_capacity) * 100, 1) if dryer_capacity > 0 else 0

        return jsonify({
            "ok": True, "period": period_desc,
            "titration_utilization": titration_util, "dryer_utilization": dryer_util,
            "titration_used": int(titration_used), "dryer_used": int(dryer_used)
        })

    except Exception as e:
        logger.error(f"Util calc failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/schedule/completion-rate", methods=["GET"])
def api_completion_rate():
    """完成率計算（完整修復版）"""
    try:
        date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
        d_slash = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y/%m/%d")
        
        if not os.path.exists(FORMULATE_DB_PATH) or not os.path.exists(WORK_ORDER_DB_PATH):
            return jsonify({"ok": True, "dispensing_rate": 0, "titration_rate": 0, "freeze_drying_rate": 0})

        # 1. 取得今日排程工單 (分母)
        with sqlite3.connect(FORMULATE_DB_PATH) as conn:
            df_sched = pd.read_sql_query(
                "SELECT DISTINCT WorkOrder FROM DropletSchedule WHERE (Date LIKE ? OR Date LIKE ?) AND WorkOrder IS NOT NULL AND WorkOrder != ''",
                conn, params=(f"{d_slash}%", f"{date_str}%")
            )
        
        target_orders = df_sched['WorkOrder'].astype(str).str.strip().unique().tolist()
        total = len(target_orders)
        
        if total == 0:
            return jsonify({"ok": True, "total_orders": 0, "dispensing_rate": 0, "titration_rate": 0})

        # 2. 查詢實際進度 (分子)
        placeholders = ','.join(['?'] * len(target_orders))
        with sqlite3.connect(WORK_ORDER_DB_PATH) as conn:
            df_rec = pd.read_sql_query(
                f"SELECT 工單號, 時間_收藥, 時間_滴定結束, 時間_凍乾開始 FROM work_orders WHERE 工單號 IN ({placeholders})",
                conn, params=target_orders
            )
        
        if df_rec.empty:
            return jsonify({"ok": True, "total_orders": total, "dispensing_rate": 0})

        def is_done(val): return val is not None and str(val).strip() not in ["", "None", "nan"]
        
        disp_cnt = df_rec[df_rec['時間_收藥'].apply(is_done)]['工單號'].nunique()
        titr_cnt = df_rec[df_rec['時間_滴定結束'].apply(is_done)]['工單號'].nunique()
        dry_cnt = df_rec[df_rec['時間_凍乾開始'].apply(is_done)]['工單號'].nunique()

        return jsonify({
            "ok": True, "date": date_str, "total_orders": total,
            "dispensing_rate": round(disp_cnt/total*100, 1),
            "titration_rate": round(titr_cnt/total*100, 1),
            "freeze_drying_rate": round(dry_cnt/total*100, 1)
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/schedule/workload-stats", methods=["GET"])
def api_workload_stats():
    """工作分派統計（完整修復版）"""
    try:
        mode = request.args.get("mode", "week")
        date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
        q_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        if not os.path.exists(FORMULATE_DB_PATH): return jsonify({"ok": True, "staff_stats": []})

        with sqlite3.connect(FORMULATE_DB_PATH) as conn:
            query = "SELECT Date, WorkOrder, Preparer FROM DropletSchedule"
            df = pd.read_sql_query(query, conn)
        
        if df.empty: return jsonify({"ok": True, "staff_stats": []})

        # 過濾日期
        df['dt'] = pd.to_datetime(df['Date'], errors='coerce')
        if mode == "week":
            iso_wd = q_date.isoweekday()
            start = q_date - dt.timedelta(days=iso_wd-1)
            end = start + dt.timedelta(days=6)
            df = df[(df['dt'].dt.date >= start) & (df['dt'].dt.date <= end)]
        else: # month
            df = df[(df['dt'].dt.year == q_date.year) & (df['dt'].dt.month == q_date.month) & (df['dt'].dt.date <= q_date)]

        # 統計
        df = df[df['WorkOrder'].notna() & df['Preparer'].notna()]
        df['key'] = df['WorkOrder'].astype(str) + "_" + df['Preparer'].astype(str)
        df_uniq = df.drop_duplicates(subset=['key'])
        
        stats = df_uniq['Preparer'].value_counts().reset_index()
        stats.columns = ['name', 'count']
        total = stats['count'].sum()
        
        result = []
        for _, row in stats.iterrows():
            result.append({
                "name": row['name'], "count": int(row['count']),
                "percentage": round(row['count']/total*100, 1) if total > 0 else 0
            })
            
        return jsonify({"ok": True, "staff_stats": result, "total_assignments": int(total)})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
# ==========================================
# [修復] 排程表查詢 API (DropletSchedule)
# 用於前端 "排程查詢" 功能
# ==========================================
# ==========================================
# [修復] 排程表查詢 API (修正 timedelta 錯誤)
# ==========================================
# === 排程查詢 API ===
@app.route("/api/schedule/search", methods=["GET"])
def api_search_schedule():
    """搜尋排程資料（DropletSchedule 版本）"""
    try:
        search_type = request.args.get("searchType", "week")
        search_value = request.args.get("searchValue", "")
        operator_filter = request.args.get("operator", "")
        
        if not search_value:
            return jsonify({"ok": False, "message": "缺少搜尋值"}), 400
        
        if not os.path.exists(FORMULATE_DB_PATH):
            logger.warning(f"⚠️ 資料庫不存在: {FORMULATE_DB_PATH}")
            return jsonify([])
        
        with sqlite3.connect(FORMULATE_DB_PATH) as conn:
            cursor = conn.cursor()
            
            # 檢查資料表是否存在
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='DropletSchedule'"
            )
            if not cursor.fetchone():
                logger.warning(f"⚠️ 資料表 DropletSchedule 不存在")
                return jsonify([])
            
            # 查詢條件
            if search_type == "week":
                # 週別搜尋：提取年份和週數
                year, week = search_value.split("_W")
                # 計算該週的日期範圍
                from datetime import datetime, timedelta
                jan_1 = datetime.strptime(f"{year}-01-01", "%Y-%m-%d")
                week_start = jan_1 + timedelta(weeks=int(week)-1)
                # 調整到週一
                week_start = week_start - timedelta(days=week_start.weekday())
                week_end = week_start + timedelta(days=6)
                
                query = """
                    SELECT * FROM DropletSchedule 
                    WHERE Date >= ? AND Date <= ?
                """
                params = (
                    week_start.strftime("%Y/%m/%d"),
                    week_end.strftime("%Y/%m/%d")
                )
            else:
                # 日期搜尋（前端傳來 YYYY-MM-DD，資料庫是 YYYY/MM/DD）
                db_date = search_value.replace("-", "/")
                query = "SELECT * FROM DropletSchedule WHERE Date = ?"
                params = (db_date,)
            
            df = pd.read_sql_query(query, conn, params=params)
        
        if df.empty:
            logger.info(f"搜尋無結果：{search_type} = {search_value}")
            return jsonify([])
        
        # 欄位映射
        column_mapping = {
            "Date": "date",
            "Marker": "marker",
            "Pump": "machine",
            "Lyophilizer": "dryer",
            "Preparer": "operator",
            "DrugGivenAt": "rdTime",
            "ExpectedTitrationStart": "start",
            "ExpectedTitrationEnd": "end",
            "Quantity": "qty",
            "Lot": "batch",
            "WorkOrder": "workOrder",
            "Remark": "remark",
        }
        
        df = df.rename(columns=column_mapping)
        
        # 日期格式轉換：2025/12/10 → 2025-12-10
        if 'date' in df.columns:
            df['date'] = df['date'].str.replace("/", "-")
        
        # 從 "Liquid form QC" 表查詢 P/N
        with sqlite3.connect(FORMULATE_DB_PATH) as conn:
            try:
                liquid_df = pd.read_sql_query(
                    'SELECT Name, PN FROM "Liquid form QC"',
                    conn
                )
                
                # 建立 Marker → PN 映射（忽略大小寫與空格）
                liquid_df['Name_normalized'] = liquid_df['Name'].str.strip().str.upper()
                marker_to_pn = dict(zip(liquid_df['Name_normalized'], liquid_df['PN']))
                
                logger.info(f"✅ 成功從 Liquid form QC 表載入 {len(marker_to_pn)} 個 Marker 的 P/N")
                
            except Exception as e:
                logger.error(f"❌ 查詢 Liquid form QC 表失敗: {e}")
                marker_to_pn = {}
        
        # 為每個 Marker 查詢對應的 P/N
        def get_pn(marker):
            if pd.isna(marker):
                return ""
            normalized = str(marker).strip().upper()
            pn = marker_to_pn.get(normalized, "")
            if not pn:
                logger.debug(f"⚠️ 找不到 Marker '{marker}' 的 P/N")
            return pn
        
        df['pn'] = df['marker'].apply(get_pn)
        
        # 確保欄位存在
        required_fields = ["date", "marker", "machine", "dryer", "operator", 
                          "rdTime", "start", "end", "qty", "pn", "batch", "workOrder", "remark"]
        for field in required_fields:
            if field not in df.columns:
                df[field] = ""
        
        # 人名過濾
        if operator_filter:
            df = df[df['operator'].str.contains(operator_filter, case=False, na=False)]
            if df.empty:
                logger.info(f"人名過濾後無結果：{operator_filter}")
                return jsonify([])
        
        # ✅ 修改：排序邏輯（IVEK → Port AM → Port PM）
        def extract_port_number(machine_name):
            """提取 Port 編號"""
            if pd.isna(machine_name) or not str(machine_name).strip():
                return 999  # 空值排最後
            match = re.search(r'(\d+)', str(machine_name))
            if match:
                return int(match.group(1))
            return 999

        def is_ivek(machine_name):
            """判斷是否為 IVEK（返回 0 表示 IVEK，排在最前面）"""
            if pd.isna(machine_name):
                return 1
            return 0 if "IVEK" in str(machine_name).upper() else 1

        def get_time_period(time_str):
            """判斷是 AM 還是 PM（0=AM, 1=PM）"""
            if pd.isna(time_str) or not str(time_str).strip():
                return 2  # 空值排最後
            try:
                time_str = str(time_str).strip()
                if ':' in time_str:
                    hour = int(time_str.split(':')[0])
                elif len(time_str) >= 3:
                    hour = int(time_str[:-2])
                else:
                    return 2
                
                # 12:00 以前是 AM，12:00 及之後是 PM
                return 0 if hour < 12 else 1
            except:
                return 2

        def parse_time_to_minutes(time_str):
            """將時間字串轉換為分鐘數（用於同時段內的排序）"""
            if pd.isna(time_str) or not str(time_str).strip():
                return 9999
            try:
                time_str = str(time_str).strip()
                if ':' in time_str:
                    h, m = time_str.split(':')
                    return int(h) * 60 + int(m)
                elif len(time_str) >= 3:
                    h = int(time_str[:-2])
                    m = int(time_str[-2:])
                    return h * 60 + m
                else:
                    return 9999
            except:
                return 9999

        # 建立排序用的輔助欄位
        df['_date_sort'] = pd.to_datetime(df['date'])
        df['_is_ivek'] = df['machine'].apply(is_ivek)
        df['_time_period'] = df['start'].apply(get_time_period)  # 0=AM, 1=PM
        df['_port_num'] = df['machine'].apply(extract_port_number)
        df['_start_time_minutes'] = df['start'].apply(parse_time_to_minutes)

        # 排序邏輯：
        # 1. 日期（升序）
        # 2. IVEK 優先（0=IVEK 在前，1=Port 在後）
        # 3. 時段（0=AM 在前，1=PM 在後）
        # 4. Port 編號（Port1, Port2, ..., Port12）
        # 5. 開始時間（同 Port 同時段內按時間）
        df = df.sort_values(
            by=['_date_sort', '_is_ivek', '_time_period', '_port_num', '_start_time_minutes'],
            ascending=[True, True, True, True, True]
        )

        # 清除輔助欄位
        df = df.drop(columns=['_date_sort', '_is_ivek', '_time_period', '_port_num', '_start_time_minutes'])
        
        output_columns = ["date", "marker", "machine", "dryer", "operator", 
                         "rdTime", "start", "end", "qty", "pn", "batch", "workOrder", "remark"]
        df_output = df[[col for col in output_columns if col in df.columns]]
        
        logger.info(f"✅ 搜尋成功：{search_type} = {search_value}, 找到 {len(df_output)} 筆資料")
        
        return jsonify(df_output.to_dict(orient="records"))
        
    except Exception as e:
        logger.error(f"❌ 搜尋失敗: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"ok": False, "message": str(e)}), 500
    
# ====================================================================
# ====== 表單生產系統 API (新增) ======
# ====================================================================
@app.post("/api/forms/fetch-schedule")
def api_forms_fetch_schedule():
    """
    表單系統：根據日期範圍讀取排程資料 (修正版 - 解決 Marker 欄位問題)
    前端 Payload: { "year": "2025", "dates": ["2025-12-08", "2025-12-09", ...] }
    
    修正重點：
    1. 標準化欄位名稱（Marker, PN, Lot 等）
    2. 處理資料庫欄位大小寫不一致問題
    3. 增加調試日誌，便於追蹤問題
    """
    try:
        data = request.get_json(force=True)
        year = str(data.get("year", ""))
        dates = data.get("dates", [])

        if not year or not dates:
            return jsonify(ok=False, message="缺少必要參數 (year, dates)"), 400

        table_name = f"schedule_{year}"
        
        # 檢查資料庫是否存在
        if not os.path.exists(DB_PATH):
            logger.warning(f"表單查詢失敗: 資料庫不存在 {DB_PATH}")
            return jsonify(ok=False, message=f"排程資料庫不存在: {DB_PATH}"), 404

        results = []
        
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. 檢查資料表是否存在
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", 
                (table_name,)
            )
            if not cursor.fetchone():
                logger.warning(f"表單查詢失敗: 資料表 {table_name} 不存在")
                return jsonify(ok=False, message=f"資料表 {table_name} 不存在"), 404

            # 2. 檢查表結構 - 記錄實際的欄位名稱
            cursor.execute(f'PRAGMA table_info("{table_name}")')
            columns_info = cursor.fetchall()
            actual_columns = {col[1]: col[1] for col in columns_info}
            
            # 建立不區分大小寫的欄位映射
            column_map_lower = {col[1].lower(): col[1] for col in columns_info}
            
            logger.info(f"📊 資料表 {table_name} 欄位數: {len(actual_columns)}")
            logger.info(f"   前10個欄位: {list(actual_columns.keys())[:10]}")
            
            # 檢查關鍵欄位是否存在
            key_fields = ['marker', 'pn', 'lot', '滴定機', '凍乾機台', '日期']
            for field in key_fields:
                if field.lower() in column_map_lower:
                    actual_name = column_map_lower[field.lower()]
                    logger.info(f"   ✅ 找到欄位: {field} -> {actual_name}")
                else:
                    logger.warning(f"   ⚠️ 缺少欄位: {field}")

            # 3. 構建查詢 SQL
            placeholders = ",".join(["?"] * len(dates))
            query = f"""
                SELECT * FROM "{table_name}"
                WHERE REPLACE("日期", '/', '-') IN ({placeholders})
            """
            
            cursor.execute(query, dates)
            rows = cursor.fetchall()
            
            logger.info(f"📋 原始查詢結果: {len(rows)} 筆")
            
            if len(rows) > 0:
                # 顯示第一筆資料的所有欄位（用於調試）
                first_row = dict(rows[0])
                logger.info(f"   第一筆資料欄位: {list(first_row.keys())}")
                logger.info(f"   Marker相關欄位值:")
                for key in first_row.keys():
                    if 'marker' in key.lower():
                        logger.info(f"      {key} = {first_row[key]}")

            # 4. 資料處理與格式化 - 標準化欄位名稱
            for row in rows:
                r_dict = {}
                
                # 將 row 轉為字典，並標準化欄位名稱
                for key in row.keys():
                    value = row[key]
                    key_lower = key.lower()
                    
                    # === 關鍵修正：標準化特殊欄位名稱 ===
                    if key_lower == 'marker':
                        r_dict['Marker'] = value if value else ""
                        logger.debug(f"   標準化 Marker: {key} -> Marker = {value}")
                    elif key_lower == 'pn':
                        r_dict['PN'] = value if value else ""
                    elif key_lower == 'lot':
                        r_dict['Lot'] = value if value else ""
                    elif key_lower == 'remark':
                        r_dict['remark'] = value if value else ""
                    elif key_lower == 'batch':
                        r_dict['Batch'] = value if value else ""
                    else:
                        # 其他欄位保持原樣
                        r_dict[key] = value if value else ""
                
                # 確保必要欄位存在（即使資料庫中沒有）
                required_fields = {
                    'Marker': '',
                    'PN': '',
                    'Lot': '',
                    'remark': '',
                    '滴定機': '',
                    '凍乾機台': '',
                    '數量': '',
                    '配藥同仁': '',
                    '日期': '',
                    'RD給藥時間': '',
                    '預計滴定時間': '',
                    '預計結束': '',
                    '工單號碼': ''
                }
                
                for field, default in required_fields.items():
                    if field not in r_dict:
                        r_dict[field] = default
                
                # 正規化: 確保「數量」是整數顯示
                if "數量" in r_dict and r_dict["數量"]:
                    try:
                        val = r_dict["數量"]
                        r_dict["數量"] = int(float(str(val).replace(',', '')))
                    except:
                        pass
                
                # 正規化: 確保日期格式統一
                if "日期" in r_dict and r_dict["日期"]:
                    r_dict["日期"] = str(r_dict["日期"]).replace('/', '-')

                results.append(r_dict)

        logger.info(f"✅ 表單查詢成功: 年份 {year}, 查詢 {len(dates)} 天, 回傳 {len(results)} 筆資料")
        
        if results:
            sample = results[0]
            logger.info(f"📋 回傳資料範例:")
            logger.info(f"   欄位數: {len(sample)}")
            logger.info(f"   Marker: {sample.get('Marker', 'N/A')}")
            logger.info(f"   PN: {sample.get('PN', 'N/A')}")
            logger.info(f"   滴定機: {sample.get('滴定機', 'N/A')}")
        
        return jsonify(ok=True, data=results)

    except Exception as e:
        logger.error(f"❌ 表單資料讀取失敗: {e}")
        logger.error(traceback.format_exc())
        return jsonify(ok=False, error=str(e)), 500

# ====================================================================
# ====== 表單系統：資料回存 API (新增) ======
# ====================================================================

@app.post("/api/forms/save-schedule")
def api_forms_save_schedule():
    """
    表單系統：將修改後的資料寫回資料庫
    前端 Payload: { "year": "2025", "rows": [ { "col1": "Port1", "col2": "Ca-B", ... }, ... ] }
    """
    try:
        data = request.get_json(force=True)
        year = str(data.get("year", ""))
        rows_to_save = data.get("rows", [])

        if not year or not rows_to_save:
            return jsonify(ok=False, message="缺少必要參數"), 400

        table_name = f"schedule_{year}"
        
        if not os.path.exists(DB_PATH):
            return jsonify(ok=False, message="資料庫不存在"), 404

        # 定義前端 col 對應到資料庫的欄位名稱
        # 前端: col1=滴定機, col2=Marker, col3=PN, col4=凍乾機台, col5=數量, col6=配藥同仁
        #       col7=日期, col8=RD給藥時間, col9=預計滴定時間, col10=預計結束, col11=工單號碼, col12=Lot, col13=備註
        col_map = {
            "col2": "marker",
            "col3": "PN",
            "col4": "凍乾機台",
            "col5": "數量",
            "col6": "配藥同仁",
            "col8": "RD給藥時間",
            "col9": "預計滴定時間",
            "col10": "預計結束",
            "col11": "工單號碼",
            "col12": "Batch", # 注意：Lot 對應 Batch
            "col13": "remark"
        }

        updated_count = 0

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # 檢查表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            if not cursor.fetchone():
                return jsonify(ok=False, message=f"資料表 {table_name} 不存在"), 404

            for row in rows_to_save:
                # 必要 Key: 日期 (col7) 和 滴定機 (col1)
                date_val = row.get("col7")
                machine_val = row.get("col1")

                # 跳過沒有 Key 的資料
                if not date_val or not machine_val:
                    continue

                # 構建 UPDATE 語句
                set_clauses = []
                params = []

                for col_key, db_col in col_map.items():
                    val = row.get(col_key, "")
                    # 數量需要特殊處理轉數字，避免存成字串
                    if col_key == "col5" and val != "":
                        try:
                            val = int(val)
                        except:
                            pass # 轉換失敗就存原樣
                    
                    set_clauses.append(f'"{db_col}" = ?')
                    params.append(val)

                # 如果沒有要更新的欄位則跳過
                if not set_clauses:
                    continue

                # 加入 WHERE 條件參數
                # 這裡需要處理日期格式相容性 (資料庫可能是 YYYY/MM/DD)
                # 我們使用 REPLACE 來忽略分隔符差異
                query = f"""
                    UPDATE "{table_name}"
                    SET {', '.join(set_clauses)}
                    WHERE REPLACE("日期", '/', '-') = ? AND "滴定機" = ?
                """
                # 將前端的 YYYY-MM-DD 轉為 - 格式傳入比對
                params.append(str(date_val).replace('/', '-'))
                params.append(machine_val)

                cursor.execute(query, params)
                updated_count += cursor.rowcount

            conn.commit()

        logger.info(f"💾 表單回存完成: 更新了 {updated_count} 筆資料")
        return jsonify(ok=True, updated=updated_count)

    except Exception as e:
        logger.error(f"❌ 表單回存失敗: {e}")
        logger.error(traceback.format_exc())
        return jsonify(ok=False, error=str(e)), 500

# === 配置新增：配藥表資料庫路徑 ===


@app.route("/api/schedule/today-stats", methods=["GET"])
def api_today_stats():
    """今日排程統計（從配藥表資料庫讀取)"""
    try:
        # 允許通過參數指定日期（用於測試）
        date_param = request.args.get("date")
        if date_param:
            try:
                today = datetime.strptime(date_param, "%Y-%m-%d").date()
                logger.info(f"📅 使用指定日期：{date_param}")
            except:
                today = date.today()
                logger.warning(f"⚠️ 日期參數格式錯誤，使用今天：{today}")
        else:
            today = date.today()
            logger.info(f"📅 使用系統日期：{today}")
        
        # 支援兩種日期格式
        today_str_dash = today.strftime("%Y-%m-%d")
        today_str_slash = today.strftime("%Y/%m/%d")
        
        # === 調試步驟 1: 檢查資料庫路徑 ===
        logger.info(f"=" * 60)
        logger.info(f"🔍 調試 - 資料庫路徑：{FORMULATE_DB_PATH}")
        if not os.path.exists(FORMULATE_DB_PATH):
            logger.error(f"❌ 資料庫檔案不存在！")
            return jsonify({
                "ok": False,
                "error": "資料庫檔案不存在",
                "tasks": 0,
                "titration_machines": 0,
                "dryers": 0,
                "titration_utilization": 0,
                "dryer_utilization": 0
            })
        
        logger.info(f"✅ 資料庫檔案存在")
        
        with sqlite3.connect(FORMULATE_DB_PATH) as conn:
            cursor = conn.cursor()
            
            # === 調試步驟 2: 檢查表是否存在 ===
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            all_tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"📋 資料庫中的所有表：{all_tables}")
            
            if 'DropletSchedule' not in all_tables:
                logger.error(f"❌ DropletSchedule 表不存在！")
                return jsonify({
                    "ok": False,
                    "error": "DropletSchedule 表不存在",
                    "available_tables": all_tables,
                    "tasks": 0,
                    "titration_machines": 0,
                    "dryers": 0,
                    "titration_utilization": 0,
                    "dryer_utilization": 0
                })
            
            logger.info(f"✅ DropletSchedule 表存在")
            
            # === 調試步驟 3: 檢查表結構 ===
            cursor.execute("PRAGMA table_info(DropletSchedule)")
            columns = [row[1] for row in cursor.fetchall()]
            logger.info(f"📊 DropletSchedule 表的欄位：{columns}")
            
            # === 調試步驟 4: 檢查總記錄數 ===
            cursor.execute("SELECT COUNT(*) FROM DropletSchedule")
            total_count = cursor.fetchone()[0]
            logger.info(f"📈 表中總記錄數：{total_count}")
            
            if total_count == 0:
                logger.warning(f"⚠️ 表是空的！")
                return jsonify({
                    "ok": True,
                    "tasks": 0,
                    "titration_machines": 0,
                    "dryers": 0,
                    "titration_utilization": 0,
                    "dryer_utilization": 0
                })
            
            # === 調試步驟 5: 查看最近的日期 ===
            cursor.execute("SELECT DISTINCT Date FROM DropletSchedule ORDER BY Date DESC LIMIT 5")
            recent_dates = [row[0] for row in cursor.fetchall()]
            logger.info(f"📅 最近的 5 個日期：{recent_dates}")
            
            # === 調試步驟 6: 查看日期格式樣本 ===
            cursor.execute("SELECT Date FROM DropletSchedule LIMIT 3")
            sample_dates = [row[0] for row in cursor.fetchall()]
            logger.info(f"📅 日期格式樣本：{sample_dates}")
            
            # === 調試步驟 7: 嘗試查詢今日數據 ===
            logger.info(f"🔍 嘗試查詢：{today_str_slash}% 或 {today_str_dash}%")
            
            query = '''
                SELECT 
                    Pump,
                    Lyophilizer,
                    Marker,
                    WorkOrder,
                    Date
                FROM DropletSchedule 
                WHERE Date LIKE ? OR Date LIKE ?
            '''
            df = pd.read_sql_query(
                query, 
                conn, 
                params=(f"{today_str_slash}%", f"{today_str_dash}%")
            )
            
            logger.info(f"📊 查詢結果筆數：{len(df)}")
        
        if df.empty:
            logger.warning(f"⚠️ 今日無排程數據")
            logger.info(f"💡 提示：")
            logger.info(f"   - 查詢日期：{today_str_slash} 或 {today_str_dash}")
            logger.info(f"   - 資料庫中最近日期：{recent_dates[0] if recent_dates else '無'}")
            logger.info(f"   - 可以使用 ?date=2025-11-21 參數測試特定日期")
            logger.info(f"=" * 60)
            
            return jsonify({
                "ok": True,
                "tasks": 0,
                "titration_machines": 0,
                "dryers": 0,
                "titration_utilization": 0,
                "dryer_utilization": 0,
                "debug_info": {
                    "query_date": today_str_slash,
                    "recent_dates": recent_dates[:3],
                    "total_records": total_count,
                    "hint": f"嘗試訪問 /api/schedule/today-stats?date=2025-11-21"
                }
            })
        
        logger.info(f"✅ 找到 {len(df)} 筆數據")
        logger.info(f"📋 數據範例：")
        logger.info(df.head(3).to_string())
        
        # 統計任務數（使用 Marker）
        if 'Marker' in df.columns:
            unique_markers = df["Marker"].dropna().astype(str).str.strip()
            unique_markers = unique_markers[unique_markers != ""]
            unique_markers = unique_markers[~unique_markers.str.contains("備註", na=False)]
            tasks_count = unique_markers.nunique()
            logger.info(f"📦 唯一 Marker 數：{tasks_count}")
        elif 'WorkOrder' in df.columns:
            unique_orders = df["WorkOrder"].dropna().astype(str).str.strip()
            unique_orders = unique_orders[unique_orders != ""]
            tasks_count = unique_orders.nunique()
            logger.info(f"📦 唯一工單數：{tasks_count}")
        else:
            tasks_count = len(df)
            logger.info(f"📦 總記錄數：{tasks_count}")
        
        # 統計滴定機（Pump）
        machines = df["Pump"].dropna().astype(str).str.strip()
        machines = machines[machines != ""]
        
        ivek_rows = machines.str.contains("IVEK", case=False, na=False)
        ivek_count = ivek_rows.sum()
        port_machines = machines[~ivek_rows]
        port_count = len(port_machines)
        
        normal_titration = port_count
       # 邏輯：<=2 算 1 台, <=4 算 2 台
        ivek_titration = (ivek_count + 1) // 2
        total_titration = normal_titration + ivek_titration
        
        used_ports = port_count + ivek_count
        titration_utilization = round((used_ports / TOTAL_TITRATION_CAPACITY) * 100, 1) if TOTAL_TITRATION_CAPACITY > 0 else 0
        
        logger.info(f"🔧 滴定機：Port={port_count}, IVEK={ivek_count}, 總計={total_titration}")
        
        # 統計凍乾機（Lyophilizer）
        dryers = df["Lyophilizer"].dropna().astype(str).str.strip()
        dryers = dryers[dryers != ""]
        unique_dryers_count = dryers.nunique()
        dryer_utilization = round((unique_dryers_count / TOTAL_DRYERS) * 100, 1) if TOTAL_DRYERS > 0 else 0
        
        logger.info(f"❄️ 凍乾機：{unique_dryers_count} 台")
        logger.info(f"=" * 60)
        
        return jsonify({
            "ok": True,
            "tasks": int(tasks_count),
            "titration_machines": int(total_titration),
            "dryers": int(unique_dryers_count),
            "titration_utilization": titration_utilization,
            "dryer_utilization": dryer_utilization
        })
        
    except Exception as e:
        logger.error(f"❌ 今日統計失敗: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            "ok": False,
            "tasks": 0,
            "titration_machines": 0,
            "dryers": 0,
            "titration_utilization": 0,
            "dryer_utilization": 0,
            "error": str(e)
        }), 500
# ====================================================================
# ====== IPQC 表單專用 API (完整修復版) ======
# ====================================================================

# 輔助函式：取得所有 IPQC 資料表名稱
def get_all_ipqc_tables(cursor):
    """取得資料庫中所有 YYYY_IPQC 格式的資料表，並由新到舊排序"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    # 篩選出格式為 "YYYY_IPQC" 的表 (例如 2025_IPQC, 2026_IPQC)
    ipqc_tables = [t for t in tables if t.endswith("_IPQC") and t[:4].isdigit()]
    # 排序：由新到舊 (2026 -> 2025)
    ipqc_tables.sort(reverse=True)
    return ipqc_tables

@app.route("/api/options", methods=["GET"])
def api_get_options():
    """
    取得篩選選項 (Marker 與 併批狀態)
    邏輯：掃描所有 IPQC 資料表，合併去重後回傳給前端下拉選單使用
    """
    response_data = {"makers": [], "batch_options": []}

    # 檢查 IPQC 資料庫是否存在
    if not os.path.exists(IPQC_DB_PATH):
        logger.warning(f"IPQC DB path not found: {IPQC_DB_PATH}")
        return jsonify(response_data)

    try:
        with sqlite3.connect(IPQC_DB_PATH) as conn:
            cursor = conn.cursor()
            
            # 1. 取得所有 IPQC 資料表
            tables = get_all_ipqc_tables(cursor)
            
            if not tables:
                return jsonify(response_data)

            all_markers = set()
            all_batches = set()

            # 2. 迴圈掃描每一張表
            for table in tables:
                try:
                    # 取得該表的欄位
                    cursor.execute(f'PRAGMA table_info("{table}")')
                    columns = {row[1] for row in cursor.fetchall()}

                    # --- 找 Marker 欄位 (相容不同命名) ---
                    marker_col = next((c for c in columns if c.lower() in ['marker', 'maker', '廠商']), None)
                    if marker_col:
                        cursor.execute(f'SELECT DISTINCT "{marker_col}" FROM "{table}"')
                        for r in cursor.fetchall():
                            if r[0] and str(r[0]).strip():
                                all_markers.add(str(r[0]).strip())

                    # --- 找 併批 欄位 ---
                    batch_col = next((c for c in columns if '併批' in c or 'Batch' in c), None)
                    if batch_col:
                        cursor.execute(f'SELECT DISTINCT "{batch_col}" FROM "{table}"')
                        for r in cursor.fetchall():
                            if r[0] and str(r[0]).strip():
                                all_batches.add(str(r[0]).strip())

                except Exception as table_err:
                    logger.warning(f"讀取表 {table} 選項時錯誤: {table_err}")
                    continue

            # 3. 轉換回 List 並排序
            response_data["makers"] = sorted(list(all_markers))
            response_data["batch_options"] = sorted(list(all_batches))
            
            return jsonify(response_data)

    except Exception as e:
        logger.error(f"❌ 取得選項失敗: {e}")
        return jsonify(response_data), 500

@app.route("/api/qc_table", methods=["GET"])
def api_get_qc_table():
    """
    主要查詢 API (跨年度搜尋)
    根據前端傳來的條件，搜尋所有年份的 IPQC 表並回傳結果
    """
    # 取得前端參數
    marker = request.args.get("marker", "")
    prod_start = request.args.get("prod_start", "")
    prod_end = request.args.get("prod_end", "")
    insp_start = request.args.get("insp_start", "")
    insp_end = request.args.get("insp_end", "")
    batchable = request.args.get("batchable", "")
    
    if not os.path.exists(IPQC_DB_PATH):
        return jsonify([])

    final_results = []

    try:
        with sqlite3.connect(IPQC_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 1. 取得所有年份資料表
            tables = get_all_ipqc_tables(cursor)
            
            # 2. 迴圈查詢每一個表
            for table_name in tables:
                try:
                    # 取得該表的欄位結構
                    cursor.execute(f'PRAGMA table_info("{table_name}")')
                    columns = {row[1] for row in cursor.fetchall()}

                    # 鎖定欄位名稱 (處理不同年份可能欄位名微調的情況)
                    prod_col = "dD生產日" if "dD生產日" in columns else next((c for c in columns if '生產' in c), None)
                    insp_col = "檢驗日期" if "檢驗日期" in columns else next((c for c in columns if '檢驗' in c), None)
                    marker_col = next((c for c in columns if c.lower() in ['marker', 'maker', '廠商']), None)
                    batch_col = next((c for c in columns if '併批' in c), None)

                    # 如果這個表連生產日或檢驗日都沒有，跳過
                    if not prod_col and not insp_col:
                        continue

                    # 組建 SQL
                    query = [f'SELECT *, "{table_name}" as source_table FROM "{table_name}" WHERE 1=1']
                    params = []

                    # --- 條件 1: Marker ---
                    if marker and marker_col:
                        query.append(f'AND "{marker_col}" = ?')
                        params.append(marker)
                    
                    # --- 條件 2: 生產日範圍 ---
                    # 使用 REPLACE 將 YYYY/MM/DD 轉為 YYYY-MM-DD 以便比較
                    if prod_col:
                        db_prod = f'DATE(REPLACE("{prod_col}", "/", "-"))'
                        if prod_start and prod_end:
                            query.append(f'AND {db_prod} >= DATE(?) AND {db_prod} <= DATE(?)')
                            params.extend([prod_start, prod_end])
                        elif prod_start:
                            query.append(f'AND {db_prod} >= DATE(?)')
                            params.append(prod_start)

                    # --- 條件 3: 檢驗日範圍 ---
                    if insp_col:
                        db_insp = f'DATE(REPLACE("{insp_col}", "/", "-"))'
                        if insp_start and insp_end:
                            query.append(f'AND {db_insp} >= DATE(?) AND {db_insp} <= DATE(?)')
                            params.extend([insp_start, insp_end])
                        elif insp_start:
                            query.append(f'AND {db_insp} >= DATE(?)')
                            params.append(insp_start)

                    # --- 條件 4: 併批 ---
                    if batchable and batch_col:
                        query.append(f'AND "{batch_col}" = ?')
                        params.append(batchable)

                    # 執行查詢
                    final_sql = " ".join(query)
                    cursor.execute(final_sql, params)
                    rows = cursor.fetchall()
                    
                    # 將結果加入總表
                    for row in rows:
                        final_results.append(dict(row))
                
                except Exception as e:
                    logger.error(f"查詢表 {table_name} 時發生錯誤: {e}")
                    continue

            # 3. 排序 (由新到舊)
            def sort_key(item):
                # 嘗試取得生產日，若無則回傳極小日期
                val = item.get('dD生產日') or item.get('生產日') or item.get('Date') or ""
                return str(val)
            
            final_results.sort(key=sort_key, reverse=True)
            
            # 限制回傳筆數 (防止前端炸裂，最多 2000 筆)
            return jsonify(final_results[:2000])

    except Exception as e:
        logger.error(f"❌ 跨年度查詢失敗: {e}")
        logger.error(traceback.format_exc())
        return jsonify([]), 500
# ====================================================================
# ====== 主程式 ======
# ====================================================================

atexit.register(stop_watch)
atexit.register(stop_wip_monitor) # 註冊停止 WIP 監控
atexit.register(final_sync_before_exit)

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Flask/同步服務整合啟動 V6 (含 WIP Polling)")
    logger.info("=" * 60)
    
    try:
        # 1. 啟動 Beads IPQC
        try:
            beads_observer = start_ipqc_monitoring()
        except Exception as e:
            logger.error(f"IPQC 啟動失敗: {e}")
            beads_observer = None

        # 2. 初始化核心服務 (A-E Sync + WIP Monitor + Watchdog)
        initialize_sync_service()

        # 3. 啟動 Flask
        app.run(host="0.0.0.0", port=8505, debug=False, threaded=True, use_reloader=False)

    except KeyboardInterrupt:
        logger.info("使用者中斷")
    finally:
        if beads_observer:
            beads_observer.stop()
            beads_observer.join()
        stop_watch()
        stop_wip_monitor()
        final_sync_before_exit()