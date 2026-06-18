"""
WIP 報表監控 Blueprint
監控 Excel 檔案並定期同步到 SQLite 資料庫
"""

import os
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
import atexit

from flask import Blueprint
from apscheduler.schedulers.background import BackgroundScheduler
import openpyxl
import pandas as pd

# 建立 Blueprint
wip_monitor_bp = Blueprint('wip_monitor', __name__)

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== 設定區 ====================
EXCEL_FILE_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\WIP報表 2025-QR01 NEW (請勿亂動連結)H.xlsm"
DB_DIR = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\分藥資料庫"
DB_NAME = "Bead_Sort_DB.db"
HEADER_ROW = 5  # Excel 的 header 在第 5 行 (index 4)
UPDATE_INTERVAL_HOURS = 2

# 全域排程器
scheduler: Optional[BackgroundScheduler] = None


class WIPMonitor:
    """WIP 報表監控類"""
    
    def __init__(self, excel_path: str, db_dir: str, db_name: str):
        self.excel_path = excel_path
        self.db_dir = db_dir
        self.db_name = db_name
        self.db_path = os.path.join(db_dir, db_name)
        
        # 確保資料庫目錄存在
        self._ensure_db_directory()
    
    def _ensure_db_directory(self):
        """確保資料庫目錄存在"""
        try:
            Path(self.db_dir).mkdir(parents=True, exist_ok=True)
            logger.info(f"資料庫目錄確認: {self.db_dir}")
        except Exception as e:
            logger.error(f"建立資料庫目錄失敗: {e}")
            raise
    
    def _get_current_year_sheet_name(self) -> str:
        """取得當前年份的工作表名稱"""
        current_year = datetime.now().year
        return f"{current_year} 明細"
    
    def _read_excel_data(self) -> Optional[pd.DataFrame]:
        """讀取 Excel 資料"""
        try:
            if not os.path.exists(self.excel_path):
                logger.error(f"Excel 檔案不存在: {self.excel_path}")
                return None
            
            sheet_name = self._get_current_year_sheet_name()
            logger.info(f"開始讀取 Excel: {self.excel_path}, 工作表: {sheet_name}")
            
            # 讀取 Excel，跳過前 4 行 (header 在第 5 行)
            df = pd.read_excel(
                self.excel_path,
                sheet_name=sheet_name,
                header=HEADER_ROW - 1,  # pandas 使用 0-based index
                usecols='A:U',  # 只讀取 A 到 U 欄
                engine='openpyxl'
            )
            
            # 移除完全空白的行
            df = df.dropna(how='all')
            
            # 加入更新時間戳記
            df['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            logger.info(f"成功讀取 {len(df)} 筆資料")
            return df
            
        except Exception as e:
            logger.error(f"讀取 Excel 失敗: {e}")
            return None
    
    def _get_table_name(self) -> str:
        """取得資料表名稱"""
        current_year = datetime.now().year
        return f"明細_{current_year}"
    
    def _create_table_if_not_exists(self, conn: sqlite3.Connection, df: pd.DataFrame):
        """建立資料表 (如果不存在)"""
        table_name = self._get_table_name()
        
        try:
            cursor = conn.cursor()
            
            # 檢查資料表是否存在
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            
            if cursor.fetchone() is None:
                # 資料表不存在，建立新表
                logger.info(f"建立新資料表: {table_name}")
                df.to_sql(table_name, conn, if_exists='replace', index=False)
            
        except Exception as e:
            logger.error(f"建立資料表失敗: {e}")
            raise
    
    def _update_database(self, df: pd.DataFrame):
        """更新資料庫"""
        try:
            table_name = self._get_table_name()
            
            with sqlite3.connect(self.db_path) as conn:
                # 確保資料表存在
                self._create_table_if_not_exists(conn, df)
                
                # 刪除舊資料並插入新資料
                logger.info(f"更新資料表: {table_name}")
                df.to_sql(table_name, conn, if_exists='replace', index=False)
                
                # 記錄更新資訊
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                
                logger.info(f"資料庫更新成功: {count} 筆資料")
                
        except Exception as e:
            logger.error(f"更新資料庫失敗: {e}")
            raise
    
    def sync_data(self):
        """同步資料 (主要功能)"""
        try:
            logger.info("=" * 50)
            logger.info("開始同步 WIP 報表資料")
            
            # 讀取 Excel
            df = self._read_excel_data()
            if df is None or df.empty:
                logger.warning("沒有資料可同步")
                return False
            
            # 更新資料庫
            self._update_database(df)
            
            logger.info("WIP 報表同步完成")
            logger.info("=" * 50)
            return True
            
        except Exception as e:
            logger.error(f"同步資料時發生錯誤: {e}")
            return False


# ==================== 排程任務 ====================
def scheduled_sync_task():
    """排程同步任務"""
    monitor = WIPMonitor(EXCEL_FILE_PATH, DB_DIR, DB_NAME)
    monitor.sync_data()


def on_shutdown():
    """程式關閉時執行"""
    logger.info("偵測到程式關閉，執行最後一次同步...")
    try:
        monitor = WIPMonitor(EXCEL_FILE_PATH, DB_DIR, DB_NAME)
        monitor.sync_data()
    except Exception as e:
        logger.error(f"關閉時同步失敗: {e}")


# ==================== Flask Blueprint 路由 ====================
@wip_monitor_bp.route('/wip/sync', methods=['POST'])
def manual_sync():
    """手動觸發同步"""
    try:
        monitor = WIPMonitor(EXCEL_FILE_PATH, DB_DIR, DB_NAME)
        success = monitor.sync_data()
        
        if success:
            return {
                'status': 'success',
                'message': '同步完成',
                'timestamp': datetime.now().isoformat()
            }, 200
        else:
            return {
                'status': 'error',
                'message': '同步失敗',
                'timestamp': datetime.now().isoformat()
            }, 500
            
    except Exception as e:
        logger.error(f"手動同步失敗: {e}")
        return {
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }, 500


@wip_monitor_bp.route('/wip/status', methods=['GET'])
def get_status():
    """取得監控狀態"""
    try:
        monitor = WIPMonitor(EXCEL_FILE_PATH, DB_DIR, DB_NAME)
        table_name = monitor._get_table_name()
        
        # 檢查資料庫狀態
        db_exists = os.path.exists(monitor.db_path)
        record_count = 0
        last_updated = None
        
        if db_exists:
            with sqlite3.connect(monitor.db_path) as conn:
                cursor = conn.cursor()
                
                # 檢查資料表是否存在
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                )
                
                if cursor.fetchone():
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    record_count = cursor.fetchone()[0]
                    
                    cursor.execute(f"SELECT MAX(last_updated) FROM {table_name}")
                    last_updated = cursor.fetchone()[0]
        
        return {
            'status': 'running',
            'excel_file': EXCEL_FILE_PATH,
            'database': monitor.db_path,
            'table_name': table_name,
            'db_exists': db_exists,
            'record_count': record_count,
            'last_updated': last_updated,
            'scheduler_running': scheduler is not None and scheduler.running,
            'update_interval_hours': UPDATE_INTERVAL_HOURS
        }, 200
        
    except Exception as e:
        logger.error(f"取得狀態失敗: {e}")
        return {
            'status': 'error',
            'message': str(e)
        }, 500


# ==================== 初始化函數 ====================
def init_wip_monitor(app):
    """
    初始化 WIP 監控模組
    在主 Flask app 中呼叫此函數
    
    用法:
        from wip_monitor_blueprint import wip_monitor_bp, init_wip_monitor
        
        app = Flask(__name__)
        app.register_blueprint(wip_monitor_bp)
        init_wip_monitor(app)
    """
    global scheduler
    
    with app.app_context():
        logger.info("初始化 WIP 監控模組...")
        
        # 程式啟動時立即同步一次
        try:
            monitor = WIPMonitor(EXCEL_FILE_PATH, DB_DIR, DB_NAME)
            monitor.sync_data()
        except Exception as e:
            logger.error(f"初始同步失敗: {e}")
        
        # 設定排程器
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            func=scheduled_sync_task,
            trigger='interval',
            hours=UPDATE_INTERVAL_HOURS,
            id='wip_sync_job',
            name='WIP 報表同步',
            replace_existing=True
        )
        
        # 啟動排程器
        scheduler.start()
        logger.info(f"排程器已啟動 (每 {UPDATE_INTERVAL_HOURS} 小時同步一次)")
        
        # 註冊關閉處理
        atexit.register(on_shutdown)
        atexit.register(lambda: scheduler.shutdown() if scheduler else None)
        
        logger.info("WIP 監控模組初始化完成")


# ==================== 獨立執行測試 ====================
if __name__ == '__main__':
    # 測試模式
    from flask import Flask
    
    app = Flask(__name__)
    app.register_blueprint(wip_monitor_bp)
    
    # 初始化監控
    init_wip_monitor(app)
    
    # 啟動 Flask
    app.run(debug=True, host='0.0.0.0', port=5000)