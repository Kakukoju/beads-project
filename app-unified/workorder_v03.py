# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3, os, re, json, datetime, socket

app = Flask(__name__)

# ✅ 啟用 CORS：允許區網所有裝置訪問 /api/*
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
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%571%'")
            tables = [r[0] for r in cur.fetchall()]

            result_rows, target_table = [], None
            for t in tables:
                rows = conn.execute(f"SELECT * FROM '{t}' WHERE 工單號碼 = ?", (work_order,)).fetchall()
                if rows:
                    result_rows.extend([dict(r) | {"來源表": t} for r in rows])
                    target_table = t
                    break

            if not result_rows:
                return jsonify({"message": f"查無工單 {work_order}"}), 404

            first = result_rows[0]

            # === DropletSchedule ===
            dispose_lots, maker_name, product_quantity = [], None, 0
            cur = conn.execute(
                "SELECT Lot, Pump, Lyophilizer, Marker, Quantity FROM DropletSchedule WHERE WorkOrder = ?",
                (work_order,),
            )
            for r in cur.fetchall():
                maker_name = r["Marker"] or maker_name
                product_quantity += safe_int(r["Quantity"])
                dispose_lots.append({
                    "id": r["Lot"],
                    "port": r["Pump"],
                    "freezeDry": r["Lyophilizer"],
                    "pump": None,
                })

            # === pump No. ===
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
                    "L1OD": safe_float(first.get("L1 OD", "") or first.get("L1OD", "")),
                    "L2OD": safe_float(first.get("L2 OD", "") or first.get("L2OD", "")),
                    "L1StartOD": safe_float(first.get("L1 起始 OD", "") or first.get("起始L1OD", "")),
                    "L2StartOD": safe_float(first.get("L2 起始 OD", "") or first.get("起始L2OD", "")),
                },
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
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%571%'")
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "No target table found"}), 404
            table = row[0]

            updated = 0
            for bead in beads:
                remark = bead.get("remark")
                cur = conn.execute(f"PRAGMA table_info('{table}')")
                cols = [r[1] for r in cur.fetchall()]
                if remark and "備註" not in cols:
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
    # ✅ 自動偵測本機 IP 並顯示給前端使用
    local_ip = socket.gethostbyname(socket.gethostname())
    print(f"🚀 Flask 啟動成功！")
    print(f"🌐 可從同網段裝置訪問： http://{local_ip}:5012")
    print(f"🧠 若前端在同電腦運行，請用： http://localhost:5012")

    app.run(host="0.0.0.0", port=5012, debug=False)
