"""
診斷 CP 是否真的被執行
"""

import sys
from datetime import datetime

def diagnose_cp_execution(demand_path, start_date="01/06"):
    """診斷 CP 執行流程"""
    
    print("="*70)
    print("🔍 診斷 CP 執行流程")
    print("="*70)
    
    # ========================================
    # Step 1: 檢查 USE_CP_SOLVER
    # ========================================
    print("\n1️⃣ 檢查 USE_CP_SOLVER...")
    
    import Beads_Scheduler_P0_P3_V1 as main_module
    
    print(f"  USE_CP_SOLVER = {main_module.USE_CP_SOLVER}")
    
    if not main_module.USE_CP_SOLVER:
        print("  ❌ USE_CP_SOLVER 是 False，不會執行 CP")
        print("  💡 請設定 main_module.USE_CP_SOLVER = True")
        return False
    
    print("  ✅ USE_CP_SOLVER 已啟用")
    
    # ========================================
    # Step 2: 設定參數
    # ========================================
    print("\n2️⃣ 設定測試參數...")
    
    from test_integration import setup_test_parameters
    setup_test_parameters(start_date_str=start_date)
    
    # ========================================
    # Step 3: 載入資料
    # ========================================
    print("\n3️⃣ 載入資料...")
    
    from Beads_Scheduler_P0_P3_V1 import load_all_data, Scheduler
    
    all_data = load_all_data(demand_path)
    
    if not all_data or all_data.get("demand") is None:
        print("  ❌ 資料載入失敗")
        return False
    
    print(f"  ✅ 資料載入成功 ({len(all_data['demand'])} 筆需求)")
    
    # ========================================
    # Step 4: 建立排程器
    # ========================================
    print("\n4️⃣ 建立排程器...")
    
    scheduler = Scheduler(all_data)
    
    print(f"  ✅ 排程器建立成功")
    print(f"  任務數: {len(scheduler.task_queue)}")
    
    # ========================================
    # Step 5: 模擬 run() 開頭的邏輯
    # ========================================
    print("\n5️⃣ 檢查 run() 中的 CP 分支...")
    
    # 檢查 scheduler_integration 是否存在
    try:
        from scheduler_integration import run_cp_scheduler_integrated
        print("  ✅ run_cp_scheduler_integrated 已導入")
    except ImportError as e:
        print(f"  ❌ 無法導入 run_cp_scheduler_integrated: {e}")
        return False
    
    # ========================================
    # Step 6: 實際調用 CP
    # ========================================
    print("\n6️⃣ 實際執行 CP 排程器...")
    print("-"*70)
    
    try:
        # 🔥 實際調用
        cp_success = run_cp_scheduler_integrated(scheduler)
        
        print("-"*70)
        print(f"\n  返回值: {cp_success}")
        
        if cp_success:
            print("  ✅ CP 執行成功")
            
            # 檢查結果
            if hasattr(scheduler, 'schedule_df') and not scheduler.schedule_df.empty:
                print(f"  ✅ schedule_df 有資料: {len(scheduler.schedule_df)} 筆")
                print(f"  涵蓋天數: {scheduler.schedule_df['日期'].nunique()}")
            else:
                print("  ⚠️ schedule_df 是空的")
        else:
            print("  ❌ CP 執行失敗（返回 False）")
            print("  💡 這會導致回退到貪婪算法")
        
        return cp_success
        
    except Exception as e:
        print(f"\n  ❌ CP 執行出錯: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python diagnose_cp_execution.py <需求檔路徑> [日期MM/DD]")
        sys.exit(1)
    
    demand_path = sys.argv[1]
    start_date = sys.argv[2] if len(sys.argv) > 2 else "01/06"
    
    success = diagnose_cp_execution(demand_path, start_date)
    
    print("\n" + "="*70)
    if success:
        print("✅ CP 應該會被正常執行")
    else:
        print("❌ CP 不會被執行或執行失敗")
    print("="*70)