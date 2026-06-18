"""
WIP 自動化管理系統 - 主程式
整合 WIP 報表監控和工單統計分析
"""

from flask import Flask, render_template_string
from wip_automation_blueprint_1 import wip_automation_bp, init_wip_automation

# 建立 Flask 應用程式
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# 註冊整合 Blueprint
app.register_blueprint(wip_automation_bp)

# 初始化 WIP 自動化系統
init_wip_automation(app)


@app.route('/')
def index():
    """首頁"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>WIP 自動化管理系統</title>
        <meta charset="UTF-8">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Microsoft JhengHei', 'Segoe UI', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px;
                text-align: center;
            }
            .header h1 {
                font-size: 36px;
                margin-bottom: 10px;
            }
            .header p {
                font-size: 18px;
                opacity: 0.9;
            }
            .content {
                padding: 40px;
            }
            .section {
                margin-bottom: 40px;
            }
            .section-title {
                font-size: 24px;
                color: #333;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 3px solid #667eea;
            }
            .button-group {
                display: flex;
                gap: 15px;
                flex-wrap: wrap;
                margin: 20px 0;
            }
            .btn {
                padding: 15px 30px;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
                display: inline-block;
            }
            .btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            }
            .btn-primary {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .btn-success {
                background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
                color: white;
            }
            .btn-info {
                background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
                color: white;
            }
            .btn-warning {
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                color: white;
            }
            .input-group {
                display: flex;
                align-items: center;
                gap: 15px;
                margin: 20px 0;
            }
            .input-group label {
                font-weight: bold;
                color: #555;
                min-width: 100px;
            }
            .input-group input {
                padding: 12px 20px;
                border: 2px solid #ddd;
                border-radius: 8px;
                font-size: 16px;
                width: 200px;
            }
            .input-group input:focus {
                outline: none;
                border-color: #667eea;
            }
            #result-display {
                background: #f8f9fa;
                padding: 20px;
                border-radius: 10px;
                margin-top: 20px;
                white-space: pre-wrap;
                font-family: 'Courier New', monospace;
                font-size: 13px;
                max-height: 600px;
                overflow-y: auto;
                display: none;
                border: 2px solid #ddd;
            }
            .stats-card {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 25px;
                border-radius: 15px;
                margin: 15px 0;
            }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }
            .stat-item {
                text-align: center;
            }
            .stat-value {
                font-size: 48px;
                font-weight: bold;
                margin: 10px 0;
            }
            .stat-label {
                font-size: 16px;
                opacity: 0.9;
            }
            .api-list {
                background: #f8f9fa;
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
            }
            .api-item {
                padding: 15px;
                margin: 10px 0;
                background: white;
                border-left: 4px solid #667eea;
                border-radius: 5px;
            }
            .api-method {
                display: inline-block;
                padding: 5px 15px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
                margin-right: 10px;
            }
            .method-get {
                background: #28a745;
                color: white;
            }
            .method-post {
                background: #007bff;
                color: white;
            }
            code {
                background: #e9ecef;
                padding: 3px 8px;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 WIP 自動化管理系統</h1>
                <p>整合 WIP 報表監控 + 工單統計分析</p>
            </div>
            
            <div class="content">
                <!-- WIP 監控 -->
                <div class="section">
                    <h2 class="section-title">📦 WIP 報表監控</h2>
                    <div class="button-group">
                        <button class="btn btn-success" onclick="syncWip()">
                            ⚡ 立即同步 WIP
                        </button>
                        <button class="btn btn-info" onclick="getWipStatus()">
                            📊 查看 WIP 狀態
                        </button>
                    </div>
                </div>
                
                <!-- 工單統計 -->
                <div class="section">
                    <h2 class="section-title">📈 工單統計分析</h2>
                    
                    <div class="button-group">
                        <button class="btn btn-primary" onclick="getQuickStats()">
                            🔥 快速統計 (周/月)
                        </button>
                    </div>
                    
                    <div class="input-group">
                        <label>📅 自訂天數:</label>
                        <input type="number" id="custom-days" value="7" min="1" max="365">
                        <button class="btn btn-warning" onclick="getCustomStats()">
                            🔍 查詢統計
                        </button>
                    </div>
                    <p style="color: #666; font-size: 14px; margin-top: 10px;">
                        💡 提示: 7 (周), 30 (月), 90 (季), 365 (年)
                    </p>
                </div>
                
                <!-- 結果顯示 -->
                <div id="result-display"></div>
                
                <!-- API 說明 -->
                <div class="section">
                    <h2 class="section-title">📡 API 端點</h2>
                    
                    <div class="api-list">
                        <div class="api-item">
                            <span class="api-method method-post">POST</span>
                            <code>/wip/sync</code>
                            <p style="margin-top: 10px; color: #666;">手動觸發 WIP 報表同步</p>
                        </div>
                        
                        <div class="api-item">
                            <span class="api-method method-get">GET</span>
                            <code>/wip/status</code>
                            <p style="margin-top: 10px; color: #666;">查詢 WIP 監控系統狀態</p>
                        </div>
                        
                        <div class="api-item">
                            <span class="api-method method-get">GET</span>
                            <code>/api/workorder/unpackaged-ratio?days=N</code>
                            <p style="margin-top: 10px; color: #666;">取得 N 天內已生產未分裝工單比例</p>
                        </div>
                        
                        <div class="api-item">
                            <span class="api-method method-get">GET</span>
                            <code>/api/workorder/quick-stats</code>
                            <p style="margin-top: 10px; color: #666;">快速取得周統計和月統計</p>
                        </div>
                        
                        <div class="api-item">
                            <span class="api-method method-get">GET</span>
                            <code>/api/workorder/detail?work_order=XXX</code>
                            <p style="margin-top: 10px; color: #666;">查詢工單明細 (支援多種 Key 查詢)</p>
                        </div>
                    </div>
                </div>
                
                <!-- 系統資訊 -->
                <div class="section">
                    <h2 class="section-title">ℹ️ 系統資訊</h2>
                    <div class="stats-card">
                        <div class="stats-grid">
                            <div class="stat-item">
                                <div class="stat-label">監控模式</div>
                                <div class="stat-value" style="font-size: 24px;">檔案變動</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-label">自動同步</div>
                                <div class="stat-value" style="font-size: 24px;">即時</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-label">資料格式</div>
                                <div class="stat-value">v1.2</div>
                            </div>
                        </div>
                        <div style="margin-top: 20px; text-align: center; opacity: 0.9;">
                            <p>✨ Excel 檔案儲存時自動同步到資料庫</p>
                            <p>🔄 無需手動操作或等待排程</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            function showResult(title, data) {
                const display = document.getElementById('result-display');
                display.style.display = 'block';
                display.innerHTML = `<strong style="font-size: 16px; color: #667eea;">📋 ${title}</strong>\n\n` + 
                                   JSON.stringify(data, null, 2);
                
                if (data.success || data.status === 'success' || data.status === 'running') {
                    display.style.borderColor = '#28a745';
                    display.style.background = '#d4edda';
                } else {
                    display.style.borderColor = '#dc3545';
                    display.style.background = '#f8d7da';
                }
                
                // 滾動到結果
                display.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
            
            function syncWip() {
                showResult('正在同步 WIP 報表...', {status: 'loading', message: '請稍候...'});
                fetch('/wip/sync', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => showResult('WIP 同步結果', data))
                    .catch(error => showResult('錯誤', {success: false, error: error.message}));
            }
            
            function getWipStatus() {
                showResult('正在查詢 WIP 狀態...', {status: 'loading'});
                fetch('/wip/status')
                    .then(response => response.json())
                    .then(data => showResult('WIP 系統狀態', data))
                    .catch(error => showResult('錯誤', {success: false, error: error.message}));
            }
            
            function getQuickStats() {
                showResult('正在查詢快速統計...', {status: 'loading'});
                fetch('/api/workorder/quick-stats')
                    .then(response => response.json())
                    .then(data => showResult('快速統計結果 (周/月)', data))
                    .catch(error => showResult('錯誤', {success: false, error: error.message}));
            }
            
            function getCustomStats() {
                const days = document.getElementById('custom-days').value;
                if (days < 1 || days > 365) {
                    alert('天數必須在 1-365 之間');
                    return;
                }
                showResult(`正在查詢 ${days} 天統計...`, {status: 'loading'});
                fetch(`/api/workorder/unpackaged-ratio?days=${days}`)
                    .then(response => response.json())
                    .then(data => showResult(`${days} 天統計結果`, data))
                    .catch(error => showResult('錯誤', {success: false, error: error.message}));
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html)


if __name__ == '__main__':
    print("=" * 70)
    print(" " * 20 + "WIP 自動化管理系統")
    print("=" * 70)
    print()
    print("🚀 系統啟動中...")
    print()
    print("📦 包含功能:")
    print("   ✓ WIP 報表檔案監控 (Excel 變動時自動同步)")
    print("   ✓ 工單統計分析 (已生產未分裝比例)")
    print("   ✓ 資料類型優化 (日期/數字/料號)")
    print()
    print("📝 監控模式:")
    print("   • 自動偵測 Excel 檔案變動")
    print("   • 檔案儲存後自動同步到資料庫")
    print("   • 無需手動操作")
    print()
    print("🌐 訪問網址:")
    print("   http://localhost:5000")
    print()
    print("=" * 70)
    
    app.run(
        debug=True,
        host='0.0.0.0',
        port=5000,
        use_reloader=True
    )