import sqlite3
from pathlib import Path
import datetime

DB_PATH = r"C:\Users\harryhrguo\WebApp\dropfreeze\work_orders.db"

def create_table_if_not_exists():
    """
    如果 work_orders 表不存在，則建立它。
    這對於第一次運行或確保表結構正確很有用。
    請確保這裡的欄位名稱和順序與您在 Streamlit 應用中查詢的 col1 到 col39 一致。
    這裡僅為範例，您可能需要根據實際資料類型調整。
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS work_orders (
                col1 TEXT,  -- 工單號
                col2 TEXT,  -- 製令數量
                col3 TEXT,  -- bead_name
                col4 TEXT,  -- PN
                col5 TEXT,  -- 是否懸浮
                col6 TEXT,  -- 日期
                col7 TEXT,  -- L1反應OD
                col8 TEXT,  -- L1起始OD
                col9 TEXT,  -- L2反應OD
                col10 TEXT, -- L2起始OD
                col11 TEXT, -- liquid_storge_避光
                col12 TEXT, -- liquid_storge_冰浴
                col13 TEXT, -- 滴定_避光
                col14 TEXT, -- 滴定_冰浴
                col15 TEXT, -- 滴定_攪拌
                col16 TEXT, -- Dispense_Lot_1
                col17 TEXT, -- port_1
                col18 TEXT, -- pump_1
                col19 TEXT, -- 凍乾機_1
                col20 TEXT, -- Dispense_Lot_2
                col21 TEXT, -- port_2
                col22 TEXT, -- pump_2
                col23 TEXT, -- 凍乾機_2
                col24 TEXT, -- Dispense_Lot_3
                col25 TEXT, -- port_3
                col26 TEXT, -- pump_3
                col27 TEXT, -- 凍乾機_3
                col28 TEXT, -- Dispense_Lot_4
                col29 TEXT, -- port_4
                col30 TEXT, -- pump_4
                col31 TEXT, -- 凍乾機_4
                col32 TEXT, -- 淨重g
                col33 TEXT, -- 時間_收藥
                col34 TEXT, -- 時間_滴定準備開始
                col35 TEXT, -- 時間_滴定開始
                col36 TEXT, -- 時間_滴定結束
                col37 TEXT, -- 時間_凍乾準備開始
                col38 TEXT, -- 時間_凍乾開始
                col39 TEXT  -- 時間_凍乾結束
            )
        """)
        conn.commit()
        print("work_orders 表已檢查/建立。")
    except sqlite3.Error as e:
        print(f"建立資料庫表時發生錯誤: {e}")
    finally:
        if conn:
            conn.close()

def insert_work_order(data):
    """
    將新的工單資料插入 work_orders 表。
    參數 data 應該是一個包含 39 個元素的列表，對應 col1 到 col39。
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 準備插入語句
        # 由於有 39 個欄位，我們用 '?' 作為佔位符
        placeholders = ', '.join(['?'] * len(data))
        insert_query = f"INSERT INTO work_orders VALUES ({placeholders})"
        
        cursor.execute(insert_query, data)
        conn.commit()
        print(f"資料成功插入: 工單號 {data[0]}")
    except sqlite3.Error as e:
        print(f"插入資料時發生錯誤: {e}")
    finally:
        if conn:
            conn.close()

def get_all_work_orders():
    """
    從資料庫中讀取所有工單資料並列印。
    用於驗證資料是否成功插入。
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM work_orders")
        rows = cursor.fetchall()
        if not rows:
            print("資料庫中沒有工單資料。")
            return
        
        # 獲取欄位名稱 (從 PRAGMA table_info 獲取原始欄位名)
        cursor.execute("PRAGMA table_info(work_orders)")
        cols = [col[1] for col in cursor.fetchall()] # col[1] 是欄位名稱
        print("\n目前資料庫中的工單資料：")
        print(cols)
        for row in rows:
            print(row)
    except sqlite3.Error as e:
        print(f"讀取資料時發生錯誤: {e}")
    finally:
        if conn:
            conn.close()

# --- 執行範例 ---
if __name__ == "__main__":
    # 確保資料庫表存在
    create_table_if_not_exists()

    # 範例 QR 文字資料（假設從 QR 碼解析得到，並轉換成列表）
    # 這裡的資料順序必須與資料庫的 col1 到 col39 一一對應
    # 您需要根據您的 QR 碼內容和資料庫設計來組織這個列表
    # 假設 col1 是工單號，col6 是日期，col33 是時間_收藥等等
    current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    qr_text_data_example_1 = [
        "TMRB250319",  # col1: 工單號
        "100",              # col2: 製令數量
        "AMY",            # col3: bead_name
        "PN123",            # col4: PN
        "是",               # col5: 是否懸浮
        "2025-06-18",       # col6: 日期
        "", "", "", "",     # col7-10: OD 相關 (初始空值)
        "", "", "", "", "", # col11-15: liquid_storge & 滴定 (初始空值)
        "", "", "", "",     # col16-19: Dispense_Lot_1 相關 (初始空值)
        "", "", "", "",     # col20-23: Dispense_Lot_2 相關 (初始空值)
        "", "", "", "",     # col24-27: Dispense_Lot_3 相關 (初始空值)
        "", "", "", "",     # col28-31: Dispense_Lot_4 相關 (初始空值)
        "",                 # col32: 淨重g (初始空值)
        current_time_str,   # col33: 時間_收藥 (假設這是 QR 碼掃描時更新的欄位)
        "", "", "", "", "", "" # col34-39: 其他時間欄位 (初始空值)
    ]

    ''''qr_text_data_example_2 = [
        "TMRB250218",  # col1: 工單號
        "200",              # col2: 製令數量
        "ALB",            # col3: bead_name
        "PN456",            # col4: PN
        "否",               # col5: 是否懸浮
        "2025-06-18",       # col6: 日期
        "", "", "", "",     # col7-10: OD 相關 (初始空值)
        "", "", "", "", "", # col11-15: liquid_storge & 滴定 (初始空值)
        "", "", "", "",     # col16-19: Dispense_Lot_1 相關 (初始空值)
        "", "", "", "",     # col20-23: Dispense_Lot_2 相關 (初始空值)
        "", "", "", "",     # col24-27: Dispense_Lot_3 相關 (初始空值)
        "", "", "", "",     # col28-31: Dispense_Lot_4 相關 (初始空值)
        "",                 # col32: 淨重g (初始空值)
        current_time_str,   # col33: 時間_收藥 (假設這是 QR 碼掃描時更新的欄位)
        "", "", "", "", "", "" # col34-39: 其他時間欄位 (初始空值)
    ]'''
    
    # 插入第一筆範例資料
    print("--- 插入第一筆資料 ---")
    insert_work_order(qr_text_data_example_1)

    '''# 插入第二筆範例資料
    print("--- 插入第二筆資料 ---")
    insert_work_order(qr_text_data_example_2)'''
    # 檢查資料庫內容
    get_all_work_orders()

    # 範例：更新現有工單的某個時間欄位
    # 假設我們要更新 WO-20250618-001 的 時間_滴定準備開始 (col34)
    def update_work_order_time(order_id, time_col_index, new_time):
        """
        更新特定工單的指定時間欄位。
        time_col_index 是 col1 到 col39 中對應時間欄位的索引 (從 0 開始)。
        """
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # 因為欄位是 col1, col2...col39，所以需要轉換索引
            db_col_name = f"col{time_col_index + 1}"
            
            update_query = f"UPDATE work_orders SET {db_col_name} = ? WHERE col1 = ?"
            cursor.execute(update_query, (new_time, order_id))
            conn.commit()
            print(f"工單 {order_id} 的 {db_col_name} 已更新為 {new_time}")
        except sqlite3.Error as e:
            print(f"更新資料時發生錯誤: {e}")
        finally:
            if conn:
                conn.close()

    print("\n--- 更新工單資料 ---")
    # 假設 '時間_滴定準備開始' 對應 col34，其索引是 33 (col1 是索引 0)
    update_work_order_time("WO-20250618-001", 33, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # 再次檢查資料庫內容以確認更新
    get_all_work_orders()
