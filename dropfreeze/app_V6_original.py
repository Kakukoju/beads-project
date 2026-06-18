from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
from pathlib import Path
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)
CORS(app)

DB_PATH = r"\\fls341\\MBBU_FAB\\MB_PD\\BeadRecord\\work_orders.db"
PHOTO_DIR = Path(r"\\fls341\\MBBU_FAB\\MB_PD\\BeadRecord\\Photos")
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
    "時間_滴定結束", "時間_凍乾準備開始", "時間_凍乾開始", "時間_凍乾結束",
    "收藥_上傳者", "滴定準備_上傳者", "滴定開始_上傳者",
    "滴定結束_上傳者", "凍乾準備_上傳者", "凍乾開始_上傳者", "凍乾結束_上傳者"
]
PHOTO_FIELDS = [
    "收藥_照片", "滴定準備_照片", "滴定開始_照片",
    "滴定結束_照片", "凍乾準備_照片", "凍乾開始_照片", "凍乾結束_照片"
]
ALL_FIELDS = QR_FIELDS + PHOTO_FIELDS

STATIONS = [
    ("收藥", "時間_收藥", "收藥_照片", "收藥_上傳者"),
    ("滴定準備", "時間_滴定準備開始", "滴定準備_照片", "滴定準備_上傳者"),
    ("滴定開始", "時間_滴定開始", "滴定開始_照片", "滴定開始_上傳者"),
    ("滴定結束", "時間_滴定結束", "滴定結束_照片", "滴定結束_上傳者"),
    ("凍乾準備", "時間_凍乾準備開始", "凍乾準備_照片", "凍乾準備_上傳者"),
    ("凍乾開始", "時間_凍乾開始", "凍乾開始_照片", "凍乾開始_上傳者"),
    ("凍乾結束", "時間_凍乾結束", "凍乾結束_照片", "凍乾結束_上傳者")
]

app = Flask(__name__)
CORS(app)

DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"
PHOTO_DIR = Path(r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\Photos")
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
    "時間_滴定結束", "時間_凍乾準備開始", "時間_凍乾開始", "時間_凍乾結束",
    "收藥_上傳者", "滴定準備_上傳者", "滴定開始_上傳者",
    "滴定結束_上傳者", "凍乾準備_上傳者", "凍乾開始_上傳者", "凍乾結束_上傳者"
]
PHOTO_FIELDS = [
    "收藥_照片", "滴定準備_照片", "滴定開始_照片",
    "滴定結束_照片", "凍乾準備_照片", "凍乾開始_照片", "凍乾結束_照片"
]
ALL_FIELDS = QR_FIELDS + PHOTO_FIELDS

STATIONS = [
    ("收藥", "時間_收藥", "收藥_照片", "收藥_上傳者"),
    ("滴定準備", "時間_滴定準備開始", "滴定準備_照片", "滴定準備_上傳者"),
    ("滴定開始", "時間_滴定開始", "滴定開始_照片", "滴定開始_上傳者"),
    ("滴定結束", "時間_滴定結束", "滴定結束_照片", "滴定結束_上傳者"),
    ("凍乾準備", "時間_凍乾準備開始", "凍乾準備_照片", "凍乾準備_上傳者"),
    ("凍乾開始", "時間_凍乾開始", "凍乾開始_照片", "凍乾開始_上傳者"),
    ("凍乾結束", "時間_凍乾結束", "凍乾結束_照片", "凍乾結束_上傳者")
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

        parts = [x.strip() for x in qr_text.split(",")]
        if len(parts) < len(QR_FIELDS):
            parts += [""] * (len(QR_FIELDS) - len(parts))
        elif len(parts) > len(QR_FIELDS):
            parts = parts[:len(QR_FIELDS)]
        parts += [""] * len(PHOTO_FIELDS)

        qr_data = dict(zip(ALL_FIELDS, parts))
        order_no = qr_data["工單號"].strip()

        if not order_no:
            return jsonify({"status": "fail", "msg": "工單號缺失或無效"}), 400

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM work_orders WHERE 工單號 = ?", (order_no,))
            row = cursor.fetchone()

            if row:
                desc = [desc[0] for desc in cursor.description]
                for station_name, time_col, photo_col, uploader_col in STATIONS:
                    idx = desc.index(time_col)
                    if not row[idx]:
                        now = datetime.now().isoformat()
                        cursor.execute(f"UPDATE work_orders SET {time_col} = ? WHERE 工單號 = ?", (now, order_no))
                        conn.commit()
                        return jsonify({
                            "status": "existing",
                            "order_no": order_no,
                            "station": station_name
                        })
                return jsonify({"status": "complete", "order_no": order_no})
            else:
                qr_data["時間_收藥"] = datetime.now().isoformat()
                columns = ", ".join(qr_data.keys())
                placeholders = ", ".join(["?"] * len(qr_data))
                cursor.execute(f"INSERT INTO work_orders ({columns}) VALUES ({placeholders})", list(qr_data.values()))
                conn.commit()
                return jsonify({
                    "status": "new",
                    "order_no": order_no,
                    "station": "收藥"
                })

    except Exception as e:
        return jsonify({"status": "fail", "msg": f"後端錯誤: {str(e)}"}), 500

@app.route("/get_status")
def get_status():
    try:
        order = request.args.get("order")
        row = get_work_order(order)
        if not row:
            return jsonify({"msg": "在資料庫中找不到該工單"}), 404

        last_completed = None
        next_station = None
        for station_name, time_col, photo_col, _ in STATIONS:
            val = row.get(time_col, "")
            if str(val).strip():
                last_completed = station_name
            else:
                next_station = station_name
                break

        response = {}
        if last_completed is None:
            response["current_station"] = STATIONS[0][0]
        elif next_station is None:
            response["current_station"] = "已完成"
        else:
            response["current_station"] = last_completed
            response["next_station"] = next_station

        for field in [
            "liquid_storge_避光", "liquid_storge_冰浴",
            "滴定_避光", "滴定_冰浴", "滴定_攪拌",
            "Dispense_Lot_1", "port_1", "pump_1", "凍乾機_1",
            "Dispense_Lot_2", "port_2", "pump_2", "凍乾機_2",
            "Dispense_Lot_3", "port_3", "pump_3", "凍乾機_3",
            "Dispense_Lot_4", "port_4", "pump_4", "凍乾機_4"
        ]:
            response[field] = str(row.get(field, "")).strip()

        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def compress_image(input_path, output_path, max_width=600, quality=70):
    img = Image.open(input_path)
    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
    img.save(output_path, format="JPEG", quality=quality, optimize=True)

@app.route("/upload_photo", methods=["POST"])
def upload_photo():
    try:
        order = request.form.get("order_no")
        station = request.form.get("station")
        uploader = request.form.get("user", "")
        photo = request.files.get("photo")

        if not order or not station or not photo:
            return jsonify({"status": "fail", "msg": "缺少參數或照片"}), 400

        filename = secure_filename(f"{order}_{station}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
        temp_path = PHOTO_DIR / f"temp_{filename}"
        final_path = PHOTO_DIR / filename
        photo.save(temp_path)
        compress_image(temp_path, final_path)
        os.remove(temp_path)

        now = datetime.now().isoformat()
        station_map = {s[0]: (s[1], s[2], s[3]) for s in STATIONS}
        if station not in station_map:
            return jsonify({"status": "fail", "msg": "無效 station"}), 400

        time_col, photo_col, uploader_col = station_map[station]

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM work_orders WHERE 工單號 = ?", (order,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO work_orders (工單號) VALUES (?)", (order,))

            cursor.execute(f'SELECT \"{time_col}\" FROM work_orders WHERE 工單號 = ?', (order,))
            current_time = cursor.fetchone()

            cursor.execute(f"""
                UPDATE work_orders SET \"{photo_col}\" = ?, \"{uploader_col}\" = ? WHERE 工單號 = ?
            """, (filename, uploader, order))

            if not current_time or not current_time[0]:
                cursor.execute(f'UPDATE work_orders SET \"{time_col}\" = ? WHERE 工單號 = ?', (now, order))

            conn.commit()

        return jsonify({"status": "success", "filename": filename})
    except Exception as e:
        print("❌ /upload_photo 錯誤：", e)
        return jsonify({"status": "fail", "msg": f"上傳錯誤: {str(e)}"}), 500

if __name__ == "__main__":
    print("🚀 Flask 後端啟動中，監聽 http://localhost:5000")
    if not os.path.exists(DB_PATH):
        init_db()
    print("🚀 Flask 後端啟動中，監聽 port 5000")
    app.run(host='0.0.0.0', port=5000)
