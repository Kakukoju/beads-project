import sqlite3

keyword = "TMRA25L050"
db = "D:\配藥表\資料庫\P01_formualte_schedule.db"

conn = sqlite3.connect(db)
cursor = conn.cursor()

# 找出所有 table 名稱
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]

for table in tables:
    # 找欄位
    cursor.execute(f"PRAGMA table_info('{table}')")
    columns = [col[1] for col in cursor.fetchall()]

    # 為文字欄位建立 LIKE 查詢
    conditions = " OR ".join([f"{col} LIKE '%{keyword}%'" for col in columns])

    query = f"SELECT '{table}' AS table_name, * FROM '{table}' WHERE {conditions}"
    
    try:
        cursor.execute(query)
        rows = cursor.fetchall()
        if rows:
            print(f"\n=== Found in table: {table} ===")
            for r in rows:
                print(r)

    except Exception:
        pass

conn.close()
