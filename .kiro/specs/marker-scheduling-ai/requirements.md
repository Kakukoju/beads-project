# Requirements Document

## Introduction

本模組為 Skyla MRP: Advanced Planning Simulator 新增「AI 排程分析與自動排程」功能。系統將從歷史 Marker 生產排程資料（2026 年）中深度分析規則，寫入衍生規則表，並根據每週 Marker 數量需求，自動拆批、排程，產生建議排程結果。排程結果寫入 `generated_schedule` 表，使用者可預覽、調整、確認後再寫入正式排程表。本模組不破壞現有工作流程，僅新增功能模組。

**生產流程**：配藥 → 滴定 → 凍乾（三階段流程），所有排程邏輯與規則分析皆須遵循此流程順序。

**規則架構**：系統中存在三個既有基準規則表（Base Rule Tables），作為不可違反的規則來源；Rule_Analyzer 從歷史資料分析產生的三個衍生規則表（Derived Rule Tables）必須以基準規則表為基礎，且不得與其衝突。

## Glossary

- **Scheduling_Engine**: 使用 Python 規則引擎或 OR-Tools 最佳化求解器進行時間安排的後端模組
- **Rule_Analyzer**: 從歷史排程資料中萃取 Marker 生產規則並寫入衍生規則表的分析模組
- **Generated_Schedule**: 自動排程結果暫存表（`P01_formualte_schedule.generated_schedule`），不直接覆蓋正式排程
- **Official_Schedule**: 正式 Marker 生產排程表（`P01_formualte_schedule.DropletSchedule`）
- **Marker**: Beads 滴定試劑的生產品項代稱
- **Freeze_Dryer**: 凍乾機，Marker 生產後需使用的乾燥設備
- **Operator**: 配藥人員。Operator 的資源佔用區間僅限配藥階段與 DrugGivenAt 前的準備階段（operator_prepare_start ~ DrugGivenAt）。滴定機台與凍乾機的衝突由 Machine_Port 與 Freeze_Dryer 資源約束負責，不預設 Operator 全程佔用。DrugGivenAt 之後，Operator 是否仍被占用由實際欄位設定決定；若無資料，預設不占用
- **Machine_Port**: 滴定機台（機台 Port）
- **Batch_Splitting**: 根據配藥限制中的數量規則，將大量需求拆分為多批次
- **Conflict_Flag**: 排程衝突標記，標示自動排程中偵測到的資源衝突
- **DrugGivenAt**: R&D 給藥時間，操作員在此時間前只能準備一種藥
- **Operator_Prepare_Interval**: Operator 準備區間，定義為 operator_prepare_start ~ DrugGivenAt。其中 operator_prepare_start = batch_date + shift_start 或前一批準備完成時間（取較晚者）。在此區間內，同一 Operator 不可同時準備兩個 Marker
- **Beads_Need**: 每週 Marker 數量需求分析結果
- **P01_formualte_schedule**: RDS beadsdb 中存放 Marker 排程相關資料的 schema
- **Frontend_Preview**: 前端排程預覽介面，供使用者確認與調整自動排程結果
- **Base_Rule_Tables**: 三個既有基準規則表，作為排程約束的權威來源，包含：`"P01_formualte_schedule".freezer_rules`（Marker 可用凍乾機 + 批次生產數量）、`"P01_formualte_schedule"."pump No."`（Markers 可用的 pump/機台）、`schedule.配藥限制`（配藥人限制/操作員）
- **Derived_Rule_Tables**: 由 Rule_Analyzer 從歷史資料分析產生的三個衍生規則表：`marker_rule`、`machine_capacity_rule`、`operator_rule`，必須以 Base_Rule_Tables 為基準且不得與其衝突
- **Production_Flow**: Marker 生產的三階段流程：配藥（Dispensing）→ 滴定（Titration）→ 凍乾（Freeze-drying），排程必須遵循此順序
- **dropletRecord**: 歷史實際生產記錄表（`P01_formualte_schedule.dropletRecord`），記錄每次滴定的實際執行資料
- **worker_order**: 工單排程表，記錄工單的排程順序與狀態，供分析比對使用
- **Schedule_Excel**: 現場共用的 Excel 排程表（`排程表week_2026.xlsm`），每週一個 sheet（`26排程表-wXX`），包含統計區域（rows 1-98）與每日排程資料區域（row 99 起，以 H 欄「日期:」為 day separator）
- **ExcelSyncService**: 獨立的 Excel 同步服務模組，負責將排程結果寫入 Schedule_Excel，與 RDS 寫入交易解耦，失敗不影響 RDS 資料

## Requirements

### Requirement 1: 歷史排程資料規則分析

**User Story:** 身為生產主管，我希望系統能自動分析歷史排程資料的規則模式，以便建立準確的自動排程規則基礎。

#### Acceptance Criteria

1. WHEN 使用者觸發規則分析功能, THE Rule_Analyzer SHALL 讀取 `P01_formualte_schedule.DropletSchedule` 中 2026 年的歷史排程資料
2. WHEN 歷史資料載入完成, THE Rule_Analyzer SHALL 交叉比對 `P01_formualte_schedule.dropletRecord` 中的實際生產記錄，以區分計畫排程與實際執行差異
3. WHEN 歷史資料載入完成, THE Rule_Analyzer SHALL 比對 `worker_order` 中的工單排程，以發現排程模式與工單關聯性
4. WHEN 歷史資料載入完成, THE Rule_Analyzer SHALL 針對每個 Marker 分析其常用 Machine_Port、常用 Freeze_Dryer、常用 Operator、常見開始與結束時間、平均生產時間、常見數量、以及備註欄中的特殊規則
5. WHEN 規則分析完成, THE Rule_Analyzer SHALL 將結果寫入三個衍生規則表：`marker_rule`（Marker 級規則）、`machine_capacity_rule`（機台容量規則）、`operator_rule`（操作員規則）
6. IF 歷史資料中某 Marker 的記錄數量少於 3 筆, THEN THE Rule_Analyzer SHALL 標記該 Marker 為「資料不足」並使用 Base_Rule_Tables（`freezer_rules`、`"pump No."`、`配藥限制`）中的靜態規則作為預設值
7. WHEN 規則寫入完成, THE Rule_Analyzer SHALL 回傳分析摘要，包含已分析的 Marker 數量、已建立的規則數量、以及資料不足的 Marker 清單

### Requirement 2: 衍生規則與基準規則一致性驗證

**User Story:** 身為生產主管，我希望系統分析產生的衍生規則不會與既有基準規則矛盾，以確保排程結果的正確性與合規性。

#### Acceptance Criteria

1. WHEN Rule_Analyzer 完成衍生規則寫入, THE Rule_Analyzer SHALL 執行一致性驗證，比對衍生規則與 Base_Rule_Tables 的內容
2. THE Rule_Analyzer SHALL 驗證 `marker_rule` 中每個 Marker 的 common_dryers 是否為 `P01_formualte_schedule.freezer_rules` 中該 Marker 可用凍乾機清單的子集
3. THE Rule_Analyzer SHALL 驗證 `marker_rule` 中每個 Marker 的 common_machines 是否為 `P01_formualte_schedule."pump No."` 中該 Marker 可用機台清單的子集
4. THE Rule_Analyzer SHALL 驗證 `operator_rule` 中每個 Operator 的 capable_markers 是否符合 `schedule.配藥限制` 中該操作員的配藥資格限制
5. THE Rule_Analyzer SHALL 驗證 `marker_rule` 中的 common_quantities 是否符合 `P01_formualte_schedule.freezer_rules` 中定義的批次生產數量範圍
6. IF 衍生規則與基準規則存在衝突, THEN THE Rule_Analyzer SHALL 標記衝突項目、記錄衝突原因，並以基準規則為準進行修正
7. WHEN 驗證完成, THE Rule_Analyzer SHALL 回傳驗證報告，包含驗證通過項目數、衝突項目數、已自動修正項目數、及各衝突的詳細說明

### Requirement 3: 生產流程順序約束

**User Story:** 身為生產規劃員，我希望排程結果嚴格遵循配藥→滴定→凍乾的生產流程順序，以確保生產作業可行性。

#### Acceptance Criteria

1. THE Scheduling_Engine SHALL 確保每個批次的排程遵循 Production_Flow 順序：配藥階段完成後才可開始滴定階段，滴定階段完成後才可開始凍乾階段
2. THE Scheduling_Engine SHALL 確保同一 Operator 在 Operator_Prepare_Interval（operator_prepare_start ~ DrugGivenAt）內僅被分配準備一種 Marker，不與該 Operator 其他批次的準備區間重疊
3. THE Scheduling_Engine SHALL 根據 Production_Flow 各階段的資源需求分別約束：配藥階段與 DrugGivenAt 前準備階段受 `schedule.配藥限制` 與 Operator 約束、滴定階段受 `P01_formualte_schedule."pump No."` 與 Machine_Port 約束、凍乾階段受 `P01_formualte_schedule.freezer_rules` 與 Freeze_Dryer 約束
4. THE Scheduling_Engine SHALL 不預設 Operator 在 DrugGivenAt 之後仍被佔用；若系統未記錄滴定/凍乾專責人員欄位資料，則 Operator 衝突檢查僅限配藥階段與 DrugGivenAt 前的準備階段
5. IF 排程結果違反 Production_Flow 順序, THEN THE Scheduling_Engine SHALL 將該批次標記為衝突並在 conflict_reason 中記錄「生產流程順序違規」

### Requirement 4: 週需求匯入與批次拆分

**User Story:** 身為生產規劃員，我希望能匯入每週 Marker 需求數量，並由系統自動拆分批次，以便快速產生排程基礎資料。

#### Acceptance Criteria

1. WHEN 使用者匯入週需求資料, THE Scheduling_Engine SHALL 接收來自 Beads_Need 分析的 Marker 數量需求清單
2. WHEN 需求資料接收完成, THE Scheduling_Engine SHALL 根據 `schedule.配藥限制` 中每個 Marker 對應的「數量」欄位進行自動拆批
3. WHEN 拆批完成, THE Scheduling_Engine SHALL 為每個批次產生以下欄位：日期、Marker、機台、凍乾機、操作員、R&D時間、開始、結束、數量、P/N、Batch、工單號碼、備註
4. THE Scheduling_Engine SHALL 依據以下規則產生 Batch 編號：Marker P/N 末三碼 + 西元年末兩碼 + 週數（兩碼）+ 批次序號（0-9 後接 A-Z）
5. WHEN Batch 編號產生後, THE Scheduling_Engine SHALL 檢查 DropletSchedule、generated_schedule、dropletRecord 是否已存在相同 Batch 編號；IF 已存在, THEN THE Scheduling_Engine SHALL 自動遞增批次序號直到產生唯一 Batch 編號
6. THE Scheduling_Engine SHALL 依據以下規則產生工單號碼：TMRA + 西元年末兩碼 + XXX（三碼月序號）；XXX 月序號 SHALL 從 DropletSchedule 與 generated_schedule 中查詢當月最大 TMRA 工單流水號後 +1，不得僅依本次排程資料重新從 001 開始
7. IF 匯入的需求數量無法被配藥限制中的數量整除, THEN THE Scheduling_Engine SHALL 使用最接近且不超過限制的數量進行拆分，並將餘量歸入最後一批

### Requirement 5: 自動排程約束求解

**User Story:** 身為生產規劃員，我希望系統能根據所有約束條件自動產生排程建議，以減少人工排程耗時並避免衝突。

#### Acceptance Criteria

1. THE Scheduling_Engine SHALL 確保同一 Machine_Port 在同一時段無時間重疊
2. THE Scheduling_Engine SHALL 確保同一 Freeze_Dryer 的同時使用量不超過 `P01_formualte_schedule.freezer_rules` 中定義的容量上限
3. WHILE 在 Operator_Prepare_Interval（operator_prepare_start ~ DrugGivenAt）內, THE Scheduling_Engine SHALL 確保同一 Operator 僅被分配準備一種 Marker
4. THE Scheduling_Engine SHALL 確保同一 Operator 的多個 Operator_Prepare_Interval 之間無時間重疊；DrugGivenAt 之後若無明確欄位設定佔用，Operator 預設為釋放狀態
5. WHEN 排程包含具有特殊備註的 Marker, THE Scheduling_Engine SHALL 遵守備註中定義的限制條件（如機台互斥、凍乾機獨佔等）
6. THE Scheduling_Engine SHALL 優先排入交期較近且優先度較高的 Marker 批次
7. THE Scheduling_Engine SHALL 使用 Python 規則引擎或 OR-Tools 最佳化求解器進行時間安排，排程邏輯不得僅依賴 LLM 生成
8. THE Scheduling_Engine SHALL 僅將 Marker 分配至 Base_Rule_Tables 中明確允許的資源（凍乾機、機台、操作員），不得分配至基準規則未列出的資源

### Requirement 6: 排程結果儲存與衝突偵測

**User Story:** 身為生產規劃員，我希望自動排程結果不會直接覆蓋正式排程，且系統能自動偵測並標記衝突，以便我進行審核。

#### Acceptance Criteria

1. WHEN 自動排程完成, THE Scheduling_Engine SHALL 將結果寫入 `P01_formualte_schedule.generated_schedule` 表，不直接修改 Official_Schedule
2. THE Generated_Schedule SHALL 包含以下欄位：id、日期、Marker、機台、凍乾機、操作員、R&D時間、開始、結束、數量、P/N、Batch、工單號碼、備註、conflict_flag、conflict_reason、priority、status
3. IF 排程結果中偵測到資源衝突, THEN THE Scheduling_Engine SHALL 將該筆記錄的 conflict_flag 設為 true 並在 conflict_reason 欄位記錄衝突原因說明
4. WHEN 衝突偵測完成, THE Scheduling_Engine SHALL 回傳衝突統計摘要，包含衝突總數與各衝突類型的數量

### Requirement 7: 前端排程預覽與確認

**User Story:** 身為生產規劃員，我希望能在前端預覽自動排程結果、手動調整後確認，再寫入正式排程表，以確保排程品質。

#### Acceptance Criteria

1. WHEN 使用者進入排程預覽頁面, THE Frontend_Preview SHALL 以表格形式顯示 Generated_Schedule 中的所有排程項目
2. THE Frontend_Preview SHALL 以紅色標記具有 conflict_flag 的排程項目，並顯示 conflict_reason 內容
3. WHEN 使用者手動調整排程項目的日期、時間、機台、凍乾機或操作員, THE Frontend_Preview SHALL 即時重新驗證該項目的約束條件並更新 conflict_flag 狀態
4. WHEN 使用者確認排程並點擊「寫入正式排程」按鈕, THE Frontend_Preview SHALL 將無衝突的排程項目寫入 Official_Schedule
5. IF 使用者嘗試寫入含有衝突的排程項目, THEN THE Frontend_Preview SHALL 顯示警告提示並要求使用者確認是否強制寫入
6. THE Frontend_Preview SHALL 提供「全部確認」與「逐筆確認」兩種寫入模式

### Requirement 8: AI 輔助分析與建議

**User Story:** 身為生產規劃員，我希望 AI 能提供排程衝突的解釋與調整建議，以幫助我更快做出正確的排程決策。

#### Acceptance Criteria

1. WHEN 排程存在衝突, THE Rule_Analyzer SHALL 使用 AI 模型分析衝突原因並產生自然語言的衝突解釋
2. WHEN 使用者查看衝突詳情, THE Rule_Analyzer SHALL 提供至少一個具體的排程調整建議，包含建議的替代時段、機台或操作員
3. THE Rule_Analyzer SHALL 基於歷史排程模式提供排程策略建議，包含最佳排程順序與資源分配模式
4. THE Rule_Analyzer SHALL 僅負責規則分析、衝突解釋與策略建議；實際時間安排由 Scheduling_Engine 執行

### Requirement 9: 規則表資料庫設計

**User Story:** 身為系統開發者，我希望有結構化的衍生規則表儲存分析結果，以便排程引擎能高效查詢和使用規則資料。

#### Acceptance Criteria

1. THE Rule_Analyzer SHALL 儲存衍生規則於 `P01_formualte_schedule` schema 的 `marker_rule` 表中，包含欄位：id、marker_name、pn、common_machines（JSON 陣列）、common_dryers（JSON 陣列）、common_operators（JSON 陣列）、avg_start_time、avg_end_time、avg_duration_minutes、common_quantities（JSON 陣列）、special_notes（JSON 陣列）、data_confidence（high/medium/low）、base_rule_validated（boolean）、last_analyzed_at
2. THE Rule_Analyzer SHALL 儲存衍生規則於 `P01_formualte_schedule` schema 的 `machine_capacity_rule` 表中，包含欄位：id、machine_id、machine_type（port/dryer）、max_concurrent、available_hours_start、available_hours_end、maintenance_schedule（JSON）、base_rule_validated（boolean）、last_updated_at
3. THE Rule_Analyzer SHALL 儲存衍生規則於 `P01_formualte_schedule` schema 的 `operator_rule` 表中，包含欄位：id、operator_name、capable_markers（JSON 陣列）、max_concurrent_tasks、available_days（JSON 陣列）、shift_start、shift_end、base_rule_validated（boolean）、last_updated_at
4. THE Scheduling_Engine SHALL 在排程計算前從衍生規則表載入最新規則資料，若衍生規則表為空則使用 Base_Rule_Tables 作為 fallback
5. THE Scheduling_Engine SHALL 在使用衍生規則前驗證 base_rule_validated 欄位為 true，若為 false 則以 Base_Rule_Tables 為準

### Requirement 10: 資料來源與分析依據

**User Story:** 身為生產主管，我希望規則分析能基於完整的資料來源，包含實際生產記錄與工單資訊，以提高分析結果的準確度。

#### Acceptance Criteria

1. THE Rule_Analyzer SHALL 從 `P01_formualte_schedule.dropletRecord` 讀取實際生產記錄，作為分析 Marker 實際生產時間、實際使用機台與實際操作員的依據
2. THE Rule_Analyzer SHALL 從 `worker_order` 讀取工單排程記錄，作為分析排程模式、工單頻率與交期規律的依據
3. WHEN 分析 Marker 生產規則時, THE Rule_Analyzer SHALL 比對 `DropletSchedule`（計畫排程）與 `dropletRecord`（實際生產）的差異，以識別計畫與實際執行的偏差模式
4. WHEN 分析排程模式時, THE Rule_Analyzer SHALL 比對 `worker_order` 中的工單排程與 `DropletSchedule` 中的生產排程，以發現工單需求與生產排程的關聯規律
5. THE Rule_Analyzer SHALL 在分析摘要中標註資料來源覆蓋率，包含 dropletRecord 的時間範圍與記錄筆數、worker_order 的時間範圍與工單筆數

### Requirement 11: API 端點設計

**User Story:** 身為前端開發者，我希望有清晰定義的 API 端點來操作排程分析與排程功能，以便前端能正確整合所有功能。

#### Acceptance Criteria

1. THE Scheduling_Engine SHALL 提供 POST `/api/ai-schedule/analyze-rules` 端點，觸發歷史排程資料的規則分析
2. THE Scheduling_Engine SHALL 提供 POST `/api/ai-schedule/generate` 端點，接收需求資料並產生自動排程結果
3. THE Scheduling_Engine SHALL 提供 GET `/api/ai-schedule/preview` 端點，回傳 Generated_Schedule 中的排程資料供前端預覽
4. THE Scheduling_Engine SHALL 提供 PUT `/api/ai-schedule/update/{id}` 端點，允許前端更新單筆排程項目
5. THE Scheduling_Engine SHALL 提供 POST `/api/ai-schedule/confirm` 端點，將已確認的排程項目寫入 Official_Schedule
6. THE Scheduling_Engine SHALL 提供 POST `/api/ai-schedule/validate` 端點，對指定排程項目執行約束驗證並回傳衝突結果
7. THE Scheduling_Engine SHALL 提供 GET `/api/ai-schedule/suggestions/{id}` 端點，回傳 AI 對特定衝突排程的調整建議
8. THE Scheduling_Engine SHALL 提供 GET `/api/ai-schedule/validation-report` 端點，回傳最近一次衍生規則與基準規則的一致性驗證報告

### Requirement 12: 排程結果同步寫入 Excel 排程表

**User Story:** 身為生產規劃員，我希望排程確認後能自動同步寫入現有的 Excel 排程表（排程表week_2026.xlsm），以便與現場人員共用的 Excel 格式一致。

#### Acceptance Criteria

1. WHEN 排程確認寫入正式排程時, THE ExcelSyncService SHALL 獨立於 RDS confirm transaction 執行 Excel 同步寫入，不得與 RDS 寫入交易綁定
2. THE ExcelSyncService SHALL 在 RDS 寫入成功後執行 Excel 寫入；即使 Excel 寫入失敗，亦不得 rollback RDS 已完成的寫入
3. IF Excel 寫入失敗, THEN THE ExcelSyncService SHALL 記錄 sync_status = failed 與 error_message 至排程記錄，供使用者後續重試
4. THE ExcelSyncService SHALL 在 Excel 中找到最靠近目標週的既有 sheet（名稱格式為 `26排程表-wXX`，忽略含 `(*)` 後綴的副本 sheet），複製該 sheet 作為新週排程的模板
5. THE ExcelSyncService SHALL 將複製的 sheet 命名為 `26排程表-wXX`，其中 XX 為目標週別（例如 w24）
6. THE ExcelSyncService SHALL 在新 sheet 的 H 欄找到所有值為「日期:」的儲存格（day separator rows），並在對應的 I 欄填入該週各工作日的日期（I 欄 = 日期, J 欄 = 星期幾）
7. THE ExcelSyncService SHALL 在每個 day section（兩個「日期:」行之間的區域）中，根據排程結果填入各筆排程資料，欄位對應為：H=滴定機、I=Marker、J=凍乾機台、K=可用凍乾機（公式）、L=數量、M=配藥同仁、N=日期、O=RD給藥時間、P=預計滴定時間、Q=預計結束、R=工單編號、S=Lot(Batch)、T=備註
8. THE ExcelSyncService SHALL 根據每日實際排程筆數動態增加或刪除 row：若某日排程筆數多於模板行數則插入新行，若少於模板行數則刪除多餘行
9. THE ExcelSyncService SHALL 保留模板 sheet 中 rows 1-98 的統計區域（PN 清單與 SUMIF 公式）不做修改，僅修改 row 99 以後的排程資料區域
10. THE ExcelSyncService SHALL 寫入目標路徑為 `/home/ubuntu/beads-project/excelData/Excel_data/排程表week_2026.xlsm`
11. IF Excel 檔案不存在或無法寫入, THEN THE ExcelSyncService SHALL 記錄錯誤但不中斷排程確認流程（Excel 寫入為附加功能，不影響 RDS 寫入）

### Requirement 13: 系統整合與不破壞原則

**User Story:** 身為系統管理員，我希望新模組不會影響現有系統的正常運作，以確保生產流程的穩定性。

#### Acceptance Criteria

1. THE Scheduling_Engine SHALL 使用獨立的 API 路由前綴 `/api/ai-schedule/`，不修改現有的 `/api/run-production-schedule` 等端點
2. THE Scheduling_Engine SHALL 使用新建的資料表（`generated_schedule`、`marker_rule`、`machine_capacity_rule`、`operator_rule`），不修改現有的 `DropletSchedule`、`配藥限制`、`BeadNeed` 等表結構
3. THE Frontend_Preview SHALL 作為 Sidebar 中的新導航項目呈現，不修改現有的「Beads 需求分析與排程」、「Panel 機構料」、「Tutti 工單」等頁面
4. IF 新模組的 API 發生錯誤, THEN THE Scheduling_Engine SHALL 記錄錯誤日誌並回傳錯誤訊息，不影響其他 API 端點的正常運作
5. THE Scheduling_Engine SHALL 在 `P01_formualte_schedule` schema 下建立所有新表，與現有 `schedule` schema 的資料隔離
6. THE Scheduling_Engine SHALL 對 Base_Rule_Tables（`freezer_rules`、`"pump No."`、`配藥限制`）僅進行讀取操作，不得修改其內容

### Requirement 14: 排程版本與重跑機制

**User Story:** 身為生產規劃員，我希望同一週可以多次產生排程版本，以便比較不同排程結果並保留歷史紀錄。

#### Acceptance Criteria

1. THE Scheduling_Engine SHALL 為每次自動排程產生唯一的 schedule_run_id
2. THE Generated_Schedule SHALL 包含 schedule_run_id、week_code、created_by、created_at、status 欄位
3. WHEN 使用者重新產生同一週排程, THE Scheduling_Engine SHALL 不覆蓋舊版本，而是建立新的 schedule_run_id 記錄
4. THE Frontend_Preview SHALL 支援依 schedule_run_id 查看不同版本排程結果
5. WHEN 使用者確認某一版本, THE Scheduling_Engine SHALL 將該 schedule_run_id 標記為 approved，其餘同週版本標記為 superseded

### Requirement 15: 審核紀錄與回復機制

**User Story:** 身為系統管理員，我希望所有自動排程寫入正式排程的動作都有紀錄，以便追蹤與必要時回復。

#### Acceptance Criteria

1. THE Scheduling_Engine SHALL 建立 `P01_formualte_schedule.ai_schedule_audit_log` 表，用於記錄所有排程寫入正式排程的審核紀錄
2. WHEN 使用者確認寫入 Official_Schedule, THE Scheduling_Engine SHALL 記錄 confirmed_by、confirmed_at、schedule_run_id、寫入筆數至 ai_schedule_audit_log
3. THE Scheduling_Engine SHALL 記錄每筆 generated_schedule 對應寫入的 DropletSchedule id，建立寫入追溯關聯
4. IF 寫入後需要回復, THEN THE Scheduling_Engine SHALL 支援依 schedule_run_id 標記 rollback（設定 rollback 狀態與時間戳記），而非直接刪除資料
5. WHEN 使用者強制寫入含衝突項目, THE Scheduling_Engine SHALL 在 ai_schedule_audit_log 中記錄 force_confirm_reason
