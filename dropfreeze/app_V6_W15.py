from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
from pathlib import Path
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image
import re
from waitress import serve

app = Flask(__name__)
CORS(app)

DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders_test.db"
PHOTO_DIR = Path(r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\Photos_test")
os.makedirs(PHOTO_DIR, exist_ok=True)

DB_TIMEOUT = 5.0
ADMIN_PIN = "36121288"

QR_FIELDS = [
    "工單號", "製令數量", "bead_name", "PN", "是否懸浮", "日期",
    "L1_反應_OD", "L1_起始_OD", "L2_反應_OD", "L2_起始_OD",
    "liquid_storge_避光", "liquid_storge_冰浴",
    "滴定_避光", "滴定_冰浴", "滴定_攪拌",
    "Dispense_Lot_1", "port_1", "pump_1", "凍乾機_1",
    "Dispense_Lot_2", "port_2", "pump_2", "凍乾機_2",
    "Dispense_Lot_3", "port_3", "pump_3", "凍乾機_3",
    "Dispense_Lot_4", "port_4", "pump_4", "凍乾機_4",
    "淨重g", "時間_收藥", "時間_滴定準備", "時間_滴定開始",
    "時間_滴定結束", "時間_凍乾準備", "時間_凍乾開始", "時間_凍乾結束",
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
    ("滴定準備", "時間_滴定準備", "滴定準備_照片", "滴定準備_上傳者"),
    ("滴定開始", "時間_滴定開始", "滴定開始_照片", "滴定開始_上傳者"),
    ("滴定結束", "時間_滴定結束", "滴定結束_照片", "滴定結束_上傳者"),
    ("凍乾準備", "時間_凍乾準備", "凍乾準備_照片", "凍乾準備_上傳者"),
    ("凍乾開始", "時間_凍乾開始", "凍乾開始_照片", "凍乾開始_上傳者"),
    ("凍乾結束", "時間_凍乾結束", "凍乾結束_照片", "凍乾結束_上傳者")
]

def get_db_connection():
    return sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT)

def init_db():
    with get_db_connection() as conn:
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

def ensure_columns(conn, table, columns):
    """
    確認 table 內存在指定欄位；若沒有就自動 ADD COLUMN（TEXT）。
    """
    cur = conn.cursor()
    cur.execute(f'PRAGMA table_info("{table}")')
    existing = {row[1] for row in cur.fetchall()}
    for col in columns:
        if col not in existing:
            cur.execute(f'ALTER TABLE "{table}" ADD COLUMN "{col}" TEXT')
    conn.commit()

def get_work_order(work_order_id):
    with get_db_connection() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM work_orders WHERE 工單號 = ?", (work_order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def validate_qr_data(qr_data: dict, qr_fields: list[str]) -> list[str]:
    errors = []
    order_no = qr_data.get("工單號", "").strip()
    if not order_no or not order_no.startswith(("TMR", "UMR")):
        errors.append("工單號格式錯誤（需以 TMR 或 UMR 開頭）")

    raw_qty = qr_data.get("製令數量", "").strip()
    try:
        qty = int(raw_qty)
        if qty <= 0:
            errors.append("製令數量必須大於 0")
    except ValueError:
        errors.append("製令數量應為正整數")

    date_str = qr_data.get("日期", "").strip()
    date_match = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", date_str)
    if date_match:
        year, month, day = date_match.groups()
        fixed_date = f"{year}-{int(month):02d}-{int(day):02d}"
        try:
            datetime.strptime(fixed_date, "%Y-%m-%d")
            qr_data["日期"] = fixed_date
        except ValueError:
            errors.append("日期格式錯誤，解析失敗")
    else:
        errors.append("日期格式錯誤，應為 YYYY-MM-DD 或 YYYY/M/D")

    if not qr_data.get("PN", "").strip():
        errors.append("PN 不得為空")
    if not qr_data.get("bead_name", "").strip():
        errors.append("bead_name 不得為空")

    weight_str = qr_data.get("淨重g", "").strip()
    if weight_str:
        try:
            float(weight_str)
        except ValueError:
            errors.append("淨重g 應為數字")

    return errors

# -------------------- 新增：更新 Port 欄位 --------------------
@app.route("/update_ports", methods=["POST"])
def update_ports():
    """
    body: { "order": "...", "auth": "36121288", "ports": ["Port1","Port2",...] }
    規則：把傳入序列依序寫入 port_1 ~ port_4，未提供的清空為 ''。
    """
    try:
        data = request.get_json(force=True)
        order = (data.get("order") or "").strip()
        auth  = (data.get("auth") or "").strip()
        ports = data.get("ports") or []

        if auth != ADMIN_PIN:
            return jsonify({"status": "fail", "msg": "未授權"}), 403
        if not order:
            return jsonify({"status": "fail", "msg": "缺少工單"}), 400

        # 正規化值
        norm = []
        for p in ports[:4]:
            p = str(p or "").strip()
            if p and not re.match(r"^Port\d+$", p, re.IGNORECASE):
                return jsonify({"status": "fail", "msg": f"非法 Port 值: {p}"}), 400
            norm.append(p)

        while len(norm) < 4:
            norm.append("")

        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM work_orders WHERE 工單號=?", (order,))
            if not c.fetchone():
                c.execute("INSERT INTO work_orders (工單號) VALUES (?)", (order,))
            for i in range(1,5):
                col = f"port_{i}"
                c.execute(f'UPDATE work_orders SET "{col}"=? WHERE 工單號=?', (norm[i-1], order))
            conn.commit()
        return jsonify({"status":"success","msg":"ports updated","ports":norm})
    except Exception as e:
        return jsonify({"status":"fail","msg":str(e)}), 500

# -------------------- 新增：一次設定四個凍乾機欄位 --------------------
@app.route("/update_freezer", methods=["POST"])
def update_freezer():
    """
    body: { "order": "...", "auth": "36121288", "freezer": "Freezer 01" }
    作用：把 freezer 值寫入 凍乾機_1..凍乾機_4（四欄同值）
         若資料表缺欄位，會自動新增；若存在舊命名 freeze_1..4 也會一併更新。
    """
    try:
        data = request.get_json(force=True)
        order = (data.get("order") or "").strip()
        auth  = (data.get("auth") or "").strip()
        freezer = (data.get("freezer") or "").strip()

        if auth != ADMIN_PIN:
            return jsonify({"status":"fail","msg":"未授權"}), 403
        if not order:
            return jsonify({"status":"fail","msg":"缺少工單"}), 400
        if not re.match(r"^Freezer\s\d{2}$", freezer):
            return jsonify({"status":"fail","msg":"freezer 格式需為 'Freezer XX'（兩位數）"}), 400

        with get_db_connection() as conn:
            cur = conn.cursor()

            # 若工單不存在先建一筆
            cur.execute('SELECT 1 FROM work_orders WHERE 工單號=?', (order,))
            if not cur.fetchone():
                cur.execute('INSERT INTO work_orders (工單號) VALUES (?)', (order,))
                conn.commit()

            # 確保新欄位存在；若有舊欄位也一起寫
            new_cols = [f"凍乾機_{i}" for i in range(1,5)]
            old_cols = [f"freeze_{i}" for i in range(1,5)]

            ensure_columns(conn, "work_orders", new_cols)

            # 寫入新欄位
            for col in new_cols:
                cur.execute(f'UPDATE work_orders SET "{col}"=? WHERE 工單號=?', (freezer, order))

            # 如果有舊欄位就一併更新（不強制新增舊欄位）
            cur.execute('PRAGMA table_info("work_orders")')
            existing = {row[1] for row in cur.fetchall()}
            for col in old_cols:
                if col in existing:
                    cur.execute(f'UPDATE work_orders SET "{col}"=? WHERE 工單號=?', (freezer, order))

            conn.commit()

        return jsonify({"status":"success","msg":"freezer updated","freezer":freezer})
    except Exception as e:
        return jsonify({"status":"fail","msg":str(e)}), 500


# -------------------- 既有 API（原樣保留） --------------------
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
        errors = validate_qr_data(qr_data, QR_FIELDS)
        if errors:
            return jsonify({"status": "fail", "msg": "；".join(errors)}), 400

        order_no = qr_data["工單號"].strip()
        if not order_no:
            return jsonify({"status": "fail", "msg": "工單號缺失或無效"}), 400

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM work_orders WHERE 工單號 = ?", (order_no,))
            row = cursor.fetchone()

            if row:
                desc = [desc[0] for desc in cursor.description]
                for station_name, time_col, photo_col, uploader_col in STATIONS:
                    idx = desc.index(time_col)
                    if not row[idx]:
                        return jsonify({
                            "status": "existing",
                            "order_no": order_no,
                            "station": station_name
                        })
                return jsonify({
                    "status": "complete",
                    "order_no": order_no,
                    "station": "凍乾結束"
                })
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

@app.route("/mark_station_time", methods=["POST"])
def mark_station_time():
    try:
        data = request.get_json()
        order_no = data.get("order")
        station = data.get("station")

        if not order_no or not station:
            return jsonify({"status": "fail", "msg": "缺少參數"}), 400

        now = datetime.now().isoformat()
        station_map = {s[0]: s[1] for s in STATIONS}
        time_col = station_map.get(station)
        if not time_col:
            return jsonify({"status": "fail", "msg": "無效 station"}), 400

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE work_orders SET \"{time_col}\" = ? WHERE 工單號 = ?", (now, order_no))
            conn.commit()

        return jsonify({"status": "success", "msg": "時間已更新"})
    except Exception as e:
        return jsonify({"status": "fail", "msg": f"標記錯誤: {str(e)}"}), 500

@app.route("/get_status")
def get_status():
    try:
        order = request.args.get("order")
        row_dict = get_work_order(order)
        if not row_dict:
            return jsonify({
                "current_station": "收藥",
                "工單號": order,
                "msg": "這是新工單（尚未寫入）"
            }), 200

        if row_dict.get("時間_凍乾結束") and str(row_dict["時間_凍乾結束"]).strip():
            current_station = "已完成"
            next_station = None
        else:
            current_station = "收藥"
            next_station = None
            for station_name, time_col, _, _ in STATIONS:
                time_val = row_dict.get(time_col)
                if time_val and str(time_val).strip():
                    current_station = station_name
                else:
                    next_station = station_name
                    break

        response = {
            "current_station": current_station,
            "next_station": next_station,
            "工單號": order,
        }

        for _, time_col, _, _ in STATIONS:
            response[time_col] = str(row_dict.get(time_col, "")).strip()

        extra_fields = [
            "liquid_storge_避光", "liquid_storge_冰浴",
            "滴定_避光", "滴定_冰浴", "滴定_攪拌",
            "Dispense_Lot_1", "port_1", "pump_1", "凍乾機_1",
            "Dispense_Lot_2", "port_2", "pump_2", "凍乾機_2",
            "Dispense_Lot_3", "port_3", "pump_3", "凍乾機_3",
            "Dispense_Lot_4", "port_4", "pump_4", "凍乾機_4",
            "bead_name", "PN", "是否懸浮", "日期", "製令數量", "淨重g"
        ]
        for field in extra_fields:
            response[field] = str(row_dict.get(field, "")).strip()

        return jsonify(response)

    except Exception as e:
        return jsonify({"status": "fail", "msg": str(e)}), 500

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

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM work_orders WHERE 工單號 = ?", (order,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO work_orders (工單號) VALUES (?)", (order,))

            cursor.execute(f'SELECT "{time_col}" FROM work_orders WHERE 工單號 = ?', (order,))
            current_time = cursor.fetchone()

            cursor.execute(f"""
                UPDATE work_orders SET "{photo_col}" = ?, "{uploader_col}" = ? WHERE 工單號 = ?
            """, (filename, uploader, order))

            if not current_time or not current_time[0]:
                cursor.execute(f'UPDATE work_orders SET "{time_col}" = ? WHERE 工單號 = ?', (now, order))

            conn.commit()

        return jsonify({"status": "success", "filename": filename})
    except Exception as e:
        return jsonify({"status": "fail", "msg": f"上傳錯誤: {str(e)}"}), 500

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"資料庫檔案 '{DB_PATH}' 不存在，正在初始化...")
        init_db()
    else:
        print(f"資料庫檔案 '{DB_PATH}' 已存在。")

    port = int(os.environ.get("PORT", 5010))
    print(f"🚀 Flask 後端啟動中，監聽 http://0.0.0.0:{port} (使用 Waitress)")
    serve(app, host='0.0.0.0', port=port)
