import sqlite3

DB_PATH = r"C:\Users\harryhrguo\WebApp\dropfreeze\work_orders.db"

# 定義應該有的欄位
required_columns = [f"col{i}" for i in range(1, 40)] + [
    "col33_photo", "col34_photo", "col35_photo", "col36_photo",
    "col37_photo", "col38_photo", "col39_photo"
]

def check_and_add_columns():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # 取得現有欄位
        cursor.execute("PRAGMA table_info(work_orders)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        for col in required_columns:
            if col not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE work_orders ADD COLUMN {col} TEXT")
                    print(f"✅ 已新增欄位: {col}")
                except Exception as e:
                    print(f"❌ 新增欄位 {col} 時出錯: {e}")
            else:
                print(f"ℹ️ 已存在欄位: {col}")

        conn.commit()
    print("✨ 欄位補齊完成！")

if __name__ == "__main__":
    check_and_add_columns()
