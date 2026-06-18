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
try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    raise ImportError(
        "APScheduler 未安裝。請執行: pip install APScheduler"
    )
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
EXCEL_FILE_PATH = r"\\fls341\MBBU_FAB\MB_PD\生管自動化\工單入庫\Wip_program\WIP報表 2025-QR01 NEW (請勿亂動連結).xlsm"
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
        """
        取得當前年份的工作表名稱
        自動偵測並處理可能的空格問題
        """
        current_year = datetime.now().year
        
        try:
            # 嘗試讀取 Excel 檔案找到正確的工作表名稱
            wb = openpyxl.load_workbook(self.excel_path, read_only=True, data_only=True)
            
            # 尋找包含年份和 "明細" 的工作表
            possible_names = [
                f"{current_year} 明細",
                f"{current_year} 明細 ",  # 後面有空格
                f"{current_year}明細",
            ]
            
            for sheet_name in wb.sheetnames:
                # 完全匹配
                if sheet_name in possible_names:
                    wb.close()
                    logger.info(f"找到工作表: '{sheet_name}'")
                    return sheet_name
                
                # 模糊匹配 (包含年份和明細)
                if str(current_year) in sheet_name and "明細" in sheet_name:
                    wb.close()
                    logger.info(f"找到工作表: '{sheet_name}' (模糊匹配)")
                    return sheet_name
            
            wb.close()
            
            # 如果找不到，使用預設值
            logger.warning(f"找不到 {current_year} 年的明細工作表，使用預設名稱")
            return f"{current_year} 明細 "
            
        except Exception as e:
            logger.warning(f"無法自動偵測工作表名稱: {e}")
            # 預設使用有空格的版本 (根據實際檔案)
            return f"{current_year} 明細 "
    
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
                engine='openpyxl',
                dtype=str  # 先全部讀取為字串，之後再轉換
            )
            
            # 移除完全空白的行
            df = df.dropna(how='all')
            
            # 處理資料類型轉換
            df = self._convert_data_types(df)
            
            # 加入更新時間戳記 (只有日期，沒有時間)
            df['last_updated'] = datetime.now().strftime('%Y-%m-%d')
            
            logger.info(f"成功讀取 {len(df)} 筆資料")
            return df
            
        except Exception as e:
            logger.error(f"讀取 Excel 失敗: {e}")
            return None
    
    def _convert_data_types(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        轉換資料類型
        - 日期欄位: 轉為 YYYY-MM-DD 格式
        - 數字欄位: 轉為整數（如果可能）
        - 料號等特定欄位: 保持字串格式
        """
        # 定義需要保持為字串的欄位（通常是 ID、編號類）
        text_columns = ['LOT NO', '料號', '工單號碼', '品名', '狀態', '備註', '差異說明']
        
        # 定義日期欄位
        date_columns = ['滴定日期', '入庫日期', '警示日期', '藥劑效期']
        
        # 定義數字欄位（需要轉為整數或保持數字）
        numeric_columns = [
            '工單數', '滴定數(扣除秤重)', '分裝數量', '實際入庫數量',
            '差異\n(負數為紅色)', '藥劑保存(月)', 'QA 檢驗', 'PE登記NG數'
        ]
        
        # 處理日期欄位
        for col in date_columns:
            if col in df.columns:
                df[col] = self._format_date_column(df[col])
        
        # 處理數字欄位
        for col in numeric_columns:
            if col in df.columns:
                df[col] = self._format_numeric_column(df[col])
        
        # 處理文字欄位（確保是字串且去除多餘空格）
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                # 將 'nan' 字串轉為空字串
                df[col] = df[col].replace('nan', '')
        
        # 處理料號欄位（特殊處理，確保是純文字）
        if '料號' in df.columns:
            df['料號'] = df['料號'].apply(self._format_material_number)
        
        return df
    
    def _format_date_column(self, series: pd.Series) -> pd.Series:
        """
        格式化日期欄位為 YYYY-MM-DD 格式
        """
        def format_date(value):
            if pd.isna(value) or value == '' or value == 'nan':
                return None
            
            try:
                # 如果是字串，嘗試解析
                if isinstance(value, str):
                    # 移除可能的時間部分
                    value = value.split(' ')[0]
                    date_obj = pd.to_datetime(value, errors='coerce')
                else:
                    # 如果是 datetime 或其他類型
                    date_obj = pd.to_datetime(value, errors='coerce')
                
                if pd.notna(date_obj):
                    return date_obj.strftime('%Y-%m-%d')
                return None
            except:
                return None
        
        return series.apply(format_date)
    
    def _format_numeric_column(self, series: pd.Series) -> pd.Series:
        """
        格式化數字欄位為整數
        返回整數類型而不是浮點數
        """
        result = []
        for value in series:
            if pd.isna(value) or value == '' or value == 'nan':
                result.append(None)
            else:
                try:
                    # 轉為浮點數再取整數
                    num = float(value)
                    # 轉為整數（四捨五入）
                    result.append(int(round(num)))
                except:
                    result.append(None)
        
        # 返回 Int64 類型（支持 None 的整數類型）
        return pd.Series(result, dtype='Int64')
    
    def _format_material_number(self, value) -> str:
        """
        格式化料號欄位
        確保料號為純文字格式，避免科學記號
        """
        if pd.isna(value) or value == '' or value == 'nan':
            return ''
        
        # 轉為字串
        value_str = str(value)
        
        # 移除 .0 結尾（避免從 Excel 讀取的浮點數格式）
        if value_str.endswith('.0'):
            value_str = value_str[:-2]
        
        # 去除空格
        value_str = value_str.strip()
        
        return value_str
    
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
        logger.error(f"🧨 DB PATH = {self.db_path}")

        try:
            table_name = self._get_table_name()
            
            with sqlite3.connect(self.db_path) as conn:
                # 確保資料表存在
                self._create_table_if_not_exists(conn, df)
                
                # 刪除舊資料並插入新資料
                logger.info(f"更新資料表: {table_name}")
                logger.error("🔥🔥🔥 即將寫入明細表，這行如果沒出現 = 100% 沒寫")

                df.to_sql(table_name, conn, if_exists='replace', index=False)
                
                logger.error("🔥🔥🔥 明細表寫入完成，如果你看到這行，DB 一定有表")

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
