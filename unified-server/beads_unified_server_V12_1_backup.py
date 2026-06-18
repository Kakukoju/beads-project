# -*- coding: utf-8 -*-
"""
====================================================================
Beads 統一服務器 V12.1 - 最終穩定優化版
====================================================================
"""
print("🔥 Beads Server V12.1 Initializing...")
import re, sys, os, time, threading, sqlite3, subprocess, json, mimetypes, urllib.parse, traceback, tempfile, atexit, logging
import datetime as dt
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pathlib import Path
from dataclasses import dataclass
import pandas as pd
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
from pandas.api.types import is_datetime64_any_dtype as is_datetime
from flask import Flask, send_from_directory, request, jsonify, send_file, abort, url_for

# --- 專案模組導入 ---
from api_beads_ipqc_importable_1 import register_beads_ipqc_routes
from wip_automation_blueprint_1 import (wip_automation_bp, init_wip_automation)
from IPQA_db_V1_importable import start_monitoring as start_ipqc_monitoring

# ====================================================================
# ====== 1. 配置與路徑常量 ======
# ====================================================================

BASE_DIR = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定"
APP_DIR = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Bead_auto_update_schedule"
DIST = Path(APP_DIR) / "beads-ui" / "dist"
SCRIPT = Path(APP_DIR) / "plan_to_bead_requirements_1.py"
SCHEDULER_SCRIPT = Path(APP_DIR) / "beads_Scheduler_V9_9_7.py"

MAIN_DB_PATH = os.path.join(BASE_DIR, "資料庫", "beads_sync.db")
DB_PATH = os.path.join(BASE_DIR, "資料庫", "Beads_Schedule.db")
WORK_ORDER_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"
FORMULATE_DB_PATH = r"D:\配藥表\資料庫\P01_formualte_schedule.db"

WIP_EXCEL_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\WIP報表 2025-QR01 NEW (請勿亂動連結).xlsm"
WIP_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\分藥資料庫\Bead_Sort_DB.db"
WIP_TABLE_NAME = "明細_2025"
WIP_CHECK_INTERVAL = 15

IPQC_DB_PATH = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Beads_QC\資料庫\P01_Beads_IPQC.db"

# === Excel 檔案配置 ===
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
    header_map={
        "料號": "PN",
        "批號": "Batch",
        "PN ": "PN",
        "PN": "PN",
        "Batch No.": "Batch",
        "Batch": "Batch",
    }
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
SHIFTS_PER_DAY = 2  # AM/PM
IVEK_PORTS = 2
TOTAL_DRYERS = 11  # 3~12號 + 小台
TOTAL_TITRATION_CAPACITY = 26  # 每天可用滴定pump

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
    """獲取 logger"""
    return logging.getLogger(name)

logger = get_logger('SYNC_SVC')

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
        self._wip_thread = None          # 👈 必須定義此屬性
        self._wip_stop_event = threading.Event()  # 👈 必須定義此屬性
    @property
    def observer(self):
        with self._lock:
            return self._observer
    
    @observer.setter
    def observer(self, value):
        with self._lock:
            self._observer = value
    
    @property
    def watched_folders(self):
        with self._lock:
            return self._watched_folders.copy()
    
    def add_watched_folder(self, folder: str):
        with self._lock:
            self._watched_folders.add(folder)
    
    def get_last_event_time(self, path: str) -> float:
        with self._lock:
            return self._last_event_ts.get(path, 0)
    
    def set_last_event_time(self, path: str, ts: float):
        with self._lock:
            self._last_event_ts[path] = ts
    
    @property
    def sync_init_done(self):
        with self._lock:
            return self._sync_init_done
    
    @sync_init_done.setter
    def sync_init_done(self, value):
        with self._lock:
            self._sync_init_done = value
    
    @property
    def sched_proc(self):
        with self._lock:
            return self._sched_proc
    
    @sched_proc.setter
    def sched_proc(self, value):
        with self._lock:
            self._sched_proc = value
    
    @property
    def demand_proc(self):
        with self._lock:
            return self._demand_proc
    
    @demand_proc.setter
    def demand_proc(self, value):
        with self._lock:
            self._demand_proc = value

# 全局狀態實例
state = StateManager()
db_lock = threading.Lock()

# ====================================================================
# ====== 工具函數 ======
# ====================================================================

def safe_ident(name: str) -> str:
    """安全的 SQL 標識符"""
    if name is None:
        name = ""
    s = str(name).replace('"', '""').strip()
    return s if s else "_col_"

def col_to_index(col: str) -> int:
    """Excel 列字母轉索引"""
    col = col.upper()
    s = 0
    for ch in col:
        s = s * 26 + (ord(ch) - 64)
    return s

def get_plan_dir() -> str:
    """獲取生產計畫目錄"""
    candidates = [
        os.path.join(BASE_DIR, "production_plan"),
        os.path.join(BASE_DIR, "paoduction_plan"),
    ]
    for d in candidates:
        if os.path.isdir(d):
            return d
    return BASE_DIR

def pick_latest_plan_file() -> Optional[str]:
    """選擇最新的生產計畫檔案"""
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
        if not m:
            continue
        ymd = m.group(1)
        try:
            d = datetime.strptime(ymd, "%Y%m%d").date()
        except Exception:
            continue
        if d <= today:
            files.append((d, os.path.join(base, name)))

    if not files:
        return None

    files.sort(key=lambda x: (today - x[0]))
    return files[0][1]

def normalize_df_for_sqlite(df: pd.DataFrame) -> pd.DataFrame:
    """正規化 DataFrame 以寫入 SQLite"""
    out = df.copy()
    for col_name in out.columns:
        col_name_str = str(col_name).strip()
        s = out[col_name]

        # 處理需要去除小數點的欄位
        if col_name_str in NO_DECIMAL_COLUMNS:
            def remove_decimal(x):
                if pd.isna(x):
                    return ""
                # 如果是數字，轉換為整數字串
                if isinstance(x, (int, float)):
                    try:
                        # 去除小數點，轉為整數
                        return str(int(float(x)))
                    except (ValueError, OverflowError):
                        return str(x)
                # 如果是字串，嘗試去除小數點
                x_str = str(x).strip()
                if '.' in x_str:
                    try:
                        # 嘗試轉換為數字再轉回整數字串
                        return str(int(float(x_str)))
                    except (ValueError, OverflowError):
                        # 如果轉換失敗，直接移除小數點部分
                        return x_str.split('.')[0]
                return x_str
            
            out[col_name] = s.map(remove_decimal)
        
        # 處理時間欄位
        elif col_name_str in TIME_COLUMNS:
            def convert_excel_time(x):
                if pd.isna(x):
                    return ""
                if isinstance(x, (dt.time, dt.datetime, pd.Timestamp)):
                    return x.strftime("%H:%M")
                if isinstance(x, (int, float)):
                    try:
                        total_seconds = int(float(x) * 86400)
                        hours = (total_seconds // 3600) % 24
                        minutes = (total_seconds % 3600) // 60
                        return f"{hours:02d}:{minutes:02d}"
                    except Exception:
                        return str(x)
                return str(x)
            out[col_name] = s.map(convert_excel_time)
        
        # 處理日期欄位
        elif is_datetime(s): 
            out[col_name] = s.dt.strftime("%Y-%m-%d").fillna("")
        
        # 處理其他欄位
        else:
            out[col_name] = s.map(
                lambda x: (
                    x.strftime("%Y-%m-%d") if isinstance(x, (dt.date, dt.datetime, pd.Timestamp))
                    else x.strftime("%H:%M") if isinstance(x, dt.time)
                    else ("" if pd.isna(x) else str(x))
                )
            )
    return out

def read_range_df(xl_path: str, sheet: str, header_row: int, data_start_row: int, 
                  last_col_letter: str, lastrow_by_col_letter: str) -> pd.DataFrame:
    """讀取 Excel 範圍並轉換為 DataFrame"""
    for i in range(READ_RETRY):
        try:
            df = pd.read_excel(
                xl_path, sheet_name=sheet, header=header_row - 1, engine="openpyxl"
            )
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
    """正規化 B 檔的欄位名稱"""
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
    """正規化欄位名稱"""
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
    """移除主鍵為空的資料列"""
    for k in keys:
        if k not in df.columns:
            return df.iloc[0:0]
        df[k] = df[k].map(lambda x: str(x).strip())
    mask = df[keys].apply(lambda s: s.str.len() > 0).all(axis=1)
    return df[mask].copy()

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
        
def run_wip_sync_once():
    """WIP: 執行同步，確保資料庫有資料供 Yield 顯示"""
    try:
        if not os.path.exists(WIP_EXCEL_PATH): return False
        xls = pd.ExcelFile(WIP_EXCEL_PATH, engine="openpyxl")
        target = next((n for n in xls.sheet_names if "2025" in n and "明細" in n), None)
        if not target: return False
        # 讀取 WIP 資料
        df = pd.read_excel(WIP_EXCEL_PATH, sheet_name=target, header=4, usecols="A:U", engine="openpyxl", dtype=str).dropna(how="all")
        with sqlite3.connect(WIP_DB_PATH, timeout=20) as conn:
            df.to_sql(WIP_TABLE_NAME, conn, if_exists="replace", index=False)
        return True
    except sqlite3.OperationalError as e:
        if "locked" in str(e):
            logger.warning("🕒 資料庫繁忙中 (Locked)，將在下次輪詢重試")
        return False
    except Exception as e:
        logger.error(f"❌ WIP 同步失敗: {e}")
        return False

def wip_monitor_loop(stop_event):
    """WIP: 背景輪詢線程 (優化版)"""
    last_mtime = 0
    while not stop_event.is_set():
        try:
            if os.path.exists(WIP_EXCEL_PATH):
                current_mtime = os.path.getmtime(WIP_EXCEL_PATH)
                
                # 只有當檔案修改時間更新時才觸發
                if current_mtime > last_mtime:
                    # 💡 增加小延遲，避免與 Excel 的儲存動作衝突 (減少 Locked 機率)
                    time.sleep(1) 
                    
                    # 執行同步，成功才更新基準時間
                    if run_wip_sync_once(): 
                        last_mtime = current_mtime
                        logger.info(f"📊 [WIP] 偵測到 Excel 更新，同步完成 (時間戳: {last_mtime})")
        
        except Exception as e:
            logger.error(f"❌ [WIP] 監控線程異常: {e}")
            
        # 這裡會等待 15 秒，除非 stop_event 被觸發
        if stop_event.wait(WIP_CHECK_INTERVAL):
            break
# ====================================================================
# ====== 資料庫操作函數 ======
# ====================================================================

def ensure_table_and_columns(conn: sqlite3.Connection, table: str, df: pd.DataFrame):
    """確保表格和欄位存在"""
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
    """確保唯一索引存在"""
    if not keys:
        return
    table_q = safe_ident(table)
    idx_name = f'ux_{table_q}_' + "_".join([safe_ident(k).lower() for k in keys])
    cols = ",".join([f'"{safe_ident(k)}"' for k in keys])
    with conn:
        conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "{idx_name}" ON "{table_q}" ({cols});')

def upsert(conn: sqlite3.Connection, table: str, df: pd.DataFrame, keys: List[str]):
    """UPSERT 操作"""
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
        sql = (
            f'INSERT INTO "{safe_ident(table)}" ({col_list}) VALUES ({placeholders}) '
            f'ON CONFLICT ({conflict}) DO UPDATE SET {set_clause};'
        )
    elif keys:
        sql = (
            f'INSERT INTO "{safe_ident(table)}" ({col_list}) VALUES ({placeholders}) '
            f'ON CONFLICT ({conflict}) DO NOTHING;'
        )
    else:
        sql = f'REPLACE INTO "{safe_ident(table)}" ({col_list}) VALUES ({placeholders});'

    with conn:
        conn.executemany(sql, df.itertuples(index=False, name=None))

# ====================================================================
# ====== Excel 重算函數 ======
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
                    try:
                        wb.Close(False)
                    except Exception:
                        pass
                if xl:
                    try:
                        xl.Quit()
                    except Exception:
                        pass
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
                try:
                    p.terminate()
                except Exception:
                    pass
        finally:
            try:
                os.unlink(vbs_path)
            except Exception:
                pass
        return tmp or filepath
    except Exception as e:
        logger.warning(f"A 檔重算：VBScript 也失敗（{e}），改讀原檔")
        return filepath

# ====================================================================
# ====== 同步核心函數 ======
# ====================================================================

def sync_file(config: FileConfig, file_key: str):
    """通用檔案同步函數"""
    global MAIN_DB_PATH
    
    filepath = config.path
    if not filepath:
        logger.warning(f"{file_key} 檔路徑為空")
        return
    
    if not os.path.exists(filepath):
        logger.warning(f"{file_key} 檔不存在：{filepath}")
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
            df = read_range_df(
                filepath,
                config.sheet,
                config.header_row,
                config.data_start_row,
                config.last_col,
                config.lastrow_by_col
            )
            
            # B 檔需要特殊處理
            if file_key == "B":
                df.columns = normalize_b_headers(list(df.columns))
            elif config.header_map:
                df = normalize_columns(df, config.header_map)
            
            # 移除空主鍵行
            if config.keys:
                df = drop_rows_with_empty_keys(df, config.keys)
            
            logger.info(f"   欄位範例: {list(df.columns)[:5]}... (共 {len(df.columns)} 欄)")
            logger.info(f"   資料筆數: {len(df)}")
            
            if len(df) == 0:
                logger.warning(f"{file_key} 檔有效資料為 0 列")
                return
            
            with sqlite3.connect(MAIN_DB_PATH) as conn:
                if config.keys:
                    upsert(conn, config.table, df, config.keys)
                else:
                    # 無主鍵：先清空再插入
                    ensure_table_and_columns(conn, config.table, df)
                    conn.execute(f'DELETE FROM "{safe_ident(config.table)}"')
                    df.to_sql(config.table, conn, if_exists='append', index=False)
            
            logger.info(f"✅ {file_key} 檔同步完成：{len(df)} 筆")
            
        except Exception as e:
            logger.error(f"❌ {file_key} 檔同步失敗：{e}")
            logger.error(traceback.format_exc())
        finally:
            if tmp_to_delete and os.path.exists(tmp_to_delete):
                try:
                    os.remove(tmp_to_delete)
                except Exception:
                    pass

def sync_A():
    """同步 A 檔"""
    sync_file(FILE_A_CONFIG, "A")

def sync_B():
    """同步 B 檔"""
    file_b = pick_latest_plan_file()
    if not file_b:
        logger.warning("找不到合法的 Production plan-YYYYMMDD.xlsm")
        return
    
    config = FileConfig(
        path=file_b,
        sheet=FILE_B_CONFIG.sheet,
        header_row=FILE_B_CONFIG.header_row,
        data_start_row=FILE_B_CONFIG.data_start_row,
        last_col=FILE_B_CONFIG.last_col,
        lastrow_by_col=FILE_B_CONFIG.lastrow_by_col,
        table=FILE_B_CONFIG.table,
        keys=FILE_B_CONFIG.keys
    )
    sync_file(config, "B")

def sync_C():
    """同步 C 檔"""
    sync_file(FILE_C_CONFIG, "C")

def sync_D():
    """同步 D 檔"""
    sync_file(FILE_D_CONFIG, "D")

def sync_E():
    """同步 E 檔"""
    sync_file(FILE_E_CONFIG, "E")

# ====================================================================
# ====== 初始化與清理 ======
# ====================================================================

def initial_sync_and_prepare_db():
    """初始化資料庫並執行首次同步"""
    global MAIN_DB_PATH
    
    if not os.path.exists(MAIN_DB_PATH):
        logger.info(f"📂 DB 不存在，將建立：{MAIN_DB_PATH}")
        os.makedirs(os.path.dirname(MAIN_DB_PATH), exist_ok=True)
        open(MAIN_DB_PATH, "ab").close()
    
    logger.info("=" * 60)
    logger.info("🔄 開始初始同步（A/B/C/D/E 五個檔案）")
    logger.info("=" * 60)
    
    sync_A()
    sync_B()
    sync_C()
    sync_D()
    sync_E()
    
    logger.info("=" * 60)
    logger.info("✅ 初始同步完成")
    logger.info("=" * 60)

def final_sync_before_exit():
    """關閉前最終同步"""
    logger.info("=" * 60)
    logger.info("🔄 關閉前最終同步開始")
    logger.info("=" * 60)
    
    for name, func in [("A", sync_A), ("B", sync_B), ("C", sync_C), 
                       ("D", sync_D), ("E", sync_E)]:
        try:
            func()
        except Exception as e:
            logger.warning(f"最終同步 {name} 失敗：{e}")
    
    logger.info("=" * 60)
    logger.info("✅ 最終同步完成")
    logger.info("=" * 60)

# ====================================================================
# ====== Watchdog 監控 ======
# ====================================================================

class Handler(FileSystemEventHandler):
    """檔案事件處理器"""
    def __init__(self):
        super().__init__()
        self.event_count = 0
        self.last_heartbeat = time.time()
    
    def on_any_event(self, event):
        """處理所有事件"""
        self.event_count += 1
        
        # 心跳日誌
        now = time.time()
        if now - self.last_heartbeat > 30:
            logger.info(f"💓 Watchdog 心跳：已處理 {self.event_count} 個事件")
            self.last_heartbeat = now
        
        logger.debug(f"🔔 檔案事件: {event.event_type} | "
                    f"{'[DIR]' if event.is_directory else '[FILE]'} | "
                    f"{os.path.basename(event.src_path)}")
        
        if event.is_directory:
            return
        
        path = os.path.abspath(event.src_path)
        filename = os.path.basename(path)
        
        # 忽略臨時檔
        if filename.startswith('~$') or filename.endswith('.tmp'):
            logger.debug("   ⏭️ 跳過（臨時檔）")
            return
        
        # Debounce
        now = time.time()
        last = state.get_last_event_time(path)
        if now - last < DEBOUNCE_SECONDS:
            logger.debug("   ⏭️ 跳過（防抖）")
            return
        state.set_last_event_time(path, now)
        
        logger.info(f"   ✅ 處理事件: {filename}")

        try:
            # 檢查 A 檔
            if os.path.abspath(FILE_A_CONFIG.path).lower() == path.lower():
                logger.info("   🎯 偵測到 A 檔變更")
                sync_A()
                return

            # 檢查 B 檔
            current_b = pick_latest_plan_file()
            if current_b and os.path.abspath(current_b).lower() == path.lower():
                logger.info("   🎯 偵測到 B 檔變更")
                sync_B()
                return

            # 檢查 C/D/E 檔
            for key, config in [("C", FILE_C_CONFIG), ("D", FILE_D_CONFIG), ("E", FILE_E_CONFIG)]:
                if os.path.abspath(config.path).lower() == path.lower():
                    logger.info(f"   🎯 偵測到 {key} 檔變更")
                    sync_file(config, key)
                    return

            # 檢查新的 B 候選檔
            plan_dir = get_plan_dir()
            if os.path.dirname(path).lower() == plan_dir.lower() and \
               re.search(r"Production plan-\d{8}\.xlsm$", os.path.basename(path), re.I):
                newer_b = pick_latest_plan_file()
                if newer_b:
                    add_watch(newer_b)
                    logger.info("   🎯 偵測到新的 B 檔")
                    sync_B()
                return
            
            logger.debug("   ⏭️ 跳過（非目標檔案）")

        except Exception as e:
            logger.error(f"   ❌ 事件處理錯誤: {e}")
            logger.error(traceback.format_exc())

def add_watch(any_path_under_folder: str):
    """添加資料夾監控"""
    observer = state.observer
    if not observer:
        logger.warning("Observer 不存在，無法添加監控")
        return
    
    folder = os.path.abspath(os.path.dirname(any_path_under_folder))
    if folder in state.watched_folders:
        logger.debug(f"資料夾已在監控中: {folder}")
        return
    
    try:
        handler = Handler()
        observer.schedule(handler, folder, recursive=False)
        state.add_watched_folder(folder)
        logger.info(f"   📁 已監看: {folder}")
    except Exception as e:
        logger.error(f"添加監控失敗: {folder}, 錯誤: {e}")

def start_watch():
    """啟動檔案監控"""
    if state.observer is not None:
        if state.observer.is_alive():
            logger.warning("⚠️ Observer 已經在運行中")
            return
        else:
            logger.warning("⚠️ Observer 存在但未運行，將重新啟動")
            state.observer = None
    
    logger.info("=" * 60)
    logger.info("🔍 啟動 Watchdog 監控")
    logger.info("=" * 60)
    
    try:
        state.observer = PollingObserver(timeout=0.5)
        handler = Handler()
        
        # 監控所有檔案
        files_to_watch = [
            ("A", FILE_A_CONFIG.path),
            ("C", FILE_C_CONFIG.path),
            ("D", FILE_D_CONFIG.path),
            ("E", FILE_E_CONFIG.path)
        ]
        
        watched_any = False
        for name, filepath in files_to_watch:
            if os.path.exists(filepath):
                folder = os.path.dirname(filepath)
                if folder not in state.watched_folders:
                    state.observer.schedule(handler, folder, recursive=False)
                    state.add_watched_folder(folder)
                    logger.info(f"✅ {name} 檔監控已設定: {folder}")
                    watched_any = True
            else:
                logger.warning(f"⚠️ {name} 檔不存在: {filepath}")
        
        # 監控 B 檔
        bfile = pick_latest_plan_file()
        if bfile and os.path.exists(bfile):
            folder = os.path.dirname(bfile)
            if folder not in state.watched_folders:
                state.observer.schedule(handler, folder, recursive=False)
                state.add_watched_folder(folder)
                logger.info(f"✅ B 檔監控已設定: {folder}")
                watched_any = True
        
        if not watched_any:
            logger.error("❌ 沒有任何檔案被監控！")
            state.observer = None
            return
        
        # 啟動 observer
        state.observer.start()
        logger.info("🚀 Observer.start() 已調用")
        
        # 等待確認啟動
        time.sleep(1)
        
        if state.observer.is_alive():
            logger.info("=" * 60)
            logger.info("✅ Watchdog 啟動成功！")
            logger.info(f"   Observer 狀態: 運行中")
            logger.info(f"   輪詢間隔: 0.5 秒")
            logger.info(f"   監控資料夾數: {len(state.watched_folders)}")
            for folder in state.watched_folders:
                logger.info(f"   - {folder}")
            logger.info("=" * 60)
        else:
            logger.error("=" * 60)
            logger.error("❌ Watchdog 啟動失敗（Observer 未運行）")
            logger.error("=" * 60)
            state.observer = None
        
    except Exception as e:
        logger.error(f"❌ Watchdog 啟動異常: {e}")
        logger.error(traceback.format_exc())
        state.observer = None

def stop_watch():
    """停止檔案監控"""
    observer = state.observer
    if observer:
        logger.info("正在停止 Watchdog...")
        try:
            observer.stop()
            observer.join(timeout=5)
            state.observer = None
            logger.info("✅ Watchdog 已停止")
        except Exception as e:
            logger.warning(f"⚠️ 停止 Watchdog 時發生錯誤: {e}")

# ====================================================================
# ====== Flask 應用程式註冊與初始化 ======
# ====================================================================

app = Flask(__name__, static_folder=str(DIST), static_url_path="/")

def _is_allowed_path(path: str) -> bool:
    """檢查路徑是否允許"""
    if not path:
        return False
    p_norm = path.lower().replace("/", "\\")
    return any(p_norm.startswith(root.lower().replace("/", "\\")) for root in ALLOWED_ROOTS)

def get_iso_week(date_obj: date) -> str:
    """取得 ISO 週數"""
    iso_cal = date_obj.isocalendar()
    year = iso_cal[0]
    week = iso_cal[1]
    return f"{year}_W{week:02d}"

# --- 註冊外部路由與藍圖 ---
# A. IPQC 註冊 (維持 V12 穩定方式)
register_beads_ipqc_routes(app)

# B. WIP 註冊 (導入藍圖)
app.register_blueprint(wip_automation_bp, url_prefix="")

# --- 初始化服務核心邏輯 ---
def initialize_sync_service():
    """
    初始化所有同步服務：
    1. A-E 檔初始同步
    2. WIP Excel 初始同步 (解決 Yield/WIP 顯示問題)
    3. 啟動背景監控 (A-E Watchdog + WIP Polling)
    """
    if state.sync_init_done:
        logger.warning("⚠️ 同步服務已經初始化過")
        return
    
    logger.info("=" * 60)
    logger.info("🚀 啟動全系統同步初始化 (V13.2)")
    logger.info("=" * 60)
    
    try:
        # 0. 確保基本目錄存在
        os.makedirs(APP_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(MAIN_DB_PATH), exist_ok=True)
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        os.makedirs(os.path.dirname(WIP_DB_PATH), exist_ok=True)

        # 1. 執行 A-E 檔初始同步 (原 File A-E)
        logger.info("步驟 1/5: 執行 A-E 檔初始同步...")
        initial_sync_and_prepare_db()

        # 2. 執行 WIP 初始同步 (解決數據為 0 或連線失敗問題)
        logger.info("步驟 2/5: 執行 WIP 報表初始同步...")
        run_wip_sync_once()

        # 3. 初始化 WIP 藍圖與自動化系統 (良率計算核心)
        logger.info("步驟 3/5: 初始化 WIP 自動化系統藍圖...")
        try:
            init_wip_automation(app)
        except Exception as e:
            logger.error(f"❌ WIP 藍圖初始化異常: {e}")

        # 4. 啟動背景輪詢監控 (WIP Polling Thread)
        logger.info("步驟 4/5: 啟動 WIP 背景輪詢監控線程...")
        start_wip_monitor()

        # 5. 啟動檔案變更監控 (A-E Watchdog)
        logger.info("步驟 5/5: 啟動 A-E 檔案變更 Watchdog...")
        start_watch()
        
        # 驗證 Watchdog 狀態
        if state.observer and state.observer.is_alive():
            logger.info("=" * 60)
            logger.info("✅ 伺服器全服務初始化成功！")
            logger.info("=" * 60)
            state.sync_init_done = True
        else:
            logger.error("❌ Watchdog 未成功啟動，但其他服務已運行。")
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"❌ 初始化程序崩潰: {e}")
        logger.error(traceback.format_exc())
        logger.error("=" * 60)

@app.before_request
def _init_before_request():
    """每次請求前檢查初始化狀態"""
    if not state.sync_init_done:
        logger.info("📍 [系統觸發] before_request 偵測到尚未初始化")
        initialize_sync_service()
        

# === API 路由 ===

@app.get("/api/health")
def health():
    """健康檢查"""
    return jsonify(
        ok=True,
        dist=str(DIST),
        index_exists=(DIST / "index.html").exists(),
        script_exists=SCRIPT.exists(),
        sync_service_running=(state.observer is not None and state.observer.is_alive()),
        databases={
            "sync_db": {
                "path": MAIN_DB_PATH,
                "exists": os.path.exists(MAIN_DB_PATH)
            },
            "schedule_db": {
                "path": DB_PATH,
                "exists": os.path.exists(DB_PATH)
            }
        },
        watched_files={
            "A_inventory": {
                "path": FILE_A_CONFIG.path,
                "exists": os.path.exists(FILE_A_CONFIG.path)
            },
            "B_production_plan": {
                "path": pick_latest_plan_file() or "Not found",
                "exists": pick_latest_plan_file() is not None
            },
            "C_schedule_limit": {
                "path": FILE_C_CONFIG.path,
                "exists": os.path.exists(FILE_C_CONFIG.path)
            },
            "D_dry_count": {
                "path": FILE_D_CONFIG.path,
                "exists": os.path.exists(FILE_D_CONFIG.path)
            },
            "E_titration_limit": {
                "path": FILE_E_CONFIG.path,
                "exists": os.path.exists(FILE_E_CONFIG.path)
            }
        },
        watched_folders=list(state.watched_folders)
    )

@app.get("/api/test/watchdog-heartbeat")
def api_watchdog_heartbeat():
    """檢查 Watchdog 心跳"""
    try:
        observer = state.observer
        status = {
            "observer_exists": observer is not None,
            "observer_alive": observer.is_alive() if observer else False,
            "observer_daemon": observer.daemon if observer else None,
            "watched_folders": list(state.watched_folders),
            "sync_init_done": state.sync_init_done
        }
        
        if observer and observer.is_alive():
            try:
                status["observer_emitters"] = len(observer.emitters)
            except:
                pass
        
        return jsonify(ok=True, status=status)
    except Exception as e:
        logger.error(f"❌ 心跳檢查失敗: {e}")
        return jsonify(ok=False, error=str(e)), 500

@app.post("/api/test/restart-watchdog")
def api_restart_watchdog():
    """重新啟動 Watchdog"""
    try:
        logger.info("🔄 API 請求：重新啟動 Watchdog")
        stop_watch()
        time.sleep(1)
        start_watch()
        
        if state.observer and state.observer.is_alive():
            return jsonify(ok=True, message="Watchdog 已重新啟動")
        else:
            return jsonify(ok=False, message="Watchdog 啟動失敗"), 500
    except Exception as e:
        logger.error(f"❌ 重啟失敗: {e}")
        return jsonify(ok=False, error=str(e)), 500

@app.post("/api/test/manual-sync")
def api_manual_sync():
    """手動觸發同步"""
    try:
        file_type = request.args.get("type", "all")
        
        sync_map = {
            "A": sync_A,
            "B": sync_B,
            "C": sync_C,
            "D": sync_D,
            "E": sync_E
        }
        
        if file_type == "all":
            for key, func in sync_map.items():
                try:
                    func()
                except Exception as e:
                    logger.error(f"同步 {key} 失敗: {e}")
            return jsonify(ok=True, message="已觸發全部檔案同步")
        elif file_type in sync_map:
            sync_map[file_type]()
            return jsonify(ok=True, message=f"{file_type} 檔同步完成")
        else:
            return jsonify(ok=False, message="無效的檔案類型"), 400
            
    except Exception as e:
        logger.error(f"❌ 手動同步失敗: {e}")
        logger.error(traceback.format_exc())
        return jsonify(ok=False, error=str(e)), 500

# === 需求統計 API ===

@app.post("/api/run/beads-demand")
def run_beads_demand():
    """執行需求統計"""
    data = request.get_json(force=True) or {}

    year = str(data.get("year", "2025"))
    date_mmdd = data.get("dateMMDD", "")
    out_path = data.get("writeBackPath", "") or r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\beads 需求模組.xlsx"
    is_dry = bool(data.get("dryRun", False))
    dry = "1" if is_dry else "0"

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--year", year,
        "--date", date_mmdd,
        "--out", out_path,
        "--dry", dry,
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env
        )
        state.demand_proc = proc
        stdout, stderr = proc.communicate()
        code = proc.returncode
        state.demand_proc = None

        if code != 0:
            return jsonify(ok=False, code=code, stdout=stdout, stderr=stderr), 500

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {}

        if is_dry:
            return jsonify(
                ok=bool(payload.get("ok", True)),
                data=payload.get("data") or payload.get("rows") or [],
                outPath=""
            )
        else:
            real_out = payload.get("out_path") or out_path
            return jsonify(ok=True, msg=payload.get("msg", "✅ 已寫入 Excel"), outPath=real_out)

    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

@app.post("/api/cancel/beads-demand")
def cancel_beads_demand():
    """取消需求統計"""
    proc = state.demand_proc
    
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            for _ in range(20):
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
            if proc.poll() is None:
                proc.kill()
            state.demand_proc = None
            return jsonify(ok=True, msg="已取消")
        except Exception as e:
            return jsonify(ok=False, error=str(e)), 500
    return jsonify(ok=True, msg="沒有執行中的任務")

# === 排程 API ===

@app.post("/api/run/beads-schedule")
def run_beads_schedule():
    """執行排程"""
    data = request.get_json(force=True) or {}

    date_mmdd = data.get("dateMMDD", "")
    need_path = data.get("needPath", "")
    holidays = data.get("holidays", [])
    batch_numbers = data.get("batchNumbers", "")
    vacation_staff = data.get("vacationStaff", "")
    out_dir = data.get("outDir") or DEFAULT_OUTDIR
    is_dry = bool(data.get("dryRun", False))
    
    if not date_mmdd:
        return jsonify(ok=False, message="缺少起始日期"), 400
    
    if not need_path:
        return jsonify(ok=False, message="缺少需求檔路徑"), 400
    
    cmd = [
        sys.executable,
        str(SCHEDULER_SCRIPT),
        "--date", date_mmdd,
        "--need", need_path,
        "--outdir", out_dir,
    ]
    
    if holidays:
        cmd.extend(["--holidays", ",".join(holidays)])
    
    if batch_numbers:
        cmd.extend(["--batch-numbers", batch_numbers])
    
    if vacation_staff:
        cmd.extend(["--vacation-staff", vacation_staff])
    
    if is_dry:
        cmd.append("--dry-run")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        logger.info(f"執行排程命令：{' '.join(cmd)}")
        
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=300
        )
        
        if proc.returncode != 0:
            logger.error(f"排程腳本執行失敗 (返回碼: {proc.returncode})")
            logger.error(f"STDERR: {proc.stderr}")
            return jsonify(ok=False, message=proc.stderr or proc.stdout), 500

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失敗: {e}")
            logger.error(f"STDOUT: {proc.stdout}")
            return jsonify(ok=False, message="腳本輸出格式錯誤"), 500

        if is_dry:
            preview = payload.get("preview") or []
            return jsonify(ok=True, preview=preview)

        out_path = payload.get("outPath")
        return jsonify(ok=True, outPath=out_path)
        
    except subprocess.TimeoutExpired:
        logger.error("排程執行超時")
        return jsonify(ok=False, message="排程執行超時（超過 5 分鐘）"), 500
        
    except Exception as e:
        logger.error(f"執行排程時發生錯誤：{e}")
        logger.error(traceback.format_exc())
        return jsonify(ok=False, message=str(e)), 500

@app.post("/api/cancel/beads-schedule")
def cancel_beads_schedule():
    """取消排程"""
    proc = state.sched_proc
    
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            for _ in range(20):
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
            if proc.poll() is None:
                proc.kill()
            state.sched_proc = None
            logger.info("排程已取消")
            return jsonify(ok=True, msg="已取消")
        except Exception as e:
            logger.error(f"取消排程時發生錯誤: {e}")
            return jsonify(ok=False, error=str(e)), 500
    
    return jsonify(ok=True, msg="沒有執行中的排程作業")

# === 檔案操作 API ===

@app.get("/api/open-file")
def api_open_file():
    """開啟檔案"""
    raw = request.args.get("path", "")
    path = urllib.parse.unquote(raw)

    if not _is_allowed_path(path):
        return abort(403, "path not allowed")

    if not os.path.exists(path):
        return abort(404, "file not found")

    mime, _ = mimetypes.guess_type(path)
    try:
        resp = send_file(
            path,
            mimetype=mime or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=False,
            download_name=os.path.basename(path),
            conditional=True,
        )
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp
    except PermissionError:
        return abort(423, "file locked (in use)")

@app.get("/api/excel-deeplink")
def api_excel_deeplink():
    """生成 Excel Deeplink"""
    raw = request.args.get("path", "")
    path = urllib.parse.unquote(raw)

    if not _is_allowed_path(path):
        return abort(403, "path not allowed")
    if not os.path.exists(path):
        return abort(404, "file not found")

    open_url = request.url_root.rstrip("/") + url_for("api_open_file") + "?path=" + urllib.parse.quote(path)
    deeplink = f"ms-excel:ofe|u|{open_url}"
    return jsonify(ok=True, deeplink=deeplink)

@app.post("/api/pick-file")
def pick_file():
    """檔案選擇器"""
    t = request.args.get("type", "need")
    base = ALLOWED_ROOTS[0] if ALLOWED_ROOTS else r"C:\\"

    # 嘗試 tkinter
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()

        if t == "outdir":
            path = filedialog.askdirectory(initialdir=base, title="選擇輸出資料夾") or ""
        else:
            path = filedialog.askopenfilename(
                initialdir=base,
                title="選擇檔案",
                filetypes=[("Excel", "*.xlsx;*.xlsm"), ("All files", "*.*")]
            ) or ""
        root.destroy()
        if path:
            return jsonify(ok=True, path=path)
        return jsonify(ok=False, message="使用者取消")
    except Exception as e:
        logger.error(f"[pick-file] tkinter failed: {e}")

    # 回傳預設值
    defaults = {
        "need": os.path.join(base, "需求檔.xlsx"),
        "limit": os.path.join(base, "滴定限制.xlsx"),
        "template": DEFAULT_TEMPLATE,
        "outdir": DEFAULT_OUTDIR,
    }
    return jsonify(ok=True, path=defaults.get(t, DEFAULT_TEMPLATE), message="fallback-default")

# === VBA 同步 API ===

def sync_sheet_from_vba(excel_path: str, sheet_name: str, table_name: str, header_row_index: int) -> bool:
    """VBA 觸發的完整工作表同步"""
    logger.info(f"VBA-Sync (Full): 請求同步 {table_name} (標題行: {header_row_index + 1})")
    
    with db_lock:
        logger.info(f"VBA-Sync (Full): 開始處理 {excel_path} -> {sheet_name}")
        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name, header=header_row_index)
            df = df.dropna(how='all')
            
            if df.empty:
                logger.info(f"VBA-Sync (Full): 工作表 '{sheet_name}' 為空")
                return True

            df = normalize_df_for_sqlite(df)
            
            with sqlite3.connect(MAIN_DB_PATH) as conn:
                logger.info(f"VBA-Sync (Full): 正在將 {len(df)} 筆資料寫入資料表 '{table_name}'...")
                df.to_sql(table_name, conn, if_exists='replace', index=False)
            
            logger.info(f"VBA-Sync (Full): 成功。已上傳 {len(df)} 筆資料到 {table_name}")
            return True
            
        except Exception as e:
            logger.error(f"VBA-Sync (Full): FAILED! 處理 '{sheet_name}' 時發生錯誤: {e}")
            logger.error(traceback.format_exc())
            return False

@app.post("/api/vba-sync")
def api_vba_sync():
    """VBA 完整同步 API"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(ok=False, message="No JSON payload provided."), 400
        
        excel_path = data.get("excel_path")
        sheet_name = data.get("sheet_name")
        table_name = data.get("table_name")
        header_row_from_vba = data.get("header_row_num", 1)
        header_row_index = int(header_row_from_vba) - 1
        
        if header_row_index < 0:
            header_row_index = 0

        if not all([excel_path, sheet_name, table_name]):
            return jsonify(ok=False, message="Missing required fields."), 400
        
        if not _is_allowed_path(excel_path):
            return abort(403, f"VBA Sync: Path not allowed '{excel_path}'")

        success = sync_sheet_from_vba(excel_path, sheet_name, table_name, header_row_index)
        
        if success:
            return jsonify(ok=True, message=f"Successfully synced {sheet_name} to {table_name}.")
        else:
            return jsonify(ok=False, message="Sync failed. Check server logs."), 500
            
    except Exception as e:
        logger.error(f"VBA-Sync: /api/vba-sync 端點發生錯誤: {e}")
        logger.error(traceback.format_exc())
        return jsonify(ok=False, message=str(e)), 500

def sync_row_from_vba(table_name: str, row_data: dict, keys: list) -> bool:
    """VBA 觸發的單行同步"""
    logger.info(f"VBA-Sync (Row): 請求同步單行到 {table_name}")
    
    try:
        df = pd.DataFrame([row_data])
        df = normalize_df_for_sqlite(df)
    except Exception as e:
        logger.error(f"VBA-Sync (Row): 轉換資料失敗: {e}")
        return False
        
    with db_lock:
        logger.info(f"VBA-Sync (Row): 準備 Upsert...")
        try:
            with sqlite3.connect(MAIN_DB_PATH) as conn:
                upsert(conn, table_name, df, keys)
            
            logger.info(f"VBA-Sync (Row): 成功 Upsert 1 筆資料到 {table_name}")
            return True
            
        except Exception as e:
            logger.error(f"VBA-Sync (Row): FAILED! Upsert 錯誤: {e}")
            logger.error(traceback.format_exc())
            return False

@app.post("/api/vba-sync-row")
def api_vba_sync_row():
    """VBA 單行同步 API"""
    try:
        data = request.get_json()
        if not data:
            return jsonify(ok=False, message="No JSON payload provided."), 400
        
        table_name = data.get("table_name")
        row_data = data.get("row_data")
        primary_key = ["日期", "Lot"]
        
        if not all([table_name, row_data]):
            return jsonify(ok=False, message="Missing required fields."), 400
        
        success = sync_row_from_vba(table_name, row_data, primary_key)
        
        if success:
            return jsonify(ok=True, message=f"Successfully synced 1 row to {table_name}.")
        else:
            return jsonify(ok=False, message="Sync row failed. Check server logs."), 500
            
    except Exception as e:
        logger.error(f"VBA-Sync (Row): /api/vba-sync-row 端點發生錯誤: {e}")
        logger.error(traceback.format_exc())
        return jsonify(ok=False, message=str(e)), 500

from datetime import date, datetime, timedelta

def iso_week_range(year: int, week: int):
    # ISO week: Monday = day 1
    start = date.fromisocalendar(year, week, 1)
    end = date.fromisocalendar(year, week, 7)
    return start, end

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
                year_str, week_str = search_value.split("_W")
                y, w = int(year_str), int(week_str)
                week_start, week_end = iso_week_range(y, w)

                query = """
                    SELECT * FROM DropletSchedule
                    WHERE Date >= ? AND Date <= ?
                """
                params = (
                    week_start.strftime("%Y/%m/%d"),
                    week_end.strftime("%Y/%m/%d"),
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

@app.route("/api/schedule/utilization", methods=["GET"])
def api_utilization():
    """稼動率計算（從配藥表資料庫讀取實際數據）"""
    try:
        # 1. 參數解析
        mode = request.args.get("mode", "day")
        date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
        
        query_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        # 支援兩種日期格式 (資料庫可能混用)
        date_str_dash = query_date.strftime("%Y-%m-%d")
        date_str_slash = query_date.strftime("%Y/%m/%d")
        
        # 2. 基本檢查
        if not os.path.exists(FORMULATE_DB_PATH):
            return jsonify({
                "ok": True, "mode": mode, "period": "", 
                "titration_utilization": 0, "dryer_utilization": 0,
                "titration_used": 0, "titration_capacity": 0, 
                "dryer_used": 0, "dryer_capacity": 0, "work_days": 0
            })
        
        # 3. 資料庫連線與資料撈取
        with sqlite3.connect(FORMULATE_DB_PATH) as conn:
            # 根據模式撈取該時段的「所有實際資料」
            
            if mode == "day":
                query = '''
                    SELECT Pump, Lyophilizer, Date 
                    FROM DropletSchedule 
                    WHERE Date LIKE ? OR Date LIKE ?
                '''
                df = pd.read_sql_query(query, conn, params=(f"{date_str_slash}%", f"{date_str_dash}%"))
                period_desc = date_str_dash
                
            elif mode == "week":
                # 計算當周範圍 (週一 ~ 週日)
                iso_weekday = query_date.isoweekday()
                week_start = query_date - pd.Timedelta(days=iso_weekday - 1)
                week_end = week_start + pd.Timedelta(days=6)
                
                iso_cal = query_date.isocalendar()
                period_desc = f"{iso_cal[0]}_W{iso_cal[1]:02d}"
                
                # 迴圈產生整週日期條件
                date_conditions = []
                params = []
                current = week_start
                while current <= week_end:
                    d_slash = current.strftime("%Y/%m/%d")
                    d_dash = current.strftime("%Y-%m-%d")
                    date_conditions.append("Date LIKE ? OR Date LIKE ?")
                    params.extend([f"{d_slash}%", f"{d_dash}%"])
                    current += pd.Timedelta(days=1)
                
                if not date_conditions:
                    df = pd.DataFrame(columns=['Pump', 'Lyophilizer', 'Date'])
                else:
                    query = f"SELECT Pump, Lyophilizer, Date FROM DropletSchedule WHERE {' OR '.join(date_conditions)}"
                    df = pd.read_sql_query(query, conn, params=params)
                
            elif mode == "month":
                # 計算當月範圍 (1號 ~ 查詢日)
                year_month = query_date.strftime("%Y-%m")
                month_start = query_date.replace(day=1)
                period_desc = year_month
                
                # 迴圈產生整月日期條件
                date_conditions = []
                params = []
                current = month_start
                while current <= query_date:
                    d_slash = current.strftime("%Y/%m/%d")
                    d_dash = current.strftime("%Y-%m-%d")
                    date_conditions.append("Date LIKE ? OR Date LIKE ?")
                    params.extend([f"{d_slash}%", f"{d_dash}%"])
                    current += pd.Timedelta(days=1)
                
                if not date_conditions:
                    df = pd.DataFrame(columns=['Pump', 'Lyophilizer', 'Date'])
                else:
                    query = f"SELECT Pump, Lyophilizer, Date FROM DropletSchedule WHERE {' OR '.join(date_conditions)}"
                    df = pd.read_sql_query(query, conn, params=params)
            
            else:
                return jsonify({"ok": False, "message": "無效的模式"}), 400

        # 若無資料
        if df.empty:
            return jsonify({
                "ok": True, "mode": mode, "period": period_desc,
                "titration_utilization": 0, "dryer_utilization": 0,
                "titration_used": 0, "titration_capacity": 0,
                "dryer_used": 0, "dryer_capacity": 0, "work_days": 0
            })

        # --- 4. 統計計算 (Business Logic) ---

        # 計算實際有工作的日期天數 (作為分母乘數)
        df['date_only'] = df['Date'].astype(str).str.split(' ').str[0]
        work_days = df['date_only'].nunique()
        if work_days == 0: work_days = 1 

        # === B. 滴定 (Titration) 計算 ===
        machines = df["Pump"].dropna().astype(str).str.strip()
        machines = machines[machines != ""]
        
        # 分類 Port 與 IVEK
        ivek_rows = machines.str.contains("IVEK", case=False, na=False)
        ivek_count = ivek_rows.sum()        # IVEK 任務總數
        port_count = (~ivek_rows).sum()     # 一般 Port 任務總數
        
        # [邏輯修改] 分子：Port 權重=1, IVEK 權重=1
        # 計算總點數
        titration_used = (port_count * 1) + (ivek_count)
        
        # [邏輯修改] 分母：工作天數 * 全域常數 TOTAL_TITRATION_CAPACITY (26)
        titration_capacity = work_days * TOTAL_TITRATION_CAPACITY
        
        # 計算稼動率
        titration_utilization = round((titration_used / titration_capacity) * 100, 1) if titration_capacity > 0 else 0

        # === C. 凍乾 (Dryer) 計算 ===
        dryers = df["Lyophilizer"].dropna().astype(str).str.strip()
        dryers = dryers[dryers != ""]
        
        if mode == "day":
            # 日模式：直接算不重複機台
            dryer_used = dryers.nunique()
        else:
            # 週/月模式：每一天分開算 Unique 機台數後加總 (累計佔用量)
            dryer_used = 0
            for day in df['date_only'].unique():
                day_df = df[df['date_only'] == day]
                day_dryers = day_df['Lyophilizer'].dropna().astype(str).str.strip()
                day_dryers = day_dryers[day_dryers != ""]
                dryer_used += day_dryers.nunique()
        
        # [邏輯修改] 分母：工作天數 * 全域常數 TOTAL_DRYERS (11)
        dryer_capacity = work_days * TOTAL_DRYERS
        
        # 計算稼動率
        dryer_utilization = round((dryer_used / dryer_capacity) * 100, 1) if dryer_capacity > 0 else 0
        
        logger.info(f"✅ 稼動率 ({mode}): 天數={work_days}, 滴定={titration_used}/{titration_capacity} ({titration_utilization}%), 凍乾={dryer_used}/{dryer_capacity} ({dryer_utilization}%)")
        
        return jsonify({
            "ok": True,
            "mode": mode,
            "period": period_desc,
            "titration_utilization": titration_utilization,
            "dryer_utilization": dryer_utilization,
            "titration_used": int(titration_used),
            "titration_capacity": int(titration_capacity),
            "dryer_used": int(dryer_used),
            "dryer_capacity": int(dryer_capacity),
            "work_days": int(work_days)
        })
        
    except Exception as e:
        logger.error(f"❌ 稼動率計算失敗: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            "ok": False, "mode": mode, "period": "", "error": str(e)
        }), 500

@app.route("/api/schedule/completion-rate", methods=["GET"])
def api_completion_rate():
    """
    完成率計算 (跨資料庫比對 - 修正版 V2)
    邏輯：
    1. 分母 (Total): 從 DropletSchedule (排程表) 取得當日不重複的工單號。
    2. 分子 (Completed): 拿這些工單號去 work_orders (記錄表) 查詢狀態。
       - 配藥完成: '時間_收藥' 有值
       - 滴定完成: '時間_滴定結束' 有值
       - 凍乾完成: '時間_凍乾開始' 有值 (依據最新需求調整)
    """
    try:
        # 1. 取得日期參數 (預設今天)
        date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
        
        # 轉換日期格式
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        date_slash = date_obj.strftime("%Y/%m/%d")
        date_dash = date_str

        # 2. 檢查資料庫是否存在
        if not os.path.exists(FORMULATE_DB_PATH) or not os.path.exists(WORK_ORDER_DB_PATH):
            logger.warning("⚠️ 資料庫檔案缺失，無法計算完成率")
            return jsonify({
                "ok": True, "date": date_str, "total_orders": 0,
                "dispensing_rate": 0, "titration_rate": 0, "freeze_drying_rate": 0,
                "dispensing_completed": 0, "titration_completed": 0, "freeze_drying_completed": 0
            })

        # ==========================================
        # STEP 1: 取得分母 (從排程表 DropletSchedule)
        # ==========================================
        scheduled_orders = []
        with sqlite3.connect(FORMULATE_DB_PATH) as conn_sched:
            # 撈取今日排程的不重複工單號
            query_sched = """
                SELECT DISTINCT WorkOrder
                FROM DropletSchedule
                WHERE (Date LIKE ? OR Date LIKE ?)
                  AND WorkOrder IS NOT NULL 
                  AND WorkOrder != ''
            """
            df_sched = pd.read_sql_query(query_sched, conn_sched, params=(f"{date_slash}%", f"{date_dash}%"))
            
            if not df_sched.empty:
                scheduled_orders = df_sched['WorkOrder'].astype(str).str.strip().unique().tolist()

        total_orders = len(scheduled_orders)

        # 若今日無排程，直接回傳 0
        if total_orders == 0:
            return jsonify({
                "ok": True, "date": date_str, "total_orders": 0,
                "dispensing_rate": 0, "titration_rate": 0, "freeze_drying_rate": 0,
                "dispensing_completed": 0, "titration_completed": 0, "freeze_drying_completed": 0
            })

        # ==========================================
        # STEP 2: 取得分子 (從實際記錄表 work_orders)
        # ==========================================
        # 構建 SQL IN (...) 的查詢字串，只查今日有排程的工單
        placeholders = ','.join(['?'] * len(scheduled_orders))
        
        with sqlite3.connect(WORK_ORDER_DB_PATH) as conn_rec:
            # 注意：這裡將查詢欄位改為 '時間_凍乾開始'
            query_rec = f"""
                SELECT 
                    工單號,
                    時間_收藥,
                    時間_滴定結束,
                    時間_凍乾開始
                FROM work_orders
                WHERE 工單號 IN ({placeholders})
            """
            df_rec = pd.read_sql_query(query_rec, conn_rec, params=tuple(scheduled_orders))

        # ==========================================
        # STEP 3: 計算完成數
        # ==========================================
        dispensing_cnt = 0
        titration_cnt = 0
        freeze_drying_cnt = 0

        if not df_rec.empty:
            df_rec['工單號'] = df_rec['工單號'].astype(str).str.strip()
            
            # 定義判斷函式：欄位不為 None 且不為空字串
            def is_completed(val):
                return val is not None and str(val).strip() != "" and str(val).strip().lower() != "none"

            # (A) 配藥完成率：根據「時間_收藥」
            dispensing_cnt = df_rec[df_rec['時間_收藥'].apply(is_completed)]['工單號'].nunique()

            # (B) 滴定完成率：根據「時間_滴定結束」
            # 若您希望滴定也改為 '開始'，請將 SQL 和此處一併修改，目前維持 '結束'
            titration_cnt = df_rec[df_rec['時間_滴定結束'].apply(is_completed)]['工單號'].nunique()

            # (C) 凍乾完成率：根據「時間_凍乾開始」 (依您的需求修改)
            freeze_drying_cnt = df_rec[df_rec['時間_凍乾開始'].apply(is_completed)]['工單號'].nunique()

        # ==========================================
        # STEP 4: 計算百分比與回傳
        # ==========================================
        def calc_rate(val, total):
            return round((val / total) * 100, 1)

        disp_rate = calc_rate(dispensing_cnt, total_orders)
        titr_rate = calc_rate(titration_cnt, total_orders)
        dryer_rate = calc_rate(freeze_drying_cnt, total_orders)

        logger.info(f"📊 完成率 ({date_str}): 總數={total_orders}, 配藥={dispensing_cnt}, 滴定={titration_cnt}, 凍乾={freeze_drying_cnt}")

        return jsonify({
            "ok": True,
            "date": date_str,
            "total_orders": int(total_orders),
            
            "dispensing_completed": int(dispensing_cnt),
            "titration_completed": int(titration_cnt),
            "freeze_drying_completed": int(freeze_drying_cnt),
            
            "dispensing_rate": disp_rate,
            "titration_rate": titr_rate,
            "freeze_drying_rate": dryer_rate
        })

    except Exception as e:
        logger.error(f"❌ 完成率計算失敗: {e}")
        logger.error(traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/schedule/workload-stats", methods=["GET"])
def api_workload_stats():
    """
    工作分派統計（從固定資料庫讀取）- 基於 WorkOrder 統計
    
    統計邏輯：
    - 以「工單號碼 (WorkOrder)」為單位
    - 統計每個 Preparer 負責的工單數
    - 相同的 [WorkOrder, Preparer] 組合只計算一次
    """
    
    mode = "unknown"
    try:
        mode = request.args.get("mode", "week")
        date_str = request.args.get("date", date.today().strftime("%Y-%m-%d"))
        
        query_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        # ✅ 檢查資料庫是否存在
        if not os.path.exists(FORMULATE_DB_PATH):
            logger.warning(f"⚠️ 配藥表資料庫不存在: {FORMULATE_DB_PATH}")
            return jsonify({
                "ok": True,
                "mode": mode,
                "period": "",
                "staff_stats": [],
                "total_assignments": 0,
                "message": f"資料庫不存在: {FORMULATE_DB_PATH}"
            })
        
        logger.info(f"📂 使用資料庫: {FORMULATE_DB_PATH}")
        
        with sqlite3.connect(FORMULATE_DB_PATH) as conn:
            cursor = conn.cursor()
            
            # ✅ 檢查表是否存在
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='DropletSchedule'"
            )
            if not cursor.fetchone():
                logger.warning("⚠️ DropletSchedule 表不存在")
                return jsonify({
                    "ok": True,
                    "mode": mode,
                    "period": "",
                    "staff_stats": [],
                    "total_assignments": 0,
                    "message": "DropletSchedule 表不存在"
                })
            
            # ✅ 檢查必要欄位是否存在
            cursor.execute("PRAGMA table_info(DropletSchedule)")
            columns = [col[1] for col in cursor.fetchall()]
            required_cols = ['Date', 'WorkOrder', 'Preparer']
            missing_cols = [col for col in required_cols if col not in columns]
            
            if missing_cols:
                logger.error(f"❌ 缺少必要欄位: {missing_cols}")
                return jsonify({
                    "ok": False,
                    "mode": mode,
                    "period": "",
                    "staff_stats": [],
                    "total_assignments": 0,
                    "error": f"缺少必要欄位: {', '.join(missing_cols)}"
                }), 400
            
            logger.info(f"✅ 表結構確認完成，可用欄位: {columns}")
            
            # ✅ 根據模式查詢
            if mode == "week":
                # 計算本周的日期範圍
                iso_weekday = query_date.isoweekday()  # 1=週一, 7=週日
                week_start = query_date - pd.Timedelta(days=iso_weekday - 1)
                week_end = week_start + pd.Timedelta(days=6)
                
                # 取得 ISO 週編號用於描述
                iso_calendar = week_start.isocalendar()
                year = iso_calendar[0]
                week = iso_calendar[1]
                period_desc = f"{year}_W{week:02d} ({week_start.strftime('%Y-%m-%d')} ~ {week_end.strftime('%Y-%m-%d')})"

                # 生成該週所有日期的查詢條件
                date_conditions = []
                params = []
                current = week_start
                while current <= week_end:
                    date_slash = current.strftime("%Y/%m/%d")
                    date_dash = current.strftime("%Y-%m-%d")
                    date_conditions.append("Date LIKE ?")
                    date_conditions.append("Date LIKE ?")
                    params.extend([f"{date_slash}%", f"{date_dash}%"])
                    current += pd.Timedelta(days=1)
                
                query = f'''
                    SELECT Date, WorkOrder, Preparer
                    FROM DropletSchedule 
                    WHERE {" OR ".join(date_conditions)}
                '''
                df = pd.read_sql_query(query, conn, params=params)
                
            elif mode == "month":
                # 從該月1號到 query_date
                year_month = query_date.strftime("%Y-%m")
                month_start = query_date.replace(day=1)
                
                # 生成從 1 號到 query_date 的所有日期條件
                date_conditions = []
                params = []
                current = month_start
                while current <= query_date:
                    date_slash = current.strftime("%Y/%m/%d")
                    date_dash = current.strftime("%Y-%m-%d")
                    date_conditions.append("Date LIKE ?")
                    date_conditions.append("Date LIKE ?")
                    params.extend([f"{date_slash}%", f"{date_dash}%"])
                    current += pd.Timedelta(days=1)
                
                if not date_conditions:
                    df = pd.DataFrame(columns=['Date', 'WorkOrder', 'Preparer'])
                else:
                    query = f'''
                        SELECT Date, WorkOrder, Preparer
                        FROM DropletSchedule 
                        WHERE {" OR ".join(date_conditions)}
                    '''
                    df = pd.read_sql_query(query, conn, params=params)
                
                # 描述
                iso_cal = query_date.isocalendar()
                current_week_str = f"{iso_cal[0]}_W{iso_cal[1]:02d}"
                period_desc = f"{year_month} (1號 至 {query_date.day}號, {current_week_str})"
                
            else:
                logger.error(f"❌ 無效的模式: {mode}")
                return jsonify({"ok": False, "message": "無效的模式，請使用 'week' 或 'month'"}), 400
        
        if df.empty:
            logger.info(f"工作分派查詢無數據：{mode} - {period_desc}")
            return jsonify({
                "ok": True,
                "mode": mode,
                "period": period_desc,
                "staff_stats": [],
                "total_assignments": 0,
                "message": "查詢期間內無資料"
            })
        
        logger.info(f"🔍 查詢到 {len(df)} 筆原始數據")
        
        # ✅ 過濾：移除 WorkOrder 或 Preparer 為空的記錄
        df = df[df['WorkOrder'].notna() & (df['WorkOrder'].astype(str).str.strip() != '')]
        df = df[df['Preparer'].notna() & (df['Preparer'].astype(str).str.strip() != '')]
        
        logger.info(f"✅ 有效數據（有工單號碼和配藥人員）：{len(df)} 筆")
        
        if df.empty:
            return jsonify({
                "ok": True,
                "mode": mode,
                "period": period_desc,
                "staff_stats": [],
                "total_assignments": 0,
                "message": "過濾後無有效資料"
            })
        
        # ✅ 標準化欄位
        df['WorkOrder'] = df['WorkOrder'].astype(str).str.strip()
        df['Preparer'] = df['Preparer'].astype(str).str.strip()
        
        # ✅ 關鍵：使用「工單號碼 + 配藥人員」去重
        df['unique_key'] = df['WorkOrder'] + '_' + df['Preparer']
        df_unique = df.drop_duplicates(subset=['unique_key'])
        
        logger.info(f"🔑 去重後（工單+人員）：{len(df_unique)} 筆唯一組合")
        
        # ✅ 統計每個人員的工單數
        staff_assignments = df_unique['Preparer'].value_counts().to_dict()
        total_assignments = len(df_unique)
        
        # ✅ 生成統計結果
        staff_stats = []
        for name, count in staff_assignments.items():
            percentage = round((count / total_assignments) * 100, 1) if total_assignments > 0 else 0
            staff_stats.append({
                "name": name,
                "count": int(count),
                "percentage": percentage
            })
        
        # ✅ 按分派數排序（從高到低）
        staff_stats = sorted(staff_stats, key=lambda x: x['count'], reverse=True)
        
        logger.info(f"✅ 工作分派統計 ({mode}): 期間={period_desc}, 總工單數={total_assignments}, 人員數={len(staff_stats)}")
        if staff_stats:
            logger.info(f"   前5名人員分派：{[(s['name'], s['count']) for s in staff_stats[:5]]}")
        
        return jsonify({
            "ok": True,
            "mode": mode,
            "period": period_desc,
            "staff_stats": staff_stats,
            "total_assignments": int(total_assignments)
        })
        
    except Exception as e:
        logger.error(f"❌ 工作分派統計失敗: {e}")
        logger.error(traceback.format_exc())
        
        return jsonify({
            "ok": False,
            "mode": mode,
            "period": "",
            "staff_stats": [],
            "total_assignments": 0,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

# ====================================================================
# ====== IPQC 表單專用 API (跨年度搜尋版) ======
# ====================================================================

# 輔助函式：取得所有 IPQC 資料表名稱
def get_all_ipqc_tables(cursor):
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    # 篩選出格式為 "YYYY_IPQC" 的表
    ipqc_tables = [t for t in tables if t.endswith("_IPQC") and t[:4].isdigit()]
    # 排序：由新到舊 (2026, 2025...)
    ipqc_tables.sort(reverse=True)
    return ipqc_tables

@app.route("/api/options", methods=["GET"])
def api_get_options():
    """
    取得篩選選項 (全資料庫掃描版)
    邏輯：不依賴單一年份，而是掃描所有存在的年份表 (2024_IPQC, 2025_IPQC...)
    將所有出現過的 Marker 與 併批狀態 合併去重後回傳。
    """
    response_data = {"makers": [], "batch_options": []}

    if not os.path.exists(IPQC_DB_PATH):
        return jsonify(response_data)

    try:
        with sqlite3.connect(IPQC_DB_PATH) as conn:
            cursor = conn.cursor()
            
            # 1. 取得所有 IPQC 資料表 (例如 ['2026_IPQC', '2025_IPQC'])
            tables = get_all_ipqc_tables(cursor)
            
            if not tables:
                return jsonify(response_data)

            # 使用 Set 來儲存，自動去除重複值
            all_markers = set()
            all_batches = set()

            logger.info(f"🔍 [Options] 正在掃描資料表: {tables} 以建立選項清單")

            # 2. 迴圈掃描每一張表
            for table in tables:
                try:
                    # 取得該表的欄位
                    cursor.execute(f'PRAGMA table_info("{table}")')
                    columns = {row[1] for row in cursor.fetchall()}

                    # --- 找 Marker 欄位 ---
                    # 優先找 Marker, Maker, 廠商
                    marker_col = next((c for c in columns if c.lower() in ['marker', 'maker', '廠商']), None)
                    
                    if marker_col:
                        cursor.execute(f'SELECT DISTINCT "{marker_col}" FROM "{table}"')
                        rows = cursor.fetchall()
                        for r in rows:
                            if r[0] and str(r[0]).strip(): # 排除空值
                                all_markers.add(str(r[0]).strip())

                    # --- 找 併批 欄位 ---
                    # 優先找 初判併批, 併批, Batchable
                    batch_col = next((c for c in columns if '併批' in c or 'Batch' in c), None)
                    
                    if batch_col:
                        cursor.execute(f'SELECT DISTINCT "{batch_col}" FROM "{table}"')
                        rows = cursor.fetchall()
                        for r in rows:
                            if r[0] and str(r[0]).strip():
                                all_batches.add(str(r[0]).strip())

                except Exception as table_err:
                    logger.warning(f"⚠️ 讀取資料表 {table} 選項時發生錯誤: {table_err}")
                    continue

            # 3. 轉換回 List 並排序
            response_data["makers"] = sorted(list(all_markers))
            response_data["batch_options"] = sorted(list(all_batches))
            
            logger.info(f"✅ 選項載入完成: {len(response_data['makers'])} 個 Marker, {len(response_data['batch_options'])} 個併批狀態")

            return jsonify(response_data)

    except Exception as e:
        logger.error(f"❌ 取得選項失敗: {e}")
        return jsonify(response_data), 500

@app.route("/api/qc_table", methods=["GET"])
def api_get_qc_table():
    """
    主要查詢 API (跨年度搜尋 V4)
    移除 year 參數，自動搜尋所有年份資料表並合併結果
    """
    marker = request.args.get("marker", "")
    
    # 生產日區間
    prod_start = request.args.get("prod_start", "")
    prod_end = request.args.get("prod_end", "")
    
    # 檢驗日區間
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
                # 取得該表的欄位結構
                cursor.execute(f'PRAGMA table_info("{table_name}")')
                columns = {row[1] for row in cursor.fetchall()}

                # 鎖定欄位
                prod_col = "dD生產日" if "dD生產日" in columns else next((c for c in columns if '生產' in c), None)
                insp_col = "檢驗日期" if "檢驗日期" in columns else next((c for c in columns if '檢驗' in c), None)
                marker_col = next((c for c in columns if c.lower() in ['marker', 'maker', '廠商']), None)
                batch_col = next((c for c in columns if '併批' in c), None)

                # 如果這個表連生產日或檢驗日都沒有，可能不是我們要的表，跳過
                if not prod_col and not insp_col:
                    continue

                query = [f'SELECT *, "{table_name}" as source_table FROM "{table_name}" WHERE 1=1']
                params = []

                # --- 條件 1: Marker ---
                if marker and marker_col:
                    query.append(f'AND "{marker_col}" = ?')
                    params.append(marker)
                
                # --- 條件 2: 生產日範圍 ---
                if prod_col:
                    db_prod = f'DATE(REPLACE("{prod_col}", "/", "-"))'
                    if prod_start and prod_end:
                        query.append(f'AND {db_prod} >= DATE(?) AND {db_prod} <= DATE(?)')
                        params.append(prod_start)
                        params.append(prod_end)
                    elif prod_start:
                        query.append(f'AND {db_prod} >= DATE(?)')
                        params.append(prod_start)

                # --- 條件 3: 檢驗日範圍 ---
                if insp_col:
                    db_insp = f'DATE(REPLACE("{insp_col}", "/", "-"))'
                    if insp_start and insp_end:
                        query.append(f'AND {db_insp} >= DATE(?) AND {db_insp} <= DATE(?)')
                        params.append(insp_start)
                        params.append(insp_end)
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

            # 3. 排序 (在 Python 記憶體中排序)
            # 優先嘗試用 'dD生產日' 排序，如果沒有則放最後
            def sort_key(item):
                # 嘗試取得生產日，若無則回傳極小日期
                val = item.get('dD生產日') or item.get('生產日') or item.get('Date') or ""
                return val
            
            # 由新到舊排序
            final_results.sort(key=sort_key, reverse=True)
            
            # 限制回傳筆數 (例如最多 2000 筆)
            return jsonify(final_results[:2000])

    except Exception as e:
        logger.error(f"❌ 跨年度查詢失敗: {e}")
        return jsonify([]), 500


# ✅ 測試用的路由 - 檢查資料庫連線和資料
@app.route("/api/schedule/test-db", methods=["GET"])
def test_db():
    """測試資料庫連線和資料結構"""
    try:
        if not os.path.exists(FORMULATE_DB_PATH):
            return jsonify(ok=False, error="FORMULATE_DB_PATH not found", path=FORMULATE_DB_PATH), 404

        with sqlite3.connect(FORMULATE_DB_PATH) as conn:
            cur = conn.cursor()

            # tables
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [r[0] for r in cur.fetchall()]

            # DropletSchedule columns + sample
            droplet_info = {"exists": False, "columns": [], "sample": []}
            if "DropletSchedule" in tables:
                droplet_info["exists"] = True
                cur.execute("PRAGMA table_info(DropletSchedule)")
                droplet_info["columns"] = [r[1] for r in cur.fetchall()]

                cur.execute("SELECT * FROM DropletSchedule LIMIT 5")
                cols = [d[0] for d in cur.description] if cur.description else []
                rows = cur.fetchall()
                droplet_info["sample"] = [dict(zip(cols, row)) for row in rows]

            # Liquid form QC columns + sample
            liquid_info = {"exists": False, "columns": [], "sample": []}
            if "Liquid form QC" in tables:
                liquid_info["exists"] = True
                cur.execute('PRAGMA table_info("Liquid form QC")')
                liquid_info["columns"] = [r[1] for r in cur.fetchall()]

                cur.execute('SELECT * FROM "Liquid form QC" LIMIT 5')
                cols = [d[0] for d in cur.description] if cur.description else []
                rows = cur.fetchall()
                liquid_info["sample"] = [dict(zip(cols, row)) for row in rows]

        return jsonify(
            ok=True,
            path=FORMULATE_DB_PATH,
            tables=tables,
            dropletSchedule=droplet_info,
            liquidFormQC=liquid_info
        )
    except Exception as e:
        logger.error(f"❌ test_db failed: {e}")
        logger.error(traceback.format_exc())
        return jsonify(ok=False, error=str(e)), 500


# === 前端路由 ===

@app.get("/")
def index():
    """首頁"""
    return send_from_directory(str(DIST), "index.html")

@app.route("/<path:path>")
def static_proxy(path):
    """靜態檔案代理"""
    target = DIST / path
    if target.exists():
        return send_from_directory(str(DIST), path)
    return send_from_directory(str(DIST), "index.html")

# ====================================================================
# ====== 主程式啟動與生命週期管理 ======
# ====================================================================

# 註冊全域清理函數
atexit.register(stop_watch)        # 停止 A-E 檔 Watchdog
atexit.register(stop_wip_monitor)  # 停止 WIP 背景監控執行緒 [補足]
atexit.register(final_sync_before_exit) # 退出前最後同步

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Beads 統一服務器 V13.2 - 啟動中")
    logger.info("=" * 60)
    
    beads_observer = None
    
    try:
        # 顯示關鍵路徑資訊
        logger.info(f"Flask 服務將在 http://0.0.0.0:8505 啟動")
        logger.info(f"📂 同步資料庫: {MAIN_DB_PATH}")
        logger.info(f"📂 排程資料庫: {DB_PATH}")
        logger.info(f"📂 WIP 資料庫: {WIP_DB_PATH}")
        logger.info("⚠️ 監控模式: PollingObserver (支援網路路徑)")
        
        # ----------------------------------------------------
        # ✅ 1. 啟動 IPQC 上傳同步監控 (獨立 Observer)
        # ----------------------------------------------------
        logger.info("\n[Step 1] 啟動 Beads IPQC 同步服務...")
        try:
            # 呼叫來自 IPQA_db_V1_importable 的函式
            beads_observer = start_ipqc_monitoring()
            if beads_observer:
                logger.info("✅ IPQC 同步服務已在背景執行 (監視 Excel 變更)")
            else:
                logger.warning("❌ IPQC 同步服務啟動失敗 (請檢查路徑權限)")
        except Exception as e:
            logger.error(f"❌ IPQC 服務啟動異常: {e}")

        # ----------------------------------------------------
        # ✅ 2. 初始化核心服務 (A-E 同步 + WIP 啟動)
        # ----------------------------------------------------
        logger.info("\n[Step 2] 執行全系統初始化服務...")
        # 此函式內部會呼叫 initial_sync_and_prepare_db(), run_wip_sync_once(), 
        # init_wip_automation() 以及 start_wip_monitor()
        initialize_sync_service()
        
        if not state.sync_init_done:
            logger.warning("⚠️ 警告：核心同步服務初始化未完全成功")
        
        # ----------------------------------------------------
        # ✅ 3. 啟動 Flask Web 服務
        # ----------------------------------------------------
        logger.info("\n" + "=" * 60)
        logger.info("🚀 啟動 Flask 服務 (Port: 8505)")
        logger.info("=" * 60 + "\n")
        
        app.run(
            host="0.0.0.0",
            port=8505,
            debug=False,
            threaded=True,
            use_reloader=False
        )
        
    except KeyboardInterrupt:
        logger.info("\n[System] 偵測到使用者中斷 (Ctrl+C)")
    except Exception as e:
        logger.error(f"\n❌ Flask 主服務異常潰散: {e}")
        logger.error(traceback.format_exc())
    finally:
        logger.info("\n" + "=" * 60)
        logger.info("🔄 執行伺服器安全關閉程序")
        logger.info("=" * 60)
        
        # 停止 IPQC 監控
        if beads_observer:
            logger.info("正在關閉 IPQC Observer...")
            beads_observer.stop()
            beads_observer.join()
        
        # 停止 WIP 背景執行緒
        stop_wip_monitor()
        
        # 停止 A-E 檔 Watchdog
        stop_watch()
        
        # 執行最後同步
        final_sync_before_exit()
        
        logger.info("✅ 所有背景服務已安全關閉，伺服器停止。")