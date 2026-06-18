# 配藥Server - 接收 CSV 上傳並存入 SQLite（支援 return=csv 回傳工單結果）
# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, Response
from pathlib import Path
import sqlite3, csv, io, re, logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ===== 基本設定 =====
DB_PATH = Path(r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\資料庫\配藥\P01_v1.db")  # SQLite 檔案路徑
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

AUTH_TOKEN = ""  # 例如 "s3cr3t"；空字串=不驗證
# ===================


# ---------------- 共用小工具 ----------------
def auth_ok() -> bool:
    return (not AUTH_TOKEN) or request.headers.get("Authorization", "") == ("Bearer " + AUTH_TOKEN)

def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'

def get_existing_cols(con: sqlite3.Connection, table: str):
    cur = con.execute(f'PRAGMA table_info({qident(table)});')
    return [r[1] for r in cur.fetchall()]

def ensure_table_and_columns(con: sqlite3.Connection, table: str, headers: list[str]) -> None:
    # 建表（若無），或補缺欄
    cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table,))
    exists = cur.fetchone() is not None
    if not exists:
        cols_def = ", ".join(f'{qident(h)} TEXT' for h in headers)
        con.execute(f'CREATE TABLE {qident(table)} ({cols_def});')
        return
    existing = set(get_existing_cols(con, table))
    for h in headers:
        if h not in existing:
            con.execute(f'ALTER TABLE {qident(table)} ADD COLUMN {qident(h)} TEXT;')

def ensure_unique_index(con: sqlite3.Connection, table: str, pk_cols: list[str]) -> None:
    if not pk_cols:
        return
    idx = "ux_" + re.sub(r'[^A-Za-z0-9_]', '_', table) + "__" + "__".join(
        re.sub(r'[^A-Za-z0-9_]', '_', c) for c in pk_cols
    )
    cols = ", ".join(qident(c) for c in pk_cols)
    con.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS {qident(idx)} ON {qident(table)} ({cols});')

def upsert_rows(con: sqlite3.Connection, table: str, headers: list[str], rows: list[tuple], pk_cols: list[str]) -> tuple[int,int]:
    """回傳 (inserted, updated) 估計值（SQLite 無法100%精確取，這裡做近似）"""
    if not rows:
        return (0, 0)
    cols = ", ".join(qident(h) for h in headers)
    q = ", ".join(["?"] * len(headers))
    inserted = 0
    updated = 0
    upd_cols = [h for h in headers if h not in pk_cols]
    if upd_cols:
        upd = ", ".join(f'{qident(c)}=excluded.{qident(c)}' for c in upd_cols)
        sql = f'INSERT INTO {qident(table)} ({cols}) VALUES ({q}) ' \
              f'ON CONFLICT({", ".join(qident(c) for c in pk_cols)}) DO UPDATE SET {upd};'
    else:
        sql = f'INSERT INTO {qident(table)} ({cols}) VALUES ({q}) ' \
              f'ON CONFLICT({", ".join(qident(c) for c in pk_cols)}) DO NOTHING;'
    # 粗略估算：先數現有 pk，再數結束後 pk
    try:
        before = count_distinct_pk(con, table, pk_cols)
    except Exception:
        before = None
    con.executemany(sql, rows)
    try:
        after = count_distinct_pk(con, table, pk_cols)
        if before is not None:
            inserted = max(0, after - before)
            updated = max(0, len(rows) - inserted)
    except Exception:
        pass
    return (inserted, updated)

def insert_rows(con: sqlite3.Connection, table: str, headers: list[str], rows: list[tuple]) -> int:
    if not rows:
        return 0
    cols = ", ".join(qident(h) for h in headers)
    q = ", ".join(["?"] * len(headers))
    con.executemany(f'INSERT INTO {qident(table)} ({cols}) VALUES ({q});', rows)
    return len(rows)

def replace_rows(con: sqlite3.Connection, table: str, headers: list[str], rows: list[tuple]) -> int:
    con.execute(f'DELETE FROM {qident(table)};')
    return insert_rows(con, table, headers, rows)

def count_distinct_pk(con: sqlite3.Connection, table: str, pk_cols: list[str]) -> int:
    if not pk_cols:
        cur = con.execute(f'SELECT COUNT(*) FROM {qident(table)};')
    else:
        cols = ", ".join(qident(c) for c in pk_cols)
        cur = con.execute(f'SELECT COUNT(DISTINCT {cols}) FROM {qident(table)};')
    return int(cur.fetchone()[0])

def parse_csv_text(text: str) -> tuple[list[str], list[tuple]]:
    """以 UTF-8(-sig) 解析 CSV 文字，回傳 (headers, rows)"""
    # 去除 BOM
    if text and text[:1] == '\ufeff':
        text = text.lstrip('\ufeff')
    reader = csv.reader(io.StringIO(text))
    try:
        headers = next(reader)
    except StopIteration:
        headers = []
    headers = [h.strip() if h else f"col_{i+1}" for i, h in enumerate(headers)]
    rows = []
    for r in reader:
        if len(r) < len(headers):
            r = r + [""] * (len(headers) - len(r))
        elif len(r) > len(headers):
            r = r[:len(headers)]
        rows.append(tuple(r))
    return headers, rows

def get_mode() -> str:
    mode = (request.form.get("mode") or request.args.get("mode") or "replace").strip().lower()
    if mode not in ("append", "replace", "upsert"):
        mode = "replace"
    return mode

def want_csv_response() -> bool:
    """是否回傳純文字 CSV 結果（用於前端 VBA 逐工單畫勾/叉）"""
    return (request.args.get("return") or "").strip().lower() == "csv"

def extract_work_orders(headers: list[str], rows: list[tuple]) -> list[str]:
    """
    從上傳內容中蒐集「工單號碼」欄位的唯一清單。
    欄位名優先比對中文 '工單號碼'，若沒有可擴充其他別名。
    """
    # 你也可在這裡支援別名： e.g. 'work_order', '工單'
    candidates = ["工單號碼"]
    idx = -1
    for name in candidates:
        try:
            idx = headers.index(name)
            break
        except ValueError:
            continue
    if idx < 0:
        return []
    seen = set()
    out = []
    for r in rows:
        if idx < len(r):
            wo = str(r[idx]).strip()
            if wo and wo not in seen:
                seen.add(wo)
                out.append(wo)
    return out

def to_csv_response_line_list(work_orders: list[str], status: str) -> str:
    """
    產生純文字 CSV，表頭固定 'work_order,status'
    每個工單一列，status= 'OK' 或 'FAIL'
    """
    buf = io.StringIO()
    buf.write("work_order,status\n")
    for wo in work_orders:
        # 若工單內含逗號，可用 csv.writer；這裡假設沒有
        buf.write(f"{wo},{status}\n")
    return buf.getvalue()


# ---------------- 請求處理核心 ----------------
def handle_upload(table: str, pk_cols: list[str], headers: list[str], rows: list[tuple], mode: str):
    """
    新增：支援 return=csv
      - 成功：對本次上傳中所有出現的工單號碼回 'OK'
      - 失敗：對本次上傳中所有出現的工單號碼回 'FAIL'
    備註：
      若要更精細到「每列是否入庫」，需逐列 try/except，但成本較高。
      目前策略：只要整體 DB 操作成功，視為該批工單皆 OK。
    """
    if not table:
        return jsonify({"ok": False, "error": "missing table"}), 400

    # 若未指定 pk，且表頭有「工單號碼,料號」或「工單號碼」可自動採用
    if not pk_cols:
        if "工單號碼" in headers and "料號" in headers:
            pk_cols = ["工單號碼", "料號"]
        elif "工單號碼" in headers:
            pk_cols = ["工單號碼"]

    # 先把這批「工單清單」抓出來，成功/失敗都要回（VBA 要逐欄標記）
    batch_work_orders = extract_work_orders(headers, rows)

    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=OFF;")
    con.execute("PRAGMA temp_store=MEMORY;")

    try:
        with con:
            ensure_table_and_columns(con, table, headers)
            if pk_cols:
                ensure_unique_index(con, table, pk_cols)

            # 模式決策
            if mode == "append":
                if pk_cols:
                    upsert_rows(con, table, headers, rows, pk_cols)  # 有 pk → 視為 upsert append
                else:
                    insert_rows(con, table, headers, rows)  # 純累加
            elif mode == "upsert":
                if not pk_cols:
                    return jsonify({"ok": False, "error": "pk required for upsert"}), 400
                upsert_rows(con, table, headers, rows, pk_cols)
            else:  # replace（預設）
                if pk_cols:
                    upsert_rows(con, table, headers, rows, pk_cols)
                else:
                    replace_rows(con, table, headers, rows)

    except Exception as e:
        # 失敗：return=csv 則回整批 FAIL；否則回 JSON 500
        con.close()
        if want_csv_response():
            csv_text = to_csv_response_line_list(batch_work_orders, "FAIL")
            return Response(csv_text, status=500, mimetype="text/csv; charset=utf-8")
        else:
            app.logger.exception("upload failed")
            return jsonify({"ok": False, "error": str(e)}), 500

    con.close()

    # 成功：依需求回應
    if want_csv_response():
        csv_text = to_csv_response_line_list(batch_work_orders, "OK")
        # 200 （或 201 皆可）；為了簡單就用 200
        return Response(csv_text, status=200, mimetype="text/csv; charset=utf-8")
    else:
        # 舊行為：無內容 204
        return Response(status=204)


# ---------------- 端點：multipart ----------------
@app.route("/upload_csv", methods=["POST"])
def upload_csv():
    if not auth_ok():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    table = (request.form.get("table") or request.args.get("table") or "").strip()
    pk_raw = (request.form.get("pk") or request.args.get("pk") or "").strip()
    pk_cols = [c.strip() for c in pk_raw.split(",") if c.strip()]
    mode = get_mode()

    f = request.files.get("file") or request.files.get("csv")
    if not f:
        # 附帶診斷資訊，便於前端除錯
        return jsonify({
            "ok": False,
            "error": "missing file",
            "debug": {
                "form": list(request.form.keys()),
                "files": list(request.files.keys()),
                "content_type": request.headers.get("Content-Type", ""),
            }
        }), 400

    raw = f.read()
    text = raw.decode("utf-8-sig", errors="replace")
    headers, rows = parse_csv_text(text)
    return handle_upload(table, pk_cols, headers, rows, mode)


# ---------------- 端點：raw CSV 本文 ----------------
@app.route("/upload_csv_raw", methods=["POST"])
def upload_csv_raw():
    if not auth_ok():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    table = (request.args.get("table") or "").strip()
    pk_raw = (request.args.get("pk") or "").strip()
    mode = get_mode()
    pk_cols = [c.strip() for c in pk_raw.split(",") if c.strip()]

    text = request.get_data(cache=False, as_text=True)
    if not text:
        return jsonify({"ok": False, "error": "empty body"}), 400

    headers, rows = parse_csv_text(text)
    return handle_upload(table, pk_cols, headers, rows, mode)

if __name__ == "__main__":
    # 開發可用內建；正式建議用 Waitress / gunicorn 後面掛反代
    app.run(host="0.0.0.0", port=8055)
    # from waitress import serve
    # serve(app, host="0.0.0.0", port=8055)
