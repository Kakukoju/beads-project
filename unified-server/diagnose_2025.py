"""
診斷 2025 年 ALB 資料
檢查為什麼沒有趨勢圖
"""
import sqlite3
import os

DB_PATH = r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Beads_QC\資料庫\P01_Beads_IPQC.db"

print("=" * 70)
print("診斷 2025 年 ALB 資料")
print("=" * 70)

if not os.path.exists(DB_PATH):
    print(f"❌ 資料庫不存在")
    exit(1)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

table = "2025_IPQC"
marker = "ALB"
month = 11

print(f"\n測試條件:")
print(f"  表名: {table}")
print(f"  Marker: {marker}")
print(f"  月份: {month}\n")

# 1. 檢查總資料筆數
cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
total = cursor.fetchone()[0]
print(f"✅ 總資料筆數: {total:,}")

# 2. 檢查所有可用的 Marker
cursor.execute(f'SELECT DISTINCT Marker FROM "{table}" WHERE Marker IS NOT NULL ORDER BY Marker')
all_markers = [row[0] for row in cursor.fetchall()]
print(f"\n✅ 可用的 Marker ({len(all_markers)} 個):")
print(f"   {', '.join(all_markers)}")

# 3. 檢查 ALB 是否存在
if marker in all_markers:
    print(f"\n✅ {marker} 存在於資料表中")
    
    # 檢查 ALB 的總數
    cursor.execute(f'SELECT COUNT(*) FROM "{table}" WHERE Marker = ?', (marker,))
    alb_total = cursor.fetchone()[0]
    print(f"   {marker} 總筆數: {alb_total:,}")
    
    # 檢查 ALB 在各月份的分布
    print(f"\n   {marker} 各月份分布:")
    cursor.execute(f'''
        SELECT CAST(substr(匹配批號, 5, 2) AS INTEGER) as month, COUNT(*) as count
        FROM "{table}"
        WHERE Marker = ?
        GROUP BY month
        ORDER BY month
    ''', (marker,))
    
    month_dist = cursor.fetchall()
    for m, count in month_dist:
        indicator = " ← 你查詢的月份" if m == month else ""
        print(f"      {m:2d} 月: {count:4d} 筆{indicator}")
    
    # 檢查 11 月的 ALB
    if month in [m[0] for m in month_dist]:
        print(f"\n✅ {month} 月有 {marker} 資料")
        
        # 查看實際資料
        cursor.execute(f'''
            SELECT 匹配批號
            FROM "{table}"
            WHERE Marker = ?
            AND CAST(substr(匹配批號, 5, 2) AS INTEGER) = ?
            ORDER BY 匹配批號
            LIMIT 10
        ''', (marker, month))
        
        batches = [row[0] for row in cursor.fetchall()]
        print(f"   批號範例 (前10筆):")
        for batch in batches:
            print(f"      {batch}")
        
        # 檢查是否有 OD 欄位
        cursor.execute(f'PRAGMA table_info("{table}")')
        columns = [col[1] for col in cursor.fetchall()]
        
        od_cols = [col for col in columns if 'OD' in col.upper() and 'Mean' in col]
        print(f"\n   可用的 OD 欄位:")
        print(f"      {', '.join(od_cols) if od_cols else '(無)'}")
        
        # 測試完整查詢
        if od_cols:
            print(f"\n   測試查詢前 3 筆資料:")
            query = f'''
                SELECT 匹配批號, {', '.join(od_cols[:4])}
                FROM "{table}"
                WHERE Marker = ?
                AND CAST(substr(匹配批號, 5, 2) AS INTEGER) = ?
                ORDER BY 匹配批號
                LIMIT 3
            '''
            cursor.execute(query, (marker, month))
            rows = cursor.fetchall()
            
            for i, row in enumerate(rows, 1):
                print(f"      {i}. {row[0]}: {row[1:]}")
    else:
        print(f"\n❌ {month} 月沒有 {marker} 資料")
        print(f"\n💡 建議:")
        print(f"   請選擇有資料的月份: {', '.join(map(str, [m[0] for m in month_dist]))}")
    
else:
    print(f"\n❌ {marker} 不存在於資料表中")
    print(f"\n💡 建議:")
    print(f"   請選擇以下 Marker 之一:")
    for m in all_markers[:10]:
        print(f"      - {m}")

# 4. 檢查批號格式
print(f"\n檢查批號格式:")
cursor.execute(f'SELECT 匹配批號 FROM "{table}" LIMIT 5')
samples = [row[0] for row in cursor.fetchall()]
print(f"   批號範例:")
for batch in samples:
    if batch and len(batch) >= 6:
        month_part = batch[4:6]
        print(f"      {batch:20s} → 月份部分: {month_part}")
    else:
        print(f"      {batch:20s} → 格式不符")

conn.close()

print("\n" + "=" * 70)
print("診斷完成")
print("=" * 70)