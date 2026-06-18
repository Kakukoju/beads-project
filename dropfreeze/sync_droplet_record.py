# -*- coding: utf-8 -*-
import os
import re
import sqlite3
import time
import traceback
from pathlib import Path
from collections import defaultdict
from datetime import datetime

MAIN_DB        = "/opt/beadsops/data/P01_formualte_schedule.db"
WORK_ORDER_DB  = "/opt/beadsops/data/work_orders.db"

SCRIPT_LOCK    = Path("/tmp/droplet_sync_running.lock")
LOCK_TTL_SEC   = 5 * 60


# --------------------------------------------------
# DB utils
# --------------------------------------------------
def get_conn(db_path: str):
    conn = sqlite3.connect(db_path, timeout=20, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=15000;")
    return conn


# --------------------------------------------------
# Lock
# --------------------------------------------------
def acquire_lock_or_skip() -> bool:
    SCRIPT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    if SCRIPT_LOCK.exists():
        age = time.time() - SCRIPT_LOCK.stat().st_mtime
        if age < LOCK_TTL_SEC:
            print(f"⏭️  sync skipped: 另一個執行中 (age={int(age)}s)")
            return False
        print(f"⚠️  殭屍 lock 偵測 (age={int(age)}s)，強制清除")
        try:
            SCRIPT_LOCK.unlink()
        except Exception:
            return False
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(SCRIPT_LOCK), flags)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{time.time()}|pid={os.getpid()}")
        return True
    except FileExistsError:
        return False

def release_lock():
    try:
        SCRIPT_LOCK.unlink(missing_ok=True)
    except Exception:
        pass


# --------------------------------------------------
# 建立 marker → pump_needle / syringe 對照表
# --------------------------------------------------
def build_needle_map(conn) -> dict:
    """滴定針頭號數表: Reagent → 針頭號數"""
    cur = conn.execute("SELECT Reagent, 針頭號數 FROM 滴定針頭號數表")
    return {r[0]: r[1] for r in cur.fetchall() if r[0]}

def build_syringe_map(conn) -> dict:
    """pump No.: marker → 所有可用 pump 編號 (以 - 串接)"""
    cur = conn.execute('SELECT * FROM "pump No."')
    cols = [d[0] for d in cur.description]
    reagent_cols = [c for c in cols if c.startswith("可滴定之試劑")]

    marker_pumps: dict[str, list] = {}
    for row in cur.fetchall():
        pump_id = str(row[cols.index("pump編號")]).strip()
        for rc in reagent_cols:
            val = str(row[cols.index(rc)] or "").strip()
            if val:
                marker_pumps.setdefault(val, []).append(pump_id)

    return {m: "-".join(pumps) for m, pumps in marker_pumps.items()}


# --------------------------------------------------
# Core sync
# --------------------------------------------------
def sync_droplet_record():
    with get_conn(MAIN_DB) as conn:
        conn.execute("BEGIN IMMEDIATE;")

        # ── Step 1: 有效日期 ──────────────────────────────────────────
        dates = [
            r[0] for r in conn.execute("""
                SELECT DISTINCT Date FROM DropletSchedule
                WHERE Date IS NOT NULL AND Date != ''
                  AND Date NOT LIKE '%1900%' AND Date NOT LIKE '%年%'
            """).fetchall()
        ]
        print(f"  📅 有效日期數: {len(dates)} 筆")
        if not dates:
            print("  ⚠️  無有效日期，中止 sync")
            conn.commit()
            return

        # ── Step 2: DELETE 舊資料 ─────────────────────────────────────
        placeholders = ",".join("?" for _ in dates)
        deleted = conn.execute(
            f'DELETE FROM dropletRecord WHERE record_date IN ({placeholders})', dates
        ).rowcount
        print(f"  🗑️  已刪除舊資料: {deleted} 筆")

        # ── Step 3: INSERT 新資料 ─────────────────────────────────────
        rows = conn.execute(f"""
            SELECT Date, Marker, Lyophilizer, Quantity,
                   DrugGivenAt, ExpectedTitrationStart, ExpectedTitrationEnd,
                   WorkOrder, Pump, AvailableLyophilizer, Remark, Lot
            FROM DropletSchedule WHERE Date IN ({placeholders})
        """, dates).fetchall()

        conn.executemany("""
            INSERT OR IGNORE INTO dropletRecord (
                record_date, marker, lyophilizer, quantity,
                rd_dose_time, plan_titrate_time, plan_end_time,
                work_order, titration_port, available_lyophilizer,
                remark, lot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        print(f"  ✍️  插入: {len(rows)} 筆")

        # ── Step 4: 補入滴定條件 ──────────────────────────────────────
        conn.execute("""
            UPDATE dropletRecord SET
                store_expiry            = (SELECT c.Liquid_storge_time  FROM 滴定條件 c WHERE c.Name = marker LIMIT 1),
                store_temp              = (SELECT c.儲存時冰浴            FROM 滴定條件 c WHERE c.Name = marker LIMIT 1),
                store_light_protect     = (SELECT c.儲存時避光            FROM 滴定條件 c WHERE c.Name = marker LIMIT 1),
                titration_light_protect = (SELECT c.滴定時避光            FROM 滴定條件 c WHERE c.Name = marker LIMIT 1),
                titration_stir          = (SELECT c.滴定_Mixing           FROM 滴定條件 c WHERE c.Name = marker LIMIT 1),
                titration_ice_bath      = (SELECT c.滴定時冰浴            FROM 滴定條件 c WHERE c.Name = marker LIMIT 1),
                titration_volume        = (SELECT c.滴定_drop_Vol_MFG    FROM 滴定條件 c WHERE c.Name = marker LIMIT 1),
                pre_stir                = (SELECT c.滴定時攪拌            FROM 滴定條件 c WHERE c.Name = marker LIMIT 1)
            WHERE EXISTS (SELECT 1 FROM 滴定條件 c WHERE c.Name = marker)
        """)
        print("  ✍️  滴定條件 UPDATE 完成")

        # ── Step 4.5: 補入預冷溫度 (freezer_rules → pre_cool_temp) ──
        # 建立 (Marker, 數量) → 預冷溫度 對照，同 key 多值取最低溫
        rules = conn.execute(
            'SELECT Marker, "數量", "預冷溫度" FROM freezer_rules '
            'WHERE "預冷溫度" IS NOT NULL AND "預冷溫度" != ""'
        ).fetchall()

        temp_map = {}          # (marker, qty) → (temp_str, temp_val)
        marker_fallback = {}   # marker → (temp_str, temp_val)  不管數量的 fallback
        key_temps = defaultdict(set)

        for r in rules:
            mk, qty, temp = r["Marker"], r["數量"], r["預冷溫度"]
            m = re.search(r"(-?\d+)", temp.replace(" ", ""))
            val = int(m.group(1)) if m else 0
            key = (mk, qty)
            key_temps[key].add(temp.strip())
            if key not in temp_map or val < temp_map[key][1]:
                temp_map[key] = (temp, val)
            if mk not in marker_fallback or val < marker_fallback[mk][1]:
                marker_fallback[mk] = (temp, val)

        multi_keys = {k for k, ts in key_temps.items() if len(ts) > 1}

        need = conn.execute(
            'SELECT id, marker, quantity, remark FROM dropletRecord '
            'WHERE pre_cool_temp IS NULL OR pre_cool_temp = ""'
        ).fetchall()

        updated_temp = warned = 0
        for r in need:
            rid, mk, qty, remark = r["id"], r["marker"], r["quantity"], r["remark"] or ""
            key = (mk, qty)
            if key in temp_map:
                temp_str = temp_map[key][0]
            elif mk in marker_fallback:
                temp_str = marker_fallback[mk][0]
            else:
                continue
            conn.execute('UPDATE dropletRecord SET pre_cool_temp = ? WHERE id = ?', (temp_str, rid))
            updated_temp += 1
            # 同 Marker+數量有多種預冷溫度 → 備註警示
            if key in multi_keys and "預冷溫度有多值" not in remark:
                warn = "⚠️預冷溫度有多值，已取最低溫，請確認凍乾參數"
                new_remark = (remark + "/" + warn) if remark else warn
                conn.execute('UPDATE dropletRecord SET remark = ? WHERE id = ?', (new_remark, rid))
                warned += 1

        print(f"  ✍️  pre_cool_temp UPDATE: {updated_temp} 筆, 備註警示: {warned} 筆")

        # ── Step 5: 補入針頭號數 (pump_needle) ───────────────────────
        conn.execute("""
            UPDATE dropletRecord SET
                pump_needle = (SELECT n.針頭號數 FROM 滴定針頭號數表 n WHERE n.Reagent = marker LIMIT 1)
            WHERE EXISTS (SELECT 1 FROM 滴定針頭號數表 n WHERE n.Reagent = marker)
        """)
        print("  ✍️  pump_needle UPDATE 完成")

        # ── Step 6: 補入 Pump No. (syringe) — Python 迴圈處理多欄 ──
        syringe_map = build_syringe_map(conn)
        updated_syringe = 0
        for marker, pump_str in syringe_map.items():
            cur = conn.execute(
                'UPDATE dropletRecord SET syringe = ? WHERE marker = ? AND (syringe IS NULL OR syringe = "")',
                (pump_str, marker)
            )
            updated_syringe += cur.rowcount
        print(f"  ✍️  syringe UPDATE 完成: {updated_syringe} 筆")

        conn.commit()

    # ── Step 7: work_orders 跨 DB 回寫實際時間 ───────────────────────
    print("  🔗 連線 work_orders DB...")
    try:
        with get_conn(WORK_ORDER_DB) as src, get_conn(MAIN_DB) as tgt:
            rows = src.execute("""
                SELECT 工單號, 時間_收藥, 時間_滴定開始, 時間_滴定結束,
                       Dispense_Lot_1, Dispense_Lot_2, Dispense_Lot_3, Dispense_Lot_4
                FROM work_orders
            """).fetchall()
            updated = 0
            for wo, t1, t2, t3, *lots in rows:
                for lot in lots:
                    if lot:
                        cur = tgt.execute("""
                            UPDATE dropletRecord
                            SET drug_acquire_time=?, titration_start_time=?, titration_end_time=?
                            WHERE work_order=? AND lot=?
                        """, (t1, t2, t3, wo, lot))
                        updated += cur.rowcount
            tgt.commit()
            print(f"  ✍️  work_orders 回寫: {updated} 筆")
    except Exception as e:
        print(f"  ⚠️  work_orders 回寫失敗（NAS 可能離線）: {e}")


# --------------------------------------------------
# Entry
# --------------------------------------------------
def main():
    if not acquire_lock_or_skip():
        return
    try:
        print(f"🔄 sync start @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        sync_droplet_record()
        print(f"✅ sync done  @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception:
        traceback.print_exc()
    finally:
        release_lock()
        print("🔓 lock released")


if __name__ == "__main__":
    main()
