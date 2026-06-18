#!/usr/bin/env python3
"""
Watch P01_formualte_schedule.db for changes (inotify) and push all tables to RDS PostgreSQL.
Schema: P01_formualte_schedule
"""
import sqlite3, psycopg2, time, logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

SQLITE_PATH = "/opt/beadsops/data/P01_formualte_schedule.db"
SCHEMA = "P01_formualte_schedule"

RDS = {
    "host": "database-1.cfutwrwyrxts.ap-northeast-1.rds.amazonaws.com",
    "port": 5432,
    "dbname": "beadsdb",
    "user": "harryguo",
    "password": "skyla168",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sync")

TYPE_MAP = {"INTEGER": "TEXT", "REAL": "TEXT", "TEXT": "TEXT", "BLOB": "TEXT"}


def pg_conn():
    conn = psycopg2.connect(**RDS)
    conn.autocommit = True
    return conn


def get_sqlite_tables():
    con = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro", uri=True)
    cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in cur.fetchall()]
    con.close()
    return tables


def safe_col(name):
    return f'"{name}"'


def sync_table(pg, sqlite_con, table):
    cur_s = sqlite_con.execute(f'PRAGMA table_info("{table}")')
    cols = cur_s.fetchall()  # (cid, name, type, notnull, default, pk)
    if not cols:
        return

    col_defs = ", ".join(
        f'{safe_col(c[1])} {TYPE_MAP.get(c[2].upper(), "TEXT")}' for c in cols
    )
    col_names = ", ".join(safe_col(c[1]) for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))
    pg_table = f'"{SCHEMA}"."{table}"'

    with pg.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {pg_table}")
        cur.execute(f"CREATE TABLE {pg_table} ({col_defs})")

        rows = sqlite_con.execute(f'SELECT * FROM "{table}"').fetchall()
        if rows:
            args = ",".join(cur.mogrify(f"({placeholders})", row).decode() for row in rows)
            cur.execute(f"INSERT INTO {pg_table} ({col_names}) VALUES {args}")

    log.info(f"  {table}: {len(rows) if cols else 0} rows")


def full_sync():
    log.info("Starting full sync...")
    start = time.time()
    pg = pg_conn()
    with pg.cursor() as cur:
        cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')

    sqlite_con = sqlite3.connect(f"file:{SQLITE_PATH}?mode=ro", uri=True)
    tables = get_sqlite_tables()

    for t in tables:
        try:
            sync_table(pg, sqlite_con, t)
        except Exception as e:
            log.error(f"  {t} FAILED: {e}")

    sqlite_con.close()
    pg.close()
    log.info(f"Sync done. {len(tables)} tables in {time.time()-start:.1f}s")


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
    log.info(f"Watching {SQLITE_PATH} for changes...")
    observer = Observer()
    observer.schedule(Handler(), str(Path(SQLITE_PATH).parent), recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    watch()
