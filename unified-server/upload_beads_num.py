import pandas as pd
import sqlite3
import os

# ====================================================================
# *** 1. 設定參數 ***
# ====================================================================

FILE_PATH = r"D:\auto_schedule\beads_dry_num_1.xlsx" 
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\beads_sync.db"
TABLE_NAME = "Beads_Dry_Count" 
HEADER_ROW = 1 # 0-based index (第 2 行是標題)

# ====================================================================

def load_data_to_sqlite(file_path, db_path, table_name, header_row):
    """
    讀取 Excel 檔案，處理合併儲存格和資料類型，然後上傳到 SQLite 資料庫。
    """
    print(f"正在讀取 Excel 檔案: {file_path}...")
    try:
        df = pd.read_excel(file_path, header=header_row, sheet_name=0)
            
    except FileNotFoundError:
        print(f"錯誤: 找不到檔案 {file_path}。請確保路徑正確。")
        return
    except Exception as e:
        print(f"讀取 Excel 時發生錯誤: {e}")
        print("提示: 您可能需要先安裝 'openpyxl' 函式庫 (pip install openpyxl)")
        return

    # --- 資料清理與轉換 ---
    
    # 1. 刪除所有欄位都為空 (NaN) 的行
    df = df.dropna(how='all')

    # 2. *** [新功能] 處理 '藥名' 的合併儲存格 ***
    if "藥名" in df.columns:
        df["藥名"].ffill(inplace=True)
        print("已處理 '藥名' 欄位的合併儲存格 (向前填充)。")
    else:
        print("警告: 找不到 '藥名' 欄位，請檢查 Excel 第 2 行的標題是否正確。")

    # 3. *** [新功能] 處理 '凍乾數' 為整數 ***
    if "凍乾數" in df.columns:
        # 步驟 a: 先將欄位轉為數字，無法轉換的 (例如文字) 會變為 NaT/NaN
        df["凍乾數"] = pd.to_numeric(df["凍乾數"], errors='coerce')
        
        # 步驟 b: 將數字轉換為 'Int64' (可為空的整數)
        # 1000.0 會變為 1000, NaN 會變為 <NA>
        df["凍乾數"] = df["凍乾數"].astype('Int64')
        print("已將 '凍乾數' 欄位轉換為整數 (Int64)。")
    else:
        print("警告: 找不到 '凍乾數' 欄位，請檢查 Excel 第 2 行的標題是否正確。")

    if df.empty:
        print("錯誤: 讀取後沒有發現任何資料。")
        return

    print(f"\n資料讀取與轉換成功，共 {len(df)} 筆記錄。")
    print("資料前 5 筆預覽:")
    print(df.head())

    # --- 2. 上傳到 SQLite ---
    
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
            print(f"\n已創建資料庫目錄: {db_dir}")
        except OSError as e:
            print(f"警告: 無法創建網路路徑目錄 {db_dir}。請確保路徑有效且有權限。錯誤: {e}")

    conn = None
    try:
        print(f"\n正在連接資料庫: {db_path}...")
        conn = sqlite3.connect(db_path)
        
        print(f"正在上傳資料到資料表: {table_name}...") 
        
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        
        print("\n資料上傳成功！")

    except sqlite3.Error as e:
        print(f"SQLite 資料庫操作失敗，請檢查網路連接及權限。錯誤: {e}")
    except Exception as e:
        print(f"發生一般錯誤: {e}")
    finally:
        if conn:
            conn.close()

# --- 主程式執行區 ---
if __name__ == "__main__":
    load_data_to_sqlite(FILE_PATH, DB_PATH, TABLE_NAME, HEADER_ROW)