import sqlite3
import os

# ================= 設定路徑 =================
# 請確保這兩個檔案都在同一個資料夾，或是修改為絕對路徑
TARGET_DB = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"       # 目標 (要匯入到的主資料庫)
SOURCE_DB = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders_test.db"  # 來源 (測試資料庫)

def merge_databases_fixed():
    # 1. 檢查檔案是否存在
    if not os.path.exists(TARGET_DB):
        print(f"❌ 找不到目標資料庫: {TARGET_DB}")
        return
    if not os.path.exists(SOURCE_DB):
        print(f"❌ 找不到來源資料庫: {SOURCE_DB}")
        return

    try:
        conn = sqlite3.connect(TARGET_DB)
        cursor = conn.cursor()

        # 2. 將來源資料庫 "掛載" (Attach)
        cursor.execute(f"ATTACH DATABASE '{SOURCE_DB}' AS source_db")

        # 3. 自動抓取來源資料庫的欄位名稱 (避免手動輸入錯誤)
        # 這樣會自動取得除了 id 和 最後一欄以外的所有欄位
        cursor.execute("PRAGMA source_db.table_info(work_orders)")
        src_columns_info = cursor.fetchall()
        
        # 取出所有欄位名稱 (如: '工單號', '製令數量'...)
        # 來源資料庫少 id 和最後一欄，所以這些欄位剛好能對應到目標資料庫的中間部分
        src_columns = [col[1] for col in src_columns_info]
        
        # 組合 SQL 欄位字串 (例如: "工單號", "製令數量", ...)
        cols_string = ", ".join([f'"{col}"' for col in src_columns])
        
        print(f"🔄 偵測到 {len(src_columns)} 個欄位，開始匯入...")

        # 4. 執行匯入
        # 指定插入這些欄位，目標資料庫的 'id' 會自動遞增，'滴定機閒置時間(hrs)' 會留空
        merge_sql = f"""
        INSERT INTO main.work_orders ({cols_string})
        SELECT {cols_string} 
        FROM source_db.work_orders AS src
        WHERE NOT EXISTS (
            SELECT 1 FROM main.work_orders AS dest 
            WHERE dest.工單號 = src.工單號
        );
        """
        
        cursor.execute(merge_sql)
        inserted_count = cursor.rowcount
        conn.commit()
        
        print("="*30)
        if inserted_count > 0:
            print(f"✅ 匯入成功！共新增了 {inserted_count} 筆資料。")
        else:
            print("💡 提示：沒有新增資料 (工單都已存在)。")
        print("="*30)

    except sqlite3.Error as e:
        print(f"❌ 資料庫錯誤: {e}")
    except Exception as e:
        print(f"❌ 發生未預期錯誤: {e}")
    finally:
        if conn:
            try:
                cursor.execute("DETACH DATABASE source_db")
            except:
                pass
            conn.close()
            print("🔌 資料庫連線已關閉")

if __name__ == "__main__":
    merge_databases_fixed()