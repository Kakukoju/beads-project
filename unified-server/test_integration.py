"""
CP 排程器整合測試腳本
支援完整參數設定：日期、休假日、工單編號、休假人員
"""

import sys
from datetime import datetime, timedelta

# ========================================
# 設定全域參數（模擬命令行參數）
# ========================================

def setup_test_parameters(
    start_date_str: str = "01/06",  # MM/DD 格式
    holidays_str: str = "",          # 例如 "01/10,01/11"
    batch_start: int = 1,
    vacation_str: str = ""           # 例如 "01/10-張三,01/11-李四"
):
    """
    設定測試參數（替代命令行參數）
    
    Args:
        start_date_str: 排程起始日期 MM/DD
        holidays_str: 休假日，逗號分隔
        batch_start: 工單起始編號
        vacation_str: 休假人員，逗號分隔
    """
    
    # 導入原程式的全域變數
    import Beads_Scheduler_P0_P3_V1 as main_module
    
    print("="*70, file=sys.stderr)
    print("⚙️  設定測試參數", file=sys.stderr)
    print("="*70, file=sys.stderr)
    
    # ========================================
    # 1. 設定起始日期
    # ========================================
    try:
        current_year = datetime.now().year
        parts = start_date_str.split('/')
        month, day = int(parts[0]), int(parts[1])
        start_date = datetime(current_year, month, day)
        
        # 調整到週一
        if start_date.weekday() != 0:
            start_date = start_date - timedelta(days=start_date.weekday())
        
        main_module.SCHEDULE_START_DATE = start_date
        
        print(f"  ✅ 排程起始日期（週一）: {start_date.strftime('%Y-%m-%d')}", file=sys.stderr)
        
    except Exception as e:
        print(f"  ❌ 日期解析失敗: {e}", file=sys.stderr)
        sys.exit(1)
    
    # ========================================
    # 2. 設定休假日
    # ========================================
    if holidays_str:
        holidays = set()
        start_month = start_date.month
        
        for date_str in holidays_str.split(','):
            try:
                date_str = date_str.strip().replace('-', '/')
                parts = date_str.split('/')
                
                if len(parts) == 2:
                    month = int(parts[0])
                    day = int(parts[1])
                    
                    # 跨年邏輯
                    if start_month == 12 and month == 1:
                        year = current_year + 1
                    else:
                        year = current_year
                    
                    holiday_date = datetime(year, month, day).date()
                    holidays.add(holiday_date)
                    print(f"  ✅ 休假日: {holiday_date.strftime('%Y-%m-%d')}", file=sys.stderr)
            except Exception as e:
                print(f"  ⚠️ 休假日解析失敗 '{date_str}': {e}", file=sys.stderr)
        
        main_module.HOLIDAYS = holidays
    else:
        main_module.HOLIDAYS = set()
        print(f"  ℹ️ 無休假日設定", file=sys.stderr)
    
    # ========================================
    # 3. 設定工單批次編號
    # ========================================
    main_module.BATCH_START_NUMBER = batch_start
    print(f"  ✅ 工單起始編號: {batch_start}", file=sys.stderr)
    
    # ========================================
    # 4. 設定休假人員
    # ========================================
    if vacation_str:
        vacation_staff = {}
        
        for entry in vacation_str.split(','):
            try:
                if '-' not in entry:
                    continue
                
                date_part, person = entry.split('-', 1)
                date_part = date_part.strip().replace('/', '/')
                person = person.strip().lower()
                
                parts = date_part.split('/')
                if len(parts) == 2:
                    month = int(parts[0])
                    day = int(parts[1])
                    vacation_date = datetime(current_year, month, day).date()
                    date_str = vacation_date.strftime('%Y-%m-%d')
                    
                    if date_str not in vacation_staff:
                        vacation_staff[date_str] = set()
                    vacation_staff[date_str].add(person)
                    
                    print(f"  ✅ 休假人員: {date_str} - {person}", file=sys.stderr)
            except Exception as e:
                print(f"  ⚠️ 休假人員解析失敗 '{entry}': {e}", file=sys.stderr)
        
        main_module.VACATION_STAFF = vacation_staff
    else:
        main_module.VACATION_STAFF = {}
        print(f"  ℹ️ 無休假人員設定", file=sys.stderr)
    
    print("="*70 + "\n", file=sys.stderr)
    
    return main_module.SCHEDULE_START_DATE


# ========================================
# 主測試函數
# ========================================

def test_integration(
    demand_path: str,
    start_date: str = "01/06",
    holidays: str = "",
    batch_start: int = 1,
    vacation: str = "",
    use_cp: bool = True
):
    """
    完整測試流程
    
    Args:
        demand_path: 需求檔路徑
        start_date: 開始日期 MM/DD
        holidays: 休假日 MM/DD,MM/DD
        batch_start: 工單起始編號
        vacation: 休假人員 MM/DD-人名,MM/DD-人名
        use_cp: 是否使用 CP 排程器
    """
    
    print("="*70, file=sys.stderr)
    print("🧪 CP 排程器整合測試", file=sys.stderr)
    print("="*70, file=sys.stderr)
    
    # ========================================
    # 1. 設定參數
    # ========================================
    monday = setup_test_parameters(
        start_date_str=start_date,
        holidays_str=holidays,
        batch_start=batch_start,
        vacation_str=vacation
    )
    
    # ========================================
    # 2. 載入資料
    # ========================================
    print("📂 Step 1: 載入需求資料...", file=sys.stderr)
    
    from Beads_Scheduler_P0_P3_V1 import load_all_data, Scheduler
    
    all_data = load_all_data(demand_path)
    
    if not all_data or all_data["demand"] is None:
        print("❌ 資料載入失敗", file=sys.stderr)
        return False
    
    print(f"  ✅ 需求表載入成功 ({len(all_data['demand'])} 筆)\n", file=sys.stderr)
    
    # ========================================
    # 3. 設定 CP 開關
    # ========================================
    import Beads_Scheduler_P0_P3_V1 as main_module
    main_module.USE_CP_SOLVER = use_cp
    
    print(f"🎯 排程模式: {'CP-SAT' if use_cp else '貪婪算法'}\n", file=sys.stderr)
    
    # ========================================
    # 4. 建立排程器
    # ========================================
    print("🏗️  Step 2: 建立排程器...", file=sys.stderr)
    
    scheduler = Scheduler(all_data)
    
    # 模擬最少天數計算（如果需要）
    if hasattr(main_module, 'simulate_min_production_days'):
        min_days, _ = main_module.simulate_min_production_days(
            scheduler.task_queue,
            scheduler.constraints,
            monday
        )
        scheduler.days_to_schedule = min(min_days, 7)
        print(f"  ✅ 計算最少天數: {min_days} 天 (實際使用 {scheduler.days_to_schedule} 天)\n", file=sys.stderr)
    
    # ========================================
    # 5. 執行排程
    # ========================================
    print("🚀 Step 3: 執行排程...\n", file=sys.stderr)
    
    import time
    start_time = time.time()
    
    try:
        scheduler.run()
        elapsed = time.time() - start_time
        
        print(f"\n⏱️  排程耗時: {elapsed:.2f} 秒\n", file=sys.stderr)
        
    except Exception as e:
        print(f"\n❌ 排程失敗: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return False
    
    # ========================================
    # 6. 驗證結果
    # ========================================
    print("="*70, file=sys.stderr)
    print("✅ Step 4: 驗證結果", file=sys.stderr)
    print("="*70, file=sys.stderr)
    
    if not hasattr(scheduler, 'schedule_df') or scheduler.schedule_df.empty:
        print("❌ 無排程結果", file=sys.stderr)
        return False
    
    df = scheduler.schedule_df
    
    # 基本統計
    print(f"\n📊 基本統計:", file=sys.stderr)
    print(f"  總記錄數: {len(df)}", file=sys.stderr)
    print(f"  涵蓋天數: {df['日期'].nunique()}", file=sys.stderr)
    print(f"  使用凍乾機: {df['凍乾機台'].nunique()} 台", file=sys.stderr)
    print(f"  配藥人員: {df['配藥同仁'].nunique()} 人", file=sys.stderr)
    
    # Port 使用統計
    port_records = df[df['滴定機'].str.contains('Port', na=False)]
    ivek_records = df[df['滴定機'] == 'IVEK']
    
    print(f"\n🔌 滴定機使用:", file=sys.stderr)
    print(f"  Port 任務: {len(port_records)} 筆", file=sys.stderr)
    print(f"  IVEK 任務: {len(ivek_records)} 筆", file=sys.stderr)
    
    # 按日期統計
    print(f"\n📅 每日排程分佈:", file=sys.stderr)
    for date in sorted(df['日期'].unique()):
        day_df = df[df['日期'] == date]
        am_count = len(day_df[day_df['班次'] == 'AM'])
        pm_count = len(day_df[day_df['班次'] == 'PM'])
        print(f"  {date}: AM {am_count} 筆, PM {pm_count} 筆", file=sys.stderr)
    
    # 檢查約束違反
    print(f"\n🔍 約束檢查:", file=sys.stderr)
    
    # 檢查 Port 容量（每班次 <= 12）
    violations = []
    for date in df['日期'].unique():
        for shift in ['AM', 'PM']:
            shift_df = df[(df['日期'] == date) & (df['班次'] == shift)]
            port_df = shift_df[shift_df['滴定機'].str.contains('Port', na=False)]
            
            # 統計使用的 Port
            used_ports = set()
            for _, row in port_df.iterrows():
                try:
                    port_num = int(row['滴定機'].replace('Port', ''))
                    used_ports.add(port_num)
                except:
                    pass
            
            if len(used_ports) > 12:
                violations.append(f"{date} {shift}: 使用 {len(used_ports)} 個 Port (>12)")
    
    if violations:
        print(f"  ❌ 發現 {len(violations)} 個 Port 容量違反:", file=sys.stderr)
        for v in violations:
            print(f"    • {v}", file=sys.stderr)
    else:
        print(f"  ✅ Port 容量檢查通過", file=sys.stderr)
    
    # 檢查禁止收藥時段
    forbidden_violations = []
    for _, row in df.iterrows():
        try:
            end_time_str = row.get('預計結束', '')
            if end_time_str:
                hour = int(end_time_str.split(':')[0])
                if 3 <= hour < 8:
                    forbidden_violations.append(f"{row['日期']} {row['marker']}: {end_time_str}")
        except:
            pass
    
    if forbidden_violations:
        print(f"  ⚠️ 發現 {len(forbidden_violations)} 個禁止時段違反:", file=sys.stderr)
        for v in forbidden_violations[:5]:  # 只顯示前 5 個
            print(f"    • {v}", file=sys.stderr)
    else:
        print(f"  ✅ 禁止時段檢查通過", file=sys.stderr)
    
    print("\n" + "="*70, file=sys.stderr)
    print("✅ 測試完成！", file=sys.stderr)
    print("="*70 + "\n", file=sys.stderr)
    
    return True


# ========================================
# 命令行入口
# ========================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='CP 排程器整合測試')
    
    # 必要參數
    parser.add_argument('--demand', required=True, help='需求檔路徑')
    parser.add_argument('--date', required=True, help='開始日期 MM/DD')
    
    # 可選參數
    parser.add_argument('--holidays', default='', help='休假日 MM/DD,MM/DD')
    parser.add_argument('--batch', type=int, default=1, help='工單起始編號')
    parser.add_argument('--vacation', default='', help='休假人員 MM/DD-姓名')
    parser.add_argument('--no-cp', action='store_true', help='不使用 CP（使用貪婪）')
    
    args = parser.parse_args()
    
    # 執行測試
    success = test_integration(
        demand_path=args.demand,
        start_date=args.date,
        holidays=args.holidays,
        batch_start=args.batch,
        vacation=args.vacation,
        use_cp=not args.no_cp
    )
    
    sys.exit(0 if success else 1)