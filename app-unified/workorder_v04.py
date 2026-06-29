# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3, os, re, json, datetime, socket

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ====== CONFIG ======
DB_PATH = r"D:\配藥表\資料庫\P01_formualte_schedule.db"

# ====== HELPER ======
def query_db(sql, args=()):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql, args)
        return [dict(row) for row in cur.fetchall()]

def safe_float(v):
    try:
        return float(v) if v not in (None, "") else 0.0
    except:
        return 0.0

def safe_int(v):
    try:
        return int(float(v))
    except:
        return 0

def parse_range(text):
    """解析 QC 表中的範圍字串 ex. '0.2~0.35' or '0.2-0.35'"""
    if not text:
        return None
    m = re.match(r"([\d.]+)\s*[-~]\s*([\d.]+)", str(text))
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))

def check_in_range(value, text_range):
    """檢查數值是否落在 QC 範圍內"""
    if not text_range:
        return None  # 沒 QC 值
    lo, hi = text_range
    return lo <= value <= hi

def norm_name(s: str) -> str:
    """標準化 Name/Marker：去掉 - 或 _ 後綴、去空白、轉大寫"""
    if not s:
        return ""
    s = str(s).strip()
    s = re.sub(r"[-_].*$", "", s)  # 移除第一個 - 或 _ 之後的所有內容
    return s.strip().upper()

def find_table_contains_workorder(conn: sqlite3.Connection, work_order: str):
    """回傳第一個包含該工單的 table 名稱，找不到回傳 None"""
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%571%'")
    tables = [r[0] for r in cur.fetchall()]
    for t in tables:
        rows = conn.execute(f"SELECT 1 FROM '{t}' WHERE 工單號碼 = ? LIMIT 1", (work_order,)).fetchall()
        if rows:
            return t
    return None

# ====== ROUTES ======

@app.get("/api/get_workorder")
def api_get_workorder():
    work_order = request.args.get("work_order")
    if not work_order:
        return jsonify({"error": "缺少工單號碼參數"}), 400

    print(f"🔍 收到查詢工單請求: {work_order}")

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row

            # 找出含該工單的目標 table
            target_table = find_table_contains_workorder(conn, work_order)
            if not target_table:
                return jsonify({"message": f"查無工單 {work_order}"}), 404

            # 撈出全部列（同工單）
            rows = conn.execute(f"SELECT * FROM '{target_table}' WHERE 工單號碼 = ?", (work_order,)).fetchall()
            result_rows = [dict(r) | {"來源表": target_table} for r in rows]
            first = result_rows[0]

            # === DropletSchedule ===
            dispose_lots, maker_name = [], None
            titration_qty = 0        # 滴定日數量（有 Pump/Lyophilizer）
            formulation_qty = 0      # 配藥日數量（無 Pump/Lyophilizer）
            cur = conn.execute(
                "SELECT Lot, Pump, Lyophilizer, Marker, Quantity FROM DropletSchedule WHERE WorkOrder = ?",
                (work_order,),
            )
            for r in cur.fetchall():
                maker_name = r["Marker"] or maker_name
                pump_val = (r["Pump"] or "").strip()
                lyo_val  = (r["Lyophilizer"] or "").strip()
                if pump_val or lyo_val:
                    titration_qty += safe_int(r["Quantity"])
                else:
                    formulation_qty += safe_int(r["Quantity"])
                dispose_lots.append({
                    "id": r["Lot"],
                    "port": r["Pump"],
                    "freezeDry": r["Lyophilizer"],
                    "pump": None,
                })
            # 優先使用滴定日數量；僅純配藥工單（無任何滴定日記錄）才用配藥日數量
            product_quantity = titration_qty if titration_qty > 0 else formulation_qty

            # === pump No. (維持原有方式) ===
            pump_ids = []
            if maker_name:
                cur2 = conn.execute("SELECT * FROM 'pump No.'")
                for row in cur2.fetchall():
                    for k in ["可滴定之試劑-1", "可滴定之試劑-2", "可滴定之試劑-3", "可滴定之試劑-4"]:
                        val = row[k]
                        if val and maker_name.lower() in val.strip().lower():
                            pump_ids.append(row["Pump編號"])
                            break

            for i, lot in enumerate(dispose_lots):
                lot["pump"] = pump_ids[i % len(pump_ids)] if pump_ids else None

            # === QC OD 查核（強化邏輯）===
            base_name = norm_name(maker_name or "")
            qc_all = query_db("""
                SELECT Name,[L1-OD],[L2-OD],[L1-起始OD],[L2-起始OD]
                FROM [Liquid form QC]
            """)

            selected_qc = None
            for row in qc_all:
                name = norm_name(row.get("Name", ""))
                # 名稱標準化後完全相同才算
                if name == base_name:
                    # 至少有一個欄位非空（剔除純空白）
                    if any(str(row.get(col, "")).strip() for col in ["L1-OD","L2-OD","L1-起始OD","L2-起始OD"]):
                        selected_qc = row
                        break

            if not selected_qc:
                selected_qc = {
                    "L1-OD": None,
                    "L2-OD": None,
                    "L1-起始OD": None,
                    "L2-起始OD": None,
                }

            # === 製劑實測 OD 值 ===
            L1OD = safe_float(first.get("L1 OD", "") or first.get("L1OD", ""))
            L2OD = safe_float(first.get("L2 OD", "") or first.get("L2OD", ""))
            L1StartOD = safe_float(first.get("L1 起始 OD", "") or first.get("起始L1OD", ""))
            L2StartOD = safe_float(first.get("L2 起始 OD", "") or first.get("起始L2OD", ""))

            # === QC 比對 ===
            qc_map = {
                "L1OD": "L1-OD",
                "L2OD": "L2-OD",
                "L1StartOD": "L1-起始OD",
                "L2StartOD": "L2-起始OD",
            }
            values = {"L1OD": L1OD, "L2OD": L2OD, "L1StartOD": L1StartOD, "L2StartOD": L2StartOD}

            check_results = {}
            for k, qc_col in qc_map.items():
                rng = parse_range(selected_qc.get(qc_col))
                val = values[k]
                check_results[k] = {
                    "value": val,
                    "qc_range": selected_qc.get(qc_col),
                    "pass": check_in_range(val, rng),
                }

            # === 組合回傳 ===
            match_571 = re.search(r"571\d{5,}", target_table or "")
            product_model = match_571.group(0) if match_571 else target_table

            data = {
                "workOrderNo": work_order,
                "productModel": product_model,
                "markerName": maker_name or (target_table or "").split("_")[0],
                "productQuantity": product_quantity,
                "date": first.get("試劑配製日期", ""),
                "beads": [
                    {
                        "beadName": r.get("化學品名", ""),
                        "beadPN": r.get("料號", ""),
                        "unit": "mg",
                        "qtyPerBead": r.get("總重量", 0),
                        "totalQty": r.get("重量紀錄", 0),
                        "lotNo": r.get("Filler_Lot", ""),
                    }
                    for r in result_rows
                ],
                "reagent": {
                    "preparedBy": first.get("配製人員", ""),
                    "confirm": {"dyeing": True, "washing": False},
                },
                "bufferBase": {
                    "L1OD": L1OD,
                    "L2OD": L2OD,
                    "L1StartOD": L1StartOD,
                    "L2StartOD": L2StartOD,
                },
                "qcRanges": {
                    "L1-OD": selected_qc.get("L1-OD"),
                    "L2-OD": selected_qc.get("L2-OD"),
                    "L1-起始OD": selected_qc.get("L1-起始OD"),
                    "L2-起始OD": selected_qc.get("L2-起始OD"),
                },
                "qcCheckResult": check_results,
                "disposeLots": dispose_lots,
            }

            return jsonify(data)

    except Exception as e:
        print("❌ 查詢錯誤:", e)
        return jsonify({"error": str(e)}), 500


@app.post("/api/save_workorder")
def save_workorder():
    try:
        payload = request.get_json(force=True)
        work_order = payload.get("workOrderNo")
        if not work_order:
            return jsonify({"error": "workOrderNo missing"}), 400

        print(f"💾 收到儲存請求: {work_order}")

        beads = payload.get("beads", [])
        reagent = payload.get("reagent", {})
        buffer = payload.get("bufferBase", {})

        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row

            # ✅ 找到真的含該工單的 table（避免更新錯表）
            table = find_table_contains_workorder(conn, work_order)
            if not table:
                return jsonify({"error": f"No table contains work order {work_order}"}), 404

            updated = 0
            for bead in beads:
                remark = bead.get("remark")

                # 確保有 備註 欄
                cur = conn.execute(f"PRAGMA table_info('{table}')")
                cols = [r[1] for r in cur.fetchall()]
                if remark is not None and "備註" not in cols:
                    conn.execute(f"ALTER TABLE '{table}' ADD COLUMN 備註 TEXT")
                    conn.commit()

                sql = f"""
                    UPDATE '{table}'
                    SET L1OD=?, L2OD=?, 起始L1OD=?, 起始L2OD=?, 配製人員=?, 總重量=?, 重量紀錄=?"""
                args = [
                    buffer.get("L1OD", ""),
                    buffer.get("L2OD", ""),
                    buffer.get("L1StartOD", ""),
                    buffer.get("L2StartOD", ""),
                    reagent.get("preparedBy", ""),
                    bead.get("totalQty", 0),
                    bead.get("qtyPerBead", 0),
                ]
                if remark is not None:
                    sql += ", 備註=?"
                    args.append(remark)

                sql += " WHERE 工單號碼=? AND 料號=?"
                args.extend([work_order, bead.get("beadPN", "")])

                conn.execute(sql, args)
                conn.commit()
                updated += conn.total_changes

        return jsonify({"message": f"✅ 已更新 {updated} 筆資料", "table": table})

    except Exception as e:
        print("❌ save_workorder error:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    local_ip = socket.gethostbyname(socket.gethostname())
    print("🚀 Flask 啟動成功！")
    print(f"🌐 可從同網段裝置訪問： http://{local_ip}:5012")
    print(f"🧠 若前端在同電腦運行，請用： http://localhost:5012")
    app.run(host="0.0.0.0", port=5012, debug=False)
