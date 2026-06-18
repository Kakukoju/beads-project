from flask import Flask, request, jsonify
import os
import sqlite3
from datetime import datetime

app = Flask(__name__)
DB_PATH = r"C:\Users\harryhrguo\WebApp\dropfreeze\work_orders.db"
PHOTO_DIR = r"C:\Users\harryhrguo\WebApp\dropfreeze\photos"
os.makedirs(PHOTO_DIR, exist_ok=True)

@app.route("/upload_photo", methods=["POST"])
def upload_photo():
    order = request.form.get("order")
    file = request.files.get("photo")
    if not file or not order:
        return jsonify({"status": "fail", "msg": "缺少資料"}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT col33, col34, col35, col36, col37, col38, col39 
        FROM work_orders WHERE col1 = ?
    """, (order,))
    row = cursor.fetchone()
    conn.close()

    station_map = ["收藥", "滴定準備開始", "滴定開始", "滴定結束", "凍乾準備開始", "凍乾開始", "凍乾結束"]
    station = "未開始"
    if row:
        for val, name in reversed(list(zip(row, station_map))):
            if val:
                station = name
                break

    filename = f"{order}_{station}.jpg"
    filepath = os.path.join(PHOTO_DIR, filename)
    file.save(filepath)

    return jsonify({"status": "success", "filename": filename})

if __name__ == "__main__":
    app.run(port=5000)
