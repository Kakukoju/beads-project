# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3, os, re, json, datetime

app = Flask(__name__)
CORS(app)

# ====== CONFIG ======
DB_PATH = r"D:\配藥表\資料庫\P01_formualte_schedule.db"

# ====== HELPER ======
def query_db(sql, args=()):
    """查詢 DB 並回傳 list[dict]"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql, args)
        return [dict(row) for row in cur.fetchall()]

def execute_db(sql, args=()):
    """執行修改動作並回傳影響列數"""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.rowcount

def safe_float(v):
    """將任何值安全轉成 float"""
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except:
        return 0.0
    
def safe_int(v):
    """安全轉 int"""
    try:
        return int(float(v))
    except:
        return 0

# ====== ROUTES ======

# ✅ Flask: /api/get_workorder — 查詢工單所有資料 (含滴定凍乾機 & 滴定 pump)
@app.get("/api/get_workorder")
def api_get_workorder():
    work_order = request.args.get("work_order")
    if not work_order:
        return jsonify({"error": "缺少工單號碼參數"}), 400

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        # === 1️⃣ 找出工單所在產品表 (*_571*) ===
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%571%'")
        tables = [r[0] for r in cur.fetchall()]
        if not tables:
            return jsonify({"error": "找不到產品資料表"}), 404

        result_rows = []
        target_table = None
        for t in tables:
            try:
                rows = conn.execute(f"SELECT * FROM '{t}' WHERE 工單號碼 = ?", (work_order,)).fetchall()
                if rows:
                    for r in rows:
                        r = dict(r)
                        r["來源表"] = t
                        result_rows.append(r)
                    target_table = t
                    break  # ✅ 找到即停止
            except Exception as e:
                print(f"⚠️ skip table {t}: {e}")

        if not result_rows:
            return jsonify({"message": f"查無工單 {work_order}"}), 404

        first = result_rows[0]

        # === 2️⃣ 查詢 DropletSchedule ===
        dispose_lots = []
        maker_name = None
        product_quantity = 0  # ✅ DropletSchedule.Quantity 總和 = 產品數量

        try:
            cur = conn.execute(
                "SELECT Lot, Pump, Lyophilizer, Marker, Quantity FROM DropletSchedule WHERE WorkOrder = ?",
                (work_order,),
            )
            rows = cur.fetchall()
            for r in rows:
                lot_id = r["Lot"]
                port = r["Pump"]
                lyoph = r["Lyophilizer"]
                maker_name = r["Marker"] or maker_name
                qty = safe_int(r["Quantity"])
                product_quantity += qty
                dispose_lots.append({
                    "id": lot_id,
                    "port": port,
                    "freezeDry": lyoph,
                    "pump": None,
                })
            print(f"🧪 Marker: {maker_name}, 產品數量合計: {product_quantity}")
        except Exception as e:
            print(f"⚠️ DropletSchedule 查詢錯誤: {e}")

        # === 3️⃣ 查 pump No. ===
        pump_ids = []
        if maker_name:
            try:
                maker_lower = maker_name.strip().lower()
                cur2 = conn.execute("SELECT * FROM 'pump No.'")
                pump_rows = cur2.fetchall()
                for row in pump_rows:
                    for k in [
                        "可滴定之試劑-1",
                        "可滴定之試劑-2",
                        "可滴定之試劑-3",
                        "可滴定之試劑-4",
                    ]:
                        val = row[k]
                        if val and maker_lower in val.strip().lower():
                            pump_ids.append(row["Pump編號"])
                            break
                print(f"📦 可用 Pump IDs: {pump_ids}")
            except Exception as e:
                print(f"⚠️ pump No. 查詢錯誤: {e}")

        # === 4️⃣ 填入 pump ===
        for i, lot in enumerate(dispose_lots):
            lot["pump"] = pump_ids[i % len(pump_ids)] if pump_ids else None

        # === 5️⃣ 組合回傳 ===
        match_571 = re.search(r"571\d{5,}", target_table or "")
        product_model = match_571.group(0) if match_571 else (target_table or "")

        # ✅ DropletSchedule Marker 優先，否則由表名推導（571 前、底線→ -）
        if maker_name:
            marker_name = maker_name
        else:
            table_name = target_table or ""
            prefix_match = re.match(r"^(.*?)571", table_name)
            marker_name = prefix_match.group(1).replace("_", "-") if prefix_match else table_name

        data = {
            "workOrderNo": work_order,
            "productModel": product_model,
            "markerName": marker_name,
            "productQuantity": product_quantity,  # ✅ DropletSchedule.Quantity 總和（產品數量）
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


@app.route("/api/save_workorder", methods=["POST"])
def save_workorder():
    """
    儲存或更新工單內容
    若該表沒有「備註」欄位，且有寫入備註時，會自動新增欄位。
    """
    try:
        payload = request.get_json(force=True)
        work_order = payload.get("workOrderNo")
        beads = payload.get("beads", [])
        reagent = payload.get("reagent", {})
        buffer = payload.get("bufferBase", {})

        if not work_order:
            return jsonify({"error": "workOrderNo missing"}), 400

        # 找到第一個含 _571 的表
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%571%'")
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "No target table found"}), 404
            table = row[0]

        updated = 0
        for bead in beads:
            remark = bead.get("remark", None)

            # --- Step 1️⃣: 檢查欄位 ---
            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.execute(f"PRAGMA table_info('{table}')")
                cols = [r[1] for r in cur.fetchall()]
                has_remark = "備註" in cols

                # --- Step 2️⃣: 若有備註內容且欄位不存在，動態新增 ---
                if remark and not has_remark:
                    conn.execute(f"ALTER TABLE '{table}' ADD COLUMN 備註 TEXT")
                    conn.commit()
                    print(f"🆕 Added column 備註 to {table}")

            # --- Step 3️⃣: 執行 UPDATE ---
            sql = f"""
                UPDATE '{table}'
                SET 
                    L1OD=?,
                    L2OD=?,
                    起始L1OD=?,
                    起始L2OD=?,
                    配製人員=?,
                    總重量=?,
                    重量紀錄=?
            """

            args = [
                buffer.get("L1OD", ""),
                buffer.get("L2OD", ""),
                buffer.get("L1StartOD", ""),
                buffer.get("L2StartOD", ""),
                reagent.get("preparedBy", ""),
                bead.get("totalQty", 0),
                bead.get("qtyPerBead", 0),
            ]

            # 若表格已有「備註」欄位或剛新增，且有內容 → 一併更新
            if remark is not None:
                sql += ", 備註=?"
                args.append(remark)

            sql += " WHERE 工單號碼=? AND 料號=?"
            args.extend([work_order, bead.get("beadPN", "")])

            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(sql, args)
                conn.commit()
                updated += conn.total_changes

        return jsonify({"message": f"✅ 已更新 {updated} 筆資料", "table": table})
    except Exception as e:
        print("❌ save_workorder error:", e)
        return jsonify({"error": str(e)}), 500
    

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5012, debug=False)
