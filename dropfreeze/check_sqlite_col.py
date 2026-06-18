import sqlite3

conn = sqlite3.connect("work_orders.db")
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(work_orders);")
columns = cursor.fetchall()
for col in columns:
    print(col)
conn.close()
