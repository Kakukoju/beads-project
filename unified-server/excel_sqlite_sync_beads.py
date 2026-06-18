# -*- coding: utf-8 -*-
import os, re, time, signal, threading, sqlite3
from datetime import datetime, date
from typing import Optional, Tuple, List

import pandas as pd
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from pandas.api.types import is_datetime64_any_dtype as is_datetime
import datetime as dt
import pandas as pd


# ====== 固定設定（依你的要求） ======
BASE_DIR = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定"
FILE_A = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\★2024-最新版【勿動】-BEADS庫存-20241126.xlsm"
# B 檔是「Production plan-YYYYMMDD.xlsm」多檔，需挑選 <= 今天且最接近今天者
FILE_B_PATTERN = os.path.join(BASE_DIR, "Production plan-*.xlsm")

# A 檔：sheet/表頭/資料範圍規則
A_SHEET = "BEADS庫存表(202405~"    # 你給的是中文同名檔；此處為 sheet 名，請與實際一致
A_HEADER_ROW = 5                   # 表頭在第 5 列（1-based）
A_DATA_START_ROW = 6               # 資料從第 6 列起
A_DATA_LAST_COL = "O"              # A:O
A_LASTROW_BY_COL = "B"             # 用 B 欄來決定最後列
A_TABLE = "beads_Inventory"             # SQLite 表名
A_KEYS = ["PN", "Batch"]           # 主鍵：PN + Batch（請確保與表頭欄名一致，區分大小寫）

# B 檔：sheet/表頭/資料範圍規則
B_SHEET = "P_plan Reagent"
B_HEADER_ROW = 2                   # 表頭在第 2 列
B_DATA_START_ROW = 3               # 資料從第 3 列
B_DATA_LAST_COL = "PQ"             # A:PQ
B_LASTROW_BY_COL = "B"             # 用 B 欄來決定最後列
B_TABLE = "production_Plan"                   # SQLite 表名
B_KEYS = ["PN"]                    # 主鍵：PN（請確保與表頭欄名一致）

# DB 與執行資料夾
APP_DIR = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Bead_auto_update_schedule"
# === DB 路徑 ===
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\beads_sync.db"

# 其他
DEBOUNCE_SECONDS = 2.0
READ_RETRY = 4
READ_RETRY_SLEEP = 0.6

# ====== 內部狀態 ======
_shutdown_flag = False
_db_lock = threading.Lock()
_last_event_ts = {}
_observer: Optional [Observer] = None
_watched_files: set = set()


# ====== 小工具 ======
def log(msg: str):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}")

def col_to_index(col: str) -> int:
    # Excel 欄位字母轉 1-based 索引
    col = col.upper()
    s = 0
    for ch in col:
        s = s * 26 + (ord(ch) - 64)
    return s

def pick_latest_plan_file() -> Optional[str]:
    """從 FILE_B_PATTERN 中挑選 <= 今天且最接近今天的 Production plan-YYYYMMDD.xlsm"""
    files = []
    today = date.today()
    rx = re.compile(r"Production plan-(\d{8})\.xlsm$", re.IGNORECASE)
    base = os.path.dirname(FILE_B_PATTERN)
    for name in os.listdir(base):
        m = rx.match(name)
        if not m:
            continue
        ymd = m.group(1)
        try:
            d = datetime.strptime(ymd, "%Y%m%d").date()
        except:
            continue
        if d <= today:
            files.append((d, os.path.join(base, name)))
    if not files:
        return None
    files.sort(key=lambda x: (today - x[0]))  # 差距最小者優先
    return files[0][1]

def read_range_df(
    xl_path: str, sheet: str, header_row: int, data_start_row: int,
    last_col_letter: str, lastrow_by_col_letter: str
) -> pd.DataFrame:
    """
    讀取指定範圍：表頭列 = header_row；資料從 data_start_row 到由「lastrow_by_col」決定的最後列；
    欄位 A 到 last_col_letter。自動去除全空白列，NaN -> ""。
    """
    # 先用 openpyxl 引擎讀整表，再切片
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

    # 計算最後列（用 B 欄或指定欄的非空到哪一列）
    last_col_idx = col_to_index(last_col_letter)
    lastrow_col_idx = col_to_index(lastrow_by_col_letter)

    # 確保欄數足夠
    if df.shape[1] < last_col_idx:
        # 若實際欄位少於指定最後欄，截不到；這時就以實際欄位為準
        last_col_idx = df.shape[1]

    # DataFrame 的列是以 header_row 為 0 列起算，所以要扣掉
    # 原始 Excel 資料列 index（1-based）= header_row + df.index_offset
    # 我們要 data_start_row ~ last_row
    # 先找 B 欄（或指定欄）在 df 中的第 N 欄：DataFrame 的欄位是標題名，不是字母
    # 但你給的最後列規則是以「B 欄非空」，比較穩的方式：直接從原檔再讀一次該欄，這裡用 df.iloc 的第 1 欄等價處理。
    # 假設原表頭與實際顯示一致，我們以第 (lastrow_col_idx-1) 欄判空。
    target_col_pos = lastrow_col_idx - 1
    target_col_pos = min(target_col_pos, df.shape[1] - 1)

    # 資料起始在 data_start_row，換算成 df 的 iloc 起點：
    iloc_start = data_start_row - header_row - 1
    iloc_start = max(iloc_start, 0)

    # 找最後非空列（以 target_col_pos）
    sub = df.iloc[iloc_start:, :]
    nonempty = sub.iloc[:, target_col_pos].astype(str).str.strip() != ""
    if not nonempty.any():
        # 沒有任何資料
        df2 = df.iloc[0:0, :last_col_idx]
        return df2.fillna("")

    # 最後一個非空的相對位置
    last_rel_idx = nonempty[nonempty].index[-1]
    iloc_end = df.index.get_loc(last_rel_idx) + 1  # iloc 結尾是「不含」
    # 只取 A ~ last_col_idx
    df2 = df.iloc[iloc_start:iloc_end, :last_col_idx].copy()

        # 清洗
    df2.columns = [str(c).replace("\n", " ").strip() for c in df2.columns]
    df2 = df2.dropna(how="all").fillna("")

    # ★ 新增：日期/時間轉字串（YYYY-MM-DD），避免 sqlite 綁定錯誤
    df2 = normalize_df_for_sqlite(df2)

    return df2


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


def ensure_table_and_columns(conn: sqlite3.Connection, table: str, df: pd.DataFrame):
    cols = [f'"{c}" TEXT' for c in df.columns]
    with conn:
        conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(cols)});')
        # 補欄
        cur = conn.execute(f'PRAGMA table_info("{table}")')
        existing = {row[1] for row in cur.fetchall()}
        for c in df.columns:
            if c not in existing:
                conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{c}" TEXT;')

def ensure_unique_index(conn: sqlite3.Connection, table: str, keys: List[str]):
    if not keys:
        return
    idx_name = f'ux_{table}_' + "_".join([k.lower() for k in keys])
    cols = ",".join([f'"{k}"' for k in keys])
    with conn:
        conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "{idx_name}" ON "{table}" ({cols});')

def upsert(conn: sqlite3.Connection, table: str, df: pd.DataFrame, keys: List[str]):
    ensure_table_and_columns(conn, table, df)
    ensure_unique_index(conn, table, keys)

    cols = list(df.columns)
    col_list = ", ".join([f'"{c}"' for c in cols])
    placeholders = ", ".join(["?"] * len(cols))
    nonkeys = [c for c in cols if c not in keys]
    set_clause = ", ".join([f'"{c}"=excluded."{c}"' for c in nonkeys]) if nonkeys else "/* no update */"
    conflict = ", ".join([f'"{k}"' for k in keys])

    sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ' \
          f'ON CONFLICT ({conflict}) DO UPDATE SET {set_clause};'

    with conn:
        conn.executemany(sql, df.itertuples(index=False, name=None))

def sync_A():
    with _db_lock:
        log("同步 A 檔開始")
        df = read_range_df(
            FILE_A, A_SHEET, A_HEADER_ROW, A_DATA_START_ROW,
            A_DATA_LAST_COL, A_LASTROW_BY_COL
        )
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
        df = read_range_df(
            file_b, B_SHEET, B_HEADER_ROW, B_DATA_START_ROW,
            B_DATA_LAST_COL, B_LASTROW_BY_COL
        )
        with sqlite3.connect(DB_PATH) as conn:
            upsert(conn, B_TABLE, df, B_KEYS)
        log(f"同步 B 檔完成：rows={len(df)}")

def initial_sync_and_prepare_db():
    # 動作一：先檢查 DB 是否存在；無則建立（實際在 upsert 時自動建表/加欄）
    if not os.path.exists(DB_PATH):
        log(f"DB 不存在，將建立：{DB_PATH}")
        open(DB_PATH, "ab").close()

    # 首次同步（A、B 各一次）
    sync_A()
    sync_B()

def final_sync_before_exit():
    # 動作二：關閉前再同步一次
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
        # 防抖
        now = time.time()
        last = _last_event_ts.get(path, 0)
        if now - last < DEBOUNCE_SECONDS:
            return
        _last_event_ts[path] = now

        try:
            # 若是 A 檔變動
            if os.path.abspath(FILE_A).lower() == path.lower():
                log(f"A 檔變更事件：{event.event_type}")
                sync_A()
                return

            # 若是目前選中的 B 檔變動
            current_b = pick_latest_plan_file()
            if current_b and os.path.abspath(current_b).lower() == path.lower():
                log(f"B 檔變更事件：{event.event_type} | {os.path.basename(current_b)}")
                sync_B()
                return

            # 也有可能是新增了新的 B 檔（今天或更接近今天的日期）
            if os.path.dirname(path).lower() == BASE_DIR.lower() and re.search(r"Production plan-\d{8}\.xlsm$", os.path.basename(path), re.I):
                newer_b = pick_latest_plan_file()
                if newer_b:
                    # 如有更接近今天的合法檔，切換監看目標並同步一次
                    if newer_b not in _watched_files:
                        add_watch(newer_b)  # 加入新檔監看
                    log(f"偵測到新的 B 候選檔：{os.path.basename(newer_b)} → 重新同步")
                    sync_B()

        except Exception as e:
            log(f"事件處理錯誤：{e}")

def add_watch(path: str):
    global _observer
    if not _observer:
        return
    abspath = os.path.abspath(path)
    if abspath in _watched_files:
        return
    _observer.schedule(Handler(), os.path.dirname(abspath), recursive=False)
    _watched_files.add(abspath)
    log(f"已監看資料夾：{os.path.dirname(abspath)}  (含檔：{os.path.basename(abspath)})")

def start_watch():
    global _observer
    _observer = Observer()
    _observer.daemon = True

    # 監看 A 檔所在資料夾
    add_watch(FILE_A)

    # 監看當前選中的 B 檔所在資料夾（同 BASE_DIR）
    bfile = pick_latest_plan_file()
    if bfile:
        add_watch(bfile)
    else:
        # 至少監看 BASE_DIR，以便捕捉新 B 檔產生
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
    # 確保執行目錄
    try:
        os.makedirs(APP_DIR, exist_ok=True)
    except Exception:
        pass

    initial_sync_and_prepare_db()
    start_watch()

    # 信號處理：Ctrl+C 或服務結束時做最後一次同步
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

    # 常駐
    try:
        while not _shutdown_flag:
            time.sleep(1)
    except KeyboardInterrupt:
        _graceful(signal.SIGINT, None)

if __name__ == "__main__":
    log("Excel↔SQLite 同步服務啟動")
    log(f"DB 路徑：{DB_PATH}")
    main()
