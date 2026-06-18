# app_csv_update.py
# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify
import sqlite3, pandas as pd, datetime as dt, re, os, time
from io import StringIO
from pandas.api.types import is_datetime64_any_dtype as is_datetime
from datetime import datetime, timedelta

# === DB 路徑 ===
DB_PATH = r"D:\VBAforbeadsprod\beads_sync.db"  # DB實際路徑
# A → beads_Inventory (key: PN + Batch)；B → production_Plan (key: PN)
TABLE_MAP = {
    "A": {"table": "beads_Inventory", "keys": ["PN", "Batch"]},
    "B": {"table": "production_Plan", "keys": ["PN"]},
}

# ---------- 連線 & 通用工具 ----------
def open_conn():
    """每次開啟連線時，強制使用單檔模式(DELETE)並設置常用 PRAGMA。"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=DELETE;")   # 關 WAL，避免外部工具看不到最新內容
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    return conn

def safe_ident(name: str) -> str:
    """將欄名/表名轉為可安全置於 SQL 的識別字。"""
    if name is None:
        name = ""
    name = str(name).replace('"', '""').strip()
    return name if name else "_col_"

# 日期/內容正規化
EXCEL_EPOCH = datetime(1899, 12, 30)  # Windows Excel serial 1 = 1899-12-31，實務用 1899-12-30
DATE_COLS = {"生產日期", "效期"}  # 需要可再加

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
    """將 DataFrame 內容正規化成字串；清理錯誤字樣；將指定欄位的日期轉 YYYY-MM-DD。"""
    out = df.copy().fillna("").astype(str)
    # 清除 Excel 錯誤字樣
    out = out.replace(
        {r"^\s*錯誤\s*2042\s*$": "", r"^\s*Error\s*2042\s*$": "", r"^\s*#N/?A\s*$": ""},
        regex=True,
    )
    # 指定日期欄做轉換
    for col in list(out.columns):
        base = col.strip()
        if base in DATE_COLS:
            out[col] = out[col].map(excel_serial_to_date_str).map(_canon_date)
    return out

# ---------- 結構維護 ----------
def ensure_table_and_columns(conn: sqlite3.Connection, table: str, df: pd.DataFrame):
    """建表（若無）並自動補缺欄位；用大小寫不敏感比對，避免重複加欄。"""
    table_q = safe_ident(table)
    cols_sql = ", ".join([f'"{safe_ident(c)}" TEXT' for c in df.columns])
    with conn:
        conn.execute(f'CREATE TABLE IF NOT EXISTS "{table_q}" ({cols_sql});')
        cur = conn.execute(f'PRAGMA table_info("{table_q}")')
        existing = [row[1] for row in cur.fetchall()]
        existing_ci = {str(e).strip().lower() for e in existing}  # ★ 大小寫不敏感

        for c in df.columns:
            cq = safe_ident(c)
            key = cq.strip().lower()
            if key not in existing_ci:
                try:
                    conn.execute(f'ALTER TABLE "{table_q}" ADD COLUMN "{cq}" TEXT;')
                    existing_ci.add(key)
                except sqlite3.OperationalError as e:
                    # 若別處已加過、或 SQLite 判定同名（大小寫差異），就忽略
                    if "duplicate column name" in str(e).lower():
                        existing_ci.add(key)
                    else:
                        raise


def ensure_unique_index(conn: sqlite3.Connection, table: str, keys: list[str]):
    """建立唯一索引（若不存在）。"""
    if not keys: return
    table_q = safe_ident(table)
    keys_q  = [safe_ident(k) for k in keys]
    idx     = f'ux_{table_q}_' + "_".join([k.lower() for k in keys_q])
    cols    = ",".join([f'"{k}"' for k in keys_q])
    with conn:
        conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "{idx}" ON "{table_q}" ({cols});')

# ---------- UPSERT ----------
def upsert(conn: sqlite3.Connection, table: str, df: pd.DataFrame, keys: list[str]) -> int:
    """以 keys 做 UPSERT；只在值不同時 UPDATE。回傳本次實際更動列數。"""
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
        diff_pred  = " OR ".join([f'"{c}" IS NOT excluded."{c}"' for c in nonkeys_q])  # 值不同才更新
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
        # 寫入後做 checkpoint（即使非 WAL 也不影響）
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
    after = conn.total_changes
    return after - before

# ---------- Flask ----------
app = Flask(__name__)

@app.post("/update_rows_csv")
def update_rows_csv():
    """
    以 CSV 作為 request body，上傳一批列。
    用 querystring 指定 ?file=A 或 ?file=B
    Content-Type: text/csv; charset=utf-8
    第一行=標題（中文可），其後為資料列。
    """
    try:
        file_tag = request.args.get("file", "").upper()
        info = TABLE_MAP.get(file_tag)
        if not info:
            return jsonify({"ok": False, "msg": "querystring 需帶 file=A 或 file=B"}), 400

        raw = request.get_data(cache=False, as_text=False)
        if not raw:
            return jsonify({"ok": False, "msg": "空的 CSV"}), 400

        # 解碼（優先 utf-8-sig，其次 CP950）
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp950", errors="ignore")

        # 讀 CSV 為 DataFrame（字串型，避免 NA 被當成 NaN）
        try:
            df = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False)
        except Exception as e:
            return jsonify({"ok": False, "msg": f"CSV parse error: {e}"}), 400
        if df.empty:
            return jsonify({"ok": False, "msg": "CSV has header but no data rows"}), 400

        # 欄名白名單 + 對映
        ALLOWED = ["限制","PN","BEADS別","保存期限 (天)","Unrestricted","Batch",
           "生產日期","併批","備註","效期","BEADS工單","工單數","入庫","累計領用","可使用庫存"]

        CANON = {
            "保存期限_天": "保存期限 (天)",
            "beads工單": "BEADS工單",
            "BEAD工單": "BEADS工單",
            "Beads工單": "BEADS工單",
        }
        df.columns = [CANON.get(str(c).strip(), str(c).strip()) for c in df.columns]
        keep = [c for c in ALLOWED if c in df.columns]
        if not keep:
            return jsonify({"ok": False, "msg": "no allowed columns in CSV header"}), 400
        df = df[keep].copy()

        # 必要鍵檢查
        missing = [k for k in info["keys"] if k not in df.columns]
        if missing:
            return jsonify({"ok": False, "msg": f"missing key columns: {missing}"}), 400

        # 修剪鍵值、刪掉鍵值空白的列
        for k in info["keys"]:
            df[k] = df[k].astype(str).str.strip()
        mask = df[info["keys"]].apply(lambda s: s.str.len() > 0).all(axis=1)
        df = df.loc[mask].copy()
        if df.empty:
            # 沒有可寫入的資料列也要回 200，避免前端誤判
            st = os.stat(DB_PATH)
            return jsonify({
                "ok": True,
                "table": info["table"],
                "rows": 0,
                "total_changes": 0,
                "db_path": os.path.abspath(DB_PATH),
                "db_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
            }), 200

        # 內容正規化（日期/錯誤字樣）
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
        # 無論什麼錯都保證回傳 JSON
        return jsonify({"ok": False, "msg": f"internal error: {e}"}), 500



@app.get("/debug_row")
def debug_row():
    pn = request.args.get("pn", "")
    batch = request.args.get("batch", "")
    if not pn or not batch:
        return jsonify({"ok": False, "msg": "need pn and batch"}), 400
    with open_conn() as conn:
        cur = conn.execute(
            f'SELECT * FROM "{safe_ident("beads_Inventory")}" '
            f'WHERE "{safe_ident("PN")}"=? AND "{safe_ident("Batch")}"=?',
            (pn, batch),
        )
        row = cur.fetchone()
        cols = [d[0] for d in cur.description] if cur.description else []
    return jsonify({
        "ok": True,
        "db_path": os.path.abspath(DB_PATH),
        "found": 1 if row else 0,
        "columns": cols,
        "row": row
    })

@app.get("/debug_keys")
def debug_keys():
    pn = request.args.get("pn", "")
    if not pn:
        return jsonify({"ok": False, "msg": "need pn"}), 400
    with open_conn() as conn:
        cur = conn.execute(
            f'SELECT "{safe_ident("PN")}", "{safe_ident("Batch")}" '
            f'FROM "{safe_ident("beads_Inventory")}" WHERE "{safe_ident("PN")}"=?',
            (pn,)
        )
        rows = cur.fetchall()
    return jsonify({"ok": True, "count": len(rows), "keys": rows, "db_path": os.path.abspath(DB_PATH)})

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

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
