#!/usr/bin/env python3
"""
查詢未分裝工單
簡單易用的命令列工具
"""

import requests
import sys
from datetime import datetime

def show_unpackaged_orders(days=7, show_all=False):
    """
    顯示未分裝工單
    
    Args:
        days: 查詢天數（預設 7 天）
        show_all: 是否顯示所有工單分類（預設 False，只顯示未分裝）
    """
    
    print("=" * 70)
    print(f"{'未分裝工單查詢':^70}")
    print("=" * 70)
    print()
    
    # API 查詢
    try:
        url = f'http://localhost:5000/api/workorder/unpackaged-ratio?days={days}'
        print(f"正在查詢最近 {days} 天的工單...")
        print()
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
    except requests.exceptions.ConnectionError:
        print("❌ 錯誤: 無法連接到服務")
        print("   請確認程式已啟動: python main.py")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("❌ 錯誤: 請求逾時")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        sys.exit(1)
    
    if not data.get('success'):
        print("❌ 查詢失敗")
        if 'message' in data:
            print(f"   {data['message']}")
        sys.exit(1)
    
    # 查詢資訊
    query_info = data['query_info']
    stats = data['statistics']
    work_orders = data['work_orders']
    
    print(f"📅 查詢期間: {query_info['start_date']} 至 {query_info['end_date']} (不含)")
    print()
    
    # 統計資訊
    print("📊 統計摘要:")
    print("-" * 70)
    print(f"   已生產工單: {stats['produced_count']:4d} 張")
    print(f"   已分裝工單: {stats['packaged_count']:4d} 張")
    print(f"   未分裝工單: {stats['unpackaged_count']:4d} 張")
    print(f"   未分裝比例: {stats['unpackaged_percentage']:>7s}")
    print("-" * 70)
    print()
    
    # 資料驗證
    validation = data['data_validation']
    if validation['work_orders_conflict']:
        print("⚠️  資料庫衝突警告:")
        print(f"   配藥表: {validation['formulate_db_count']} 張")
        print(f"   WIP 資料庫: {validation['wip_db_count']} 張")
        if validation['only_in_formulate']:
            print(f"   僅在配藥表: {len(validation['only_in_formulate'])} 張")
        if validation['only_in_wip']:
            print(f"   僅在 WIP: {len(validation['only_in_wip'])} 張")
        print()
    
    # 未分裝工單列表
    unpackaged = work_orders['unpackaged']
    
    if unpackaged:
        print(f"📋 未分裝工單清單 ({len(unpackaged)} 張):")
        print("=" * 70)
        
        # 分欄顯示
        cols = 3  # 3 欄
        for i in range(0, len(unpackaged), cols):
            row_items = unpackaged[i:i+cols]
            row_text = "   ".join([f"{item:15s}" for item in row_items])
            print(f"   {row_text}")
        
        print("=" * 70)
    else:
        print("✅ 所有工單都已完成分裝！")
        print("=" * 70)
    
    print()
    
    # 顯示所有工單分類（可選）
    if show_all:
        print("📦 已分裝工單:")
        print("-" * 70)
        packaged = work_orders['packaged']
        if packaged:
            for i in range(0, len(packaged), 3):
                row_items = packaged[i:i+3]
                row_text = "   ".join([f"{item:15s}" for item in row_items])
                print(f"   {row_text}")
        else:
            print("   (無)")
        print("-" * 70)
        print()
    
    # 時間戳記
    print(f"查詢時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()


def main():
    """主程式"""
    
    # 簡單的命令列參數處理
    days = 7
    show_all = False
    
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
            if days < 1 or days > 365:
                print("錯誤: 天數必須在 1-365 之間")
                sys.exit(1)
        except ValueError:
            print("錯誤: 天數必須是數字")
            print()
            print("使用方法:")
            print("  python list_unpackaged.py [天數] [--all]")
            print()
            print("範例:")
            print("  python list_unpackaged.py           # 查詢最近 7 天")
            print("  python list_unpackaged.py 30        # 查詢最近 30 天")
            print("  python list_unpackaged.py 7 --all   # 查詢並顯示所有分類")
            sys.exit(1)
    
    if '--all' in sys.argv or '-a' in sys.argv:
        show_all = True
    
    # 執行查詢
    show_unpackaged_orders(days, show_all)


if __name__ == '__main__':
    main()