# 系統架構對應表

## 後端 Server（正式運行版本）

| 用途 | 路徑 |
|------|------|
| 滴定凍乾主 API Server | `/opt/beadsops/dropfreeze/app_V13_W03.py` |
| 統一排程/IPQC Server | `/opt/beadsops/unified-server/beads_unified_server_V15.py` |

## WO 管理 API Server

| 用途 | 路徑 |
|------|------|
| WO 管理 API (port 5011) | `/opt/beadsops/app-unified/app_unified128.py` |
| systemd service | `flask-app-unified.service` |

## 前端（nginx serve）

| 用途 | 網址路徑 | 檔案路徑 |
|------|----------|----------|
| Dashboard（首頁） | `http://54.199.19.240/` | `/opt/beadsops/frontend-dashboard/dist/` |
| 手機端（滴定凍乾行動紀錄） | `http://54.199.19.240/mobile/` | `/opt/beadsops/dropfreeze/Web-2/` |
| Beads 管理 UI | `http://54.199.19.240/beads-ui/` | `/opt/beadsops/unified-server/beads-ui/dist/` |
| WO 管理 UI | `http://54.199.19.240/wo/` | `/opt/beadsops/app-unified/WO-managerment/滴定凍乾資訊管理UI/11_2/WO_Mana/dist/` |

### 前端原始碼（開發用）

| 用途 | 路徑 |
|------|------|
| 手機端原始碼 | `/opt/beadsops/dropfreeze/Web/index.html`（開發版）、`/opt/beadsops/dropfreeze/Web-2/`（正式 nginx serve） |
| 排程管理 UI（Vite + React） | `/opt/beadsops/unified-server/beads_schedule/` |
| Beads 管理 UI（Vite + React） | `/opt/beadsops/unified-server/beads-ui/` |
| Dashboard 前端 | `/opt/beadsops/frontend-dashboard/` |
| 配藥前端 | `/opt/beadsops/app-unified/bead-formulation-fe/index.html` |
| WO 管理 UI | `/opt/beadsops/app-unified/WO-managerment/滴定凍乾資訊管理UI/11_2/WO_Mana/` |

### WO-managerment 路徑備忘

| 用途 | 路徑 |
|------|------|
| WO-managerment 根目錄 | `/opt/beadsops/app-unified/WO-managerment` |
| 滴定凍乾資訊管理 UI 原始碼 | `/opt/beadsops/app-unified/WO-managerment/滴定凍乾資訊管理UI/11_2/WO_Mana/` |
| nginx `/wo/` 實際 serve 的 build | `/opt/beadsops/app-unified/WO-managerment/滴定凍乾資訊管理UI/11_2/WO_Mana/dist/` |
| UI 壓縮備份 | `/opt/beadsops/app-unified/WO-managerment/滴定凍乾資訊管理UI.7z` |

## 資料庫

| 用途 | 路徑 |
|------|------|
| 工單紀錄（滴定凍乾時間/照片） | `/opt/beadsops/data/work_orders.db` → 表 `work_orders` |
| 排程 + 配藥 | `/opt/beadsops/data/P01_formualte_schedule.db` → 表 `DropletSchedule`、配藥表 |
| IPQC 品質數據 | `/opt/beadsops/data/beads_ipqc.db` |

## Nginx 與 Port 對應

| Port | 後端程式 | 負責 API |
|------|----------|----------|
| 5100 | `app_V13_W03.py` | `/api/mobile/*`、`/api/ops`、`/api/abnormal_*`、`/api/titration`、`/photos`、WebSocket |
| 8505 | `beads_unified_server_V15.py` | `/api/schedule`、`/api/workorder`、`/api/beads-ipqc`、`/api/dashboard`、`/api/wip` |
| 5011 | WO 管理 API (`app_unified128.py`) | `/api/droplet-records`、`/api/upload_droplet_schedule`、`/api/get_workorder` |
| 5001 | Titration Stats | `/api/titration/stats`、`/api/titration/period_stats` |

Nginx 設定檔：`/etc/nginx/conf.d/beadsops.conf`

## 關鍵 API 路由（app_V13_W03.py）

| 路由 | 用途 |
|------|------|
| `GET /api/mobile/work-orders` | 手機端取得近三天工單列表（只顯示有 Pump 的滴定日） |
| `GET /api/mobile/status` | 取得單一工單各步驟狀態 |
| `GET /api/mobile/check-access` | 檢查工單是否已完成 5714 配藥 |
| `POST /api/mobile/upload` | 手機拍照上傳（S3 + 更新 work_orders.db） |
| `POST /api/mobile/delete-photo` | 刪除照片 |
| `POST /api/mobile/update-freezer` | 掃描確認凍乾機 |
| `POST /api/abnormal_record` | 異常事件回報 |

## 關鍵函數（app_V13_W03.py）

| 函數 | 用途 |
|------|------|
| `sync_single_order_logic(order_id)` | 從 DropletSchedule 同步工單資訊到 work_orders.db（日期、Pump、凍乾機、Lot） |
| `get_db_connection()` | 取得 work_orders.db 連線 |
| `now_tw()` | 取得台灣時間 |

## 重要邏輯備註

- **配藥與滴定不同天**：DropletSchedule 中同一工單可能有兩天記錄（配藥日 Pump 為空，滴定日有 Pump）。`sync_single_order_logic` 優先取有 Pump 的滴定日作為 work_orders.db 的「日期」欄位。
- **手機前端不寫入日期**：前端只送 work_order/step_id/user/photo，日期由後端 sync 邏輯決定。
- **照片存 S3**：bucket `beads-photos-harry`，prefix `workorder_photo/` 和 `abnormal_photo/`。
