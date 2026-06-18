from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
from pathlib import Path
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

DB_PATH = r"C:\Users\harryhrguo\WebApp\dropfreeze\work_orders.db"
PHOTO_DIR = Path(r"C:\Users\harryhrguo\WebApp\dropfreeze\photos")
os.makedirs(PHOTO_DIR, exist_ok=True)

QR_FIELDS = [
    "工單號", "製令數量", "bead_name", "PN", "是否懸浮", "日期",
    "L1_反應_OD", "L1_起始_OD", "L2_反應_OD", "L2_起始_OD",
    "liquid_storge_避光", "liquid_storge_冰浴",
    "滴定_避光", "滴定_冰浴", "滴定_攪拌",
    "Dispense_Lot_1", "port_1", "pump_1", "凍乾機_1",
    "Dispense_Lot_2", "port_2", "pump_2", "凍乾機_2",
    "Dispense_Lot_3", "port_3", "pump_3", "凍乾機_3",
    "Dispense_Lot_4", "port_4", "pump_4", "凍乾機_4",
    "淨重g", "時間_收藥", "時間_滴定準備開始", "時間_滴定開始",
    "時間_滴定結束", "時間_凍乾準備開始", "時間_凍乾開始", "時間_凍乾結束"
]
PHOTO_FIELDS = [
    "收藥_照片", "滴定準備_照片", "滴定開始_照片",
    "滴定結束_照片", "凍乾準備_照片", "凍乾開始_照片", "凍乾結束_照片"
]
ALL_FIELDS = QR_FIELDS + PHOTO_FIELDS

STATIONS = [
    ("收藥", "時間_收藥", "收藥_照片"),
    ("滴定準備", "時間_滴定準備開始", "滴定準備_照片"),
    ("滴定開始", "時間_滴定開始", "滴定開始_照片"),
    ("滴定結束", "時間_滴定結束", "滴定結束_照片"),
    ("凍乾準備", "時間_凍乾準備開始", "凍乾準備_照片"),
    ("凍乾開始", "時間_凍乾開始", "凍乾開始_照片"),
    ("凍乾結束", "時間_凍乾結束", "凍乾結束_照片")
]

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        col_defs = ", ".join([f'"{col}" TEXT' for col in ALL_FIELDS])
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS work_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {col_defs}
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_orders_order_no ON work_orders (工單號)")
        conn.commit()

@app.route("/qr_hook", methods=["POST"])
def qr_hook():
    data = request.get_json()
    qr_text = data.get("qr_text") if data else None
    if not qr_text:
        return jsonify({"status": "fail", "msg": "缺少 qr_text"}), 400

    print("="*50)
    print(f"收到 qr_text: {qr_text}")

    parts = [x.strip() for x in qr_text.split(",")]
    print(f"初步拆解 parts 數量: {len(parts)}")
    print(f"parts: {parts}")

    # 補齊 QR_FIELDS
    if len(parts) < len(QR_FIELDS):
        parts += [""] * (len(QR_FIELDS) - len(parts))
    elif len(parts) > len(QR_FIELDS):
        parts = parts[:len(QR_FIELDS)]

    # 補照片欄空值
    parts += [""] * len(PHOTO_FIELDS)

    print(f"最終 parts 數量: {len(parts)}")
    qr_data = dict(zip(ALL_FIELDS, parts))
    order_no = qr_data["工單號"].strip()

    print(f"工單號: {order_no}")
    print(f"qr_data: {qr_data}")

    if not order_no:
        return jsonify({"status": "fail", "msg": "工單號缺失或無效"}), 400

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM work_orders WHERE 工單號 = ?", (order_no,))
        row = cursor.fetchone()

        if row:
            print("資料庫已有該工單，進行時間欄更新")
            for station_name, time_col, photo_col in STATIONS:
                idx = [desc[0] for desc in cursor.description].index(time_col)
                if not row[idx]:
                    now = datetime.now().isoformat()
                    cursor.execute(f"UPDATE work_orders SET {time_col} = ? WHERE 工單號 = ?", (now, order_no))
                    conn.commit()
                    print(f"更新 {time_col} 為 {now}")
                    return jsonify({
                        "status": "existing",
                        "order_no": order_no,
                        "station": station_name,
                        "next_time_col": time_col,
                        "next_photo_col": photo_col
                    })
            print("該工單已完成所有工站")
            return jsonify({"status": "complete", "order_no": order_no})
        else:
            print("資料庫無該工單，執行 INSERT")
            qr_data["時間_收藥"] = datetime.now().isoformat()
            columns = ", ".join(qr_data.keys())
            placeholders = ", ".join(["?"] * len(qr_data))
            values = list(qr_data.values())
            try:
                cursor.execute(f"INSERT INTO work_orders ({columns}) VALUES ({placeholders})", values)
                conn.commit()
                print(f"工單 {order_no} 插入成功")
            except Exception as e:
                print(f"INSERT 發生錯誤: {e}")
                return jsonify({"status": "fail", "msg": str(e)}), 500

            return jsonify({
                "status": "new",
                "order_no": order_no,
                "station": "收藥",
                "next_time_col": "時間_收藥",
                "next_photo_col": "收藥_照片"
            })

@app.route("/upload_photo", methods=["POST"])
def upload_photo():
    order = request.form.get("order_no")
    station = request.form.get("station")
    photo = request.files.get("photo")
    if not order or not station or not photo:
        return jsonify({"status": "fail", "msg": "缺少參數或照片"}), 400

    safe_filename = secure_filename(f"{order}_{station}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
    save_path = PHOTO_DIR / safe_filename

    try:
        photo.save(save_path)
        station_photo_map = {s[0]: s[2] for s in STATIONS}
        photo_col = station_photo_map.get(station)
        if photo_col:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(f"UPDATE work_orders SET {photo_col} = ? WHERE 工單號 = ?", (safe_filename, order))
                conn.commit()
        return jsonify({"status": "success", "filename": safe_filename})
    except Exception as e:
        print(f"照片儲存錯誤: {e}")
        return jsonify({"status": "fail", "msg": str(e)}), 500

if __name__ == "__main__":
    init_db()
    app.run(port=5000)