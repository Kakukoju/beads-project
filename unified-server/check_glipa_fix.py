#!/usr/bin/env python3
"""
GLIPA 修正狀態檢查工具
檢查 scheduler.py 是否已經套用新版修正
"""

import sys
import os

def check_scheduler_file(filepath=r"D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Bead_auto_update_schedule\beads_Scheduler_V9_9_7.py"):
    """檢查 scheduler.py 是否包含新版 GLIPA 邏輯"""
    
    if not os.path.exists(filepath):
        print(f"❌ 找不到檔案: {filepath}")
        print(f"   請確認檔案路徑")
        return False
    
    print(f"📋 檢查檔案: {filepath}")
    print("=" * 60)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 檢查標記
    checks = {
        "新版 _check_availability_glipa": [
            "[DEBUG] GLIPA 開始檢查資源",
            "[DEBUG] 開始為 GLIPA-AD 尋找凍乾機",
            "[DEBUG] GLIPA-AD 選定凍乾機",
            "[DEBUG] 開始為 GLIPA-AU 尋找凍乾機",
            "if dryer == dryer1:",
            "跳過 {dryer}（與 dryer1 相同）"
        ],
        "新版 _book_and_record_glipa": [
            "[DEBUG] GLIPA 開始記錄",
            "凍乾機1: {dryer1}, 凍乾機2: {dryer2}",
            "dryer = dryer1 if idx == 0 else dryer2"
        ]
    }
    
    all_ok = True
    
    for section, markers in checks.items():
        print(f"\n🔍 檢查：{section}")
        section_ok = True
        
        for marker in markers:
            # 移除格式化字符串的佔位符來檢查
            check_str = marker.replace("{dryer}", "").replace("{dryer1}", "").replace("{dryer2}", "")
            if check_str in content:
                print(f"   ✅ 找到: {marker[:50]}...")
            else:
                print(f"   ❌ 缺少: {marker[:50]}...")
                section_ok = False
        
        if section_ok:
            print(f"   ✓ {section} 已正確更新")
        else:
            print(f"   ✗ {section} 未更新或不完整")
            all_ok = False
    
    print("\n" + "=" * 60)
    
    if all_ok:
        print("✅ 所有檢查通過！scheduler.py 已包含新版 GLIPA 邏輯")
        return True
    else:
        print("❌ 檢查失敗！scheduler.py 未包含完整的新版邏輯")
        print("\n建議：")
        print("1. 重新複製 glipa_final_fix.py 中的方法")
        print("2. 確保完整替換整個方法（從 def 到下一個 def 之前）")
        print("3. 檢查是否有縮排錯誤")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        # 嘗試常見路徑
        possible_paths = [
            "scheduler.py",
            "../scheduler.py",
            "../../scheduler.py",
        ]
        filepath = None
        for path in possible_paths:
            if os.path.exists(path):
                filepath = path
                break
        
        if filepath is None:
            print("❌ 找不到 scheduler.py")
            print("使用方式: python check_glipa_fix.py [scheduler.py路徑]")
            sys.exit(1)
    
    success = check_scheduler_file(filepath)
    sys.exit(0 if success else 1)
