#!/usr/bin/env python3
"""
GLIPA 自動修正腳本
自動替換 scheduler.py 中的兩個方法
"""

import sys
import os
import shutil
from datetime import datetime

def backup_file(filepath):
    """備份原檔案"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup_{timestamp}"
    shutil.copy2(filepath, backup_path)
    print(f"✅ 已備份至: {backup_path}")
    return backup_path

def read_new_methods():
    """讀取新方法的程式碼"""
    new_check_method = '''    def _check_availability_glipa(self, batch_tasks, constraints_list, delivery_dt, slot_name, priority=None):
        """
        ✅ GLIPA 專用資源檢查（確保兩台不同凍乾機）
        """
        import sys
        from datetime import timedelta
        
        day_key = delivery_dt.strftime('%Y-%m-%d')
        
        print(f"    🔥 [DEBUG] GLIPA 開始檢查資源", file=sys.stderr)
        
        # 1. 檢查人員
        person_result = self.find_available_person_v10(constraints_list, delivery_dt, slot_name, priority)
        if not person_result or person_result[0] is None:
            print(f"    🔴 GLIPA: 找不到可用人員", file=sys.stderr)
            return None
        
        person, is_single_slot = person_result
        print(f"    ✅ [DEBUG] GLIPA 選定人員: {person}", file=sys.stderr)
        
        # 2. ✅ 分別為兩個 PN 找凍乾機
        print(f"    🔍 [DEBUG] 開始為 GLIPA-AD 尋找凍乾機...", file=sys.stderr)
        
        dryer1 = None
        if len(batch_tasks) > 0 and len(constraints_list) > 0:
            dryer1 = self.find_available_dryer_v10(
                [constraints_list[0]],
                delivery_dt, 
                priority, 
                [batch_tasks[0]]
            )
        
        if not dryer1:
            print(f"    🔴 GLIPA: 找不到第一台凍乾機 (GLIPA-AD)", file=sys.stderr)
            return None
        
        if not self._is_dryer_clean_for_glipa(dryer1, delivery_dt):
            print(f"    🔴 GLIPA: 凍乾機 {dryer1} 前兩天不乾淨", file=sys.stderr)
            return None
        
        print(f"    ✅ [DEBUG] GLIPA-AD 選定凍乾機: {dryer1}", file=sys.stderr)
        
        # 2.2 為第二個 PN 找凍乾機（必須與 dryer1 不同）
        print(f"    🔍 [DEBUG] 開始為 GLIPA-AU 尋找凍乾機（需與 {dryer1} 不同）...", file=sys.stderr)
        
        dryer2 = None
        if len(constraints_list) > 1:
            constr2 = constraints_list[1]
        elif len(constraints_list) == 1:
            constr2 = constraints_list[0]
        else:
            print(f"    🔴 GLIPA: 無約束條件", file=sys.stderr)
            return None
        
        available_dryers_str = str(constr2.get("可用凍乾機", "")).strip()
        if not available_dryers_str:
            print(f"    🔴 GLIPA-AU: 無可用凍乾機設定", file=sys.stderr)
            return None
        
        candidate_dryers = [d.strip() for d in available_dryers_str.split(',') if d.strip()]
        print(f"    📋 [DEBUG] GLIPA-AU 候選凍乾機: {candidate_dryers}", file=sys.stderr)
        
        for dryer in candidate_dryers:
            if dryer == dryer1:
                print(f"       ⚠️ [DEBUG] 跳過 {dryer}（與 dryer1 相同）", file=sys.stderr)
                continue
            
            if not self.resources.is_dryer_available(dryer, day_key, priority):
                print(f"       ⚠️ [DEBUG] 跳過 {dryer}（已被佔用）", file=sys.stderr)
                continue
            
            if not self._is_dryer_clean_for_glipa(dryer, delivery_dt):
                print(f"       ⚠️ [DEBUG] 跳過 {dryer}（前兩天不乾淨）", file=sys.stderr)
                continue
            
            dryer2 = dryer
            print(f"    ✅ [DEBUG] GLIPA-AU 選定凍乾機: {dryer2}", file=sys.stderr)
            break
        
        if not dryer2:
            print(f"    🔴 GLIPA: 找不到第二台合適的凍乾機", file=sys.stderr)
            return None
        
        if dryer1 == dryer2:
            print(f"    🔴 GLIPA: 兩台凍乾機相同 ({dryer1})，邏輯錯誤", file=sys.stderr)
            return None
        
        print(f"    ✅ [DEBUG] GLIPA 凍乾機配對成功: {dryer1} 和 {dryer2}", file=sys.stderr)
        
        # 3. 從資料庫讀取 Port 數
        pn_port_map = {}
        total_ports_needed = 0
        
        print(f"    📊 [DEBUG] GLIPA Port 配置:", file=sys.stderr)
        
        for task in batch_tasks:
            pn = task[2]
            num_ports = 2
            if pn in self.constraints.index:
                constr = self.constraints.loc[pn]
                if isinstance(constr, pd.DataFrame):
                    constr = constr.iloc[0]
                num_ports_str = str(constr.get("Port數", "2")).strip()
                try:
                    num_ports = int(num_ports_str)
                except:
                    num_ports = 2
            pn_port_map[pn] = num_ports
            total_ports_needed += num_ports
            print(f"       {pn}: {num_ports} Port", file=sys.stderr)
        
        print(f"    📊 [DEBUG] 總共需要: {total_ports_needed} Port", file=sys.stderr)
        
        # 4. 計算時間
        try:
            dosing_start_dt = delivery_dt + timedelta(minutes=DOSING_PREP_TIME_MIN)
            total_short_qty = sum(t[3] for t in batch_tasks)
            qtys = []
            for c in constraints_list:
                qty_str = c.get("數量", 0)
                qty = self._parse_quantity_with_options(qty_str, total_short_qty)
                if qty > 0:
                    qtys.append(qty)
            max_qty = max(qtys) if qtys else 2500
            max_ports = max(pn_port_map.values())
            dosing_hrs = max_qty / (DOSING_RATE_PER_HR * max_ports)
            dosing_end_dt = add_hours_to_time(dosing_start_dt, dosing_hrs)
            freeze_duration = float(max(c.get("凍乾時間", 12) for c in constraints_list))
            final_end_dt = add_hours_to_time(dosing_end_dt, freeze_duration)
        except Exception as e:
            print(f"    🔴 GLIPA 時間計算失敗: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return None
        
        print(f"    ✅ [DEBUG] GLIPA 資源檢查完成！", file=sys.stderr)
        
        return {
            "person": person,
            "dryer": dryer1,
            "dryer2": dryer2,
            "is_single_slot": is_single_slot,
            "times": {
                "delivery_dt": delivery_dt,
                "dosing_start_dt": dosing_start_dt,
                "dosing_end_dt": dosing_end_dt,
                "final_end_dt": final_end_dt,
                "freeze_duration_hr": freeze_duration,
                "dosing_hrs": dosing_hrs
            },
            "pn_port_map": pn_port_map,
            "total_ports_needed": total_ports_needed,
            "num_ports_str": str(total_ports_needed),
            'constraints_list': constraints_list,
            "is_glipa": True
        }
'''

    new_book_method = '''    def _book_and_record_glipa(self, resources, batch_tasks, current_day, slot_name, priority=None):
        """
        ✅ GLIPA 專用記錄方法（使用兩台不同凍乾機）
        """
        import sys
        import pandas as pd
        
        times = resources["times"]
        person = resources.get("person", "")
        dryer1 = resources.get("dryer", "N/A")
        dryer2 = resources.get("dryer2", "N/A")
        freeze_duration = times.get("freeze_duration_hr", "N/A")
        pn_port_map = resources.get("pn_port_map", {})
        total_ports_needed = resources.get("total_ports_needed", 3)
        
        day_key = current_day.strftime("%Y-%m-%d")
        shift_key = f"{day_key}_{slot_name}"
        
        print(f"    📝 [DEBUG] GLIPA 開始記錄", file=sys.stderr)
        print(f"       凍乾機1: {dryer1}, 凍乾機2: {dryer2}", file=sys.stderr)
        
        if dryer1 == dryer2:
            print(f"    ❌ GLIPA: 兩台凍乾機相同 ({dryer1})，無法記錄", file=sys.stderr)
            return
        
        if shift_key not in self.shift_port_counter:
            self.shift_port_counter[shift_key] = 1
        
        port_start = self.shift_port_counter[shift_key]
        
        while self.resources.is_p0_strict_port_booked(shift_key, port_start):
            print(f"    ⚠️ P0 (非實驗) 佔用: Port{port_start}，自動跳過", file=sys.stderr)
            port_start += 1
        
        if priority is not None and priority >= 3:
            while self.resources.is_p0_experiment_port_booked(shift_key, port_start):
                print(f"    ⚠️ P0 (實驗) 佔用: Port{port_start}，P{priority} 自動跳過", file=sys.stderr)
                port_start += 1
        
        if port_start + total_ports_needed - 1 > MAX_PORTS:
            print(f"    ⚠️ {shift_key} Port 不足（GLIPA 需要 {total_ports_needed} Port）", file=sys.stderr)
            return
        
        rows = []
        current_port = port_start
        
        print(f"    📝 [DEBUG] GLIPA 排程明細:", file=sys.stderr)
        
        for idx, task in enumerate(batch_tasks):
            week, subp, pn, short_qty, tag, group_name, marker_name, prod_qty = task
            num_ports = pn_port_map.get(pn, 2)
            ports_for_this_pn = list(range(current_port, current_port + num_ports))
            port_str = ",".join([f"Port{p}" for p in ports_for_this_pn])
            dryer = dryer1 if idx == 0 else dryer2
            
            rows.append({
                "日期": current_day.strftime("%Y-%m-%d"),
                "marker": marker_name,
                "滴定機": port_str,
                "凍乾機台": dryer,
                "配藥同仁": person,
                "RD給藥時間": times["delivery_dt"].strftime("%H:%M"),
                "預計滴定時間": times["dosing_start_dt"].strftime("%H:%M"),
                "預計結束": times["final_end_dt"].strftime("%H:%M"),
                "預冷時間": (times["dosing_end_dt"] + timedelta(hours=2)).strftime("%H:%M"),
                "凍乾時間": f"{freeze_duration:.1f} hr",
                "收藥時間": times["final_end_dt"].strftime("%H:%M"),
                "數量": prod_qty,
                "lot": pn,
                "班次": slot_name,
                "ports_list": ",".join(map(str, ports_for_this_pn))
            })
            
            print(f"       PN {pn} ({marker_name}):", file=sys.stderr)
            print(f"          Port: {port_str} ({num_ports} Port)", file=sys.stderr)
            print(f"          凍乾機: {dryer}", file=sys.stderr)
            
            current_port += num_ports
        
        self.shift_port_counter[shift_key] = current_port
        
        print(f"    ✅ [DEBUG] GLIPA 記錄完成:", file=sys.stderr)
        print(f"       Port 範圍: Port{port_start}-Port{current_port-1} (共 {total_ports_needed} Port)", file=sys.stderr)
        print(f"       凍乾機: {dryer1}, {dryer2} ✓不同", file=sys.stderr)
        
        new_df = pd.DataFrame(rows)
        if not hasattr(self, "schedule_df") or self.schedule_df.empty:
            self.schedule_df = new_df
        else:
            self.schedule_df = pd.concat([self.schedule_df, new_df], ignore_index=True)
'''
    
    return new_check_method, new_book_method

def replace_methods(filepath):
    """替換兩個方法"""
    
    if not os.path.exists(filepath):
        print(f"❌ 找不到檔案: {filepath}")
        return False
    
    # 備份
    backup_path = backup_file(filepath)
    
    # 讀取原檔案
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 找到兩個方法的位置
    check_start = None
    check_end = None
    book_start = None
    book_end = None
    
    for i, line in enumerate(lines):
        if 'def _check_availability_glipa(' in line:
            check_start = i
        elif check_start is not None and check_end is None:
            if line.strip().startswith('def ') and 'def _check_availability_glipa' not in line:
                check_end = i
        
        if 'def _book_and_record_glipa(' in line:
            book_start = i
        elif book_start is not None and book_end is None:
            if line.strip().startswith('def ') and 'def _book_and_record_glipa' not in line:
                book_end = i
    
    if check_start is None:
        print("❌ 找不到 _check_availability_glipa 方法")
        return False
    
    if book_start is None:
        print("❌ 找不到 _book_and_record_glipa 方法")
        return False
    
    print(f"\n📍 找到方法位置:")
    print(f"   _check_availability_glipa: 行 {check_start+1} - {check_end}")
    print(f"   _book_and_record_glipa: 行 {book_start+1} - {book_end}")
    
    # 取得新方法
    new_check, new_book = read_new_methods()
    
    # 替換方法
    new_lines = []
    
    # 第一部分：check_start 之前
    new_lines.extend(lines[:check_start])
    
    # 插入新的 _check_availability_glipa
    new_lines.append(new_check + '\n')
    
    # 第二部分：check_end 到 book_start
    new_lines.extend(lines[check_end:book_start])
    
    # 插入新的 _book_and_record_glipa
    new_lines.append(new_book + '\n')
    
    # 第三部分：book_end 之後
    if book_end:
        new_lines.extend(lines[book_end:])
    else:
        # 如果沒找到結尾，就保留到檔案結束
        pass
    
    # 寫入檔案
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print(f"\n✅ 成功替換兩個方法！")
    print(f"\n📝 變更摘要:")
    print(f"   - 替換 _check_availability_glipa")
    print(f"   - 替換 _book_and_record_glipa")
    print(f"   - 原檔案已備份至: {backup_path}")
    
    return True

def main():
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath=r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Bead_auto_update_schedule\beads_Scheduler_V9_9_7.py"
    
    print("=" * 60)
    print("GLIPA 自動修正腳本")
    print("=" * 60)
    
    if replace_methods(filepath):
        print("\n" + "=" * 60)
        print("✅ 修正完成！")
        print("\n下一步：")
        print("1. 執行驗證: python /home/claude/check_glipa_fix.py scheduler.py")
        print("2. 測試排程: python scheduler.py --date 11/24 --need demand.xlsx")
        print("=" * 60)
        return 0
    else:
        print("\n❌ 修正失敗")
        return 1

if __name__ == "__main__":
    sys.exit(main())
