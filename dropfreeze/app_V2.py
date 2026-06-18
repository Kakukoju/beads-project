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
        cursor.execute("DROP TABLE IF EXISTS work_orders")
        col_defs = ", ".join([f'"{col}" TEXT' for col in ALL_FIELDS])
        cursor.execute(f"""
            CREATE TABLE work_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {col_defs}
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_orders_order_no ON work_orders (工單號)")
        conn.commit()
        print("✅ 已重新建立資料庫表 work_orders")

def get_work_order(work_order_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM work_orders WHERE 工單號 = ?", (work_order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


@app.route("/rebuild_db")
def rebuild_db():
    init_db()
    return jsonify({"status": "success", "msg": "資料庫已重建"})

@app.route("/qr_hook", methods=["POST"])
def qr_hook():
    try:
        data = request.get_json()
        qr_text = data.get("qr_text") if data else None
        if not qr_text:
            return jsonify({"status": "fail", "msg": "缺少 qr_text"}), 400

        print("=" * 50)
        print(f"收到 qr_text: {qr_text}")

        parts = [x.strip() for x in qr_text.split(",")]
        print(f"初步拆解 parts 數量: {len(parts)}")
        print(f"parts: {parts}")

        if len(parts) < len(QR_FIELDS):
            parts += [""] * (len(QR_FIELDS) - len(parts))
        elif len(parts) > len(QR_FIELDS):
            parts = parts[:len(QR_FIELDS)]
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
                desc = [desc[0] for desc in cursor.description]
                for station_name, time_col, photo_col in STATIONS:
                    idx = desc.index(time_col)
                    if not row[idx]:
                        now = datetime.now().isoformat()
                        cursor.execute(f"UPDATE work_orders SET {time_col} = ? WHERE 工單號 = ?", (now, order_no))
                        conn.commit()
                        print(f"更新 {time_col} 為 {now}")
                        response_data = {
                            "status": "existing",
                            "order_no": order_no,
                            "station": station_name,
                            "next_time_col": time_col,
                            "next_photo_col": photo_col
                        }
                        print(f"回傳資料: {response_data}")
                        return jsonify(response_data)

                # 所有工站已完成
                response_data = {
                    "status": "complete",
                    "order_no": order_no
                }
                print(f"回傳資料: {response_data}")
                return jsonify(response_data)

            else:
                print("資料庫無該工單，執行 INSERT")
                qr_data["時間_收藥"] = datetime.now().isoformat()
                columns = ", ".join(qr_data.keys())
                placeholders = ", ".join(["?"] * len(qr_data))
                values = list(qr_data.values())
                cursor.execute(f"INSERT INTO work_orders ({columns}) VALUES ({placeholders})", values)
                conn.commit()
                print(f"工單 {order_no} 插入成功")
                response_data = {
                    "status": "new",
                    "order_no": order_no,
                    "station": "收藥",
                    "next_time_col": "時間_收藥",
                    "next_photo_col": "收藥_照片"
                }
                print(f"回傳資料: {response_data}")
                return jsonify(response_data)

    except Exception as e:
        print(f"qr_hook 發生例外: {e}")
        return jsonify({"status": "fail", "msg": f"後端錯誤: {str(e)}"}), 500


@app.route("/get_status", methods=["GET"])
def get_status():
    work_order_id = request.args.get("order")
    if not work_order_id:
        return jsonify({"error": "缺少工單號碼參數"}), 400

    row = get_work_order(work_order_id)
    if not row:
        return jsonify({"msg": "在資料庫中找不到該工單"}), 404

    STATIONS = [
        ("收藥", "收藥_照片"),
        ("滴定準備", "滴定準備_照片"),
        ("滴定開始", "滴定開始_照片"),
        ("滴定結束", "滴定結束_照片"),
        ("凍乾準備", "凍乾準備_照片"),
        ("凍乾開始", "凍乾開始_照片"),
        ("凍乾結束", "凍乾結束_照片"),
    ]

    for station_name, photo_col in STATIONS:
        if not row.get(photo_col):
            return jsonify({"current_station": station_name})

    return jsonify({"current_station": "已完成"})



@app.route("/upload_photo", methods=["POST"])
def upload_photo():
    try:
        order = request.form.get("order_no")
        station = request.form.get("station")
        photo = request.files.get("photo")
        if not order or not station or not photo:
            return jsonify({"status": "fail", "msg": "缺少參數或照片"}), 400
        print(f"收到上傳: order_no={order}, station={station}, photo={photo.filename if photo else '無檔案'}")
        safe_filename = secure_filename(f"{order}_{station}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
        save_path = PHOTO_DIR / safe_filename

        photo.save(save_path)
        station_photo_map = {s[0]: s[2] for s in STATIONS}
        photo_col = station_photo_map.get(station)
        if photo_col:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row  # 先設 row_factory 6/24
                cursor = conn.cursor()
                cursor.execute(f"UPDATE work_orders SET {photo_col} = ? WHERE 工單號 = ?", (safe_filename, order))
                conn.commit()
                cursor.execute("SELECT * FROM work_orders WHERE 工單號 = ?", (order,)) #6/24
                row = cursor.fetchone() #6/24
                if row:
                    dict_row = {k: row[k] for k in row.keys()} # 6/24
                    print(f"📌 上傳後資料: {dict_row}")
                else:
                    print("⚠ 找不到該工單資料")
        #return jsonify({"status": "success", "filename": safe_filename})
        return jsonify({
            "status": "success",
            "filename": safe_filename,
            "photo_col": photo_col,
            "current_row": dict(row)
            })

    except Exception as e:
        print(f"upload_photo 發生例外: {e}")
        return jsonify({"status": "fail", "msg": f"後端錯誤: {str(e)}"}), 500

if __name__ == "__main__":
    init_db()
    app.run(port=5000)
