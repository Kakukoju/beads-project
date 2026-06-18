# patch_remaining.py
DATA = "/opt/beadsops/data"

# === 1. dropfreeze/app_V13_W03.py ===
f1 = "/opt/beadsops/dropfreeze/app_V13_W03.py"
with open(f1, "r", encoding="utf-8") as f:
    c = f.read()

c = c.replace(
    r'DB_SCHEDULE = r"D:\配藥表\資料庫\P01_formualte_schedule.db"',
    f'DB_SCHEDULE = "{DATA}/P01_formualte_schedule.db"'
)
c = c.replace(
    r'DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\BeadRecord\work_orders.db"',
    f'DB_PATH = "{DATA}/work_orders.db"'
)
c = c.replace(
    r'DB_BEADS_SYNC = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\beads_sync.db"',
    f'DB_BEADS_SYNC = "{DATA}/beads_sync.db"'
)

with open(f1, "w", encoding="utf-8") as f:
    f.write(c)
print("OK: dropfreeze patched")

# === 2. app-unified/app_unified128.py ===
f2 = "/opt/beadsops/app-unified/app_unified128.py"
with open(f2, "r", encoding="utf-8") as f:
    c2 = f.read()

c2 = c2.replace(
    r'DB_PATH = os.environ.get("DB_PATH", r"D:\配藥表\資料庫\P01_formualte_schedule.db")',
    f'DB_PATH = os.environ.get("DB_PATH", "{DATA}/P01_formualte_schedule.db")'
)

with open(f2, "w", encoding="utf-8") as f:
    f.write(c2)
print("OK: app-unified patched")
