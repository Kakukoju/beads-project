"""
排程整合層
負責 CP 排程器與原程式之間的資料轉換
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from scheduler_cp import (
    Task, CPScheduler, ScheduleResult,
    convert_legacy_to_cp_tasks
)

# ========================================
# CP 結果 → schedule_df 轉換
# ========================================

def convert_cp_results_to_schedule_df(
    results: List[ScheduleResult],
    tasks: List[Task],
    base_monday: datetime,
    work_order_start: int = 1
) -> pd.DataFrame:
    """
    將 CP 排程結果轉換為原程式的 schedule_df 格式
    
    Args:
        results: CP 排程結果列表
        tasks: 任務列表
        base_monday: 週一基準日期
        work_order_start: 工單起始編號
    
    Returns:
        符合原程式格式的 DataFrame
    """
    
    records = []
    work_order_counter = work_order_start
    pn_work_order_map = {}
    pn_week_port_counter = {}
    
    # 按日期和班次排序
    sorted_results = sorted(
        zip(results, tasks),
        key=lambda x: (x[0].start_time_min, x[0].get_shift())
    )
    
    for result, task in sorted_results:
        # ========================================
        # 1. 計算時間資訊
        # ========================================
        start_dt = result.get_datetime(base_monday)
        day_key = start_dt.strftime("%Y-%m-%d")
        shift = result.get_shift()
        
        # RD 給藥時間
        rd_time = start_dt.strftime("%H:%M")
        
        # 滴定時間
        dosing_start_dt = start_dt + timedelta(minutes=30)  # 準備時間
        dosing_start_str = dosing_start_dt.strftime("%H:%M")
        
        # 滴定結束時間
        dosing_end_dt = dosing_start_dt + timedelta(minutes=task.dosing_duration_min)
        
        # 預計結束時間（收藥）
        final_end_dt = start_dt + timedelta(minutes=task.total_duration_min)
        final_end_str = final_end_dt.strftime("%H:%M")
        
        # 預冷時間（滴定結束後 2 小時）
        precool_dt = dosing_end_dt + timedelta(hours=2)
        precool_str = precool_dt.strftime("%H:%M")
        
        # 凍乾時間（小時）
        freeze_hrs = task.freeze_duration_min / 60
        
        # ========================================
        # 2. 工單號碼生成
        # ========================================
        if task.pn not in pn_work_order_map:
            try:
                year_yy = start_dt.strftime("%y")
                month_char = chr(64 + start_dt.month)  # A=1月, B=2月...
                work_order_num = f"TMRA{year_yy}{month_char}{work_order_counter:03d}"
                pn_work_order_map[task.pn] = work_order_num
                work_order_counter += 1
            except:
                pn_work_order_map[task.pn] = f"TMRA25L{work_order_counter:03d}"
                work_order_counter += 1
        
        work_order = pn_work_order_map[task.pn]
        
        # ========================================
        # 3. Batch Code 生成
        # ========================================
        try:
            iso_year, iso_week, _ = start_dt.isocalendar()
            year_yy = start_dt.strftime("%y")
            pn_last3 = task.pn[-3:] if len(task.pn) >= 3 else task.pn.zfill(3)
            
            # 計算同一週內同一 PN 的批次計數
            pn_week_key = (task.pn, iso_week)
            if pn_week_key not in pn_week_port_counter:
                pn_week_port_counter[pn_week_key] = 0
            pn_week_port_counter[pn_week_key] += 1
            port_count = pn_week_port_counter[pn_week_key]
            
            # 批次序號字元（1-8 直接用數字，9 用 A，10 用 B...）
            if port_count <= 8:
                count_char = str(port_count)
            elif port_count == 9:
                count_char = 'A'
            else:
                count_char = chr(65 + (port_count - 9))
            
            batch_code = f"{pn_last3}{year_yy}{iso_week:02d}{count_char}"
        except:
            batch_code = f"{task.pn}_BATCH"
        
        # ========================================
        # 4. 滴定機顯示（支援 IVEK 和 Port）
        # ========================================
        if task.is_ivek:
            # IVEK 任務：拆成兩筆（原邏輯）
            qty_per_record = task.quantity / 2
            
            for i in range(2):
                record = {
                    "日期": day_key,
                    "marker": task.marker,
                    "滴定機": "IVEK",
                    "凍乾機台": result.dryer,
                    "數量": qty_per_record,
                    "配藥同仁": result.person,
                    "RD給藥時間": rd_time,
                    "預計滴定時間": dosing_start_str,
                    "預計結束": final_end_str,
                    "預冷時間": precool_str,
                    "凍乾時間": f"{freeze_hrs:.1f} hr",
                    "收藥時間": final_end_str,
                    "lot": task.pn,
                    "班次": shift,
                    "ports_list": "IVEK",
                    "工單號碼": work_order,
                    "Lot": batch_code,
                    "備註": "",
                    "record_type": "P1-P5",
                    "has_conflict": False
                }
                records.append(record)
        
        else:
            # Port 任務：可能多個 Port
            qty_per_port = task.quantity / len(result.ports) if result.ports else task.quantity
            
            for port_num in result.ports:
                record = {
                    "日期": day_key,
                    "marker": task.marker,
                    "滴定機": f"Port{port_num}",
                    "凍乾機台": result.dryer,
                    "數量": qty_per_port,
                    "配藥同仁": result.person,
                    "RD給藥時間": rd_time,
                    "預計滴定時間": dosing_start_str,
                    "預計結束": final_end_str,
                    "預冷時間": precool_str,
                    "凍乾時間": f"{freeze_hrs:.1f} hr",
                    "收藥時間": final_end_str,
                    "lot": task.pn,
                    "班次": shift,
                    "ports_list": str(port_num),
                    "工單號碼": work_order,
                    "Lot": batch_code,
                    "備註": "",
                    "record_type": "P1-P5",
                    "has_conflict": False
                }
                records.append(record)
    
    # 轉換為 DataFrame
    df = pd.DataFrame(records)
    
    return df


# ========================================
# 主整合函數
# ========================================

def run_cp_scheduler_integrated(scheduler_instance):
    """在 Scheduler 實例中執行 CP 排程器"""
    import sys
    
    print("\n" + "="*70, file=sys.stderr)
    print("🧠 啟用 CP-SAT 排程引擎", file=sys.stderr)
    print("="*70, file=sys.stderr)
    
    try:
        # ========================================
        # 🔥 從主程式導入全域變數
        # ========================================
        import Beads_Scheduler_P0_P3_V1 as main_module
        
        # 直接使用已存在的全域變數
        SCHEDULE_START_DATE = main_module.SCHEDULE_START_DATE
        HOLIDAYS = main_module.HOLIDAYS
        VACATION_STAFF = main_module.VACATION_STAFF
        BATCH_START_NUMBER = main_module.BATCH_START_NUMBER
        
        # ✅ 驗證必要變數
        if SCHEDULE_START_DATE is None:
            print("  ❌ SCHEDULE_START_DATE 未設定", file=sys.stderr)
            print("  💡 請確認 main() 或測試腳本中有設定此變數", file=sys.stderr)
            return False
        
        print(f"  ✅ 全域變數載入成功", file=sys.stderr)
        print(f"    • 開始日期: {SCHEDULE_START_DATE.strftime('%Y-%m-%d')}", file=sys.stderr)
        print(f"    • 休假日: {len(HOLIDAYS)} 天", file=sys.stderr)
        print(f"    • 休假人員: {len(VACATION_STAFF)} 筆", file=sys.stderr)
        print(f"    • 工單起始: {BATCH_START_NUMBER}", file=sys.stderr)
        
        # ========================================
        # Step 1: 轉換任務格式
        # ========================================
        print("\n📦 Step 1: 轉換任務格式...", file=sys.stderr)
        
        cp_tasks = convert_legacy_to_cp_tasks(
            scheduler_instance.task_queue,
            scheduler_instance.constraints,
            scheduler_instance.beads_dry_info
        )
        
        if not cp_tasks:
            print("  ❌ 無有效任務，回退到貪婪算法", file=sys.stderr)
            return False
        
        print(f"  ✅ 成功轉換 {len(cp_tasks)} 個任務", file=sys.stderr)
        
        # ========================================
        # Step 2: 建立 CP 排程器
        # ========================================
        print("\n🏗️  Step 2: 建立 CP 模型...", file=sys.stderr)
        
        from scheduler_cp import CPScheduler
        
        cp_scheduler = CPScheduler(
            tasks=cp_tasks,
            base_monday=SCHEDULE_START_DATE,  # ✅ 使用正確的變數
            max_days=scheduler_instance.days_to_schedule,
            holidays=HOLIDAYS,
            vacation_staff=VACATION_STAFF
        )
        
        # ========================================
        # Step 3: 建構模型
        # ========================================
        cp_scheduler.build_model()
        
        # ========================================
        # Step 4: 求解
        # ========================================
        print("\n🚀 Step 3: 執行 CP-SAT 求解器...", file=sys.stderr)
        
        success, results = cp_scheduler.solve(time_limit_sec=300)
        
        print(f"\n  📊 求解結果: success={success}", file=sys.stderr)
        print(f"  📊 結果數量: {len(results) if results else 0}", file=sys.stderr)
        
        if not success:
            print("\n  ❌ CP 求解失敗", file=sys.stderr)
            print("  🔙 即將返回 False（觸發回退）", file=sys.stderr)
            return False  # 🔥 這會導致回退
        
        # ========================================
        # Step 5: 轉換結果
        # ========================================
        print("\n📊 Step 4: 轉換排程結果...", file=sys.stderr)
        
        schedule_df = convert_cp_results_to_schedule_df(
            results,
            cp_tasks,
            SCHEDULE_START_DATE,  # ✅ 使用正確的變數
            work_order_start=BATCH_START_NUMBER
        )
        
        print(f"  ✅ 成功生成 {len(schedule_df)} 筆排程記錄", file=sys.stderr)
        
        # ========================================
        # Step 6: 合併所有記錄
        # ========================================
        print(f"\n📦 Step 5: 合併所有記錄...", file=sys.stderr)
        
        all_records = []
        
        if hasattr(scheduler_instance, 'p0_strict_records') and scheduler_instance.p0_strict_records:
            count = len(scheduler_instance.p0_strict_records)
            print(f"  📌 P0 (非實驗): {count} 筆", file=sys.stderr)
            all_records.extend(scheduler_instance.p0_strict_records)
        
        if hasattr(scheduler_instance, 'p0_experiment_records') and scheduler_instance.p0_experiment_records:
            count = len(scheduler_instance.p0_experiment_records)
            print(f"  📌 P0 (實驗): {count} 筆", file=sys.stderr)
            all_records.extend(scheduler_instance.p0_experiment_records)
        
        if hasattr(scheduler_instance, 'no_dryer_records') and scheduler_instance.no_dryer_records:
            count = len(scheduler_instance.no_dryer_records)
            print(f"  📌 no_dryer: {count} 筆", file=sys.stderr)
            all_records.extend(scheduler_instance.no_dryer_records)
        
        all_records.extend(schedule_df.to_dict('records'))
        
        final_df = pd.DataFrame(all_records)
        
        if not final_df.empty and '日期' in final_df.columns:
            final_df = final_df.sort_values(
                ['日期', '班次'], 
                ascending=[True, True],
                na_position='last'
            )
        
        scheduler_instance.schedule_df = final_df
        
        print(f"  ✅ 合併完成，總計 {len(final_df)} 筆", file=sys.stderr)
        
        # ========================================
        # Step 7: 調用最終處理
        # ========================================
        print(f"\n💾 Step 6: 執行最終處理...", file=sys.stderr)
        
        scheduler_instance._finalize_and_output()
        
        print("\n" + "="*70, file=sys.stderr)
        print("✅ run_cp_scheduler_integrated() 執行成功", file=sys.stderr)
        print("🔙 即將返回 True", file=sys.stderr)
        print("="*70 + "\n", file=sys.stderr)
        
        return True  # 🔥 成功返回
        
    except Exception as e:
        print(f"\n❌ run_cp_scheduler_integrated() 發生錯誤: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        print("  🔙 即將返回 False（觸發回退）", file=sys.stderr)
        return False  # 🔥 錯誤返回