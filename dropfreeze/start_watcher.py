# -*- coding: utf-8 -*-
import time
import sqlite3
import os
import hashlib
import traceback
from datetime import datetime
import sync_droplet_record_back
CHECK_INTERVAL = 10

# 修改重點：在此列表中加入第二個字典物件
TARGETS = [
    {
        "name": "DropletSchedule",
        "path": r"D:\配藥表\資料庫\P01_formualte_schedule.db",
        "table": "DropletSchedule"
    },
    {
        "name": "WorkOrders",  # 自訂識別名稱
        "path": r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db", # 網芳路徑
        "table": "work_orders" # 指定監控的 table
    }
]

BAD_STATES = {"FILE_NOT_FOUND", "TABLE_ERROR"}

def get_table_hash(target):
    path = target["path"]
    table = target["table"]

    if not os.path.exists(path):
        return "FILE_NOT_FOUND"

    try:
        # 連接資料庫
        with sqlite3.connect(path, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=15000;")
            cur = conn.cursor()
            # 選取指定 table 內容
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

def main():
    print("🚀 Watcher start")

    # 1️⃣ initial sync
    print("🔄 initial sync")
    sync_droplet_record_back.main()

    # 2️⃣ baseline
    for t in TARGETS:
        t["last_hash"] = get_table_hash(t)
        print(f"[{t['name']}] baseline = {t['last_hash']}")

    print("👀 watching...")

    while True:
        try:
            for t in TARGETS:
                h = get_table_hash(t)

                if h in BAD_STATES or (isinstance(h, str) and h.startswith("ERROR")):
                    # 如果讀取錯誤（例如網路斷線），暫時跳過，等待下次檢查
                    continue

                if h != t["last_hash"]:
                    print(f"⚡ change detected {t['name']} {datetime.now():%H:%M:%S}")
                    t["last_hash"] = h

                    # 觸發同步程式
                    sync_droplet_record_back.main()

                    # sync 後重新定錨，避免同步過程修改資料庫導致無限迴圈
                    time.sleep(0.3)
                    nh = get_table_hash(t)
                    if isinstance(nh, str) and len(nh) == 32:
                        t["last_hash"] = nh

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("🛑 watcher stopped")
            break
        except Exception:
            traceback.print_exc()
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()