import sqlite3
import os
from datetime import datetime

# 請確認這是您的正確路徑
DB_PATH = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Beads_QC\資料庫\P01_Beads_IPQC.db"

def test_connection():
    print(f"1. 檢查路徑: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("❌ 錯誤：找不到資料庫檔案！請確認路徑。")
        return

    print("✅ 資料庫檔案存在。")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 2. 列出所有 Table
        print("\n2. 列出資料庫中的 Tables:")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"   找到的 Tables: {tables}")

        # 3. 測試當年度 Table
        current_year = datetime.now().year
        target_table = f"{current_year}_IPQC"
        print(f"\n3. 檢查目標 Table: {target_table}")

        if target_table not in tables:
            print(f"❌ 警告：找不到 {target_table}！ (可能只有去年的資料?)")
            # 嘗試找最新的年份
            ipqc_tables = [t for t in tables if '_IPQC' in t]
            if ipqc_tables:
                print(f"   💡 建議：改用 {sorted(ipqc_tables)[-1]} 進行測試")
        else:
            print(f"✅ 找到 {target_table}，檢查欄位...")
            cursor.execute(f'PRAGMA table_info("{target_table}")')
            columns = [row[1] for row in cursor.fetchall()]
            print(f"   欄位清單: {columns}")

            # 檢查關鍵欄位
            required = ["dD生產日", "最終判定"]
            for r in required:
                if r in columns:
                    print(f"   ✅ 欄位 '{r}' 存在")
                else:
                    print(f"   ❌ 錯誤：找不到欄位 '{r}'！請確認拼字。")

    except Exception as e:
        print(f"\n❌ 資料庫讀取發生例外錯誤: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    test_connection()