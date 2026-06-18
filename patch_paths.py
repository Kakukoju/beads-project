# patch_paths.py - 修改 Flask 檔案中的 Windows 路徑為 EC2 路徑
import re

DATA = "/opt/beadsops/data"
APP1 = "/opt/beadsops/unified-server"
APP2 = "/opt/beadsops/app-unified"
APP3 = "/opt/beadsops/dropfreeze"

# === 1. beads_unified_server_V14.py ===
f1 = f"{APP1}/beads_unified_server_V14.py"
with open(f1, "r", encoding="utf-8") as f:
    c = f.read()

# 路徑替換
replacements = {
    r'APP_DIR = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Bead_auto_update_schedule"': f'APP_DIR = "{APP1}"',
    r'MAIN_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\beads_sync.db"': f'MAIN_DB_PATH = "{DATA}/beads_sync.db"',
    r'DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\Beads_Schedule.db"': f'DB_PATH = "{DATA}/Beads_Schedule.db"',
    r'WORK_ORDER_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"': f'WORK_ORDER_DB_PATH = "{DATA}/work_orders.db"',
    r'FORMULATE_DB_PATH = r"D:\配藥表\資料庫\P01_formualte_schedule.db"': f'FORMULATE_DB_PATH = "{DATA}/P01_formualte_schedule.db"',
    r'IPQC_DB_PATH = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Beads_QC\資料庫\P01_Beads_IPQC.db"': f'IPQC_DB_PATH = "{DATA}/P01_Beads_IPQC.db"',
    r'WIP_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\分藥資料庫\Bead_Sort_DB.db"': f'WIP_DB_PATH = "{DATA}/Bead_Sort_DB.db"',
}

for old, new in replacements.items():
    if old in c:
        c = c.replace(old, new)
        print(f"  ✅ replaced: {new.split('=')[0].strip()}")
    else:
        print(f"  ⚠️ not found: {old[:60]}...")

# 移除 win32com / pythoncom import（整個 recalc 函數保留但不會被呼叫）
# 把 import pythoncom / import win32com.client 包在 try-except
c = c.replace(
    "        import pythoncom\n        import win32com.client",
    "        raise ImportError('win32com not available on Linux')\n        import pythoncom\n        import win32com.client"
)
print("  ✅ disabled win32com import")

with open(f1, "w", encoding="utf-8") as f:
    f.write(c)
print(f"✅ Patched {f1}\n")

# === 2. app_unified128.py ===
f2 = f"{APP2}/app_unified128.py"
try:
    with open(f2, "r", encoding="utf-8") as f:
        c2 = f.read()

    # 移除 pythoncom import
    c2 = c2.replace(
        "import sqlite3, csv, io, os, re, json, datetime, time, logging, uuid, shutil, pythoncom, socket",
        "import sqlite3, csv, io, os, re, json, datetime, time, logging, uuid, shutil, socket"
    )
    print("  ✅ removed pythoncom from imports")

    # 移除 win32com import
    c2 = c2.replace(
        "from win32com.client import Dispatch",
        "# from win32com.client import Dispatch  # disabled on Linux"
    )
    print("  ✅ disabled win32com import")

    with open(f2, "w", encoding="utf-8") as f:
        f.write(c2)
    print(f"✅ Patched {f2}\n")
except FileNotFoundError:
    print(f"⚠️ {f2} not found, skipping\n")

print("🎉 All patches done!")
