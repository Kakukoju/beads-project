import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", r"D:\配藥表\資料庫\P01_formualte_schedule.db")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 1️⃣ 取得所有 table
cur.execute("""
SELECT name
FROM sqlite_master
WHERE type='table'
AND name NOT LIKE 'sqlite_%'
""")

tables = [row[0] for row in cur.fetchall()]

found_tables = []

# 2️⃣ 逐 table 檢查 NABU 是否存在
for table in tables:
    try:
        sql = f'''
        SELECT EXISTS (
            SELECT 1
            FROM "{table}"
            WHERE Unit = ? COLLATE NOCASE
        )
        '''
        cur.execute(sql, ("QNa-BU",))
        exists = cur.fetchone()[0]

        if exists:
            found_tables.append(table)

    except sqlite3.OperationalError:
        # 該 table 沒有 Unit 欄位，直接略過
        pass

conn.close()

print("NABU 存在於以下 tables：")
for t in found_tables:
    print(" -", t)
