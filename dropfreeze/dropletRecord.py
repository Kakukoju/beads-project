import sqlite3
from pathlib import Path

DB_PATH = r"D:\配藥表\資料庫\P01_formualte_schedule.db"
TABLE_NAME = "dropletRrcode"

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

create_table_sql = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    record_date TEXT NOT NULL,

    marker TEXT,
    lyophilizer TEXT,
    quantity INTEGER,

    rd_dose_time TEXT,
    plan_titrate_time TEXT,
    plan_end_time TEXT,

    work_order TEXT,
    lyophilizer_max_qty INTEGER,

    titration_port TEXT,
    syringe TEXT,

    store_expiry TEXT,
    store_temp TEXT,
    store_light_protect TEXT,

    titration_light_protect TEXT,
    titration_stir TEXT,
    titration_ice_bath TEXT,
    titration_volume REAL,

    pump_s1 TEXT,
    pump_y TEXT,
    pump_needle TEXT,

    drug_acquire_time TEXT,
    titration_start_time TEXT,
    titration_end_time TEXT,

    operator TEXT,
    checker TEXT,
    available_lyophilizer TEXT,

    remark TEXT,

    pre_stir TEXT,
    pre_cool_temp TEXT,

    record_time TEXT DEFAULT (datetime('now','localtime')),

    id INTEGER PRIMARY KEY AUTOINCREMENT
);
"""

cursor.execute(create_table_sql)

# 🔑 常用索引（你後面一定會用到）
cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_date ON {TABLE_NAME}(record_date)")
cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_wo ON {TABLE_NAME}(work_order)")
cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_lyo ON {TABLE_NAME}(lyophilizer)")

conn.commit()
conn.close()

print("✅ dropletRrcode table ready (32 columns)")
