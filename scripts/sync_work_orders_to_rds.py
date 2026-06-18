#!/usr/bin/env python3
"""
Watch work_orders.db for changes (watchdog) and push table `work_orders` to RDS PostgreSQL.
Schema: work_orders   Table: work_orders
"""
import os, sqlite3, psycopg2, psycopg2.extras, time, logging, re
from pathlib import Path
from threading import Timer
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

SQLITE_PATH = "/opt/beadsops/data/work_orders.db"
SCHEMA = "work_orders"
TARGET_TABLE = "work_orders"
PERIODIC_SYNC_INTERVAL = 60  # fallback sync every 60s

RDS = {
    "host": os.environ.get("RDS_HOST", "database-1.cfutwrwyrxts.ap-northeast-1.rds.amazonaws.com"),
    "port": int(os.environ.get("RDS_PORT", 5432)),
    "dbname": os.environ.get("RDS_DBNAME", "beadsdb"),
    "user": os.environ.get("RDS_USER", "harryguo"),
    "password": os.environ.get("RDS_PASSWORD", "skyla168"),
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sync-work-orders")

TYPE_MAP = {"INTEGER": "BIGINT", "REAL": "DOUBLE PRECISION", "TEXT": "TEXT", "BLOB": "BYTEA"}

VALID_NAME_RE = re.compile(r'^[\w\-\s\u4e00-\u9fff\u3400-\u4dbf()（）/]+$')


def validate_name(name):
    if not VALID_NAME_RE.match(name):
        raise ValueError(f"Invalid identifier: {name}")
    return f'"{name}"'


def pg_conn_with_retry(max_retries=3, backoff=2):
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(**RDS)
            conn.autocommit = False
            return conn
        except psycopg2.OperationalError as e:
            if attempt == max_retries - 1:
                raise
            wait = backoff * (2 ** attempt)
            log.warning(f"RDS connect failed (attempt {attempt+1}), retry in {wait}s: {e}")
            time.sleep(wait)


def sync_table():
    sqlite_con = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro", uri=True)
    cur_s = sqlite_con.execute(f'PRAGMA table_info("{TARGET_TABLE}")')
    cols = cur_s.fetchall()
    if not cols:
        sqlite_con.close()
        return

    col_names_validated = [validate_name(c[1]) for c in cols]
    col_defs = ", ".join(
        f'{validate_name(c[1])} {TYPE_MAP.get(c[2].upper(), "TEXT")}' for c in cols
    )
    col_names_str = ", ".join(col_names_validated)
    placeholders = ", ".join(["%s"] * len(cols))

    tmp_table = f"{TARGET_TABLE}_tmp"
    pg_schema = validate_name(SCHEMA)
    pg_tmp = f'{pg_schema}.{validate_name(tmp_table)}'
    pg_target = f'{pg_schema}.{validate_name(TARGET_TABLE)}'

    rows = sqlite_con.execute(f'SELECT * FROM "{TARGET_TABLE}"').fetchall()
    sqlite_con.close()

    pg = pg_conn_with_retry()
    try:
        with pg.cursor() as cur:
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS {pg_schema}')
            cur.execute(f'DROP TABLE IF EXISTS {pg_tmp}')
            cur.execute(f'CREATE TABLE {pg_tmp} ({col_defs})')

            if rows:
                sql = f'INSERT INTO {pg_tmp} ({col_names_str}) VALUES ({placeholders})'
                psycopg2.extras.execute_batch(cur, sql, rows, page_size=500)

            cur.execute(f'DROP TABLE IF EXISTS {pg_target}')
            cur.execute(f'ALTER TABLE {pg_tmp} RENAME TO {validate_name(TARGET_TABLE)}')

        pg.commit()
        log.info(f"Synced {len(rows)} rows to RDS")
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def full_sync():
    log.info("Starting work_orders sync...")
    start = time.time()
    try:
        sync_table()
    except Exception as e:
        log.error(f"Sync FAILED: {e}")
    else:
        log.info(f"Sync done in {time.time()-start:.1f}s")


class PeriodicSync:
    def __init__(self, interval):
        self.interval = interval
        self._timer = None

    def start(self):
        self._run()

    def _run(self):
        self._timer = Timer(self.interval, self._run)
        self._timer.daemon = True
        self._timer.start()
        try:
            full_sync()
        except Exception as e:
            log.error(f"Periodic sync error: {e}")

    def stop(self):
        if self._timer:
            self._timer.cancel()


class Handler(FileSystemEventHandler):
    def __init__(self):
        self.last_sync = 0

    def on_modified(self, event):
        if Path(event.src_path).name == Path(SQLITE_PATH).name:
            now = time.time()
            if now - self.last_sync > 3:
                self.last_sync = now
                try:
                    full_sync()
                except Exception as e:
                    log.error(f"Sync error: {e}")


def watch():
    full_sync()
    log.info(f"Watching {SQLITE_PATH} for changes (+ periodic every {PERIODIC_SYNC_INTERVAL}s)...")

    periodic = PeriodicSync(PERIODIC_SYNC_INTERVAL)
    periodic.start()

    observer = Observer()
    observer.schedule(Handler(), str(Path(SQLITE_PATH).parent), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        periodic.stop()
    observer.join()


if __name__ == "__main__":
    watch()
