# diagnose_cp_infeasibility.py
"""
诊断 CP-SAT 为什么判定无解
"""

from scheduler_cp import CPScheduler, convert_legacy_to_cp_tasks
from Beads_Scheduler_P0_P3_V1 import Scheduler, load_all_data
import Beads_Scheduler_P0_P3_V1 as main_module
from datetime import datetime, timedelta
from ortools.sat.python import cp_model

def diagnose_infeasibility(demand_file, start_date_str):
    """逐步移除约束，找出导致无解的约束"""
    
    # 1. 载入数据
    parts = start_date_str.split('/')
    month, day = int(parts[0]), int(parts[1])
    start_date = datetime(datetime.now().year, month, day)
    
    if start_date.weekday() != 0:
        start_date = start_date - timedelta(days=start_date.weekday())
    
    main_module.SCHEDULE_START_DATE = start_date
    
    data = load_all_data(demand_file)
    scheduler = Scheduler(data)
    
    # 2. 转换任务
    cp_tasks = convert_legacy_to_cp_tasks(
        scheduler.task_queue,
        scheduler.constraints,
        scheduler.beads_dry_info
    )
    
    print(f"\n📦 任务数量: {len(cp_tasks)}")
    
    # 打印任务详情
    for task in cp_tasks:
        print(f"\n  📋 {task.id}")
        print(f"     优先级: P{task.priority}")
        print(f"     Port数: {task.num_ports if not task.is_ivek else 'IVEK'}")
        print(f"     滴定时间: {task.dosing_duration_min} 分钟")
        print(f"     凍乾时间: {task.freeze_duration_min} 分钟")
        print(f"     可用凍乾機: {', '.join(task.usable_dryers)}")
        print(f"     可用人员: {', '.join(task.usable_people)}")
        print(f"     特殊类型: {task.special_type or 'None'}")
    
    print("\n" + "="*80)
    print("🔍 开始约束诊断（逐步移除约束）")
    print("="*80)
    
    # 测试 1: 无约束（只有变量定义）
    print("\n📝 测试 1: 只有变量定义（无约束）")
    test_basic_model(cp_tasks, start_date)
    
    # 测试 2: 只有 Port 容量约束
    print("\n📝 测试 2: 只有 Port 容量约束")
    test_port_only(cp_tasks, start_date)
    
    # 测试 3: Port + 凍乾機约束
    print("\n📝 测试 3: Port + 凍乾機约束")
    test_port_dryer(cp_tasks, start_date)
    
    # 测试 4: Port + 凍乾機 + 人员约束
    print("\n📝 测试 4: Port + 凍乾機 + 人员约束")
    test_port_dryer_person(cp_tasks, start_date)
    
    # 测试 5: 全部约束（除禁止收药）
    print("\n📝 测试 5: 全部约束（除禁止收药时段）")
    test_without_forbidden_harvest(cp_tasks, start_date)
    
    # 测试 6: 全部约束
    print("\n📝 测试 6: 全部约束")
    test_full_model(cp_tasks, start_date)

def test_basic_model(cp_tasks, start_date):
    """测试 1: 最基础的模型（只有变量）"""
    
    cp_scheduler = CPScheduler(
        tasks=cp_tasks,
        base_monday=start_date,
        max_days=7,  # 增加天数
        holidays=set(),
        vacation_staff={}
    )
    
    # 只创建变量，不添加约束
    cp_scheduler._build_resource_maps()
    cp_scheduler._create_variables()
    
    # 简单的目标：最小化 makespan
    makespan = cp_scheduler.model.NewIntVar(0, cp_scheduler.horizon, 'makespan')
    
    for task in cp_tasks:
        task_end = cp_scheduler.model.NewIntVar(0, cp_scheduler.horizon, f'end_{task.id}')
        cp_scheduler.model.Add(task_end == cp_scheduler.start_vars[task.id] + task.total_duration_min)
        cp_scheduler.model.Add(makespan >= task_end)
    
    cp_scheduler.model.Minimize(makespan)
    
    # 求解
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60
    status = solver.Solve(cp_scheduler.model)
    
    print(f"  结果: {solver.StatusName(status)}")
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        print(f"  ✅ 有解！makespan = {solver.Value(makespan) / 60:.1f} 小时")
    else:
        print(f"  ❌ 无解")

def test_port_only(cp_tasks, start_date):
    """测试 2: 只有 Port 容量约束"""
    
    cp_scheduler = CPScheduler(
        tasks=cp_tasks,
        base_monday=start_date,
        max_days=7,
        holidays=set(),
        vacation_staff={}
    )
    
    cp_scheduler._build_resource_maps()
    cp_scheduler._create_variables()
    cp_scheduler._add_port_capacity_constraints()
    cp_scheduler._set_objective()
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60
    status = solver.Solve(cp_scheduler.model)
    
    print(f"  结果: {solver.StatusName(status)}")

def test_port_dryer(cp_tasks, start_date):
    """测试 3: Port + 凍乾機约束"""
    
    cp_scheduler = CPScheduler(
        tasks=cp_tasks,
        base_monday=start_date,
        max_days=7,
        holidays=set(),
        vacation_staff={}
    )
    
    cp_scheduler._build_resource_maps()
    cp_scheduler._create_variables()
    cp_scheduler._add_port_capacity_constraints()
    cp_scheduler._add_dryer_capacity_constraints()
    cp_scheduler._set_objective()
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60
    status = solver.Solve(cp_scheduler.model)
    
    print(f"  结果: {solver.StatusName(status)}")

def test_port_dryer_person(cp_tasks, start_date):
    """测试 4: Port + 凍乾機 + 人员约束"""
    
    cp_scheduler = CPScheduler(
        tasks=cp_tasks,
        base_monday=start_date,
        max_days=7,
        holidays=set(),
        vacation_staff={}
    )
    
    cp_scheduler._build_resource_maps()
    cp_scheduler._create_variables()
    cp_scheduler._add_port_capacity_constraints()
    cp_scheduler._add_dryer_capacity_constraints()
    cp_scheduler._add_person_capacity_constraints()
    cp_scheduler._set_objective()
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60
    status = solver.Solve(cp_scheduler.model)
    
    print(f"  结果: {solver.StatusName(status)}")

def test_without_forbidden_harvest(cp_tasks, start_date):
    """测试 5: 全部约束（除禁止收药时段）"""
    
    cp_scheduler = CPScheduler(
        tasks=cp_tasks,
        base_monday=start_date,
        max_days=7,
        holidays=set(),
        vacation_staff={}
    )
    
    cp_scheduler._build_resource_maps()
    cp_scheduler._create_variables()
    cp_scheduler._add_port_capacity_constraints()
    cp_scheduler._add_dryer_capacity_constraints()
    cp_scheduler._add_person_capacity_constraints()
    # cp_scheduler._add_forbidden_harvest_constraints()  # 🔥 跳过此约束
    cp_scheduler._add_special_case_constraints()
    cp_scheduler._add_dryer_contamination_constraints()
    cp_scheduler._set_objective()
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60
    status = solver.Solve(cp_scheduler.model)
    
    print(f"  结果: {solver.StatusName(status)}")

def test_full_model(cp_tasks, start_date):
    """测试 6: 完整模型"""
    
    cp_scheduler = CPScheduler(
        tasks=cp_tasks,
        base_monday=start_date,
        max_days=7,
        holidays=set(),
        vacation_staff={}
    )
    
    cp_scheduler.build_model()
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60
    status = solver.Solve(cp_scheduler.model)
    
    print(f"  结果: {solver.StatusName(status)}")

if __name__ == "__main__":
    import sys
    
    demand_file = sys.argv[1] if len(sys.argv) > 1 else "需求檔.xlsx"
    date_str = sys.argv[2] if len(sys.argv) > 2 else "12/29"
    
    diagnose_infeasibility(demand_file, date_str)