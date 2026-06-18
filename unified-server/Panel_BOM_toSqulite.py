import pandas as pd
import sqlite3
import os

# ====================================================================
# *** 設定參數 ***
# ====================================================================
FILE_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\Panel 明細.xlsx"
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\beads_sync.db"
TABLE_NAME = "BOM_Details"
# 修正: 資料內容從第 1 行開始 (0-based index: 0)
DATA_START_ROW = 0 
COMPONENT_START_COL = 3 # D 欄的索引是 3 (0=A, 1=B, 2=C, 3=D)
# ====================================================================

def normalize_excel_data_merged(file_path, data_start_row):
    """
    讀取 Excel 文件，處理 C 欄的合併儲存格結構，並將其正規化為 BOM 格式。
    
    Args:
        file_path (str): Excel 文件路徑。
        data_start_row (int): 實際資料內容起始行 (0-based index)。
        
    Returns:
        pd.DataFrame: 正規化後的資料。
    """
    print(f"正在讀取檔案: {file_path}...")
    
    try:
        # 關鍵修正: skiprows=data_start_row (0) 意味著從第一行開始讀取
        # header=None 意味著不將任何行視為標題
        df = pd.read_excel(file_path, header=None, skiprows=data_start_row)
    except Exception as e:
        print(f"讀取 Excel 檔案失敗，請確保檔案存在且未被開啟。錯誤: {e}")
        return pd.DataFrame()

    # 刪除所有完全為空（NaN）的行，避免處理到不必要的空白區域
    df_data = df.dropna(axis=0, how='all').copy()
    df_data.reset_index(drop=True, inplace=True) 

    # 1. 處理 C 欄的合併儲存格：使用向前填充 (ffill)
    # 假設 C 欄 (索引 2) 的值只出現在合併範圍的第一行
    df_data[2].fillna(method='ffill', inplace=True) 
    
    normalized_data = []
    
    # 2. 遍歷數據並組合
    CHUNK_SIZE = 3 
    
    for i in range(0, len(df_data), CHUNK_SIZE):
        
        chunk = df_data.iloc[i:i + CHUNK_SIZE]
        if chunk.empty:
            continue
        
        # 檢查半品料號行（第一行，從 D 欄開始）是否有效
        component_row = chunk.iloc[0, COMPONENT_START_COL:]
        if component_row.dropna().empty:
            continue
            
        # 提取這一組半品清單對應的 成品料號 (Column A, 索引 0)
        # 取這 3 行 A 欄中所有不重複且非空的值。
        finished_parts = df_data.iloc[i:i + CHUNK_SIZE, 0].dropna().unique()

        if len(finished_parts) == 0:
            # 這一組沒有對應的成品料號，跳過
            continue
            
        # 半成品的三行數據
        comp_nos = chunk.iloc[0, COMPONENT_START_COL:]   # 料號 (D1, E1, F1...)
        comp_names = chunk.iloc[1, COMPONENT_START_COL:] # 名稱 (D2, E2, F2...)
        quantities = chunk.iloc[2, COMPONENT_START_COL:] # 數量 (D3, E3, F3...)

        # 3. 交叉組合 (Finished_PartNo X Component_Detail)
        for part_no in finished_parts:
            # 遍歷所有的半成品欄位
            for j in range(len(comp_nos)):
                comp_no = comp_nos.iloc[j]
                comp_name = comp_names.iloc[j]
                quantity = quantities.iloc[j]
                
                # 只有當半成品料號存在且數量有效時，才視為有效配方
                if pd.notna(comp_no) and pd.notna(quantity):
                    try:
                        qty_float = float(quantity)
                    except ValueError:
                        # 處理數量不是數字的情況，將其設為 0.0
                        qty_float = 0.0
                        
                    if qty_float != 0.0:
                         normalized_data.append({
                            'Finished_PartNo': str(part_no).strip(),
                            'Component_No': str(comp_no).strip(),
                            'Component_Name': str(comp_name).strip() if pd.notna(comp_name) else '',
                            'Quantity': qty_float,
                        })

    return pd.DataFrame(normalized_data)


def import_to_sqlite(df, db_path, table_name):
    """
    將 DataFrame 匯入指定的 SQLite 資料庫。
    """
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir)
            print(f"已創建資料庫目錄: {db_dir}")
        except OSError as e:
            print(f"警告: 無法創建網路路徑目錄 {db_dir}。請確保路徑有效。錯誤: {e}")
        
    conn = None
    try:
        print(f"正在連接資料庫: {db_path}...")
        conn = sqlite3.connect(db_path)
        
        # if_exists='replace' 會刪除舊表並建立新表
        df.to_sql(table_name, conn, if_exists='replace', index=False)
        
        print(f"成功匯入 {len(df)} 條記錄到資料表 '{table_name}'。")

    except sqlite3.Error as e:
        print(f"SQLite 資料庫操作失敗，請檢查網路連接及權限。錯誤: {e}")
    except Exception as e:
        print(f"發生一般錯誤: {e}")
    finally:
        if conn:
            conn.close()


# --- 主程式執行區 ---
if __name__ == "__main__":
    
    # 1. 正規化資料
    normalized_df = normalize_excel_data_merged(FILE_PATH, DATA_START_ROW)
    
    if not normalized_df.empty:
        print("\n資料正規化成功 (前 5 筆):")
        print(normalized_df.head())
        
        # 2. 匯入 SQLite
        import_to_sqlite(normalized_df, DB_PATH, TABLE_NAME)
    else:
        print("\n沒有有效的資料可以匯入。")