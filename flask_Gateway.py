# -*- coding: utf-8 -*-
"""
Beads Production Data Gateway v3 (EC2)
Port: 8100

Deploy target: ssh:beadsops-ec2
DB: /opt/beadsops/data/P01_formualte_schedule.db

Supported formats:
  - pumpno       -> table "pump No."
  - liquidFormQC -> table "Liquid form QC" (upsert by 版本+PN)

API:
GET  /api/health
POST /api/upload-table-csv?wait=1&timeout=120
GET  /api/job/<job_id>
GET  /api/formats
"""

from __future__ import annotations
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import pandas as pd
import queue
import threading
import uuid
import hashlib
import time
import traceback
import io
from datetime import datetime
from pathlib import Path
from typing import Dict, Callable, Any, Optional

# =========================
# App
# =========================
app = Flask(__name__)
CORS(app)
PORT = 8100

# =========================
# Config
# =========================
DB_PATH = "/opt/beadsops/data/P01_formualte_schedule.db"
LOG_DB_PATH = "/opt/beadsops/logs/gateway_log.db"

OVERWRITE_POLICY = "drop"
HASH_TTL = 5

# =========================
# Utilities
# =========================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def ensure_parent_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)

def connect_db() -> sqlite3.Connection:
    ensure_parent_dir(DB_PATH)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=15000;")
    return conn

def sanitize_columns(cols) -> list[str]:
    out = []
    for c in cols:
        c = str(c).strip()
        if not c or c.lower().startswith("unnamed"):
            out.append("")
        else:
            out.append(c)
    return [c for c in out if c != ""]

def df_from_csv_text(csv_text: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(csv_text), dtype=str, keep_default_na=False)
    df.columns = sanitize_columns(df.columns)
    df = df.loc[:, [c for c in df.columns if c != ""]]
    df = df.dropna(how="all")
    return df

# =========================
# Format Registry
# =========================
FORMAT_REGISTRY: Dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {}

def register_format(name: str):
    def wrap(fn):
        FORMAT_REGISTRY[name] = fn
        return fn
    return wrap

@register_format("pumpno")
def transform_pumpno(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "pump編號" not in df.columns:
        raise ValueError("pumpno format missing column: pump編號")
    df = df.dropna(how="all")
    df.loc[:, "pump編號"] = (
        df["pump編號"].astype(str).str.strip().str.replace(".0", "", regex=False)
    )
    df = df.drop_duplicates()
    return df

@register_format("liquidFormQC")
def transform_liquid_form_qc(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.dropna(how="all")
    df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]

    rename_map = {
        "Liquid 外觀": "懸浮物",
    }
    df = df.rename(columns=rename_map)

    required_cols = [
        "Marker name", "PN", "Name", "懸浮物", "反應後呈色",
        "absorbance wavelength", "L1-OD", "L2-OD",
        "L1-起始OD", "L2-起始OD", "版本",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"liquidFormQC format missing columns: {missing}")

    df = df[required_cols].copy()
    df["Marker name"] = df["Marker name"].astype(str).str.strip()
    df = df[df["Marker name"] != ""]
    for c in required_cols:
        df[c] = df[c].astype(str).str.strip()
    df["PN"] = df["PN"].str.replace(".0", "", regex=False)
    df = df.drop_duplicates()

    if df.empty:
        raise ValueError("no rows after transform")
    return df

# =========================
# Upload Dedup
# =========================
UPLOAD_HASH_CACHE: Dict[str, float] = {}
HASH_LOCK = threading.Lock()

def is_duplicate_upload(csv_text: str, table: str, format_id: str) -> bool:
    key = f"{table}|{format_id}|{csv_text}"
    h = hashlib.md5(key.encode("utf-8", errors="ignore")).hexdigest()
    now = time.time()
    with HASH_LOCK:
        ts = UPLOAD_HASH_CACHE.get(h)
        if ts is not None and (now - ts) < HASH_TTL:
            return True
        UPLOAD_HASH_CACHE[h] = now
    return False

# =========================
# Job Queue
# =========================
job_q: "queue.Queue[dict]" = queue.Queue()
jobs: Dict[str, Dict[str, Any]] = {}
jobs_lock = threading.Lock()
db_lock = threading.Lock()

def new_job(payload: dict) -> str:
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now_str(),
            "started_at": None,
            "ended_at": None,
            "payload_meta": {
                "table": payload.get("table"),
                "format_id": payload.get("format_id"),
                "csv_len": len(payload.get("csv_text") or ""),
            },
            "result": None,
            "error": None,
        }
    job_q.put({"job_id": job_id, "payload": payload})
    return job_id

def set_job(job_id: str, **kw):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kw)

# =========================
# Log DB
# =========================
def log_init():
    ensure_parent_dir(LOG_DB_PATH)
    conn = sqlite3.connect(LOG_DB_PATH)
    try:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS upload_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            client_ip TEXT,
            job_id TEXT,
            table_name TEXT,
            format_id TEXT,
            rows INTEGER,
            status TEXT,
            error TEXT
        );
        """)
        conn.commit()
    finally:
        conn.close()

def log_upload(client_ip: str, job_id: str, table: str, format_id: str,
               rows: Optional[int], status: str, error: Optional[str]):
    conn = sqlite3.connect(LOG_DB_PATH)
    try:
        conn.execute(
            "INSERT INTO upload_log(ts, client_ip, job_id, table_name, format_id, rows, status, error) VALUES (?,?,?,?,?,?,?,?)",
            (now_str(), client_ip, job_id, table, format_id, rows, status, error)
        )
        conn.commit()
    finally:
        conn.close()

log_init()

# =========================
# DB write helpers
# =========================
def create_table_drop(conn: sqlite3.Connection, table: str, cols: list[str]):
    conn.execute(f'DROP TABLE IF EXISTS "{table}";')
    col_defs = ", ".join([f'"{c}" TEXT' for c in cols])
    conn.execute(f'CREATE TABLE "{table}" ({col_defs});')

def insert_rows(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> int:
    cols = list(df.columns)
    col_sql = ", ".join([f'"{c}"' for c in cols])
    placeholders = ", ".join(["?"] * len(cols))
    sql = f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders});'
    conn.executemany(sql, df[cols].values.tolist())
    return len(df)

def write_table_full(table: str, df: pd.DataFrame) -> int:
    cols = list(df.columns)
    if not cols:
        raise ValueError("No columns found in dataframe")
    with db_lock:
        conn = connect_db()
        try:
            create_table_drop(conn, table, cols)
            rows = insert_rows(conn, table, df)
            conn.commit()
            return rows
        finally:
            conn.close()

def write_liquid_form_qc_upsert(table: str, df: pd.DataFrame) -> int:
    required_cols = [
        "Marker name", "PN", "Name", "懸浮物", "反應後呈色",
        "absorbance wavelength", "L1-OD", "L2-OD",
        "L1-起始OD", "L2-起始OD", "版本",
    ]
    df = df[required_cols].copy()
    df = df.drop_duplicates()

    with db_lock:
        conn = connect_db()
        try:
            cur = conn.cursor()
            col_defs = ", ".join([f'"{c}" TEXT' for c in required_cols])
            cur.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({col_defs});')

            idx_name = f'idx_{table.replace(" ", "_")}_ver_pn'
            cur.execute(f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table}" ("版本", "PN");')

            for ver, pn in df[["版本", "PN"]].drop_duplicates().values.tolist():
                cur.execute(f'DELETE FROM "{table}" WHERE "版本" = ? AND "PN" = ?', (ver, pn))

            col_sql = ", ".join([f'"{c}"' for c in required_cols])
            placeholders = ", ".join(["?"] * len(required_cols))
            cur.executemany(
                f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders})',
                df.values.tolist()
            )
            conn.commit()
            return len(df)
        finally:
            conn.close()

# =========================
# Worker
# =========================
def worker_loop():
    while True:
        item = job_q.get()
        job_id = item["job_id"]
        payload = item["payload"]

        set_job(job_id, status="running", started_at=now_str())

        client_ip = payload.get("__client_ip", "")
        table = payload["table"]
        format_id = payload.get("format_id") or ""
        rows_written: Optional[int] = None

        try:
            csv_text = payload["csv_text"]
            df = df_from_csv_text(csv_text)

            if format_id:
                fn = FORMAT_REGISTRY.get(format_id)
                if not fn:
                    raise ValueError(f"unknown format_id: {format_id}")
                df = fn(df)

            df = df.dropna(how="all")
            if df.empty:
                raise ValueError("no rows after transform")

            if format_id == "liquidFormQC" and table == "Liquid form QC":
                rows_written = write_liquid_form_qc_upsert(table, df)
            else:
                rows_written = write_table_full(table, df)

            result = {"ok": True, "rows": rows_written}
            set_job(job_id, status="done", ended_at=now_str(), result=result, error=None)
            log_upload(client_ip, job_id, table, format_id, rows_written, "done", None)

        except Exception as e:
            err = f"{e}\n{traceback.format_exc()}"
            set_job(job_id, status="failed", ended_at=now_str(), result={"ok": False, "error": str(e)}, error=err)
            log_upload(client_ip, job_id, table, format_id, rows_written, "failed", str(e))

        finally:
            job_q.task_done()

threading.Thread(target=worker_loop, daemon=True).start()

# =========================
# API
# =========================
@app.get("/api/health")
def api_health():
    return jsonify({
        "ok": True,
        "port": PORT,
        "db": DB_PATH,
        "queue_size": job_q.qsize(),
        "overwrite_policy": OVERWRITE_POLICY,
        "formats": list(FORMAT_REGISTRY.keys()),
        "time": now_str(),
    }), 200

@app.get("/api/formats")
def api_formats():
    return jsonify({"ok": True, "formats": list(FORMAT_REGISTRY.keys())}), 200

@app.get("/api/job/<job_id>")
def api_job(job_id: str):
    with jobs_lock:
        j = jobs.get(job_id)
    if not j:
        return jsonify({"ok": False, "error": "job not found"}), 404
    return jsonify({"ok": True, "job": j, "queue_size": job_q.qsize()}), 200

@app.post("/api/upload-table-csv")
def api_upload_table_csv():
    p = request.get_json(force=True, silent=False) or {}

    for k in ("table", "csv_text"):
        if not p.get(k):
            return jsonify({"ok": False, "error": f"missing {k}"}), 400

    table = str(p["table"])
    csv_text = str(p["csv_text"])
    format_id = str(p.get("format_id") or "")

    if format_id and format_id not in FORMAT_REGISTRY:
        return jsonify({"ok": False, "error": f"unknown format_id: {format_id}"}), 400

    if is_duplicate_upload(csv_text, table, format_id):
        return jsonify({
            "ok": True,
            "note": "duplicate upload skipped",
            "job_status": "done",
            "result_ok": True,
            "rows": None,
            "result_error": None,
            "table": table,
            "format_id": format_id,
        }), 200

    p["__client_ip"] = request.remote_addr or ""
    job_id = new_job(p)

    wait = (request.args.get("wait") == "1")
    if wait:
        timeout = float(request.args.get("timeout", 60))
        t0 = time.time()

        while time.time() - t0 < timeout:
            with jobs_lock:
                j = jobs.get(job_id)
                if not j:
                    return jsonify({"ok": False, "error": "job not found"}), 404

                st = j.get("status")
                if st in ("done", "failed"):
                    result = j.get("result") or {}
                    return jsonify({
                        "job_id": job_id,
                        "job_status": st,
                        "result_ok": result.get("ok"),
                        "rows": result.get("rows"),
                        "result_error": (result.get("error") or j.get("error")),
                        "note": None,
                        "table": table,
                        "format_id": format_id,
                    }), 200
            time.sleep(0.2)

        return jsonify({
            "job_id": job_id,
            "job_status": "queued_or_running",
            "result_ok": None,
            "rows": None,
            "result_error": None,
            "note": "timeout_wait",
            "table": table,
            "format_id": format_id,
        }), 202

    return jsonify({"ok": True, "job_id": job_id, "status": "queued"}), 202

if __name__ == "__main__":
    print("Loaded formats:", list(FORMAT_REGISTRY.keys()))
    print(f"🚀 Gateway v3 EC2 running on 0.0.0.0:{PORT}")
    print(f"   DB: {DB_PATH}")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
