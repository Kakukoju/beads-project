"""
快速檢查 - produced_count 為 0 的原因
"""

import sqlite3
import os
from datetime import datetime, timedelta

# 設定
FORMULATE_DB_PATH = r"D:\配藥表\資料庫\P01_formualte_schedule.db"

print("快速診斷 produced_count 為 0 的原因")
print("=" * 50)
print()

# 檢查 1: 檔案存在嗎？
if not os.path.exists(FORMULATE_DB_PATH):
    print("❌ 配藥表資料庫不存在！")
    print(f"   路徑: {FORMULATE_DB_PATH}")
    print()
    print("解決方案:")
    print("  修改 wip_automation_blueprint.py 中的路徑")
    exit()

print("✓ 資料庫檔案存在")
print()

# 檢查 2: 能連接嗎？
try:
    conn = sqlite3.connect(FORMULATE_DB_PATH)
    cursor = conn.cursor()
    print("✓ 資料庫連接成功")
    print()
except Exception as e:
    print(f"❌ 無法連接資料庫: {e}")
    exit()

# 檢查 3: 資料表存在嗎？
try:
    cursor.execute("SELECT COUNT(*) FROM DropletSchedule")
    total = cursor.fetchone()[0]
    print(f"✓ DropletSchedule 資料表存在")
    print(f"  總筆數: {total}")
    print()
except Exception as e:
    print(f"❌ 資料表不存在或無法讀取: {e}")
    print()
    # 列出所有資料表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("可用的資料表:")
    for t in tables:
        print(f"  • {t[0]}")
    conn.close()
    exit()

# 檢查 4: 有 TMRA 工單嗎？
cursor.execute("SELECT COUNT(*) FROM DropletSchedule WHERE WorkOrder LIKE 'TMRA%'")
tmra_total = cursor.fetchone()[0]
print(f"TMRA 工單總數: {tmra_total}")

if tmra_total == 0:
    print()
    print("❌ 沒有 TMRA 開頭的工單！")
    print()
    # 顯示實際的工單格式
    cursor.execute("SELECT DISTINCT WorkOrder FROM DropletSchedule LIMIT 10")
    samples = cursor.fetchall()
    print("實際工單號碼格式:")
    for s in samples:
        print(f"  • {s[0]}")
    print()
    print("💡 解決方案:")
    print("   修改查詢條件以匹配實際格式")
    conn.close()
    exit()

print(f"✓ 找到 {tmra_total} 個 TMRA 工單")
print()

# 檢查 5: 最近 7 天有工單嗎？
end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
start_date = end_date - timedelta(days=7)

query = """
    SELECT COUNT(*) 
    FROM DropletSchedule 
    WHERE WorkOrder LIKE 'TMRA%'
      AND Date >= ?
      AND Date < ?
"""

# 使用 YYYY/MM/DD 格式（斜線）
cursor.execute(query, (start_date.strftime('%Y/%m/%d'), end_date.strftime('%Y/%m/%d')))
recent_7 = cursor.fetchone()[0]

print(f"最近 7 天的 TMRA 工單數: {recent_7}")

if recent_7 == 0:
    print()
    print("❌ 最近 7 天沒有工單！")
    print()
    
    # 檢查最近的工單日期
    cursor.execute("""
        SELECT MAX(Date) 
        FROM DropletSchedule 
        WHERE WorkOrder LIKE 'TMRA%'
    """)
    last_date = cursor.fetchone()[0]
    
    print(f"最後一筆工單日期: {last_date}")
    print()
    
    # 檢查不同天數
    for days in [30, 60, 90]:
        start = end_date - timedelta(days=days)
        cursor.execute(query, (start.strftime('%Y/%m/%d'), end_date.strftime('%Y/%m/%d')))
        count = cursor.fetchone()[0]
        print(f"最近 {days:2d} 天: {count} 個工單")
    
    print()
    print("💡 解決方案:")
    print("   使用更長的查詢範圍，例如:")
    print("   GET /api/workorder/unpackaged-ratio?days=30")
else:
    print(f"✓ 最近 7 天有 {recent_7} 個工單")
    print()
    
    # 顯示範例
    cursor.execute("""
        SELECT WorkOrder, Date 
        FROM DropletSchedule 
        WHERE WorkOrder LIKE 'TMRA%'
          AND Date >= ?
          AND Date < ?
        ORDER BY Date DESC
        LIMIT 5
    """, (start_date.strftime('%Y/%m/%d'), end_date.strftime('%Y/%m/%d')))
    
    samples = cursor.fetchall()
    print("範例工單:")
    for order, date in samples:
        print(f"  • {order} ({date})")

conn.close()

print()
print("=" * 50)
print("診斷完成")
print()