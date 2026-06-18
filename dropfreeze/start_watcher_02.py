# -*- coding: utf-8 -*-
import time
import sqlite3
import os
import hashlib
import traceback
from datetime import datetime

import sync_droplet_record_back

# ======================================================
# 設定
# ======================================================

CHECK_INTERVAL = 10
DEBOUNCE_SEC = 3.0

# 超過多久還是 running 要警告（秒）
RUNNING_WARN_SEC = 15 * 60   # 15 分鐘

MAIN_DB = r"D:\配藥表\資料庫\P01_formualte_schedule.db"

TARGETS = [
    {
        "name": "DropletSchedule",
        "path": r"D:\配藥表\資料庫\P01_formualte_schedule.db",
        "table": "DropletSchedule"
    },
    {
        "name": "WorkOrders",
        "path": r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db",
        "table": "work_orders"
    }
]

BAD_STATES = {"FILE_NOT_FOUND", "TABLE_ERROR"}


# ======================================================
# 工具函式
# ======================================================

def get_table_hash(target):
    path = target["path"]
    table = target["table"]

    if not os.path.exists(path):
        return "FILE_NOT_FOUND"

    try:
        with sqlite3.connect(path, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=15000;")

            cur = conn.cursor()
            cur.execute(f"SELECT * FROM '{table}' ORDER BY rowid")

            h = hashlib.md5()
            while True:
                rows = cur.fetchmany(500)
                if not rows:
                    break
                h.update(str(rows).encode("utf-8"))

            return h.hexdigest()

    except sqlite3.OperationalError:
        return "TABLE_ERROR"
    except Exception as e:
        return f"ERROR:{e}"


def get_sync_status():
    """
    回傳：
        (status, start_time_str)
    失敗時回傳：
        (None, None)
    """
    try:
        with sqlite3.connect(MAIN_DB, timeout=3) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT status, start_time
                FROM sync_status
                WHERE id = 1
            """)
            row = cur.fetchone()
            if not row:
                return None, None
            return row[0], row[1]
    except Exception:
        return None, None


def is_sync_running():
    status, _ = get_sync_status()
    return status == "running"


def parse_sqlite_datetime(dt_str):
    """
    你的 sync_status 用的是：
        datetime('now','localtime')
    形式通常是：
        YYYY-MM-DD HH:MM:SS
    """
    if not dt_str:
        return None

    try:
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def warn_if_running_too_long():
    """
    如果 sync_status=running 且超過 RUNNING_WARN_SEC
    直接 print 警告
    """
    status, start_str = get_sync_status()

    if status != "running":
        return

    start_dt = parse_sqlite_datetime(start_str)
    if not start_dt:
        return

    elapsed = (datetime.now() - start_dt).total_seconds()

    if elapsed >= RUNNING_WARN_SEC:
        print(
            f"⚠️ WARNING: sync still running for "
            f"{int(elapsed)} sec "
            f"(started at {start_str})"
        )


# ======================================================
# main
# ======================================================

def main():
    print("🚀 Watcher start")

    # 建立 baseline
    for t in TARGETS:
        t["last_hash"] = get_table_hash(t)
        print(f"[{t['name']}] baseline = {t['last_hash']}")

    print("👀 watching...")

    pending_sources = set()
    last_change_time = None

    while True:
        try:
            # 每一輪都先檢查是否同步跑太久
            warn_if_running_too_long()

            for t in TARGETS:
                h = get_table_hash(t)

                if h in BAD_STATES or (isinstance(h, str) and h.startswith("ERROR")):
                    continue

                if h != t["last_hash"]:
                    print(f"⚡ change detected [{t['name']}] {datetime.now():%H:%M:%S}")
                    t["last_hash"] = h
                    pending_sources.add(t["name"])
                    last_change_time = time.time()

            # 有變動，進入 debounce
            if last_change_time is not None:

                if time.time() - last_change_time < DEBOUNCE_SEC:
                    time.sleep(0.2)
                    continue

                print(f"🔔 triggering sync, sources={sorted(pending_sources)}")

                if is_sync_running():
                    print("⏸ sync_status=running, skip trigger")
                else:
                    try:
                        sync_droplet_record_back.main()
                    except Exception:
                        traceback.print_exc()

                # sync 後重新定錨
                for t in TARGETS:
                    nh = get_table_hash(t)
                    if isinstance(nh, str) and len(nh) == 32:
                        t["last_hash"] = nh

                pending_sources.clear()
                last_change_time = None

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("🛑 watcher stopped")
            break

        except Exception:
            traceback.print_exc()
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
