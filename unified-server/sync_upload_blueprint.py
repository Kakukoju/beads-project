# -*- coding: utf-8 -*-
"""
sync_upload_blueprint.py
通用 Excel → SQLite 同步 API
供 VBA (Workbook_BeforeSave / 手動按鈕) 呼叫
"""
import sqlite3
import csv
import io
import re
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

sync_upload_bp = Blueprint("sync_upload", __name__)

# ── DB 對照表 ──
DB_MAP = {
    "formulate": "/opt/beadsops/data/P01_formualte_schedule.db",
    "bead_sort": "/opt/beadsops/data/Bead_Sort_DB.db",
    "ipqc":      "/opt/beadsops/data/P01_Beads_IPQC.db",
}

SYNC_LOG_DDL = """
CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    action TEXT,
    row_count INTEGER,
    source TEXT,
    status TEXT,
    error_msg TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
)"""


def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_table_cols(conn, table, cols):
    col_defs = ", ".join(f'"{c}" TEXT' for c in cols)
    conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({col_defs})')
    existing = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
    for c in cols:
        if c not in existing:
            conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{c}" TEXT')


def _log_sync(conn, table, action, count, status, error=""):
    conn.execute(SYNC_LOG_DDL)
    conn.execute(
        "INSERT INTO sync_log(table_name,action,row_count,source,status,error_msg) VALUES(?,?,?,?,?,?)",
        (table, action, count, "vba_upload", status, error),
    )


def _parse_csv_payload(data: bytes):
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return [], []
    headers = [h.strip() for h in rows[0]]
    return headers, rows[1:]


def _sanitize_col(name: str) -> str:
    s = name.strip().replace("\u3000", "").replace("\xa0", "")
    return s if s else "col"


# ── 通用 sync endpoint ──
@sync_upload_bp.post("/api/sync/<db_name>/<table_name>")
def sync_table(db_name, table_name):
    """
    接收 CSV 或 JSON，寫入指定 DB / table。
    Query params:
      - action: upsert (default) | replace | append
      - keys:   upsert 用的主鍵欄位，逗號分隔 (e.g. keys=PN,Batch)
    """
    if db_name not in DB_MAP:
        return jsonify(ok=False, error=f"unknown db: {db_name}"), 400

    action = (request.args.get("action") or "replace").lower()
    key_str = request.args.get("keys", "")
    keys = [k.strip() for k in key_str.split(",") if k.strip()]

    # ── 解析 payload ──
    ctype = (request.content_type or "").lower()
    headers, rows = [], []

    if "application/json" in ctype:
        payload = request.get_json(silent=True) or {}
        headers = [_sanitize_col(h) for h in payload.get("headers", [])]
        rows = payload.get("rows", [])
    else:
        # CSV (text/csv or raw body)
        data = request.get_data()
        if not data:
            return jsonify(ok=False, error="empty body"), 400
        headers, rows = _parse_csv_payload(data)
        headers = [_sanitize_col(h) for h in headers]

    if not headers:
        return jsonify(ok=False, error="no headers"), 400

    db_path = DB_MAP[db_name]
    conn = _get_conn(db_path)
    try:
        _ensure_table_cols(conn, table_name, headers)

        col_list = ", ".join(f'"{c}"' for c in headers)
        placeholders = ", ".join("?" for _ in headers)

        # 對齊每列欄位數
        clean = []
        n = len(headers)
        for r in rows:
            r = list(r)
            r += [""] * max(0, n - len(r))
            clean.append(tuple(r[:n]))

        if action == "replace":
            conn.execute(f'DELETE FROM "{table_name}"')
            conn.executemany(
                f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})', clean
            )
        elif action == "upsert" and keys:
            conflict = ", ".join(f'"{k}"' for k in keys)
            nonkeys = [c for c in headers if c not in keys]
            set_clause = ", ".join(f'"{c}"=excluded."{c}"' for c in nonkeys)
            if not set_clause:
                set_clause = f'"{keys[0]}"=excluded."{keys[0]}"'
            # ensure unique index
            idx = f'ux_{table_name}_{"_".join(keys)}'
            try:
                conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "{idx}" ON "{table_name}" ({conflict})')
            except sqlite3.OperationalError:
                pass
            sql = (
                f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders}) '
                f'ON CONFLICT ({conflict}) DO UPDATE SET {set_clause}'
            )
            conn.executemany(sql, clean)
        else:
            # append
            conn.executemany(
                f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})', clean
            )

        conn.commit()
        _log_sync(conn, table_name, action, len(clean), "success")
        conn.commit()
        logger.info(f"sync ok: {db_name}/{table_name} action={action} rows={len(clean)}")
        return jsonify(ok=True, rows=len(clean))

    except Exception as e:
        conn.rollback()
        _log_sync(conn, table_name, action, 0, "failed", str(e))
        conn.commit()
        logger.error(f"sync fail: {db_name}/{table_name} {e}")
        return jsonify(ok=False, error=str(e)), 500
    finally:
        conn.close()


# ── 查詢 sync log ──
@sync_upload_bp.get("/api/sync/log")
def get_sync_log():
    db_name = request.args.get("db", "formulate")
    limit = request.args.get("limit", 50, type=int)
    if db_name not in DB_MAP:
        return jsonify(ok=False, error="unknown db"), 400
    conn = _get_conn(DB_MAP[db_name])
    try:
        conn.execute(SYNC_LOG_DDL)
        cur = conn.execute(
            "SELECT id,table_name,action,row_count,source,status,error_msg,created_at "
            "FROM sync_log ORDER BY id DESC LIMIT ?", (limit,)
        )
        cols = [d[0] for d in cur.description]
        return jsonify(ok=True, logs=[dict(zip(cols, r)) for r in cur.fetchall()])
    finally:
        conn.close()


# ── health check ──
@sync_upload_bp.get("/api/sync/health")
def sync_health():
    return jsonify(ok=True, ts=datetime.now().isoformat(), dbs=list(DB_MAP.keys()))
