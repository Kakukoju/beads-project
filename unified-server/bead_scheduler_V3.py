import pandas as pd
import sqlite3
import os
import re
from datetime import datetime, timedelta, time
from pandas.api.types import is_datetime64_any_dtype as is_datetime
import traceback

# ====================================================================
# [Option A] 排程腳本 (generate_schedule_option_A_v3_pn_fix.py)
# v3 修正 + Bug Fixes
# ====================================================================

# --------------------------------------------------------------------
# 1. 設定：檔案和資料庫路徑
# --------------------------------------------------------------------
DEMAND_CSV_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\beads 需求模組.csv" 
MAIN_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\beads_sync.db"
OUTPUT_DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\drop_dry_schedule .db"
OUTPUT_TABLE_NAME = "Schedule_Temp"
OUTPUT_EXCEL_PATH = r"D:\auto_schedule\generated_schedule_option_A.xlsx"

# --- 排程設定 ---
SCHEDULING_DAYS = 5
ALLOW_EXTEND_TO_6_DAYS = True 
MAX_PORTS = 12 
DOSING_PREP_TIME_MIN = 30 
HARVEST_TIME_MIN = 30 
DOSING_RATE_PER_HR = 1000 
WORK_START_TIME = time(8, 0)
WORK_END_TIME_LATE = time(2, 0)
WORK_END_TIME_ALERT = time(3, 0)
IVEK_COMPONENTS = ["5714400202", "5714400203", "5714400209", "5714400210"]

# --------------------------------------------------------------------
# 2. 輔助工具
# --------------------------------------------------------------------
def time_str_to_float(time_str: str) -> float:
    try:
        h, m = map(int, time_str.split(':'))
        return h + m / 60.0
    except Exception: 
        return 0.0

def float_to_time_str(hours: float) -> str:
    total_minutes = int(hours * 60)
    h = (total_minutes // 60) % 24 
    m = total_minutes % 60
    return f"{h:02d}:{m:02d}"

def add_hours_to_time(start_datetime: datetime, hours: float) -> datetime:
    return start_datetime + timedelta(minutes=int(hours * 60))

# --------------------------------------------------------------------
# 3. 資料載入 (v3 修正: 標準化 PN)
# --------------------------------------------------------------------

def standardize_pn(pn_series: pd.Series) -> pd.Series:
    """將 PN 欄位標準化為字串並移除 .0"""
    return pn_series.astype(str).str.split('.').str[0]

def load_all_data():
    """載入所有必要的輸入檔案"""
    print("Step 1: 正在載入所有資料來源...")
    
    # 1. 載入需求表 (CSV)
    try:
        df_demand = pd.read_csv(DEMAND_CSV_PATH, header=1)
        
        rename_map = {
            '庫存+滴定': 'Stock_plus_Dosing',
            '第二周週需求': '第二周需求',
            '第三周週需求': '第三周需求'
        }
        df_demand = df_demand.rename(columns=rename_map)

        if '藥名' in df_demand.columns:
            df_demand['藥名'] = df_demand['藥名'].ffill()
        else:
            raise ValueError("'滴定排程需求表' 中找不到 '藥名' 欄位。")
            
        df_demand = df_demand[df_demand['料號'].notna() & (df_demand['料號'] != "")].copy()
        
        # 標準化 PN
        df_demand['料號'] = standardize_pn(df_demand['料號'])
        print("  已將 '需求表' 中的 '料號' 標準化 (移除 .0)。")
        
        required_cols = ['藥名', '料號', 'Stock_plus_Dosing', '第一周需求', '第二周需求', '第三周需求']
        missing_cols = [col for col in required_cols if col not in df_demand.columns]
        if missing_cols:
            raise ValueError(f"需求表缺少必要欄位: {missing_cols}")

        demand_cols = ['Stock_plus_Dosing', '第一周需求', '第二周需求', '第三周需求']
        for col in demand_cols:
            df_demand[col] = pd.to_numeric(df_demand[col], errors='coerce').fillna(0)

    except Exception as e:
        print(f"錯誤：無法讀取或處理需求 CSV '{DEMAND_CSV_PATH}' -> {e}")
        return None

    # 2. 載入主資料庫
    try:
        with sqlite3.connect(MAIN_DB_PATH) as conn:
            db_tables = {}
            db_tables["BOM_Details"] = pd.read_sql("SELECT * FROM BOM_Details", conn)
            db_tables["production_Plan"] = pd.read_sql("SELECT * FROM production_Plan", conn)
            db_tables["Beads_Dry_Count"] = pd.read_sql("SELECT * FROM Beads_Dry_Count", conn)
            db_tables["Dosing_Constraints"] = pd.read_sql("SELECT * FROM '配藥限制'", conn)
            db_tables["Manual_Schedule"] = pd.read_sql("SELECT * FROM '限制 OR 插單'", conn)
            
        # 標準化所有 DB 表格的 PNs
        if "BOM_Details" in db_tables:
            db_tables["BOM_Details"]['Finished_PartNo'] = standardize_pn(db_tables["BOM_Details"]['Finished_PartNo'])
            db_tables["BOM_Details"]['Component_No'] = standardize_pn(db_tables["BOM_Details"]['Component_No'])
        if "production_Plan" in db_tables:
            db_tables["production_Plan"]['PN'] = standardize_pn(db_tables["production_Plan"]['PN'])
        if "Beads_Dry_Count" in db_tables:
            db_tables["Beads_Dry_Count"]['料號'] = standardize_pn(db_tables["Beads_Dry_Count"]['料號'])
        if "Dosing_Constraints" in db_tables:
            db_tables["Dosing_Constraints"]['PN'] = standardize_pn(db_tables["Dosing_Constraints"]['PN'])
        
        print("  已將所有資料庫表格中的 PN/料號 標準化 (移除 .0)。")

    except Exception as e:
        print(f"錯誤：無法讀取主資料庫 '{MAIN_DB_PATH}' -> {e}")
        return None
        
    # 3. 載入輸出資料庫模板
    try:
        with sqlite3.connect(OUTPUT_DB_PATH) as conn:
            df_template = pd.read_sql("SELECT * FROM Schedule_Temp LIMIT 0", conn)
    except Exception as e:
        print(f"錯誤：無法讀取輸出資料庫 '{OUTPUT_DB_PATH}' -> {e}")
        return None

    print("資料載入成功。")
    return {
        "demand": df_demand,
        "db": db_tables,
        "output_template": df_template
    }

# --------------------------------------------------------------------
# 4. 需求與優先級計算
# --------------------------------------------------------------------
def calculate_demand_queue(data: dict):
    print("Step 2: 正在計算需求優先級...")
    
    df_demand = data["demand"]
    db = data["db"]

    df_demand['W1_Balance'] = df_demand['Stock_plus_Dosing'] - df_demand['第一周需求']
    df_demand['W2_Balance'] = df_demand['W1_Balance'] - df_demand['第二周需求']
    df_demand['W3_Balance'] = df_demand['W2_Balance'] - df_demand['第三周需求']

    task_queue = [] 

    w1_urgent_pn = set()
    if "production_Plan" in db and "BOM_Details" in db:
        try:
            urgent_finished_pn = set(db["production_Plan"]["PN"])
            w1_urgent_pn = set(
                db["BOM_Details"][db["BOM_Details"]["Finished_PartNo"].isin(urgent_finished_pn)]["Component_No"]
            )
            print(f"  找到 {len(w1_urgent_pn)} 個與 'production_Plan' 相關的緊急半品。")
        except Exception as e:
            print(f"  警告: 檢查 production_Plan 優先級失敗: {e}")

    for _, row in df_demand.iterrows():
        pn = str(row['料號'])
        drug_name = str(row.get('藥名', 'UNKNOWN'))
        
        w1_short = abs(row['W1_Balance']) if row['W1_Balance'] < 0 else 0
        w2_short = abs(row['W2_Balance']) if w1_short == 0 and row['W2_Balance'] < 0 else 0
        w3_short = abs(row['W3_Balance']) if w2_short == 0 and row['W3_Balance'] < 0 else 0

        if w1_short > 0:
            sub_priority = 0 if pn in w1_urgent_pn else 1
            task_queue.append((1, sub_priority, pn, w1_short, "W1_Need", drug_name))
        elif w2_short > 0:
            task_queue.append((2, 0, pn, w2_short, "W2_Need", drug_name))
        elif w3_short > 0:
            task_queue.append((3, 0, pn, w3_short, "W3_Need", drug_name))

    task_queue.sort(key=lambda x: (x[0], x[1]))
    
    task_dict = {task[2]: task for task in task_queue}

    print(f"需求計算完成。總共有 {len(task_queue)} 個優先任務。")
    return task_queue, task_dict

# --------------------------------------------------------------------
# 5. 排程器核心
# --------------------------------------------------------------------
class Scheduler:
    def __init__(self, data):
        self.data = data
        self.db_constraints = data["db"]
        self.output_template = data["output_template"]
        self.final_schedule = [] 
        self.task_queue, self.task_dict = calculate_demand_queue(data)
        
        self.constraints = self.load_and_clean_constraints()
        
        # FIX: Better error handling for beads_dry_info
        try:
            beads_df = self.db_constraints.get("Beads_Dry_Count", pd.DataFrame())
            if not beads_df.empty and '料號' in beads_df.columns:
                # Remove duplicates before setting index
                beads_df = beads_df.drop_duplicates(subset=['料號'])
                self.beads_dry_info = beads_df.set_index('料號')
            else:
                self.beads_dry_info = pd.DataFrame()
        except Exception as e:
            print(f"警告: Beads_Dry_Count 處理失敗: {e}")
            self.beads_dry_info = pd.DataFrame()

        self.days_to_schedule = SCHEDULING_DAYS
        self.w1_needs_met = False
        self.scheduled_pns = set() 
        
        self.simulated_inventory = data["demand"].set_index('料號')['Stock_plus_Dosing'].to_dict()
        self.idle_pn_list = self.get_idle_pn_list()
        
        # 資源時間軸
        self.port_schedule = {port_id: [] for port_id in range(1, MAX_PORTS + 1)}
        
        dryer_ids = set()
        if 'Dosing_Constraints' in self.db_constraints and '可用凍乾機' in self.db_constraints['Dosing_Constraints'].columns:
            dryer_ids = set(self.db_constraints['Dosing_Constraints']['可用凍乾機'].str.split(',').explode().str.strip())
        dryer_ids.discard('')
        self.dryer_schedule = {dryer_id: [] for dryer_id in dryer_ids if dryer_id}
        if not self.dryer_schedule: 
            self.dryer_schedule = {str(i):[] for i in range(3, 13)}

        person_ids = set()
        if 'Dosing_Constraints' in self.db_constraints:
            dc = self.db_constraints['Dosing_Constraints']
            if '配藥人-1' in dc.columns:
                person_ids.update(set(dc['配藥人-1'].str.strip()))
            if '配藥人-2' in dc.columns:
                person_ids.update(set(dc['配藥人-2'].str.strip()))
            if '配藥人-3' in dc.columns:
                person_ids.update(set(dc['配藥人-3'].str.strip()))
        person_ids.discard('')
        person_ids.discard(None)
        self.person_schedule = {person: [] for person in person_ids if person}

    def load_and_clean_constraints(self):
        constraints = self.db_constraints["Dosing_Constraints"].copy()
        constraints = constraints[constraints['PN'].notna() & (constraints['PN'] != "")]
        num_cols = ["port數", "數量", "凍乾時間", "滴定後凍乾時間差距 (HR)", "配完後續要空著天數"]
        for col in num_cols:
            if col in constraints.columns:
                constraints[col] = pd.to_numeric(constraints[col], errors='coerce').fillna(0)
        
        # FIX: Handle duplicate PNs
        try:
            if constraints.index.name == 'PN' or 'PN' not in constraints.columns:
                pass  # Already indexed
            else:
                constraints = constraints.drop_duplicates(subset=['PN'])
                constraints.set_index('PN', inplace=True)
        except Exception as e:
            print(f"警告: '配藥限制' set_index('PN') 失敗: {e}")
            constraints = constraints.drop_duplicates(subset=['PN']).set_index('PN')
        return constraints

    def _is_overlap(self, timeline: list, check_start: datetime, check_end: datetime) -> bool:
        for entry in timeline:
            if len(entry) < 2:
                continue
            existing_start, existing_end = entry[0], entry[1]
            if max(existing_start, check_start) < min(existing_end, check_end):
                return True 
        return False 

    def find_batch(self, current_task_info):
        pn = current_task_info[2]
        drug_name = current_task_info[5]
        
        # FIX: Better error handling for loc access
        is_separate = False
        try:
            if not self.beads_dry_info.empty and pn in self.beads_dry_info.index:
                is_separate = self.beads_dry_info.loc[pn].get("U,D 劑分開生產排程", "") == "✓"
        except Exception as e:
            print(f"  警告: 查找 Beads_Dry_Count 中的 {pn} 時出錯: {e}")
            is_separate = False
            
        if is_separate or not drug_name or drug_name == 'UNKNOWN':
            return [current_task_info] 

        batch = [current_task_info]
        for task in self.task_queue:
            pn_other = task[2]
            drug_name_other = task[5]
            if pn_other not in self.scheduled_pns and drug_name_other == drug_name:
                try:
                    is_separate_other = False
                    if not self.beads_dry_info.empty and pn_other in self.beads_dry_info.index:
                        is_separate_other = self.beads_dry_info.loc[pn_other].get("U,D 劑分開生產排程", "") == "✓"
                except:
                    is_separate_other = False
                if not is_separate_other:
                    batch.append(task)
                    
        unique_batch = list({task[2]: task for task in batch}.values())

        if len(unique_batch) > 2:
            print(f"  [Rule 5-3] 批次 '{drug_name}' 找到 {len(unique_batch)} 個 PNs。")
            urgent_tasks = [t for t in unique_batch if self.task_dict.get(t[2], (99, 99))[1] == 0]
            
            if urgent_tasks:
                selected_tasks = urgent_tasks[:2]
                print(f"    > 自動選擇 'production_Plan' 中的 {len(selected_tasks)} 個: {[t[2] for t in selected_tasks]}")
                return selected_tasks
            else:
                print(f"    > 均不在 'production_Plan' 中。自動選擇佇列最前面的 2 個。")
                return unique_batch[:2]
        
        return unique_batch

    def check_availability(self, batch_tasks, delivery_datetime):
        try:
            constraints_list = [self.constraints.loc[task[2]].to_dict() for task in batch_tasks]
            batch_drug_name = batch_tasks[0][5] 
        except KeyError as e:
            print(f"  [Check Fail] 批次中包含無法識別的 PN: {e}")
            return None
        except Exception as e:
            print(f"  [Check Fail] 查找約束時出錯: {e}")
            return None

        person = self.find_available_person(constraints_list, delivery_datetime, batch_drug_name)
        if not person:
            return None

        dosing_start_dt = delivery_datetime + timedelta(minutes=DOSING_PREP_TIME_MIN)
        port_allocations, batch_dosing_end_dt = self.find_available_ports(
            batch_tasks, constraints_list, dosing_start_dt
        )
        if not port_allocations:
            return None

        wait_hr = max(c.get('滴定後凍乾時間差距 (HR)', 0) for c in constraints_list)
        freeze_duration_hr = max(c.get('凍乾時間', 12) for c in constraints_list)
        freeze_start_dt = add_hours_to_time(batch_dosing_end_dt, wait_hr)
        freeze_end_dt = add_hours_to_time(freeze_start_dt, freeze_duration_hr)
        
        dryer_id = self.find_available_dryer(
            constraints_list, batch_drug_name, freeze_start_dt, freeze_end_dt
        )
        if not dryer_id:
            return None

        harvest_end_dt = freeze_end_dt + timedelta(minutes=HARVEST_TIME_MIN)
        if not self.check_harvest_time(harvest_end_dt):
            return None

        return {
            "person": person,
            "ports": port_allocations, 
            "dryer": dryer_id,
            "times": {
                "delivery_dt": delivery_datetime,
                "dosing_start_dt": dosing_start_dt,
                "batch_dosing_end_dt": batch_dosing_end_dt,
                "freeze_start_dt": freeze_start_dt,
                "freeze_end_dt": freeze_end_dt,
                "harvest_end_dt": harvest_end_dt,
                "freeze_duration_hr": freeze_duration_hr
            },
            "constraints_list": constraints_list
        }

    def find_available_person(self, constraints_list, delivery_dt, batch_drug_name):
        prep_start_dt = delivery_dt
        prep_end_dt = delivery_dt + timedelta(hours=1) 
        
        c0 = constraints_list[0]
        allowed_people = [c0.get("配藥人-1", ""), c0.get("配藥人-2", ""), c0.get("配藥人-3", "")]
        
        for person in allowed_people:
            if not person or person not in self.person_schedule: 
                continue 
            if not self._is_overlap(self.person_schedule[person], prep_start_dt, prep_end_dt):
                return person 
        return None 

    def find_available_ports(self, batch_tasks, constraints_list, dosing_start_dt):
        port_allocations = {}
        all_dosing_end_times = []
        temp_port_schedule = {p: list(timeline) for p, timeline in self.port_schedule.items()}
        
        for task, constr in zip(batch_tasks, constraints_list):
            pn = task[2]
            ports_needed = int(constr.get("port數", 1))
            if ports_needed == 0: 
                ports_needed = 1
            qty = constr.get("數量", 1000)
            
            dosing_duration_hr = (qty / DOSING_RATE_PER_HR) / ports_needed
            dosing_end_dt = add_hours_to_time(dosing_start_dt, dosing_duration_hr)
            
            found_ports = []
            for port_id in range(1, MAX_PORTS + 1):
                if not self._is_overlap(temp_port_schedule[port_id], dosing_start_dt, dosing_end_dt):
                    found_ports.append(port_id)
                    if len(found_ports) == ports_needed:
                        break 
            
            if len(found_ports) < ports_needed:
                return None, None 
            
            for port_id in found_ports:
                temp_port_schedule[port_id].append((dosing_start_dt, dosing_end_dt, pn))
                
            port_allocations[pn] = found_ports
            all_dosing_end_times.append(dosing_end_dt)
        
        if not all_dosing_end_times:
            return None, None

        return port_allocations, max(all_dosing_end_times)

    def find_available_dryer(self, constraints_list, batch_drug_name, freeze_start_dt, freeze_end_dt):
        try:
            dryer_sets = [
                set(str(c.get("可用凍乾機", "")).split(',')) for c in constraints_list
            ]
            common_dryers = set.intersection(*dryer_sets)
            common_dryers.discard("") 
        except Exception:
            return None

        if not common_dryers:
            return None
            
        for dryer_id in sorted(list(common_dryers)):
            dryer_id = dryer_id.strip()
            if not dryer_id or dryer_id not in self.dryer_schedule: 
                continue
            timeline = self.dryer_schedule[dryer_id]
            if self._is_overlap(timeline, freeze_start_dt, freeze_end_dt):
                continue 
            return dryer_id
        return None 
        
    def check_harvest_time(self, harvest_end_dt: datetime) -> bool:
        harvest_time = harvest_end_dt.time()
        if time(WORK_END_TIME_LATE.hour, 0) < harvest_time < time(WORK_START_TIME.hour, 0):
            return False
        if time(WORK_END_TIME_LATE.hour, 0) < harvest_time <= time(WORK_END_TIME_ALERT.hour, 0):
            print(f"  [Alert] 收藥時間 {harvest_time} 已超過 02:00。")
        return True

    def book_resources(self, resources, batch_tasks, batch_drug_name):
        times = resources["times"]
        
        person = resources["person"]
        prep_start_dt = times["delivery_dt"]
        prep_end_dt = prep_start_dt + timedelta(hours=1) 
        self.person_schedule[person].append((prep_start_dt, prep_end_dt, batch_drug_name))
        
        port_allocations = resources["ports"]
        dosing_start_dt = times["dosing_start_dt"]
        constraints_list = resources["constraints_list"]
        
        for task, constr in zip(batch_tasks, constraints_list):
            pn = task[2]
            ports_to_book = port_allocations[pn]
            qty = constr.get("數量", 1000)
            num_ports = int(constr.get("port數", 1))
            if num_ports == 0: 
                num_ports = 1
            
            dosing_duration_hr = (qty / DOSING_RATE_PER_HR) / num_ports
            dosing_end_dt = add_hours_to_time(dosing_start_dt, dosing_duration_hr)
            
            for port_id in ports_to_book:
                self.port_schedule[port_id].append((dosing_start_dt, dosing_end_dt, pn))

        dryer_id = resources["dryer"]
        self.dryer_schedule[dryer_id].append((
            times["freeze_start_dt"], 
            times["harvest_end_dt"], 
            batch_drug_name,
            0 
        ))

    def get_idle_pn_list(self):
        try:
            if "空閒產能時可優先安排生產" in self.constraints.columns:
                idle_pn_info = self.constraints[
                    self.constraints["空閒產能時可優先安排生產"].str.strip() == "✓"
                ].index
            else:
                idle_pn_info = []
        except:
            idle_pn_info = [] 
        
        inventory_list = []
        for pn in idle_pn_info:
            if pn not in self.scheduled_pns: 
                inventory = self.simulated_inventory.get(pn, 0)
                inventory_list.append((pn, inventory))
                
        inventory_list.sort(key=lambda x: x[1])
        return inventory_list 

    def update_simulated_inventory(self, pn, qty):
        if pn in self.simulated_inventory:
            self.simulated_inventory[pn] += qty
        else:
            self.simulated_inventory[pn] = qty
        print(f"  [Rule 8] 更新模擬庫存 {pn}: {self.simulated_inventory[pn]}")

    def run(self):
        print("Step 3: 開始排程循環 (Option A, v3)...")
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        monday = (today + timedelta(days=-today.weekday(), weeks=1)) 
        
        print("--- [階段 1] 正在處理 W1-W3 需求... ---")
        
        for day_index in range(self.days_to_schedule + 1):
            if day_index == SCHEDULING_DAYS: 
                if not ALLOW_EXTEND_TO_6_DAYS or self.w1_needs_met:
                    break 
                print("警告：5 天內無法滿足第一周需求，排程延長至第 6 天。")
            
            current_day = monday + timedelta(days=day_index)
            print(f"--- 正在排程 (需求): Day {day_index + 1} ({current_day.strftime('%Y-%m-%d')}) ---")
            shifts = [("AM", 11.0), ("PM", 17.0)] 
            
            while True: 
                current_task_info = None
                for task in self.task_queue:
                    if task[2] not in self.scheduled_pns:
                        current_task_info = task
                        break
                if not current_task_info:
                    break 

                batch_tasks = self.find_batch(current_task_info)
                batch_pns = [t[2] for t in batch_tasks]
                
                if not batch_tasks: 
                    self.scheduled_pns.add(current_task_info[2]) 
                    continue 

                found_slot = False
                for shift_name, shift_hour in shifts:
                    delivery_dt = current_day.replace(hour=int(shift_hour), minute=0)
                    resources = self.check_availability(batch_tasks, delivery_dt)
                    
                    if resources:
                        print(f"  > [Slot Found] 時段 {shift_name}, 排程批次: {batch_tasks[0][5]} (共 {len(batch_tasks)} 個 PN)")
                        self.book_and_record(resources, batch_tasks, current_day)
                        found_slot = True
                        break 
                
                if not found_slot:
                    for pn in batch_pns:
                        self.scheduled_pns.add(pn)
            
            if not self.w1_needs_met:
                remaining_w1 = any(self.task_dict.get(pn, (99,99))[0] == 1 for pn in self.task_dict if pn not in self.scheduled_pns)
                if not remaining_w1:
                    self.w1_needs_met = True
                    print("...第一周需求已滿足。")

        print("--- [階段 1] W1-W3 需求排程完畢 ---")
        
        print("--- [階段 2] (Rule 8) 正在填滿空閒產能... ---")
        self.idle_pn_list = self.get_idle_pn_list()
        
        for day_index in range(self.days_to_schedule): 
            current_day = monday + timedelta(days=day_index)
            print(f"--- 正在排程 (空閒): Day {day_index + 1} ({current_day.strftime('%Y-%m-%d')}) ---")
            shifts = [("AM", 11.0), ("PM", 17.0)] 
            
            for shift_name, shift_hour in shifts:
                self.idle_pn_list = self.get_idle_pn_list()
                if not self.idle_pn_list:
                    break 
                
                pn_to_fill, inventory = self.idle_pn_list[0]
                
                if pn_to_fill not in self.task_dict:
                    idle_task_info = (10, 0, pn_to_fill, 0, "Idle_Fill", "UNKNOWN_IDLE")
                else:
                    idle_task_info = self.task_dict[pn_to_fill]
                    
                batch_tasks = [idle_task_info]
                
                delivery_dt = current_day.replace(hour=int(shift_hour), minute=0)
                resources = self.check_availability(batch_tasks, delivery_dt)

                if resources:
                    print(f"  > [Rule 8 Slot Found] 時段 {shift_name}, 填入庫存最低者: {pn_to_fill} (Inv: {inventory})")
                    self.book_and_record(resources, batch_tasks, current_day)
                    scheduled_qty = resources["constraints_list"][0].get("數量", 1000)
                    self.update_simulated_inventory(pn_to_fill, scheduled_qty)
                else:
                    self.scheduled_pns.add(pn_to_fill) 
                    self.idle_pn_list.pop(0)
            
            if not self.idle_pn_list:
                print("...已無 '空閒產能' 項目可排。")
                break 
        
        print("--- [階段 2] 空閒產能排程完畢 ---")
        print("Step 4: 排程循環結束。")

    def book_and_record(self, resources, batch_tasks, current_day):
        times = resources["times"]
        self.book_resources(resources, batch_tasks, batch_tasks[0][5]) 
        for task in batch_tasks:
            self.scheduled_pns.add(task[2])

        for i, task in enumerate(batch_tasks):
            pn = task[2]
            constraints = resources["constraints_list"][i]
            ports_alloc = resources["ports"][pn]
            
            qty = constraints.get("數量", 1000)
            num_ports = int(constraints.get("port數", 1))
            if num_ports == 0: 
                num_ports = 1
            
            dosing_duration_hr = (qty / DOSING_RATE_PER_HR) / num_ports
            dosing_end_dt = add_hours_to_time(times["dosing_start_dt"], dosing_duration_hr)

            output_row = {
                "marker": constraints.get("Name", ""),
                "凍乾機台": resources["dryer"],
                "数量": qty, 
                "配藥同仁": resources["person"],
                "RD給藥時間": times["delivery_dt"].strftime("%H:%M"),
                "預計滴定時間": times["dosing_start_dt"].strftime("%H:%M"),
                "預計結束": dosing_end_dt.strftime("%H:%M"),
                "滴定機": "IVEK" if pn in IVEK_COMPONENTS else ",".join([f"Port {p}" for p in ports_alloc]),
                "lot": pn, 
                "預冷時間": times["freeze_start_dt"].strftime("%H:%M"), 
                "凍乾時間": times["freeze_duration_hr"],
                "收藥時間": times["harvest_end_dt"].strftime("%H:%M"),
                "日期": current_day.strftime("%Y-%m-%d") 
            }
            self.final_schedule.append(output_row)

    def write_output(self):
        """將最終排程寫入輸出資料庫 和 Excel"""
        print(f"Step 5: 正在將 {len(self.final_schedule)} 筆排程寫入檔案...")
        if not self.final_schedule:
            print("沒有產生任何排程。")
            return

        df_out = pd.DataFrame(self.final_schedule)
        df_final = self.output_template.copy()
        
        if "日期" not in df_final.columns and "日期" in df_out.columns:
            df_final["日期"] = None
        
        if '数量' in df_final.columns and '數量' not in df_final.columns:
            df_out = df_out.rename(columns={"數量": "数量"})
            
        common_cols = df_out.columns.intersection(df_final.columns)
        
        # FIX: Correct empty check for Index object
        if len(common_cols) == 0:
            print("警告: 輸出模板和排程結果沒有共同欄位。")
            return
            
        df_final = pd.concat([df_final, df_out[common_cols]], ignore_index=True)
        
        if "日期" in df_final.columns:
            cols = ["日期"] + [col for col in df_final.columns if col != "日期"]
            df_final = df_final[cols]

        try:
            df_final.to_excel(OUTPUT_EXCEL_PATH, index=False)
            print(f"排程 Excel 輸出成功！ -> {OUTPUT_EXCEL_PATH}")
            
            print("\n===== 產生的排程預覽 (Markdown) =====")
            print(df_final.to_markdown(index=False))
            
        except Exception as e:
            print(f"錯誤：寫入 Excel 失敗: {e}")

        try:
            with sqlite3.connect(OUTPUT_DB_PATH) as conn:
                df_final.to_sql(OUTPUT_TABLE_NAME, conn, if_exists='replace', index=False)
            print(f"排程 DB 輸出成功！ -> {OUTPUT_DB_PATH}")
        except Exception as e:
            print(f"錯誤：寫入輸出資料庫失敗: {e}")

# --------------------------------------------------------------------
# 6. 主執行程序
# --------------------------------------------------------------------
def main():
    print("===== [Option A, v3] 排程開始 =====")
    try:
        all_data = load_all_data()
        if not all_data:
            print("===== 排程失敗：資料載入錯誤 =====")
            return

        scheduler = Scheduler(all_data)
        scheduler.run()
        scheduler.write_output()
        
        print("===== [Option A, v3] 排程作業完成 =====")
    except Exception as e:
        print(f"===== 排程失敗：發生未預期的錯誤 =====")
        print(f"錯誤訊息: {e}")
        print("詳細錯誤追蹤:")
        traceback.print_exc()

# FIX: Add main execution guard
if __name__ == "__main__":
    main()