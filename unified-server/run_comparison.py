"""
执行 CP-SAT vs 贪婪算法对比测试
"""

import sys
import os
from datetime import datetime, timedelta

# 添加路径
sys.path.insert(0, os.path.dirname(__file__))

from Beads_Scheduler_P0_P3_V1 import (
    Scheduler, load_all_data,
    setup_holidays_from_args, setup_batch_start_from_args,
    setup_vacation_staff_from_args
)
import Beads_Scheduler_P0_P3_V1 as main_module

from scheduler_integration import run_cp_scheduler_integrated
from compare_algorithms import AlgorithmComparator

def run_greedy_scheduler(data, start_date):
    """运行贪婪算法"""
    print("\n" + "="*80, file=sys.stderr)
    print("🏃 运行贪婪算法...", file=sys.stderr)
    print("="*80, file=sys.stderr)
    
    # 设置全局变量
    main_module.SCHEDULE_START_DATE = start_date
    
    scheduler = Scheduler(data)
    scheduler.run()
    
    return scheduler

def run_cp_scheduler(data, start_date):
    """运行 CP-SAT"""
    print("\n" + "="*80, file=sys.stderr)
    print("🧠 运行 CP-SAT...", file=sys.stderr)
    print("="*80, file=sys.stderr)
    
    # 设置全局变量
    main_module.SCHEDULE_START_DATE = start_date
    
    scheduler = Scheduler(data)
    
    # 先处理 P0 和 no_dryer
    scheduler.handle_p0_orders()
    scheduler.handle_no_dryer_tasks()
    
    # 运行 CP
    success = run_cp_scheduler_integrated(scheduler)
    
    if not success:
        print("  ⚠️ CP-SAT 失败，回退到贪婪算法", file=sys.stderr)
        scheduler.run()
    
    return scheduler

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='CP-SAT vs 贪婪算法对比')
    parser.add_argument('--need', required=True, help='需求檔路径')
    parser.add_argument('--date', required=True, help='开始日期 MM/DD')
    parser.add_argument('--holidays', default='', help='休假日')
    parser.add_argument('--vacation-staff', default='', help='休假人员')
    
    args = parser.parse_args()
    
    # ========================================
    # 1. 设置全局参数
    # ========================================
    parts = args.date.split('/')
    month, day = int(parts[0]), int(parts[1])
    start_date = datetime(datetime.now().year, month, day)
    
    if start_date.weekday() != 0:
        start_date = start_date - timedelta(days=start_date.weekday())
    
    # 设置全局变量
    main_module.SCHEDULE_START_DATE = start_date
    
    if args.holidays:
        setup_holidays_from_args(args.holidays, start_date)
    
    if args.vacation_staff:
        setup_vacation_staff_from_args(args.vacation_staff, start_date)
    
    print(f"\n📅 排程起始日期: {start_date.strftime('%Y-%m-%d')}")
    
    # ========================================
    # 2. 载入数据
    # ========================================
    print(f"\n📦 载入数据: {args.need}")
    
    data = load_all_data(args.need)
    
    if not data:
        print("❌ 数据载入失败")
        return
    
    # ========================================
    # 3. 创建对比器
    # ========================================
    comparator = AlgorithmComparator()
    
    # ========================================
    # 4. 运行贪婪算法
    # ========================================
    greedy_scheduler = run_greedy_scheduler(data, start_date)
    comparator.evaluate_schedule(greedy_scheduler, 'greedy')
    
    # ========================================
    # 5. 运行 CP-SAT
    # ========================================
    # 重新载入数据（避免状态污染）
    data_cp = load_all_data(args.need)
    cp_scheduler = run_cp_scheduler(data_cp, start_date)
    comparator.evaluate_schedule(cp_scheduler, 'cp')
    
    # ========================================
    # 6. 对比结果
    # ========================================
    winner = comparator.compare()
    
    # ========================================
    # 7. 保存报告
    # ========================================
    comparator.save_report('comparison_report.json')
    
    # ========================================
    # 8. 输出结论
    # ========================================
    print("\n" + "="*80)
    print("📝 结论:")
    print("="*80)
    
    if winner == 'cp':
        print("✅ CP-SAT 在完工时间和资源利用率上表现更优")
    elif winner == 'greedy':
        print("✅ 贪婪算法在完工时间和资源利用率上表现更优")
    else:
        print("🤝 两种算法表现相当")
    
    print("="*80 + "\n")

if __name__ == "__main__":
    main()