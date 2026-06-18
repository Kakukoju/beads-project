# app_csv_update.py
# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
import sqlite3, pandas as pd, re, os, time
from io import StringIO
from datetime import datetime, timedelta

# === 基本設定 ===
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\beads_sync.db"   # 請確認路徑
REMOVE_MONTH_LABELS = True                      # True: 會移除 JAN..DEC 欄位；False: 保留

# 寬表設計：A 與 B 的唯一鍵
TABLE_MAP = {
    "A": {"table": "beads_Inventory", "keys": ["PN", "Batch"]},
    "B": {"table": "production_Plan", "keys": ["PN"]},  # B = 寬表，以 PN 為鍵
}

# ---------- 連線 ----------
def open_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=DELETE;")  # 關 WAL，DB Browser 立即可見
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    return conn

def safe_ident(name: str) -> str:
    if name is None: name = ""
    name = str(name).replace('"', '""').strip()
    return name if name else "_col_"

# ---------- 資料值正規化 ----------
EXCEL_EPOCH = datetime(1899, 12, 30)

DATE_COLS = {
    # A
    "生產日期", "效期",
    # B 若有固定日期欄（非 F:PQ 表頭），可加在這裡
    "排程日期", "預計包裝日", "預計生產日", "下單日", "交期", "預計到料日",
}

def excel_serial_to_date_str(s: str) -> str:
    if s is None: return ""
    t = str(s).strip()
    if re.fullmatch(r"\d{1,6}", t):
        try:
            dnum = int(t)
            if 1 <= dnum <= 80000:
                return (EXCEL_EPOCH + timedelta(days=dnum)).strftime("%Y-%m-%d")
        except Exception:
            pass
    return t

def _canon_date(x: str) -> str:
    t = str(x).strip().replace("/", "-").replace(".", "-")
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if not m: return t
    y, mo, d = m.groups()
    try:
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    except Exception:
        return t

def normalize_df_for_sqlite(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().fillna("").astype(str)

    # 清除 Excel 錯誤字樣
    out = out.replace({
        r"^\s*錯誤\s*\d+\s*$": "",
        r"^\s*Error\s*\d+\s*$": "",
        r"^\s*#N/?A\s*$": "",
    }, regex=True)

    # 指定日期欄 → YYYY-MM-DD
    for col in list(out.columns):
        if col.strip() in DATE_COLS:
            out[col] = out[col].map(excel_serial_to_date_str).map(_canon_date)

    # 『保存期限 (天)』→ 當作純數字
    if "保存期限 (天)" in out.columns:
        out["保存期限 (天)"] = (
            out["保存期限 (天)"]
            .str.replace(",", "", regex=False)      # 去逗號
            .str.replace(r"[^\d\-]", "", regex=True) # 只留數字/負號
        )

    return out


# ---------- B 檔欄名正規化（寬表：把序列日欄名轉 YYYY-MM-DD；WK 保留） ----------
def serial_header_to_date(col: str) -> str:
    s = str(col).strip()
    # 5~6 位純數字（Excel 序列日期）
    if re.fullmatch(r"\d{5,6}", s):
        try:
            d = EXCEL_EPOCH + timedelta(days=int(s))
            return d.strftime("%Y-%m-%d")
        except Exception:
            return s
    return s

# ---------- 結構維護 ----------
def ensure_table_and_columns(conn: sqlite3.Connection, table: str, df: pd.DataFrame):
    table_q = safe_ident(table)
    cols_sql = ", ".join([f'"{safe_ident(c)}" TEXT' for c in df.columns])
    with conn:
        conn.execute(f'CREATE TABLE IF NOT EXISTS "{table_q}" ({cols_sql});')
        cur = conn.execute(f'PRAGMA table_info("{table_q}")')
        existing = [row[1] for row in cur.fetchall()]
        existing_ci = {str(e).strip().lower() for e in existing}

        for c in df.columns:
            cq = safe_ident(c)
            key = cq.strip().lower()
            if key not in existing_ci:
                try:
                    conn.execute(f'ALTER TABLE "{table_q}" ADD COLUMN "{cq}" TEXT;')
                    existing_ci.add(key)
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        existing_ci.add(key)
                    else:
                        raise

def ensure_unique_index(conn: sqlite3.Connection, table: str, keys: list[str]):
    if not keys: return
    table_q = safe_ident(table)
    keys_q  = [safe_ident(k) for k in keys]
    idx     = f'ux_{table_q}_' + "_".join([k.lower() for k in keys_q])
    cols    = ",".join([f'"{k}"' for k in keys_q])
    with conn:
        conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "{idx}" ON "{table_q}" ({cols});')

# ---------- UPSERT ----------
def upsert(conn: sqlite3.Connection, table: str, df: pd.DataFrame, keys: list[str]) -> int:
    if df is None or df.empty:
        return 0

    ensure_table_and_columns(conn, table, df)
    ensure_unique_index(conn, table, keys)

    table_q   = safe_ident(table)
    cols_q    = [safe_ident(c) for c in list(df.columns)]
    keys_q    = [safe_ident(k) for k in keys]
    keyset    = set(keys_q)
    nonkeys_q = [c for c in cols_q if c not in keyset]

    placeholders = ", ".join(["?"] * len(cols_q))
    col_list     = ", ".join([f'"{c}"' for c in cols_q])
    conflict     = ", ".join([f'"{k}"' for k in keys_q])

    if nonkeys_q:
        set_clause = ", ".join([f'"{c}"=excluded."{c}"' for c in nonkeys_q])
        # 改用 COALESCE 比較，NULL 與 "" 一致化
        diff_pred  = " OR ".join([
            f'COALESCE("{c}", "") <> COALESCE(excluded."{c}", "")' for c in nonkeys_q
        ])
        sql = (
            f'INSERT INTO "{table_q}" ({col_list}) VALUES ({placeholders}) '
            f'ON CONFLICT ({conflict}) DO UPDATE SET {set_clause} '
            f'WHERE {diff_pred};'
        )
    else:
        sql = (
            f'INSERT INTO "{table_q}" ({col_list}) VALUES ({placeholders}) '
            f'ON CONFLICT ({conflict}) DO NOTHING;'
        )

    print("[UPSERT] table=", table, "keys=", keys)
    print("[UPSERT] cols=", list(df.columns)[:8], " ... total:", len(df.columns))

    before = conn.total_changes
    with conn:
        conn.executemany(sql, df.itertuples(index=False, name=None))
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
    after = conn.total_changes
    return after - before

# ---------- Flask ----------
app = Flask(__name__)

# A 的欄名白名單；B 不套白名單（保留 Excel 的 365 天 + WK 欄）
ALLOWED_A = [
    "限制","PN","BEADS別","保存期限 (天)","Unrestricted","Batch",
    "生產日期","併批","備註","效期","BEADS工單","工單數","入庫","累計領用","可使用庫存"
]
ALLOWED_B = None

CANON = {
    # A
    "保存期限_天": "保存期限 (天)",
    "beads工單": "BEADS工單", "BEAD工單": "BEADS工單", "Beads工單": "BEADS工單",
    # B（保險）
    "desc": "Description", "描述": "Description",
}

@app.post("/update_rows_csv")
def update_rows_csv():
    """
    接收 JSON 格式的請求，內含 'file' 和 'data'。
    """
    try:
        # 檢查 Content-Type 是否為 application/json
        if not request.is_json:
            return jsonify({"ok": False, "msg": "Request must be JSON"}), 400

        # 解析 JSON 數據
        data = request.get_json()
        file_tag = data.get("file", "").upper()
        csv_text = data.get("data", "")
        
        info = TABLE_MAP.get(file_tag)
        if not info:
            return jsonify({"ok": False, "msg": "JSON payload 需帶 'file' 鍵且值為 'A' 或 'B'"}), 400
        
        if not csv_text:
            return jsonify({"ok": False, "msg": "JSON payload 中 'data' 鍵為空"}), 400

        # 這裡開始處理 CSV 數據
        try:
            df = pd.read_csv(StringIO(csv_text), dtype=str, keep_default_na=False)
        except Exception as e:
            return jsonify({"ok": False, "msg": f"CSV parse error: {e}"}), 400
        
        if df.empty:
            return jsonify({"ok": False, "msg": "CSV has header but no data rows"}), 400

        # ... (後續程式碼保持不變)
        # 你的程式碼從這裡開始繼續執行
        # 欄名對映
        cols = [str(c).strip() for c in df.columns]
        cols = [CANON.get(c, c) for c in cols]
        
        # ... (其餘邏輯保持不變)
        if file_tag == "B":
            # 1) 將 Excel 序列日欄名（如 45663）轉為 YYYY-MM-DD，WKxx 保留原樣
            cols = [serial_header_to_date(c) for c in cols]
            df.columns = cols
            # 2) 可選：移除純月份標籤欄（避免汙染 schema）
            if REMOVE_MONTH_LABELS:
                MONTH_LABELS = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"}
                df = df[[c for c in df.columns if c not in MONTH_LABELS]].copy()
        else:
            df.columns = cols

        # 白名單
        if file_tag == "A":
            keep = [c for c in ALLOWED_A if c in df.columns]
            if not keep:
                return jsonify({"ok": False, "msg": "no allowed columns in CSV header (A)"}), 400
            df = df[keep].copy()
        else:
            df = df.copy() # B：保留全部（已處理欄名）

        # 必要鍵
        missing = [k for k in info["keys"] if k not in df.columns]
        if missing:
            return jsonify({"ok": False, "msg": f"missing key columns: {missing}"}), 400

        # 修剪鍵值、移除鍵空白列
        for k in info["keys"]:
            df[k] = df[k].astype(str).str.strip()
        mask_keys = df[info["keys"]].apply(lambda s: s.str.len() > 0).all(axis=1)
        df = df.loc[mask_keys].copy()
        if df.empty:
            st = os.stat(DB_PATH)
            return jsonify({
                "ok": True,
                "table": info["table"],
                "rows": 0,
                "total_changes": 0,
                "db_path": os.path.abspath(DB_PATH),
                "db_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
            }), 200

        # 內容正規化（資料值）
        df = normalize_df_for_sqlite(df)

        # 寫入
        with open_conn() as conn:
            changed = upsert(conn, info["table"], df, info["keys"])

        st = os.stat(DB_PATH)
        return jsonify({
            "ok": True,
            "table": info["table"],
            "rows": int(len(df)),
            "total_changes": int(changed),
            "db_path": os.path.abspath(DB_PATH),
            "db_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
        }), 200

    except Exception as e:
        return jsonify({"ok": False, "msg": f"internal error: {e}"}), 500


# ---------- Debug ----------
@app.get("/debug_b_row")
def debug_b_row():
    pn = request.args.get("pn", "").strip()
    if not pn:
        return jsonify({"ok": False, "msg": "need pn"}), 400
    with open_conn() as conn:
        cur = conn.execute(
            f'SELECT * FROM "{safe_ident("production_Plan")}" WHERE "{safe_ident("PN")}"=?',
            (pn,)
        )
        row = cur.fetchone()
        cols = [d[0] for d in cur.description] if cur.description else []
    return jsonify({"ok": True, "db_path": os.path.abspath(DB_PATH), "found": 1 if row else 0, "columns": cols, "row": row})

@app.get("/debug_meta")
def debug_meta():
    with open_conn() as conn:
        jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
        page_cnt = conn.execute("PRAGMA page_count").fetchone()[0]
        wal_ckpt = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchall()
    st = os.stat(DB_PATH)
    return jsonify({
        "ok": True,
        "db_path": os.path.abspath(DB_PATH),
        "journal_mode": jm,
        "page_count": int(page_cnt),
        "mtime_readable": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
        "size_bytes": st.st_size,
        "wal_checkpoint": wal_ckpt
    })
@app.get("/debug_a_row")
def debug_a_row():
    pn = request.args.get("pn", "").strip()
    batch = request.args.get("batch", "").strip()
    if not pn or not batch:
        return jsonify({"ok": False, "msg": "need pn and batch"}), 400
    with open_conn() as conn:
        cur = conn.execute(
            f'SELECT * FROM "{safe_ident("beads_Inventory")}" '
            f'WHERE "{safe_ident("PN")}"=? AND "{safe_ident("Batch")}"=?',
            (pn, batch)
        )
        row = cur.fetchone()
        cols = [d[0] for d in cur.description] if cur.description else []
    return jsonify({"ok": True, "found": 1 if row else 0, "columns": cols, "row": row, "db_path": os.path.abspath(DB_PATH)})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
