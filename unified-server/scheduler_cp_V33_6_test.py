import pandas as pd
import sqlite3
import collections
import math
import os
from ortools.sat.python import cp_model

# 資料庫路徑 (請確認與主程式一致)
DB_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\beads_sync.db"

def safe_float(val):
    try: return float(str(val).replace(',', '')) if not pd.isna(val) and str(val).strip() != '' else 0.0
    except: return 0.0

def load_diagnostic_data():
    conn = sqlite3.connect(DB_PATH)
    df_rules = pd.read_sql_query("SELECT * FROM 配藥限制", conn)
    df_demand = pd.read_sql_query("SELECT * FROM BeadNeed WHERE date = (SELECT MAX(date) FROM BeadNeed)", conn)
    conn.close()
    return df_rules, df_demand

def run_diagnostic_solver(jobs, all_staff, horizon_days, disable_prep_busy=False, disable_deadline=False):
    """
    診斷用求解器
    disable_prep_busy: 是否暫時取消「配藥人前置2小時忙碌」
    disable_deadline: 是否暫時取消「01:00截止線」
    """
    model = cp_model.CpModel()
    grids_per_day = 35
    horizon_grids = horizon_days * grids_per_day
    all_dryers = sorted(list(set(d for j in jobs for d in j['compatible_dryers'] if not j['is_prep_only'])))
    
    job_vars = {}
    staff_ints = collections.defaultdict(list)

    for j in jobs:
        s = model.NewIntVar(0, horizon_grids, f"s_{j['id']}")
        job_vars[j['id']] = {'s': s}
        
        # 1. 滴定截止線診斷
        if not disable_deadline:
            s_in_day = model.NewIntVar(0, grids_per_day, '')
            model.AddModuloEquality(s_in_day, s, grids_per_day)
            model.Add(s_in_day + j['grid_duration'] <= 34)

        # 2. 配藥人忙碌診斷
        st_bools = []
        for idx, sname in enumerate(all_staff):
            if sname in j['compatible_staff']:
                u = model.NewBoolVar(f"u_{j['id']}_{idx}")
                st_bools.append(u)
                
                if j['is_prep_only']:
                    staff_ints[idx].append(model.NewOptionalFixedSizeIntervalVar(s, 6, u, ''))
                else:
                    if disable_prep_busy:
                        # 診斷模式：僅要求滴定期間不重疊，不考慮前置配藥
                        staff_ints[idx].append(model.NewOptionalFixedSizeIntervalVar(s, j['grid_duration'], u, ''))
                    else:
                        # 標準模式：滴定前 2 小時忙碌
                        busy_start = model.NewIntVar(-4, horizon_grids, '')
                        model.Add(busy_start == s - 4)
                        staff_ints[idx].append(model.NewOptionalFixedSizeIntervalVar(busy_start, 4, u, ''))
        
        if st_bools:
            model.Add(sum(st_bools) == 1)

    for idx in staff_ints:
        model.AddNoOverlap(staff_ints[idx])

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(model)
    return status in [cp_model.OPTIMAL, cp_model.FEASIBLE]

def main_diagnostic():
    print("🔍 開始 V33.6 排程診斷系統...")
    df_rules, df_demand = load_diagnostic_data()
    
    # 準備基礎數據 (邏輯同 V33.6)
    rules_dict = {}
    all_staff = set()
    for _, row in df_rules.iterrows():
        pn = str(row.get('PN', '')).strip().replace('.0', '')
        staff = [str(row.get(f'配藥人-{i}', '')).strip() for i in range(1, 4)]
        staff = [s for s in staff if s and s.lower() != 'nan']
        for s in staff: all_staff.add(s)
        rules_dict[pn] = {
            'pn': pn, 'name': row.get('Name'), 'num_ports': 2, # 簡化判定
            'qty_options': [1000.0], 'is_prep_only': (str(row.get('數量', '')) == ''),
            'grid_duration': 4, 'compatible_staff': staff, 'compatible_dryers': ['10', '11']
        }
    
    jobs = []
    for _, row in df_demand.iterrows():
        pn = str(row.get('pn', '')).strip().replace('.0', '')
        if pn in rules_dict:
            jobs.append({**rules_dict[pn], 'id': f"task_{pn}"})

    print(f"📊 待排任務總數: {len(jobs)}")
    print(f"👥 可用配藥人數: {len(all_staff)} ({', '.join(sorted(list(all_staff)))})")

    # --- 診斷步驟 ---
    
    print("\n--- 診斷測試 1: 標準模式 (5天) ---")
    if run_diagnostic_solver(jobs, sorted(list(all_staff)), 5):
        print("✅ 標準模式正常有解。請檢查是否為資料庫連線問題。")
        return
    else:
        print("❌ 無解。進入原因分析...")

    print("\n--- 診斷測試 2: 產能壓力測試 (放寬至 14 天) ---")
    if run_diagnostic_solver(jobs, sorted(list(all_staff)), 14):
        print("💡 結果: 增加天數後有解。原因: P1 任務過多，5 天內的總工時/總人力不足以消化所有需求。")
    else:
        print("❌ 仍無解。天數不是唯一問題。")

    print("\n--- 診斷測試 3: 人員忙碌限制測試 (取消前置 2 小時忙碌) ---")
    if run_diagnostic_solver(jobs, sorted(list(all_staff)), 5, disable_prep_busy=True):
        print("💡 結果: 取消配藥前置忙碌後有解。原因: 某些配藥人被指派太多任務，導致滴定前找不到連續 2 小時的空檔。")
    else:
        print("❌ 仍無解。")

    print("\n--- 診斷測試 4: 時間線限制測試 (取消 01:00 截止限制) ---")
    if run_diagnostic_solver(jobs, sorted(list(all_staff)), 5, disable_deadline=True):
        print("💡 結果: 取消 01:00 截止線後有解。原因: 有任務加上配藥時間後太長，無法在凌晨 01:00 前完成。")
    else:
        print("❌ 仍無解。")

    print("\n--- 診斷測試 5: 單一任務可行性掃描 ---")
    bad_pns = []
    for j in jobs:
        if not run_diagnostic_solver([j], sorted(list(all_staff)), 1):
            bad_pns.append(j['pn'])
    if bad_pns:
        print(f"💡 結果: 發現無法排程的特定 PN: {bad_pns}。原因: 這些 PN 的滴定時間設定可能超過 17 小時，或沒有指定配藥人。")
    else:
        print("💡 結果: 所有單一任務皆合法。問題出在任務之間的「組合衝突」。")

if __name__ == '__main__':
    main_diagnostic()