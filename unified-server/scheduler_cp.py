"""
Beads Scheduler - CP-SAT 版本 (修复 Port 约束)
使用 Google OR-Tools 進行約束規劃排程
"""

from ortools.sat.python import cp_model
from datetime import datetime, timedelta, time
from dataclasses import dataclass
from typing import List, Dict, Set, Tuple, Optional
import pandas as pd

# ========================================
# 資料類別定義
# ========================================

@dataclass
class Task:
    """單一排程任務"""
    id: str                          # 唯一識別碼
    pn: str                          # 料號
    marker: str                      # 藥名
    priority: int                    # 優先級 (0=P0, 1=P1, ...)
    quantity: float                  # 數量
    num_ports: int                   # Port 數量
    dosing_duration_min: int         # 滴定時間（分鐘）
    freeze_duration_min: int         # 凍乾時間（分鐘）
    usable_dryers: List[str]         # 可用凍乾機列表
    usable_people: List[str]         # 可用人員列表
    is_ivek: bool = False            # 是否為 IVEK
    special_type: Optional[str] = None  # 特殊類型 (GLIPA_AD, tCREA_B1, ...)
    
    @property
    def total_duration_min(self) -> int:
        """總處理時間（分鐘）"""
        return self.dosing_duration_min + self.freeze_duration_min

@dataclass
class Resource:
    """資源定義"""
    name: str
    capacity: int = 1  # 容量（Port 是 12，凍乾機/人員是 1）

@dataclass
class ScheduleResult:
    """排程結果"""
    task_id: str
    start_time_min: int      # 開始時間（分鐘，從週一 00:00 起算）
    dryer: str
    person: str
    ports: List[int]         # 使用的 Port 編號
    
    def get_datetime(self, base_monday: datetime) -> datetime:
        """轉換為實際日期時間"""
        return base_monday + timedelta(minutes=self.start_time_min)
    
    def get_day_index(self) -> int:
        """取得第幾天（0=週一）"""
        return self.start_time_min // (24 * 60)
    
    def get_shift(self) -> str:
        """取得班次"""
        hour = (self.start_time_min % (24 * 60)) // 60
        return "AM" if hour < 15 else "PM"

# ========================================
# CP 排程器主類別
# ========================================

class CPScheduler:
    """基於 CP-SAT 的排程器（修复版）"""
    
    def __init__(self, 
                 tasks: List[Task],
                 base_monday: datetime,
                 max_days: int = 7,
                 holidays: Set[datetime.date] = None,
                 vacation_staff: Dict[str, Set[str]] = None):
        
        self.tasks = tasks
        self.base_monday = base_monday
        self.max_days = max_days
        self.holidays = holidays or set()
        self.vacation_staff = vacation_staff or {}
        
        # 計算時間範圍（分鐘）
        self.horizon = max_days * 24 * 60
        
        # CP 模型
        self.model = cp_model.CpModel()
        
        # 變數字典
        self.start_vars = {}        # task_id -> IntVar (開始時間)
        self.dryer_vars = {}        # task_id -> IntVar (凍乾機索引)
        self.person_vars = {}       # task_id -> IntVar (人員索引)
        self.port_vars = {}         # task_id -> List[IntVar] (Port 編號)
        
        # 輔助映射
        self.dryer_to_idx = {}      # dryer_name -> index
        self.idx_to_dryer = {}
        self.person_to_idx = {}
        self.idx_to_person = {}
        
    def build_model(self):
        """建構 CP 模型"""
        print("\n🔨 開始建構 CP 模型...", flush=True)
        
        # 1. 建立資源索引映射
        self._build_resource_maps()
        
        # 2. 建立變數
        self._create_variables()
        
        # 3. 新增約束
        self._add_port_capacity_constraints()  # 🔥 使用修复后的方法
        self._add_dryer_capacity_constraints()
        self._add_person_capacity_constraints()
        self._add_forbidden_harvest_constraints()
        self._add_special_case_constraints()
        self._add_dryer_contamination_constraints()
        self._add_holiday_constraints()
        
        # 4. 設定目標
        self._set_objective()
        
        print("✅ CP 模型建構完成\n", flush=True)
    
    def _build_resource_maps(self):
        """建立資源索引映射"""
        # 收集所有凍乾機
        all_dryers = set()
        for task in self.tasks:
            all_dryers.update(task.usable_dryers)
        
        for idx, dryer in enumerate(sorted(all_dryers)):
            self.dryer_to_idx[dryer] = idx
            self.idx_to_dryer[idx] = dryer
        
        # 收集所有人員
        all_people = set()
        for task in self.tasks:
            all_people.update(task.usable_people)
        
        for idx, person in enumerate(sorted(all_people)):
            self.person_to_idx[person] = idx
            self.idx_to_person[idx] = person
        
        print(f"  資源統計: {len(all_dryers)} 台凍乾機, {len(all_people)} 位人員", flush=True)
    
    def _create_variables(self):
        """建立決策變數"""
        for task in self.tasks:
            # 開始時間
            self.start_vars[task.id] = self.model.NewIntVar(
                0, self.horizon - task.total_duration_min, f'start_{task.id}'
            )
            
            # 凍乾機選擇
            if not task.is_ivek:
                dryer_indices = [self.dryer_to_idx[d] for d in task.usable_dryers]
                self.dryer_vars[task.id] = self.model.NewIntVarFromDomain(
                    cp_model.Domain.FromValues(dryer_indices), f'dryer_{task.id}'
                )
            
            # 人員選擇
            person_indices = [self.person_to_idx[p] for p in task.usable_people]
            self.person_vars[task.id] = self.model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(person_indices), f'person_{task.id}'
            )
            
            # Port 分配（IVEK 不需要）
            if not task.is_ivek:
                self.port_vars[task.id] = [
                    self.model.NewIntVar(1, 12, f'port_{task.id}_{i}')
                    for i in range(task.num_ports)
                ]
                
                # 強制 Port 遞增（避免重複組合）
                for i in range(len(self.port_vars[task.id]) - 1):
                    self.model.Add(self.port_vars[task.id][i] < self.port_vars[task.id][i+1])
                
                # 強制從單數開始（Odd Alignment）
                self.model.AddModuloEquality(1, self.port_vars[task.id][0], 2)
    
    def _add_port_capacity_constraints(self):
        """
        Port 容量約束 - 使用 Cumulative Constraint (修复版)
        任何時刻同時進行滴定的任務，Port 總數不超過 12
        """
        print("  ➕ Port 容量約束 (Cumulative)...", flush=True)
        
        intervals = []
        demands = []
        
        for task in self.tasks:
            if task.is_ivek:
                continue
            
            # 滴定階段的區間 [start, start + dosing_duration)
            dosing_start = self.start_vars[task.id]
            dosing_duration = task.dosing_duration_min
            dosing_end = self.model.NewIntVar(
                0, self.horizon, f'dosing_end_{task.id}'
            )
            self.model.Add(dosing_end == dosing_start + dosing_duration)
            
            # 創建滴定區間
            dosing_interval = self.model.NewIntervalVar(
                dosing_start,
                dosing_duration,
                dosing_end,
                f'dosing_interval_{task.id}'
            )
            
            intervals.append(dosing_interval)
            demands.append(task.num_ports)
        
        # AddCumulative: 任何時刻的 Port 總需求 <= 12
        if intervals:
            self.model.AddCumulative(intervals, demands, 12)
            print(f"    ✅ Cumulative 約束: {len(intervals)} 個滴定區間, 容量 = 12 Port", flush=True)
    
    def _add_dryer_capacity_constraints(self):
        """凍乾機容量約束（同一台同時只能處理一個任務）"""
        print("  ➕ 凍乾機容量約束...", flush=True)
        
        # 按凍乾機分組
        tasks_by_dryer_pool = {}
        for task in self.tasks:
            if task.is_ivek:
                continue
            for dryer in task.usable_dryers:
                if dryer not in tasks_by_dryer_pool:
                    tasks_by_dryer_pool[dryer] = []
                tasks_by_dryer_pool[dryer].append(task)
        
        # 為每台凍乾機新增 NoOverlap 約束
        for dryer, tasks in tasks_by_dryer_pool.items():
            intervals = []
            
            for task in tasks:
                # 建立條件區間變數
                # 僅當任務使用此凍乾機時，才啟用區間
                
                uses_this_dryer = self.model.NewBoolVar(f'{task.id}_uses_{dryer}')
                dryer_idx = self.dryer_to_idx[dryer]
                
                self.model.Add(self.dryer_vars[task.id] == dryer_idx).OnlyEnforceIf(uses_this_dryer)
                self.model.Add(self.dryer_vars[task.id] != dryer_idx).OnlyEnforceIf(uses_this_dryer.Not())
                
                # 凍乾階段的區間 [dosing_end, total_end)
                dosing_end_var = self.model.NewIntVar(0, self.horizon, f'{task.id}_dosing_end')
                self.model.Add(dosing_end_var == self.start_vars[task.id] + task.dosing_duration_min)
                
                freeze_end_var = self.model.NewIntVar(0, self.horizon, f'{task.id}_freeze_end')
                self.model.Add(freeze_end_var == dosing_end_var + task.freeze_duration_min)
                
                # 建立可選區間
                interval = self.model.NewOptionalIntervalVar(
                    dosing_end_var,
                    task.freeze_duration_min,
                    freeze_end_var,
                    uses_this_dryer,
                    f'freeze_interval_{task.id}_{dryer}'
                )
                intervals.append(interval)
            
            # 該凍乾機的所有區間不能重疊
            if intervals:
                self.model.AddNoOverlap(intervals)
    
    def _add_person_capacity_constraints(self):
        """人員容量約束（同一人同一班次只能做一個任務）"""
        print("  ➕ 人員容量約束...", flush=True)
        
        # 每個班次（12 小時 = 720 分鐘）
        shift_duration = 12 * 60
        
        for shift_start in range(0, self.horizon, shift_duration):
            shift_end = shift_start + shift_duration
            
            # 按人員分組
            for person_idx in range(len(self.person_to_idx)):
                person_tasks = []
                
                for task in self.tasks:
                    if person_idx not in [self.person_to_idx[p] for p in task.usable_people]:
                        continue
                    
                    # 任務是否使用此人且在此班次？
                    uses_person = self.model.NewBoolVar(f'{task.id}_uses_p{person_idx}_shift{shift_start}')
                    in_shift = self.model.NewBoolVar(f'{task.id}_in_shift{shift_start}')
                    
                    self.model.Add(self.person_vars[task.id] == person_idx).OnlyEnforceIf(uses_person)
                    self.model.Add(self.start_vars[task.id] >= shift_start).OnlyEnforceIf(in_shift)
                    self.model.Add(self.start_vars[task.id] < shift_end).OnlyEnforceIf(in_shift)
                    
                    both = self.model.NewBoolVar(f'both_p{person_idx}_{task.id}_s{shift_start}')
                    self.model.AddBoolAnd([uses_person, in_shift]).OnlyEnforceIf(both)
                    
                    person_tasks.append(both)
                
                # 該人員在該班次最多做一個任務
                if person_tasks:
                    self.model.Add(sum(person_tasks) <= 1)
    
    def _add_forbidden_harvest_constraints(self):
        """禁止收藥時段約束（03:00-08:00）"""
        print("  ➕ 禁止收藥時段約束...", flush=True)
        
        forbidden_start_min = 3 * 60   # 03:00
        forbidden_end_min = 8 * 60     # 08:00
        
        for task in self.tasks:
            end_time = self.model.NewIntVar(0, self.horizon, f'end_{task.id}')
            self.model.Add(end_time == self.start_vars[task.id] + task.total_duration_min)
            
            # 計算收藥時間在當天的分鐘數（0-1439）
            end_time_of_day = self.model.NewIntVar(0, 24 * 60 - 1, f'end_tod_{task.id}')
            self.model.AddModuloEquality(end_time_of_day, end_time, 24 * 60)
            
            # 不能在 [180, 480) 區間內
            is_forbidden = self.model.NewBoolVar(f'forbidden_{task.id}')
            
            self.model.Add(end_time_of_day >= forbidden_start_min).OnlyEnforceIf(is_forbidden)
            self.model.Add(end_time_of_day < forbidden_end_min).OnlyEnforceIf(is_forbidden)
            
            # 禁止
            self.model.Add(is_forbidden == 0)
    
    def _add_special_case_constraints(self):
        """特殊案例約束（GLIPA, tCREA, Na 系列）"""
        print("  ➕ 特殊案例約束...", flush=True)
        
        # GLIPA: 雙凍乾機（同時開始，不同凍乾機）
        glipa_tasks = [t for t in self.tasks if t.special_type and 'GLIPA' in t.special_type]
        if len(glipa_tasks) >= 2:
            t1, t2 = glipa_tasks[0], glipa_tasks[1]
            
            # 同時開始
            self.model.Add(self.start_vars[t1.id] == self.start_vars[t2.id])
            
            # 不同凍乾機
            self.model.Add(self.dryer_vars[t1.id] != self.dryer_vars[t2.id])
            
            print(f"    • GLIPA 雙凍乾機: {t1.id} ≠ {t2.id}", flush=True)
        
        # tCREA: Batch1 和 Batch2 同天不同時段
        tcrea_b1 = [t for t in self.tasks if t.special_type == 'tCREA_B1']
        tcrea_b2 = [t for t in self.tasks if t.special_type == 'tCREA_B2']
        
        if tcrea_b1 and tcrea_b2:
            for t1 in tcrea_b1:
                for t2 in tcrea_b2:
                    # 同一天
                    day1 = self.model.NewIntVar(0, self.max_days - 1, f'day_{t1.id}')
                    day2 = self.model.NewIntVar(0, self.max_days - 1, f'day_{t2.id}')
                    
                    self.model.AddDivisionEquality(day1, self.start_vars[t1.id], 24 * 60)
                    self.model.AddDivisionEquality(day2, self.start_vars[t2.id], 24 * 60)
                    
                    self.model.Add(day1 == day2)
                    
                    # 不同時段（時間差 >= 6 小時）
                    time_diff = self.model.NewIntVar(0, self.horizon, f'diff_{t1.id}_{t2.id}')
                    self.model.AddAbsEquality(time_diff, self.start_vars[t1.id] - self.start_vars[t2.id])
                    self.model.Add(time_diff >= 6 * 60)
                    
                    # 不同凍乾機
                    self.model.Add(self.dryer_vars[t1.id] != self.dryer_vars[t2.id])
                    
                    print(f"    • tCREA 同日異時: {t1.id} 與 {t2.id}", flush=True)
    
    def _add_dryer_contamination_constraints(self):
        """凍乾機污染約束（CK/PHOS/K 後 3 天內 GLIPA 不可用）"""
        print("  ➕ 凍乾機污染約束...", flush=True)
        
        blocking_tasks = [t for t in self.tasks if t.special_type in ['CK', 'PHOS', 'K']]
        glipa_tasks = [t for t in self.tasks if t.special_type and 'GLIPA' in t.special_type]
        
        contamination_days = 3
        
        for blocking_task in blocking_tasks:
            for glipa_task in glipa_tasks:
                # 如果使用同一台凍乾機
                same_dryer = self.model.NewBoolVar(f'same_dryer_{blocking_task.id}_{glipa_task.id}')
                
                self.model.Add(
                    self.dryer_vars[blocking_task.id] == self.dryer_vars[glipa_task.id]
                ).OnlyEnforceIf(same_dryer)
                
                # 則 GLIPA 必須在 blocking 任務結束後 3 天
                blocking_end = self.model.NewIntVar(0, self.horizon, f'end_{blocking_task.id}')
                self.model.Add(
                    blocking_end == self.start_vars[blocking_task.id] + blocking_task.total_duration_min
                )
                
                self.model.Add(
                    self.start_vars[glipa_task.id] >= blocking_end + contamination_days * 24 * 60
                ).OnlyEnforceIf(same_dryer)
        
        if blocking_tasks and glipa_tasks:
            print(f"    • 污染規則: {len(blocking_tasks)} 個污染源 → {len(glipa_tasks)} 個 GLIPA", flush=True)
    
    def _add_holiday_constraints(self):
        """休假日約束（任務不能在休假日進行）"""
        if not self.holidays:
            return
        
        print(f"  ➕ 休假日約束 ({len(self.holidays)} 天)...", flush=True)
        
        for holiday in self.holidays:
            day_offset = (holiday - self.base_monday.date()).days
            
            if day_offset < 0 or day_offset >= self.max_days:
                continue
            
            # 該天的時間範圍
            holiday_start = day_offset * 24 * 60
            holiday_end = (day_offset + 1) * 24 * 60
            
            for task in self.tasks:
                # 任務不能在休假日開始
                is_on_holiday = self.model.NewBoolVar(f'{task.id}_on_{holiday}')
                
                self.model.Add(self.start_vars[task.id] >= holiday_start).OnlyEnforceIf(is_on_holiday)
                self.model.Add(self.start_vars[task.id] < holiday_end).OnlyEnforceIf(is_on_holiday)
                
                # 禁止
                self.model.Add(is_on_holiday == 0)
    
    def _set_objective(self):
        """設定優化目標"""
        print("  🎯 設定目標函數...", flush=True)
        
        # 目標 1: 最小化完成時間 (makespan)
        makespan = self.model.NewIntVar(0, self.horizon, 'makespan')
        
        for task in self.tasks:
            task_end = self.model.NewIntVar(0, self.horizon, f'end_{task.id}')
            self.model.Add(task_end == self.start_vars[task.id] + task.total_duration_min)
            self.model.Add(makespan >= task_end)
        
        # 目標 2: 懲罰高優先級任務的延遲
        weighted_vars = []
        
        for task in self.tasks:
            # 為每個任務建立加權結束時間變數
            task_end_var = self.model.NewIntVar(0, self.horizon, f'end_{task.id}_var')
            self.model.Add(task_end_var == self.start_vars[task.id] + task.total_duration_min)
            
            # P0 權重 1000, P1 權重 100, P2 權重 10, P3 權重 1
            weight = {0: 1000, 1: 100, 2: 10, 3: 1}.get(task.priority, 1)
            
            # 使用線性表達式
            weighted_vars.append(task_end_var * weight)
        
        # 修正：使用適當的縮放
        # makespan 優先（乘以 100），加上加權完成時間
        self.model.Minimize(makespan * 100 + sum(weighted_vars))
    
        print("  ✅ 目標函數設定完成", flush=True)
        
    def solve(self, time_limit_sec: int = 300) -> Tuple[bool, List[ScheduleResult]]:
        """求解模型"""
        print(f"\n🚀 開始求解 (時間限制: {time_limit_sec} 秒)...\n", flush=True)
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_sec
        solver.parameters.log_search_progress = True
        solver.parameters.num_search_workers = 8  # 多核心加速
        
        status = solver.Solve(self.model)
        
        if status == cp_model.OPTIMAL:
            print("\n✅ 找到最優解！\n", flush=True)
        elif status == cp_model.FEASIBLE:
            print("\n✅ 找到可行解（未達最優）\n", flush=True)
        else:
            print(f"\n❌ 無解 (狀態: {solver.StatusName(status)})\n", flush=True)
            return False, []
        
        # 提取結果
        results = []
        
        for task in self.tasks:
            start_min = solver.Value(self.start_vars[task.id])
            
            dryer = "IVEK" if task.is_ivek else self.idx_to_dryer[solver.Value(self.dryer_vars[task.id])]
            person = self.idx_to_person[solver.Value(self.person_vars[task.id])]
            
            ports = []
            if not task.is_ivek:
                ports = [solver.Value(pv) for pv in self.port_vars[task.id]]
            
            results.append(ScheduleResult(
                task_id=task.id,
                start_time_min=start_min,
                dryer=dryer,
                person=person,
                ports=ports
            ))
        
        # 統計
        makespan_min = max(r.start_time_min + t.total_duration_min 
                          for r, t in zip(results, self.tasks))
        
        print(f"📊 排程統計:", flush=True)
        print(f"  完成時間: {makespan_min / 60:.1f} 小時 ({makespan_min / (24*60):.2f} 天)", flush=True)
        print(f"  任務總數: {len(results)}", flush=True)
        print(f"  求解時間: {solver.WallTime():.2f} 秒\n", flush=True)
        
        return True, results

# ========================================
# 輔助函數：轉換現有資料
# ========================================

def convert_legacy_to_cp_tasks(
    task_queue: list,
    constraints_df: pd.DataFrame,
    beads_dry_info: pd.DataFrame
) -> List[Task]:
    """將現有的 task_queue 轉換為 CP 任務列表"""
    
    cp_tasks = []
    
    for task in task_queue:
        priority, _, pn, qty_short, tag, group_name, marker_name, bdc_qty = task
        
        # 取得約束
        if pn not in constraints_df.index:
            continue
        
        c = constraints_df.loc[pn]
        if isinstance(c, pd.DataFrame):
            c = c.iloc[0]
        
        # Port 數
        port_str = str(c.get("Port數", "2")).strip()
        is_ivek = (port_str.upper() == "IVEK")
        num_ports = 0 if is_ivek else int(port_str)
        
        # 時間計算
        prod_qty = bdc_qty if bdc_qty > 0 else qty_short
        dosing_hrs = (prod_qty / (1500 * max(num_ports, 1))) + 0.5
        freeze_hrs = float(c.get("凍乾時間", 12.0))
        
        # 可用資源
        dryer_str = str(c.get("可用凍乾機", "")).strip()
        usable_dryers = [d.strip() for d in dryer_str.split(',') if d.strip()] if dryer_str else []
        
        usable_people = []
        for key in ["配藥人-1", "配藥人-2", "配藥人-3"]:
            person = c.get(key)
            if person and str(person).strip():
                usable_people.append(str(person).strip())
        
        # 特殊類型判斷
        special_type = None
        if pn in ['5714400220', '5714400221']:
            special_type = 'GLIPA_AD' if pn == '5714400220' else 'GLIPA_AU'
        elif pn in ['5714400180', '5714400181']:
            special_type = 'tCREA_B1'
        elif pn == '5714400182':
            special_type = 'tCREA_B2'
        elif pn in ['5714400222', '5714400199']:
            special_type = 'CK'
        elif pn in ['5714400214', '5714400215']:
            special_type = 'PHOS'
        elif pn in ['5714400116', '5714400226', '5714400216', '5714400117']:
            special_type = 'K'
        
        cp_task = Task(
            id=f"{group_name}_{pn}",
            pn=pn,
            marker=marker_name,
            priority=priority,
            quantity=prod_qty,
            num_ports=num_ports,
            dosing_duration_min=int(dosing_hrs * 60),
            freeze_duration_min=int(freeze_hrs * 60),
            usable_dryers=usable_dryers,
            usable_people=usable_people,
            is_ivek=is_ivek,
            special_type=special_type
        )
        
        cp_tasks.append(cp_task)
    
    return cp_tasks