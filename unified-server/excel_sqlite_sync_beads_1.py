# -*- coding: utf-8 -*-
import os, re, time, signal, threading, sqlite3
from datetime import datetime, date
from typing import Optional, List

import pandas as pd
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from pandas.api.types import is_datetime64_any_dtype as is_datetime
import datetime as dt

# ====== 固定設定（依你的要求） ======
BASE_DIR = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定"
FILE_A = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\★2024-最新版【勿動】-BEADS庫存-20241126.xlsm"
FILE_B_PATTERN = os.path.join(BASE_DIR, "Production plan-*.xlsm")

# A 檔規格
A_SHEET = "BEADS庫存表(202405~"
A_HEADER_ROW = 5
A_DATA_START_ROW = 6
A_DATA_LAST_COL = "O"      # A:O
A_LASTROW_BY_COL = "B"     # 以 B 欄決定最後列
A_TABLE = "beads_Inventory"
A_KEYS = ["PN", "Batch"]

# B 檔規格
B_SHEET = "P_plan Reagent"
B_HEADER_ROW = 2
B_DATA_START_ROW = 3
B_DATA_LAST_COL = "PQ"     # A:PQ
B_LASTROW_BY_COL = "B"
B_TABLE = "production_Plan"
B_KEYS = ["PN"]

# DB 與執行資料夾
APP_DIR = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Bead_auto_update_schedule"
DB_PATH  = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\beads_sync.db"

# 其他
DEBOUNCE_SECONDS = 2.0
READ_RETRY = 4
READ_RETRY_SLEEP = 0.6

# ====== 內部狀態 ======
_shutdown_flag = False
_db_lock = threading.Lock()
_last_event_ts = {}
_observer: Optional[Observer] = None
_watched_folders: set = set()   # 存資料夾路徑（避免重複 schedule）

# ====== 小工具 ======
def log(msg: str):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")

def safe_ident(name: str) -> str:
    """表名/欄名安全轉義（把內部雙引號變成兩個 ""）"""
    if name is None:
        name = ""
    s = str(name).replace('"', '""').strip()
    return s if s else "_col_"

def col_to_index(col: str) -> int:
    col = col.upper()
    s = 0
    for ch in col:
        s = s * 26 + (ord(ch) - 64)
    return s

def pick_latest_plan_file() -> Optional[str]:
    """挑選 <= 今天且最接近今天的 Production plan-YYYYMMDD.xlsm"""
    files = []
    today = date.today()
    rx = re.compile(r"Production plan-(\d{8})\.xlsm$", re.IGNORECASE)
    base = os.path.dirname(FILE_B_PATTERN)
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
    files.sort(key=lambda x: (today - x[0]))  # 差距最小者優先
    return files[0][1]

def normalize_df_for_sqlite(df: pd.DataFrame) -> pd.DataFrame:
    """把日期型欄位統一轉成 'YYYY-MM-DD' 字串；NaN→空字串；其他轉字串。"""
    out = df.copy()
    for col in out.columns:
        s = out[col]
        if is_datetime(s):
            out[col] = s.dt.strftime("%Y-%m-%d").fillna("")
        else:
            out[col] = s.map(
                lambda x: (
                    x.strftime("%Y-%m-%d") if isinstance(x, (dt.date, dt.datetime, pd.Timestamp))
                    else ("" if pd.isna(x) else str(x))
                )
            )
    return out

def read_range_df(
    xl_path: str, sheet: str, header_row: int, data_start_row: int,
    last_col_letter: str, lastrow_by_col_letter: str
) -> pd.DataFrame:
    """
    讀取指定範圍：表頭列 = header_row；
    資料從 data_start_row 到「lastrow_by_col」決定的最後列；
    欄位 A 到 last_col_letter。自動去除全空白列，NaN -> ""。
    """
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
    iloc_end = df.index.get_loc(last_rel_idx) + 1  # iloc 結尾不含

    df2 = df.iloc[iloc_start:iloc_end, :last_col_idx].copy()

    # 清洗
    df2.columns = [str(c).replace("\n", " ").strip() for c in df2.columns]
    df2 = df2.dropna(how="all").fillna("")

    # 日期標準化
    df2 = normalize_df_for_sqlite(df2)
    return df2

# ---- 只給 B 檔用：將 yyyy-MM-dd HH:mm:ss 欄名縮成 yyyy-MM-dd ----
def normalize_b_headers(cols: list[str]) -> list[str]:
    """
    把像 '2025-01-07 00:00:00' 轉成 '2025-01-07'；其他維持原樣。
    也會處理 '2025-1-7 00:00:00' 這類，統一成兩位數。
    """
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

# ====== A 檔：強制重算並存檔 ======
def recalc_and_save_excel(filepath: str, timeout_sec: int = 30):
    """
    先嘗試：pywin32 COM（強制關閉 makepy；晚期繫結；新實例；含 timeout）
    失敗就退回：VBScript（cscript 呼叫 Excel 計算/存檔），同樣有 timeout。
    兩者都不通就安靜跳過（不阻塞同步）。
    """
    # ---- 方案1：pywin32（關閉 makepy）----
    try:
        import pythoncom, subprocess, sys, tempfile, textwrap, os, time, threading
        import win32com.client
        # 關閉 makepy（重要！不然會嘗試寫 gen_py 而卡住）
        try:
            win32com.client.gencache.is_readonly = True
        except Exception:
            pass

        def _com_job():
            pythoncom.CoInitialize()
            excel = None
            wb = None
            try:
                # 開新實例，避免附掛到已存在的 EXCEL.EXE
                excel = win32com.client.DispatchEx("Excel.Application")  # 晚期繫結，不跑 makepy
                # 某些環境這兩個屬性無法設置；吞掉例外
                for attr, val in (("Visible", False), ("DisplayAlerts", False)):
                    try:
                        setattr(excel, attr, val)
                    except Exception:
                        pass
                # 避免外部連結卡住
                try:
                    wb = excel.Workbooks.Open(filepath, ReadOnly=False, UpdateLinks=0)
                except Exception:
                    wb = excel.Workbooks.Open(filepath, ReadOnly=False)
                # 逐層嘗試重算
                ok = False
                for f in (
                    lambda: excel.CalculateFullRebuild(),
                    lambda: excel.CalculateFull(),
                    lambda: wb.Application.CalculateFullRebuild(),
                    lambda: wb.Application.CalculateFull(),
                ):
                    try:
                        f()
                        ok = True
                        break
                    except Exception:
                        continue
                try:
                    if wb:
                        wb.Save()
                finally:
                    if wb:
                        wb.Close(SaveChanges=False)
            finally:
                if excel:
                    try:
                        excel.Quit()
                    except Exception:
                        pass
                pythoncom.CoUninitialize()

        t = threading.Thread(target=_com_job, daemon=True)
        t.start()
        t.join(timeout_sec)
        if t.is_alive():
            # COM 逾時 -> 走 VBScript
            raise TimeoutError("COM recalc timeout")
        return
    except Exception as e:
        log(f"A 檔重算：COM 方案失敗，改用 VBScript（{e}）")

    # ---- 方案2：VBScript 落地呼叫 Excel ----
    try:
        import subprocess, tempfile, textwrap, os, threading

        vbs = textwrap.dedent(f"""
        On Error Resume Next
        Dim xl, wb
        Set xl = CreateObject("Excel.Application")
        If Not xl Is Nothing Then
            On Error Resume Next
            xl.DisplayAlerts = False
            xl.Visible = False
            Set wb = xl.Workbooks.Open("{filepath.replace('"','""')}", 0, False)
            If Not wb Is Nothing Then
                Err.Clear
                xl.CalculateFullRebuild
                If Err.Number <> 0 Then
                    Err.Clear
                    xl.CalculateFull
                End If
                wb.Save
                wb.Close False
            End If
            xl.Quit
        End If
        """)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".vbs") as f:
            f.write(vbs.encode("utf-8-sig"))
            vbs_path = f.name

        try:
            # 用 cscript 執行，避免圖形介面
            p = subprocess.Popen(
                ["cscript.exe", "//nologo", vbs_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # 自行實作 timeout
            waited = 0
            step = 0.5
            while p.poll() is None and waited < timeout_sec:
                time.sleep(step)
                waited += step
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
    except Exception as e:
        log(f"A 檔重算：VBScript 方案也失敗（{e}），跳過重算")


# ====== 欄名對映 + 鍵值防呆 ======
A_HEADER_MAP = {
    "料號": "PN",
    "批號": "Batch",
    "PN ": "PN",
    "PN": "PN",
    "Batch No.": "Batch",
    "Batch": "Batch",
}

def normalize_columns(df: pd.DataFrame, header_map: dict[str, str]) -> pd.DataFrame:
    """清除換行/全形空白，套用對映；若重複欄名，自動加 __n 後綴避免衝突。"""
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

def drop_rows_with_empty_keys(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """去除鍵值為空的列，避免 ON CONFLICT 以空鍵把多列擠成一列。"""
    for k in keys:
        if k not in df.columns:
            return df.iloc[0:0]
        df[k] = df[k].map(lambda x: str(x).strip())
    mask = df[keys].apply(lambda s: s.str.len() > 0).all(axis=1)
    return df[mask].copy()

# ====== 結構維護 / UPSERT ======
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
    if not keys:
        return
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

    if nonkeys:
        set_clause = ", ".join([f'"{c}"=excluded."{c}"' for c in nonkeys])
        sql = (
            f'INSERT INTO "{safe_ident(table)}" ({col_list}) VALUES ({placeholders}) '
            f'ON CONFLICT ({conflict}) DO UPDATE SET {set_clause};'
        )
    else:
        sql = (
            f'INSERT INTO "{safe_ident(table)}" ({col_list}) VALUES ({placeholders}) '
            f'ON CONFLICT ({conflict}) DO NOTHING;'
        )

    with conn:
        conn.executemany(sql, df.itertuples(index=False, name=None))

# ====== 同步 ======
def sync_A():
    with _db_lock:
        log("同步 A 檔開始")

        # ① 先強制重算並存檔，確保公式快取更新
        try:
            recalc_and_save_excel(FILE_A)
        except Exception as e:
            log(f"A 檔重算/存檔警告：{e}（將嘗試直接讀取）")

        df = read_range_df(FILE_A, A_SHEET, A_HEADER_ROW, A_DATA_START_ROW, A_DATA_LAST_COL, A_LASTROW_BY_COL)

        # ② 欄名校正
        df = normalize_columns(df, A_HEADER_MAP)

        # ③ 去空白鍵值列
        df = drop_rows_with_empty_keys(df, A_KEYS)

        # ④ 觀察性日誌
        log(f"A cols(sample): {list(df.columns)[:10]} ... total_cols={len(df.columns)}, rows={len(df)}")
        if len(df) == 0:
            log("A 檔有效資料為 0 列（鍵值缺漏或表頭對不上）")
            return

        # ⑤ 進行 UPSERT
        with sqlite3.connect(DB_PATH) as conn:
            upsert(conn, A_TABLE, df, A_KEYS)
        log(f"同步 A 檔完成：rows={len(df)}")

def sync_B():
    file_b = pick_latest_plan_file()
    if not file_b:
        log("找不到合法的 Production plan-YYYYMMDD.xlsm（<= 今天）")
        return
    with _db_lock:
        log(f"同步 B 檔開始：{os.path.basename(file_b)}")
        df = read_range_df(file_b, B_SHEET, B_HEADER_ROW, B_DATA_START_ROW, B_DATA_LAST_COL, B_LASTROW_BY_COL)
        df.columns = normalize_b_headers(list(df.columns))

        for k in B_KEYS:
            if k in df.columns:
                df[k] = df[k].map(lambda x: str(x).strip())

        log(f"B cols(sample): {list(df.columns)[:10]} ... total_cols={len(df.columns)}, rows={len(df)}")
        if len(df) == 0:
            log("B 檔有效資料為 0 列")
            return

        with sqlite3.connect(DB_PATH) as conn:
            upsert(conn, B_TABLE, df, B_KEYS)
        log(f"同步 B 檔完成：rows={len(df)}")

def initial_sync_and_prepare_db():
    if not os.path.exists(DB_PATH):
        log(f"DB 不存在，將建立：{DB_PATH}")
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        open(DB_PATH, "ab").close()
    sync_A()
    sync_B()

def final_sync_before_exit():
    log("關閉前最終同步開始")
    try:
        sync_A()
    except Exception as e:
        log(f"最終同步 A 失敗：{e}")
    try:
        sync_B()
    except Exception as e:
        log(f"最終同步 B 失敗：{e}")
    log("關閉前最終同步完成")

# ====== 監看（watch） ======
class Handler(FileSystemEventHandler):
    def on_any_event(self, event):
        if event.is_directory:
            return
        path = os.path.abspath(event.src_path)
        now = time.time()
        last = _last_event_ts.get(path, 0)
        if now - last < DEBOUNCE_SECONDS:
            return
        _last_event_ts[path] = now

        try:
            if os.path.abspath(FILE_A).lower() == path.lower():
                log(f"A 檔變更事件：{event.event_type}")
                sync_A()
                return

            current_b = pick_latest_plan_file()
            if current_b and os.path.abspath(current_b).lower() == path.lower():
                log(f"B 檔變更事件：{event.event_type} | {os.path.basename(current_b)}")
                sync_B()
                return

            # 若在 BASE_DIR 內新增了新的 B 檔
            if os.path.dirname(path).lower() == BASE_DIR.lower() and re.search(r"Production plan-\d{8}\.xlsm$", os.path.basename(path), re.I):
                newer_b = pick_latest_plan_file()
                if newer_b:
                    add_watch(newer_b)
                    log(f"偵測到新的 B 候選檔：{os.path.basename(newer_b)} → 重新同步")
                    sync_B()

        except Exception as e:
            log(f"事件處理錯誤：{e}")

def add_watch(any_path_under_folder: str):
    """以『資料夾』為單位加入監看，避免重複 schedule。"""
    global _observer
    if not _observer:
        return
    folder = os.path.abspath(os.path.dirname(any_path_under_folder))
    if folder in _watched_folders:
        return
    _observer.schedule(Handler(), folder, recursive=False)
    _watched_folders.add(folder)
    log(f"已監看資料夾：{folder}")

def start_watch():
    global _observer
    _observer = Observer()
    _observer.daemon = True

    # 監看 A 檔所在資料夾
    add_watch(FILE_A)

    # 監看目前選中的 B 檔所在資料夾；若暫時找不到，至少監看 BASE_DIR
    bfile = pick_latest_plan_file()
    if bfile:
        add_watch(bfile)
    else:
        add_watch(os.path.join(BASE_DIR, "dummy.txt"))

    _observer.start()
    log("監看啟動完成")

def stop_watch():
    global _observer
    if _observer:
        _observer.stop()
        _observer.join(timeout=5)
        _observer = None
        log("監看已停止")

# ====== 主程式 ======
def main():
    try:
        os.makedirs(APP_DIR, exist_ok=True)
    except Exception:
        pass

    initial_sync_and_prepare_db()
    start_watch()

    def _graceful(sig, frm):
        global _shutdown_flag
        if _shutdown_flag:
            return
        _shutdown_flag = True
        log(f"收到結束信號：{sig}")
        stop_watch()
        final_sync_before_exit()
        raise SystemExit(0)

    for s in (signal.SIGINT, signal.SIGTERM, signal.SIGBREAK if hasattr(signal, "SIGBREAK") else signal.SIGTERM):
        try:
            signal.signal(s, _graceful)
        except Exception:
            pass

    try:
        while not _shutdown_flag:
            time.sleep(1)
    except KeyboardInterrupt:
        _graceful(signal.SIGINT, None)

if __name__ == "__main__":
    log("Excel↔SQLite 同步服務啟動")
    log(f"DB 路徑：{DB_PATH}")
    main()
