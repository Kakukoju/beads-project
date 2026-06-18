"""
CP-SAT vs 贪婪算法 - 完工时间与资源利用率对比
"""

import sys
import os
import pandas as pd
from datetime import datetime, timedelta
import json

class AlgorithmComparator:
    """排程算法对比器（聚焦完工时间和资源利用率）"""
    
    def __init__(self):
        self.metrics = {
            'greedy': None,
            'cp': None
        }
    
    def evaluate_schedule(self, scheduler, algorithm_name):
        """评估排程质量"""
        
        metrics = {
            'algorithm': algorithm_name,
            'success': False,
            'makespan': None,
            'total_days': 0,
            'total_hours': 0,
            'p1_completion_rate': 0,
            'resource_utilization': {},
            'task_count': 0,
            'violations': []
        }
        
        # 检查是否有排程结果
        if not hasattr(scheduler, 'schedule_df') or scheduler.schedule_df.empty:
            print(f"  ⚠️ {algorithm_name} 无排程结果", file=sys.stderr)
            return metrics
        
        df = scheduler.schedule_df
        metrics['success'] = True
        metrics['task_count'] = len(df)
        
        # ========================================
        # 1. 完工时间分析（主要指标）
        # ========================================
        try:
            # 找出最晚的完工时间
            latest_records = []
            
            for _, row in df.iterrows():
                date_str = row.get('日期', '')
                end_time_str = row.get('預計結束', '')
                
                if not date_str or not end_time_str:
                    continue
                
                try:
                    dt = datetime.strptime(f"{date_str} {end_time_str}", "%Y-%m-%d %H:%M")
                    latest_records.append(dt)
                except:
                    pass
            
            if latest_records:
                makespan_dt = max(latest_records)
                metrics['makespan'] = makespan_dt.strftime("%Y-%m-%d %H:%M")
                
                # 计算总工期
                earliest_dt = min(latest_records)
                total_duration = makespan_dt - earliest_dt
                
                metrics['total_days'] = total_duration.days + 1
                metrics['total_hours'] = total_duration.total_seconds() / 3600
                
                print(f"\n  📅 {algorithm_name} 完工时间:", file=sys.stderr)
                print(f"     最早开始: {earliest_dt.strftime('%Y-%m-%d %H:%M')}", file=sys.stderr)
                print(f"     最晚结束: {makespan_dt.strftime('%Y-%m-%d %H:%M')}", file=sys.stderr)
                print(f"     总工期: {metrics['total_days']} 天 ({metrics['total_hours']:.1f} 小时)", file=sys.stderr)
        
        except Exception as e:
            print(f"  ⚠️ 完工时间计算失败: {e}", file=sys.stderr)
        
        # ========================================
        # 2. P1 完成率
        # ========================================
        try:
            p1_tasks = [t for t in scheduler.task_queue if t[0] == 1]
            metrics['p1_total'] = len(p1_tasks)
            
            # ✅ 从 schedule_df 中获取已排程的 PN
            if hasattr(scheduler, 'schedule_df') and not scheduler.schedule_df.empty:
                scheduled_pns = set(scheduler.schedule_df['lot'].dropna().unique())
                metrics['p1_completion'] = len([t for t in p1_tasks if t[2] in scheduled_pns])
            else:
                metrics['p1_completion'] = 0
            
            metrics['p1_completion_rate'] = (
                metrics['p1_completion'] / metrics['p1_total'] * 100 
                if metrics['p1_total'] > 0 else 0
            )
            
            print(f"  ✅ P1 完成率: {metrics['p1_completion']}/{metrics['p1_total']} ({metrics['p1_completion_rate']:.1f}%)", file=sys.stderr)
        
        except Exception as e:
            print(f"  ⚠️ P1 完成率计算失败: {e}", file=sys.stderr)
        
        # ========================================
        # 3. 资源利用率分析（次要指标）
        # ========================================
        
        # 3.1 Port 利用率
        port_utilization_data = self._calculate_port_utilization(df)
        
        if port_utilization_data:
            avg_port_util = sum(v['rate'] for v in port_utilization_data.values()) / len(port_utilization_data)
            metrics['resource_utilization']['port_avg'] = avg_port_util
            metrics['resource_utilization']['port_detail'] = port_utilization_data
            
            print(f"  📊 平均 Port 利用率: {avg_port_util:.1f}%", file=sys.stderr)
        
        # 3.2 凍乾機利用率
        dryer_utilization_data = self._calculate_dryer_utilization(df)
        
        if dryer_utilization_data:
            avg_dryer_util = sum(v['rate'] for v in dryer_utilization_data.values()) / len(dryer_utilization_data)
            metrics['resource_utilization']['dryer_avg'] = avg_dryer_util
            metrics['resource_utilization']['dryer_detail'] = dryer_utilization_data
            
            print(f"  📊 平均凍乾機利用率: {avg_dryer_util:.1f}%", file=sys.stderr)
        
        # 3.3 人员利用率
        person_utilization_data = self._calculate_person_utilization(df)
        
        if person_utilization_data:
            avg_person_util = sum(v['rate'] for v in person_utilization_data.values()) / len(person_utilization_data)
            metrics['resource_utilization']['person_avg'] = avg_person_util
            
            print(f"  📊 平均人员利用率: {avg_person_util:.1f}%", file=sys.stderr)
        
        # ========================================
        # 4. 约束违反检查
        # ========================================
        violations = self._check_violations(df)
        metrics['violations'] = violations
        
        if violations:
            print(f"  ⚠️ 约束违反: {len(violations)} 个", file=sys.stderr)
        else:
            print(f"  ✅ 无约束违反", file=sys.stderr)
        
        self.metrics[algorithm_name] = metrics
        return metrics
    
    def _calculate_port_utilization(self, df):
        """计算 Port 利用率"""
        port_util = {}
        
        for date in df['日期'].unique():
            day_df = df[df['日期'] == date]
            
            for shift in ['AM', 'PM']:
                shift_df = day_df[day_df['班次'] == shift]
                
                used_ports = set()
                for _, row in shift_df.iterrows():
                    ports_str = str(row.get('ports_list', ''))
                    
                    if not ports_str or ports_str == 'IVEK':
                        continue
                    
                    try:
                        ports = [int(p.strip()) for p in ports_str.split(',') if p.strip().isdigit()]
                        used_ports.update(ports)
                    except:
                        pass
                
                shift_key = f"{date}_{shift}"
                port_util[shift_key] = {
                    'used': len(used_ports),
                    'total': 12,
                    'rate': len(used_ports) / 12 * 100
                }
        
        return port_util
    
    def _calculate_dryer_utilization(self, df):
        """计算凍乾機利用率"""
        dryer_util = {}
        
        total_dryers = 18  # LD-3 ~ LD-20
        
        for date in df['日期'].unique():
            day_df = df[df['日期'] == date]
            
            used_dryers = set()
            for _, row in day_df.iterrows():
                dryer = str(row.get('凍乾機台', '')).strip()
                if dryer and dryer != 'N/A':
                    used_dryers.add(dryer)
            
            dryer_util[date] = {
                'used': len(used_dryers),
                'total': total_dryers,
                'rate': len(used_dryers) / total_dryers * 100,
                'dryers': sorted(list(used_dryers))
            }
        
        return dryer_util
    
    def _calculate_person_utilization(self, df):
        """计算人员利用率"""
        person_util = {}
        
        # 收集所有人员
        all_people = set()
        for _, row in df.iterrows():
            person = str(row.get('配藥同仁', '')).strip()
            if person:
                all_people.add(person)
        
        total_people = len(all_people)
        
        if total_people == 0:
            return {}
        
        for date in df['日期'].unique():
            day_df = df[df['日期'] == date]
            
            for shift in ['AM', 'PM']:
                shift_df = day_df[day_df['班次'] == shift]
                
                used_people = set()
                for _, row in shift_df.iterrows():
                    person = str(row.get('配藥同仁', '')).strip()
                    if person:
                        used_people.add(person)
                
                shift_key = f"{date}_{shift}"
                person_util[shift_key] = {
                    'used': len(used_people),
                    'total': total_people,
                    'rate': len(used_people) / total_people * 100
                }
        
        return person_util
    
    def _check_violations(self, df):
        """检查约束违反"""
        violations = []
        
        # 检查 1: 禁止收药时段 (03:00-08:00)
        for idx, row in df.iterrows():
            end_time_str = row.get('預計結束', '')
            
            if not end_time_str:
                continue
            
            try:
                hour = int(end_time_str.split(':')[0])
                if 3 <= hour < 8:
                    violations.append({
                        'type': '禁止收药时段',
                        'date': row.get('日期', ''),
                        'pn': row.get('lot', ''),
                        'end_time': end_time_str
                    })
            except:
                pass
        
        # 检查 2: Port 超限
        for date in df['日期'].unique():
            day_df = df[df['日期'] == date]
            
            for shift in ['AM', 'PM']:
                shift_df = day_df[day_df['班次'] == shift]
                
                used_ports = set()
                for _, row in shift_df.iterrows():
                    ports_str = str(row.get('ports_list', ''))
                    
                    if ports_str and ports_str != 'IVEK':
                        try:
                            ports = [int(p.strip()) for p in ports_str.split(',') if p.strip().isdigit()]
                            used_ports.update(ports)
                        except:
                            pass
                
                if len(used_ports) > 12:
                    violations.append({
                        'type': 'Port 超限',
                        'date': date,
                        'shift': shift,
                        'used': len(used_ports)
                    })
        
        return violations
    
    def compare(self):
        """对比两种算法（聚焦完工时间和资源利用率）"""
        
        print("\n" + "="*80)
        print("📊 CP-SAT vs 贪婪算法 - 对比报告")
        print("="*80)
        
        greedy = self.metrics.get('greedy')
        cp = self.metrics.get('cp')
        
        if not greedy or not cp:
            print("  ⚠️ 缺少对比数据")
            return None
        
        # ========================================
        # 1. 完工时间对比（主要指标）⭐⭐⭐
        # ========================================
        print("\n🏁 完工时间对比（越短越好）:")
        print("-" * 80)
        
        if greedy.get('makespan'):
            print(f"  贪婪算法:")
            print(f"    完成时间: {greedy['makespan']}")
            print(f"    总工期:   {greedy['total_days']} 天 ({greedy['total_hours']:.1f} 小时)")
        
        if cp.get('makespan'):
            print(f"\n  CP-SAT:")
            print(f"    完成时间: {cp['makespan']}")
            print(f"    总工期:   {cp['total_days']} 天 ({cp['total_hours']:.1f} 小时)")
        
        # 计算时间差异
        if greedy.get('total_hours') and cp.get('total_hours'):
            time_diff = greedy['total_hours'] - cp['total_hours']
            time_improvement = (time_diff / greedy['total_hours'] * 100) if greedy['total_hours'] > 0 else 0
            
            print(f"\n  📈 时间差异:")
            if time_diff > 0:
                print(f"    CP-SAT 提前完工: {time_diff:.1f} 小时 ({time_improvement:.1f}%)")
                print(f"    ✅ CP-SAT 胜出")
            elif time_diff < 0:
                print(f"    贪婪算法提前完工: {abs(time_diff):.1f} 小时 ({abs(time_improvement):.1f}%)")
                print(f"    ✅ 贪婪算法胜出")
            else:
                print(f"    🤝 完工时间相同")
        
        # ========================================
        # 2. 资源利用率对比（次要指标）⭐⭐
        # ========================================
        print("\n\n📊 资源利用率对比（越高越好）:")
        print("-" * 80)
        
        # 2.1 Port 利用率
        greedy_port = greedy.get('resource_utilization', {}).get('port_avg', 0)
        cp_port = cp.get('resource_utilization', {}).get('port_avg', 0)
        
        print(f"\n  Port 利用率:")
        print(f"    贪婪算法: {greedy_port:.1f}%")
        print(f"    CP-SAT:   {cp_port:.1f}%")
        
        if cp_port > greedy_port:
            print(f"    ✅ CP-SAT 高 {cp_port - greedy_port:.1f}%")
        elif greedy_port > cp_port:
            print(f"    ✅ 贪婪算法高 {greedy_port - cp_port:.1f}%")
        else:
            print(f"    🤝 相同")
        
        # 2.2 凍乾機利用率
        greedy_dryer = greedy.get('resource_utilization', {}).get('dryer_avg', 0)
        cp_dryer = cp.get('resource_utilization', {}).get('dryer_avg', 0)
        
        print(f"\n  凍乾機利用率:")
        print(f"    贪婪算法: {greedy_dryer:.1f}%")
        print(f"    CP-SAT:   {cp_dryer:.1f}%")
        
        if cp_dryer > greedy_dryer:
            print(f"    ✅ CP-SAT 高 {cp_dryer - greedy_dryer:.1f}%")
        elif greedy_dryer > cp_dryer:
            print(f"    ✅ 贪婪算法高 {greedy_dryer - cp_dryer:.1f}%")
        else:
            print(f"    🤝 相同")
        
        # 2.3 人员利用率
        greedy_person = greedy.get('resource_utilization', {}).get('person_avg', 0)
        cp_person = cp.get('resource_utilization', {}).get('person_avg', 0)
        
        print(f"\n  人员利用率:")
        print(f"    贪婪算法: {greedy_person:.1f}%")
        print(f"    CP-SAT:   {cp_person:.1f}%")
        
        if cp_person > greedy_person:
            print(f"    ✅ CP-SAT 高 {cp_person - greedy_person:.1f}%")
        elif greedy_person > cp_person:
            print(f"    ✅ 贪婪算法高 {greedy_person - cp_person:.1f}%")
        else:
            print(f"    🤝 相同")
        
        # ========================================
        # 3. P1 完成率
        # ========================================
        print("\n\n📋 P1 完成率:")
        print("-" * 80)
        print(f"  贪婪算法: {greedy.get('p1_completion_rate', 0):.1f}%")
        print(f"  CP-SAT:   {cp.get('p1_completion_rate', 0):.1f}%")
        
        # ========================================
        # 4. 约束违反
        # ========================================
        print("\n\n⚠️  约束违反:")
        print("-" * 80)
        print(f"  贪婪算法: {len(greedy.get('violations', []))} 个")
        print(f"  CP-SAT:   {len(cp.get('violations', []))} 个")
        
        # ========================================
        # 5. 综合评分（完工时间 70% + 资源利用率 30%）
        # ========================================
        print("\n\n🏆 综合评分 (满分 100):")
        print("-" * 80)
        
        greedy_score = self._calculate_score(greedy)
        cp_score = self._calculate_score(cp)
        
        print(f"  贪婪算法: {greedy_score:.1f} 分")
        print(f"  CP-SAT:   {cp_score:.1f} 分")
        
        print("\n" + "="*80)
        
        if cp_score > greedy_score:
            print(f"✅ 胜出: CP-SAT (+{cp_score - greedy_score:.1f} 分)")
        elif greedy_score > cp_score:
            print(f"✅ 胜出: 贪婪算法 (+{greedy_score - cp_score:.1f} 分)")
        else:
            print(f"🤝 平手")
        
        print("="*80 + "\n")
        
        # 返回胜者
        if cp_score > greedy_score:
            return 'cp'
        elif greedy_score > cp_score:
            return 'greedy'
        else:
            return 'tie'
    
    def _calculate_score(self, metrics):
        """
        计算综合评分（满分 100）
        
        权重分配:
        - 完工时间: 70 分（主要指标）
        - 资源利用率: 30 分（次要指标）
        """
        
        if not metrics or not metrics.get('success'):
            return 0
        
        score = 0
        
        # ========================================
        # 1. 完工时间得分（70 分）⭐⭐⭐
        # ========================================
        total_hours = metrics.get('total_hours', 0)
        
        if total_hours > 0:
            # 3 天（72 小时）= 满分 70
            # 每多 1 小时扣 1 分
            time_score = max(0, 70 - (total_hours - 72))
            score += min(70, time_score)
        
        # ========================================
        # 2. 资源利用率得分（30 分）⭐⭐
        # ========================================
        resource_util = metrics.get('resource_utilization', {})
        
        # Port 利用率（10 分）
        port_avg = resource_util.get('port_avg', 0)
        score += port_avg * 0.1
        
        # 凍乾機利用率（10 分）
        dryer_avg = resource_util.get('dryer_avg', 0)
        score += dryer_avg * 0.1
        
        # 人员利用率（10 分）
        person_avg = resource_util.get('person_avg', 0)
        score += person_avg * 0.1
        
        return score
    
    def save_report(self, filename='comparison_report.json'):
        """保存详细报告"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.metrics, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"📄 详细报告已保存: {filename}")