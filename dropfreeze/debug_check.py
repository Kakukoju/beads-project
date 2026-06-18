# debug_check.py
import os
import sqlite3

# 設定你的路徑
PATHS = [
    {
        "name": "Local DB",
        "path": r"D:\配藥表\資料庫\P01_formualte_schedule.db",
        "keyword": "DropletSchedule"
    },
    {
        "name": "Network DB",
        "path": r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db",
        "keyword": "order"
    }
]

def check_db(target):
    print(f"\n🔍 檢查: {target['name']}")
    path = target['path']
    
    # 1. 檢查檔案是否存在
    if not os.path.exists(path):
        print(f"❌ 錯誤: 找不到檔案！請檢查路徑:\n   {path}")
        return
    print(f"✅ 檔案存在")

    # 2. 嘗試連線並列出所有 Tables
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        
        # 列出所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"ℹ️  資料庫內的所有表: {tables}")

        # 3. 尋找目標表
        target_table = None
        for t in tables:
            if target['keyword'].lower() in t.lower():
                target_table = t
                break
        
        if not target_table:
            print(f"❌ 錯誤: 找不到包含關鍵字 '{target['keyword']}' 的表名")
            return

        print(f"✅ 鎖定目標表: [{target_table}]")

        # 4. 讀取數據特徵
        cursor.execute(f"SELECT count(*), max(rowid) FROM '{target_table}'")
        row = cursor.fetchone()
        print(f"✅ 目前狀態: 筆數={row[0]}, 最後ID={row[1]}")
        
        conn.close()

    except Exception as e:
        print(f"❌ 連線或讀取失敗: {e}")

if __name__ == "__main__":
    print("=== 開始診斷 ===")
    for p in PATHS:
        check_db(p)
    input("\n按 Enter 鍵離開...")