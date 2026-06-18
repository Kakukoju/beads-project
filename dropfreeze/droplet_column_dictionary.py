import sqlite3

DB_PATH = r"D:\配藥表\資料庫\P01_formualte_schedule.db"

columns = [
    ("dropletRrcode","record_date","紀錄日期","record_date",1),
    ("dropletRrcode","marker","Marker","marker",2),
    ("dropletRrcode","lyophilizer","凍乾機台","lyophilizer",3),
    ("dropletRrcode","quantity","數量","quantity",4),
    ("dropletRrcode","rd_dose_time","RD給藥時間","rd_dose_time",5),
    ("dropletRrcode","plan_titrate_time","預計滴定時間","plan_titrate_time",6),
    ("dropletRrcode","plan_end_time","預計結束","plan_end_time",7),
    ("dropletRrcode","work_order","工單號碼","work_order",8),
    ("dropletRrcode","lyophilizer_max_qty","凍乾最大數量","lyophilizer_max_qty",9),
    ("dropletRrcode","titration_port","滴定port","titration_port",10),
    ("dropletRrcode","syringe","Syringe","syringe",11),
    ("dropletRrcode","store_expiry","保存條件-期限","store_expiry",12),
    ("dropletRrcode","store_temp","保存條件-溫度","store_temp",13),
    ("dropletRrcode","store_light_protect","保存條件-避光","store_light_protect",14),
    ("dropletRrcode","titration_light_protect","滴定條件-避光","titration_light_protect",15),
    ("dropletRrcode","titration_stir","滴定條件-攪拌","titration_stir",16),
    ("dropletRrcode","titration_ice_bath","滴定條件-冰浴","titration_ice_bath",17),
    ("dropletRrcode","titration_volume","滴定條件-體積","titration_volume",18),
    ("dropletRrcode","pump_s1","Pump 參數-S1","pump_s1",19),
    ("dropletRrcode","pump_y","Pump 參數-y","pump_y",20),
    ("dropletRrcode","pump_needle","Pump 參數-針頭","pump_needle",21),
    ("dropletRrcode","drug_acquire_time","藥劑取得時間","drug_acquire_time",22),
    ("dropletRrcode","titration_start_time","滴定開始時間","titration_start_time",23),
    ("dropletRrcode","titration_end_time","滴定結束時間","titration_end_time",24),
    ("dropletRrcode","operator","架藥者","operator",25),
    ("dropletRrcode","checker","確認者","checker",26),
    ("dropletRrcode","available_lyophilizer","可凍乾機台","available_lyophilizer",27),
    ("dropletRrcode","remark","備註","remark",28),
    ("dropletRrcode","pre_stir","前置條件-攪拌","pre_stir",29),
    ("dropletRrcode","pre_cool_temp","前置條件-預冷溫度","pre_cool_temp",30),
    ("dropletRrcode","record_time","系統寫入時間","record_time",31),
    ("dropletRrcode","id","流水號","id",99)
]

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS column_dictionary (
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    zh_name TEXT NOT NULL,
    en_name TEXT NOT NULL,
    display_order INTEGER,
    PRIMARY KEY (table_name, column_name)
)
""")

cursor.executemany("""
INSERT OR REPLACE INTO column_dictionary
(table_name, column_name, zh_name, en_name, display_order)
VALUES (?, ?, ?, ?, ?)
""", columns)

conn.commit()
conn.close()

print("✅ column_dictionary ready & populated")
