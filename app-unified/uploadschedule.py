# app.py — DropletSchedule API (全修正版: 日期＋時間欄位修正)
# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import sqlite3, csv, io, os, re, json, datetime

# ==================== CONFIG ====================
DB_PATH = r"D:\配藥表\資料庫\P01_formualte_schedule.db"
TABLE_NAME = "DropletSchedule"
ALLOW_ORIGINS = ["*"]

# 中文表頭 → 英文欄位映射
HEADER_MAP = {
    "Pump": "Pump",
    "Marker": "Marker",
    "凍乾機台": "Lyophilizer",
    "可用凍乾機": "AvailableLyophilizer",
    "數量": "Quantity",
    "配藥同仁": "Preparer",
    "日期": "Date",
    "RD給藥時間": "DrugGivenAt",
    "預計滴定時間": "ExpectedTitrationStart",
    "預計結束": "ExpectedTitrationEnd",
    "工單編號": "WorkOrder",
    "Lot": "Lot",
    "備註": "Remark",
}

# ==================== APP INIT ====================
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ALLOW_ORIGINS}})

# ==================== DB UTILS ====================
def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def table_exists(conn, name):
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,))
    return cur.fetchone() is not None

def remove_cn_spaces(s):
    if s is None:
        return ""
    s = str(s).replace("\u3000", "").replace("\xa0", "").strip()
    return s

def sanitize_for_ident(name):
    s = remove_cn_spaces(name).replace(" ", "")
    s = re.sub(r"[^0-9A-Za-z_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return "col"
    if s[0].isdigit():
        s = "_" + s
    return s

def zh_header_to_en(h):
    base = remove_cn_spaces(h).replace(" ", "")
    if base in HEADER_MAP:
        return sanitize_for_ident(HEADER_MAP[base])
    return sanitize_for_ident(base)

def normalize_headers(headers):
    seen, out = set(), []
    for idx, h in enumerate(headers):
        name = zh_header_to_en(h) or f"col_{idx+1}"
        orig = name
        i = 2
        while name in seen:
            name = f"{orig}_{i}"
            i += 1
        seen.add(name)
        out.append(name)
    return out

def ensure_table_and_columns(conn, headers):
    cols = normalize_headers(headers)
    if not table_exists(conn, TABLE_NAME):
        col_defs = ", ".join(f'"{c}" TEXT' for c in cols)
        conn.execute(f'CREATE TABLE "{TABLE_NAME}" ({col_defs});')
        conn.commit()
        return cols

    existing = {row[1] for row in conn.execute(f'PRAGMA table_info("{TABLE_NAME}")')}
    for c in cols:
        if c not in existing:
            conn.execute(f'ALTER TABLE "{TABLE_NAME}" ADD COLUMN "{c}" TEXT;')
    conn.commit()
    return cols

def truncate_table(conn):
    if table_exists(conn, TABLE_NAME):
        conn.execute(f'DELETE FROM "{TABLE_NAME}";')
        conn.commit()

def parse_csv_text(text):
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return [], []
    headers = [remove_cn_spaces(h) for h in rows[0]]
    return headers, rows[1:]

def parse_csv_file(file_storage):
    text = file_storage.read().decode("utf-8-sig", errors="replace")
    return parse_csv_text(text)

# ========== 日期欄位修正 ==========
def fix_date_field(rows, headers):
    """
    強制將 Date 欄位轉為 yyyy/mm/dd 字串
    - 若為 Excel 數字日期序號 (例如 45930)，轉回日期字串
    - 若為日期文字，統一為 yyyy/mm/dd
    """
    fixed = []
    if "Date" not in headers:
        return rows

    idx = headers.index("Date")

    for r in rows:
        r = list(r)
        val = remove_cn_spaces(r[idx])

        # ✅ Excel 日期數字轉換：序號 +1899-12-30
        if re.fullmatch(r"\d{4,6}", val):
            try:
                base = datetime.datetime(1899, 12, 30)
                d = base + datetime.timedelta(days=int(val))
                r[idx] = d.strftime("%Y/%m/%d")
            except Exception:
                r[idx] = val
        else:
            # 嘗試解析日期字串
            parsed = None
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%m/%d/%Y"):
                try:
                    parsed = datetime.datetime.strptime(val, fmt)
                    break
                except Exception:
                    continue
            if parsed:
                r[idx] = parsed.strftime("%Y/%m/%d")
            else:
                r[idx] = val
        fixed.append(r)

    return fixed

# ========== 時間欄位修正 ==========
def fix_time_fields(rows, headers):
    """
    將 Excel 時間序號 (fraction of a day, e.g. 0.625) 轉為 hh:mm
    若為文字格式的時間（15:00）則保留原樣
    """
    time_fields = {"DrugGivenAt", "ExpectedTitrationStart", "ExpectedTitrationEnd"}
    fixed = []
    idxs = {h: i for i, h in enumerate(headers) if h in time_fields}
    if not idxs:
        return rows

    for r in rows:
        r = list(r)
        for h, i in idxs.items():
            val = str(r[i]).strip()
            if not val:
                continue

            # ✅ 若是數值（Excel 時間序號）
            try:
                f = float(val)
                if 0 <= f < 1:
                    seconds = int(round(f * 86400))
                    hh = seconds // 3600
                    mm = (seconds % 3600) // 60
                    r[i] = f"{hh:02d}:{mm:02d}"
                    continue
            except Exception:
                pass

            # ✅ 若是日期時間格式 (e.g. 1899-12-30 15:00:00)
            try:
                if "1899" in val or "1900" in val:
                    dt = datetime.datetime.fromisoformat(val)
                    r[i] = dt.strftime("%H:%M")
                    continue
            except Exception:
                pass

            # ✅ 若是正常時間字串 "15:00", "3:30 PM"
            parsed = None
            for fmt in ("%H:%M", "%I:%M %p", "%H:%M:%S"):
                try:
                    parsed = datetime.datetime.strptime(val, fmt)
                    break
                except Exception:
                    continue
            if parsed:
                r[i] = parsed.strftime("%H:%M")

        fixed.append(r)
    return fixed


# ==================== ROUTES ====================

@app.post("/api/upload_droplet_schedule")
def upload_droplet_schedule():
    """
    支援 text/csv / multipart/form-data / JSON
    - 自動修正 Date 欄與時間欄格式
    """
    mode = (request.args.get("mode") or "").lower()
    headers, rows = [], []
    ctype = (request.content_type or "").lower()

    if "multipart/form-data" in ctype:
        # Handles file uploads from a standard form
        if "file" not in request.files:
            return Response("missing file", 400)
        # Uses the robust "utf-8-sig" decoding for files
        headers, rows = parse_csv_file(request.files["file"])

    elif "application/json" in ctype:
        # Handles JSON payloads
        payload = request.get_json(silent=True) or {}
        headers = [remove_cn_spaces(h) for h in (payload.get("headers") or [])]
        rows = payload.get("rows") or []

    elif "text/csv" in ctype or request.data:
        # Handles raw CSV data sent as the request body (like from the VBA client)
        data = request.get_data() # Get data as raw bytes
        if not data:
             return Response("empty request body", 400)

        # **CRITICAL FIX: Decode using "utf-8-sig" to handle BOM**
        try:
            text = data.decode("utf-8-sig", errors="replace")
        except UnicodeDecodeError:
            # Should not happen with errors="replace" but provides a safety net
            return Response("CSV decoding failed due to incorrect encoding or corrupted data.", 400)

        headers, rows = parse_csv_text(text)

    else:
        return Response("unsupported content-type", 415)

    if not headers:
        return Response("empty headers or data", 400)

    # --- Database Processing ---
    try:
        with connect() as conn:
            if mode == "replace":
                truncate_table(conn)

            # 1. Normalize headers and ensure table/columns exist
            cols = ensure_table_and_columns(conn, headers)

            # 2. Apply data fixes (date/time parsing)
            # Note: fix_date_field and fix_time_fields should handle potential parsing errors gracefully
            # by falling back to the original string value.
            rows = fix_date_field(rows, cols)
            rows = fix_time_fields(rows, cols)

            # 3. Clean and prepare rows for insertion
            clean_rows = []
            for r in rows:
                row = [remove_cn_spaces(v) for v in r]
                # Ensure every row has the same number of columns as the header definition
                row += [""] * max(0, len(cols) - len(row))
                clean_rows.append(row[:len(cols)])

            # 4. Execute bulk insertion
            placeholders = ", ".join("?" for _ in cols)
            collist = ", ".join(f'"{c}"' for c in cols)
            sql = f'INSERT INTO "{TABLE_NAME}" ({collist}) VALUES ({placeholders})'
            conn.executemany(sql, clean_rows)
            conn.commit()

        return Response(status=204) # 204 No Content is standard for a successful PUT/POST with no response body

    except sqlite3.Error as e:
        # Catch explicit DB errors
        app.logger.error(f"Database Error: {e}")
        return Response(f"Database operation failed: {e}", 500)
    except Exception as e:
        # Catch any other unexpected server-side errors
        app.logger.error(f"Unexpected Server Error during upload: {e}")
        return Response("Internal Server Error during data processing.", 500)


@app.get("/api/preview")
def preview():
    limit = int(request.args.get("limit", "50"))
    with connect() as conn:
        if not table_exists(conn, TABLE_NAME):
            return jsonify({"columns": [], "rows": []})
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{TABLE_NAME}")')]
        cur = conn.execute(f'SELECT * FROM "{TABLE_NAME}" LIMIT {limit}')
        rows = [dict(r) for r in cur.fetchall()]
        return jsonify({"columns": cols, "rows": rows})


# ==================== MAIN ====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5011, debug=True)
