# -*- coding: utf-8 -*-
"""
beads_sync_manager.py

功能：
1. 提供 Beads IPQC Excel 與 SQLite 之間的同步邏輯。
2. 可單獨執行 (Standalone)：作為背景服務執行。
3. 可被匯入 (Importable)：供 Flask 或其他主程式呼叫啟動。
"""

import os
import re
import time
import sqlite3
import hashlib
import logging
import pandas as pd
from datetime import datetime
from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

# =============================
# 預設配置 (Default Config)
# =============================
DEFAULT_CONFIG = {
    "WATCH_DIR": r"\\fls341\MBBU_FAB\MB_QA\Dora\2.Disk A",
    "TARGET_SHEET": "P01 Beads總表",
    "DB_PATH": r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Beads_QC\資料庫\P01_Beads_IPQC.db",
    "LOG_FILE": "daily_sync.log",
    "IDENTITY_COLS": ['Maker', '季', '月', 'Weekly']
}

PRIMARY_KEY_COL = "rowhash"
DEBOUNCE_SECONDS = 2.0

# 建立 Module 級別的 Logger (不設定 Handler，交由主程式決定)
logger = logging.getLogger("BeadsSync")

# =============================
# Helper Functions
# =============================

def setup_logging(log_file=None):
    """
    配置 Logging。
    如果是被 import 使用，主程式通常會自己設定 logging，可以不呼叫此函數。
    如果是單獨執行，則呼叫此函數來設定輸出。
    """
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding='utf-8', mode='a'))
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers,
        force=True # 強制覆蓋現有設定
    )

def sanitize_column_name(col, idx=None):
    if col is None or str(col).strip() == "":
        return f"col_{idx:02d}"
    col = str(col).strip()
    col = re.sub(r'[^0-9A-Za-z_\u4e00-\u9fa5]', "", col)
    if re.match(r"^[0-9]", col):
        col = "c_" + col
    return col

def make_unique_columns_case_insensitive(columns):
    seen_lower = {}
    result = []
    for col in columns:
        col_lower = col.lower()
        if col_lower not in seen_lower:
            seen_lower[col_lower] = 1
            result.append(col)
        else:
            seen_lower[col_lower] += 1
            new_col = f"{col}_{seen_lower[col_lower]}"
            result.append(new_col)
    return result

def make_rowhash(row):
    text = "|".join([str(v) for v in row.values])
    return hashlib.sha1(text.encode("utf-8")).hexdigest()

def clean_dataframe_dates(df):
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime('%Y-%m-%d').fillna('')
    return df

# =============================
# 資料庫邏輯
# =============================

def ensure_table(conn, year, df):
    table = f"{year}_IPQC"
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    table_exists = cur.fetchone() is not None
    
    if table_exists:
        cur = conn.execute(f'PRAGMA table_info("{table}")')
        db_columns = {row[1] for row in cur.fetchall()}
        excel_columns = set(df.columns)
        
        if db_columns != excel_columns:
            logger.warning(f"⚠️ 結構變更！重建資料表 '{table}'")
            conn.execute(f'DROP TABLE "{table}"')
            return ensure_table(conn, year, df)
        else:
            return table
    
    logger.info(f"🆕 建立新資料表：{table}")
    data_columns = [c for c in df.columns if c != PRIMARY_KEY_COL]
    cols = ", ".join([f'"{c}" TEXT' for c in data_columns])
    conn.execute(f'CREATE TABLE "{table}" ("{PRIMARY_KEY_COL}" TEXT PRIMARY KEY, {cols})')
    conn.commit()
    return table

def sync_with_smart_logging(conn, table, df, identity_cols):
    df = df.fillna("")
    excel_hashes = set(df[PRIMARY_KEY_COL].tolist())
    
    cur = conn.execute(f'SELECT * FROM "{table}"')
    db_rows = cur.fetchall()
    
    cur = conn.execute(f'PRAGMA table_info("{table}")')
    db_columns = [row[1] for row in cur.fetchall()]
    
    db_hashes = {row[0] for row in db_rows}
    db_data = {row[0]: dict(zip(db_columns, row)) for row in db_rows}
    
    to_delete = db_hashes - excel_hashes
    to_insert = excel_hashes - db_hashes
    
    logger.info(f"🔄 智能同步... (待增:{len(to_insert)}, 待刪:{len(to_delete)})")
    
    # 決定識別用的 Key
    available_id_cols = [c for c in identity_cols if c in df.columns]
    key_columns = available_id_cols if len(available_id_cols) == len(identity_cols) else [c for c in df.columns if c != PRIMARY_KEY_COL][:3]

    # 修改判斷邏輯
    likely_updates = []
    if to_delete and to_insert:
        insert_map = {}
        for hash_val in to_insert:
            row = df[df[PRIMARY_KEY_COL] == hash_val].iloc[0]
            key_tuple = tuple(str(row[c]) for c in key_columns)
            insert_map[key_tuple] = {'hash': hash_val, 'values': list(row.values)}
        
        for del_hash in list(to_delete):
            if del_hash not in db_data: continue
            del_row = db_data[del_hash]
            del_key_tuple = tuple(str(del_row.get(c, "")) for c in key_columns)
            
            if del_key_tuple in insert_map:
                ins_info = insert_map[del_key_tuple]
                preview_str = " + ".join([f"{k}:{v}" for k, v in zip(key_columns, del_key_tuple)])
                likely_updates.append({
                    'old_hash': del_hash,
                    'new_hash': ins_info['hash'],
                    'preview': preview_str,
                    'new_values': ins_info['values']
                })
                to_delete.discard(del_hash)
                to_insert.discard(ins_info['hash'])
                del insert_map[del_key_tuple]

    # 執行 SQL
    if likely_updates:
        logger.info(f"↻ 修改 {len(likely_updates)} 筆")
        for update in likely_updates:
            conn.execute(f'DELETE FROM "{table}" WHERE "{PRIMARY_KEY_COL}"=?', (update['old_hash'],))
            cols = ", ".join([f'"{c}"' for c in df.columns])
            qmarks = ",".join(["?"] * len(df.columns))
            conn.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({qmarks})', update['new_values'])

    if to_insert:
        logger.info(f"✚ 新增 {len(to_insert)} 筆")
        for hash_val in to_insert:
            row = df[df[PRIMARY_KEY_COL] == hash_val].iloc[0]
            cols = ", ".join([f'"{c}"' for c in df.columns])
            qmarks = ",".join(["?"] * len(df.columns))
            conn.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({qmarks})', list(row.values))

    if to_delete:
        logger.info(f"✖ 刪除 {len(to_delete)} 筆")
        for hash_val in to_delete:
            conn.execute(f'DELETE FROM "{table}" WHERE "{PRIMARY_KEY_COL}"=?', (hash_val,))

    conn.commit()
    logger.info("✅ 同步完成")
    return len(to_insert), len(likely_updates)

# =============================
# 同步執行入口
# =============================

def sync_excel_to_db(excel_path, config=DEFAULT_CONFIG):
    """
    主要的同步邏輯函數。
    :param excel_path: Excel 檔案路徑
    :param config: 設定字典 (包含 DB_PATH, TARGET_SHEET 等)
    """
    db_path = config.get("DB_PATH", DEFAULT_CONFIG["DB_PATH"])
    target_sheet = config.get("TARGET_SHEET", DEFAULT_CONFIG["TARGET_SHEET"])
    identity_cols = config.get("IDENTITY_COLS", DEFAULT_CONFIG["IDENTITY_COLS"])

    try:
        logger.info(f"{'='*50}")
        logger.info(f"📌 觸發同步：{os.path.basename(excel_path)}")

        fname = os.path.basename(excel_path)
        year = fname[:4]

        # 讀取 Excel
        logger.info("[1/7] 讀取 Excel...")
        try:
            df = pd.read_excel(excel_path, sheet_name=target_sheet)
        except ValueError as ve:
             logger.warning(f"⚠️ 找不到 Sheet: {target_sheet}，跳過此檔案。")
             return

        # 基礎處理
        df = df.iloc[:, 1:] # 排除 A 欄
        # 過濾前幾欄都為空的行
        df = df.dropna(subset=df.columns[1:5], how='all').reset_index(drop=True)
        
        # 欄名處理
        cols_new = [sanitize_column_name(col, i) for i, col in enumerate(df.columns, 1)]
        df.columns = make_unique_columns_case_insensitive(cols_new)
        
        # 日期與格式
        df = clean_dataframe_dates(df)
        df = df.astype(str).replace("nan", "")
        
        # Rowhash
        df[PRIMARY_KEY_COL] = df.apply(make_rowhash, axis=1)
        df = df.drop_duplicates(subset=[PRIMARY_KEY_COL], keep='first')
        
        # 寫入 DB
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(db_path)
        table = ensure_table(conn, year, df)
        sync_with_smart_logging(conn, table, df, identity_cols)
        conn.close()
        
    except Exception as e:
        logger.error(f"❌ 同步失敗：{e}")
        import traceback
        logger.error(traceback.format_exc())

# =============================
# Watchdog Handler 與 啟動器
# =============================

class IPQCHandler(FileSystemEventHandler):
    def __init__(self, config):
        self.config = config
        self.last_trigger_time = 0

    def _should_sync(self, file_path):
        fname = os.path.basename(file_path)
        if fname.startswith('~$') or fname.endswith('.tmp'): return False
        if "Beads IPQC" not in fname: return False
        if not fname.endswith(('.xlsx', '.xls')): return False
        return True
    
    def _try_sync(self, file_path):
        if not self._should_sync(file_path): return
        
        now = time.time()
        if now - self.last_trigger_time < DEBOUNCE_SECONDS:
            return
        
        self.last_trigger_time = now
        sync_excel_to_db(file_path, self.config)

    def on_modified(self, event):
        if not event.is_directory: self._try_sync(event.src_path)
    def on_created(self, event):
        if not event.is_directory: self._try_sync(event.src_path)
    def on_moved(self, event):
        if not event.is_directory: self._try_sync(event.dest_path)

def start_monitoring(config=None):
    """
    啟動監控服務 (API 入口)。
    
    Args:
        config (dict): 自定義配置，若為 None 則使用 DEFAULT_CONFIG
        
    Returns:
        observer: Watchdog observer 物件 (需由呼叫者管理，如 observer.stop())
    """
    final_config = DEFAULT_CONFIG.copy()
    if config:
        final_config.update(config)

    watch_dir = final_config["WATCH_DIR"]
    
    if not os.path.exists(watch_dir):
        logger.error(f"❌ 找不到監控資料夾：{watch_dir}")
        return None

    # 初始掃描
    logger.info(f"📂 執行初始掃描: {watch_dir}")
    try:
        excel_files = [f for f in os.listdir(watch_dir) 
                       if "Beads IPQC" in f and f.endswith(('.xlsx', '.xls')) and not f.startswith('~$')]
        for f in excel_files:
            sync_excel_to_db(os.path.join(watch_dir, f), final_config)
    except Exception as e:
        logger.error(f"❌ 初始掃描失敗: {e}")

    # 啟動 Watchdog
    logger.info("📡 啟動 Watchdog 監控...")
    handler = IPQCHandler(final_config)
    observer = PollingObserver(timeout=1.0)
    observer.schedule(handler, watch_dir, recursive=False)
    observer.start()
    return observer

# =============================
# Standalone Execution (單獨執行)
# =============================

if __name__ == "__main__":
    # 只有在單獨執行時，才配置全域 Logging 和進入無限迴圈
    setup_logging(DEFAULT_CONFIG["LOG_FILE"])
    
    print("=" * 70)
    print("📡 IPQC Sync Service (Standalone)")
    print("=" * 70)

    observer = start_monitoring()
    
    if observer:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("⏹️ 停止監控")
            observer.stop()
            observer.join()