# Implementation Plan: Marker Scheduling AI

## Overview

本實作計畫將 AI 排程分析與自動排程功能拆解為漸進式的編碼任務。從後端資料模型與基礎架構開始，逐步建構規則分析、排程引擎（CP-SAT）、衝突偵測、Excel 同步，最後整合前端預覽介面。每個任務皆建構在前一任務的成果上，確保無孤立代碼。

## Tasks

- [x] 1. Set up project structure, data models, and Flask Blueprint
  - [x] 1.1 Create `ai_schedule/` Python package with module files
    - Create directory `/home/ubuntu/beads-project/ai_schedule/` with `__init__.py`
    - Create empty module files: `routes.py`, `rule_analyzer.py`, `scheduling_engine.py`, `batch_splitter.py`, `excel_sync_service.py`, `conflict_detector.py`, `ai_advisor.py`, `models.py`, `rule_validator.py`
    - In `__init__.py`, export the Flask Blueprint from `routes.py`
    - _Requirements: 13.1, 13.2_

  - [x] 1.2 Implement SQLAlchemy models in `ai_schedule/models.py`
    - Define `GeneratedSchedule`, `MarkerRule`, `MachineCapacityRule`, `OperatorRule`, `AIScheduleAuditLog` models
    - All tables in `P01_formualte_schedule` schema as defined in design Data Models section
    - Include all columns, constraints, indexes (idx_gs_run_id, idx_gs_week_code, idx_gs_status, unique batch)
    - Use existing `db` instance from `mrpFlask_5.py` (import pattern)
    - _Requirements: 9.1, 9.2, 9.3, 6.2, 15.1_

  - [x] 1.3 Register Blueprint in `mrpFlask_5.py` and create database tables
    - Add `from ai_schedule import ai_schedule_bp` import
    - Register blueprint: `app.register_blueprint(ai_schedule_bp)`
    - Add migration script or `db.create_all()` call for new tables in `P01_formualte_schedule` schema
    - Ensure `search_path` in SQLAlchemy config includes `P01_formualte_schedule`
    - _Requirements: 13.1, 13.5_

  - [x] 1.4 Create Flask Blueprint routes skeleton in `ai_schedule/routes.py`
    - Define `ai_schedule_bp = Blueprint('ai_schedule', __name__, url_prefix='/api/ai-schedule')`
    - Add all 8 endpoint stubs: `POST /analyze-rules`, `POST /generate`, `GET /preview`, `PUT /update/<id>`, `POST /confirm`, `POST /validate`, `GET /suggestions/<id>`, `GET /validation-report`
    - Each stub returns `{"ok": false, "error": "not_implemented"}` with status 501
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

- [x] 2. Checkpoint - Ensure project structure is correct
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement Rule Analyzer and Rule Validator
  - [x] 3.1 Implement `ai_schedule/rule_analyzer.py` — historical data loading and marker analysis
    - Implement `RuleAnalyzer.__init__(self, db_session)` with database session
    - Implement `_load_historical_data()` to query `DropletSchedule` (2026), `dropletRecord`, and `worker_order`
    - Implement `_analyze_marker()` for single Marker: extract common_machines, common_dryers, common_operators, avg times, common_quantities, special_notes from records
    - Implement `analyze_all()` orchestrator: load data → analyze each Marker → write to `marker_rule`, `machine_capacity_rule`, `operator_rule` tables
    - If a Marker has fewer than 3 records, mark `data_confidence='low'` and use Base_Rule_Tables as defaults
    - Return `AnalysisSummary` with markers_analyzed, rules_created, insufficient_data_markers list
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 3.2 Implement `ai_schedule/rule_validator.py` — base rule consistency validation
    - Implement `RuleValidator.__init__(self, db_session)` with database session
    - Implement `validate_marker_rules()`: check common_dryers ⊆ freezer_rules, common_machines ⊆ "pump No.", common_quantities within batch size ranges
    - Implement `validate_operator_rules()`: check capable_markers against `配藥限制`
    - Implement `_correct_conflicts()`: auto-correct by constraining derived rules to base rule sets
    - Implement `generate_validation_report()`: return passed/conflicts_found/auto_corrected/conflict_details
    - Set `base_rule_validated = true` for passing rules, `false` for failed ones
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 3.3 Wire Rule Analyzer into `POST /analyze-rules` endpoint
    - Implement the route handler to instantiate `RuleAnalyzer`, call `analyze_all()`
    - After analysis, call `RuleValidator.validate_marker_rules()` and `validate_operator_rules()`
    - Return JSON response with analysis summary and validation report
    - Handle errors: partial results on failure, 500 status with error details
    - _Requirements: 11.1, 1.7, 2.7_

  - [ ]* 3.4 Write property test for data sufficiency classification
    - **Property 17: Historical Analysis Data Sufficiency Check**
    - **Validates: Requirements 1.6**

  - [ ]* 3.5 Write property test for derived rules subset of base rules
    - **Property 6: Derived Rules Subset of Base Rules**
    - **Validates: Requirements 2.2, 2.3, 2.5**

  - [ ]* 3.6 Write property test for rule loading fallback
    - **Property 15: Rule Loading Fallback**
    - **Validates: Requirements 9.4, 9.5**

- [x] 4. Implement Batch Splitter
  - [x] 4.1 Implement `ai_schedule/batch_splitter.py` — demand splitting and ID generation
    - Implement `BatchSplitter.__init__(self, db_session)` with database session for existing batch/order lookups
    - Implement `split_demands(demands, limits)`: split each MarkerDemand by 配藥限制 quantity, remainder goes to last batch
    - Implement `_generate_batch_number(pn, year, week, seq, existing_batches)`: format = PN末三碼 + 年末兩碼 + 週數(2碼) + 序號(0-9,A-Z), check uniqueness across DropletSchedule, generated_schedule, dropletRecord
    - Implement `_generate_work_order(year, month, existing_max_seq)`: format = TMRA + 年末兩碼 + 三碼月序號, query max existing sequence then +1
    - Handle edge cases: demand_qty < batch_size (single batch), demand_qty not divisible (remainder in last batch)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 4.2 Write property test for batch splitting correctness
    - **Property 7: Batch Splitting Correctness**
    - **Validates: Requirements 4.2, 4.7**

  - [ ]* 4.3 Write property test for batch number uniqueness
    - **Property 8: Batch Number Uniqueness**
    - **Validates: Requirements 4.4, 4.5**

  - [ ]* 4.4 Write property test for work order number monotonicity
    - **Property 9: Work Order Number Monotonicity**
    - **Validates: Requirements 4.6**

- [x] 5. Implement Scheduling Engine (CP-SAT Solver)
  - [x] 5.1 Implement `ai_schedule/scheduling_engine.py` — rule loading and model construction
    - Implement `SchedulingEngine.__init__(self, db_session)` with solver initialization
    - Implement `_load_rules()`: load from derived rule tables (with base_rule_validated=true), fallback to Base_Rule_Tables if empty/invalid
    - Implement `_build_cp_model(batches, rules, horizon_days)`: create CpModel with variables per batch (day, start_grid, machine_idx, dryer_idx, operator_idx)
    - Use 30-min grids matching existing `scheduler_api.py` pattern (10:00~25:30, grids_per_day=31)
    - _Requirements: 5.7, 9.4, 9.5_

  - [x] 5.2 Implement CP-SAT constraint functions
    - Implement `_add_production_flow_constraints()`: dispensing_end ≤ titration_start ≤ freeze_start per batch
    - Implement `_add_machine_port_constraints()`: NoOverlap2D for IntervalVars on same machine_port
    - Implement `_add_dryer_capacity_constraints()`: per dryer per day count ≤ max_concurrent using BoolVars
    - Implement `_add_operator_constraints()`: NoOverlap for Operator_Prepare_Intervals (prepare_start ~ DrugGivenAt), release after DrugGivenAt
    - Implement `_add_base_rule_resource_constraints()`: restrict machine/dryer/operator indices to Base_Rule_Tables allowed sets
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3, 5.4, 5.8_

  - [x] 5.3 Implement solver execution and result extraction
    - Implement `_solve(model)`: execute CP-SAT solver (max_time=30s, workers=4)
    - Implement `_extract_solution()`: convert solver variables to schedule entry dicts
    - Implement priority objective: Minimize(priority * 2000 + day * 100 + start_grid)
    - Implement degradation retry: if INFEASIBLE, try W1+W2 → W1 only
    - _Requirements: 5.6, 5.7_

  - [x] 5.4 Implement `generate()` orchestrator and wire to `POST /generate` endpoint
    - Implement `SchedulingEngine.generate(week_code, demands, resource_config)` orchestrator: load rules → split batches → build model → solve → detect conflicts → write to generated_schedule
    - Create unique `schedule_run_id` (UUID) for each run
    - Wire into `POST /api/ai-schedule/generate` route with request validation
    - Return response with schedule_run_id, data array, conflicts_summary
    - _Requirements: 11.2, 6.1, 14.1, 14.2_

  - [ ]* 5.5 Write property test for production flow ordering
    - **Property 1: Production Flow Ordering Invariant**
    - **Validates: Requirements 3.1, 3.5**

  - [ ]* 5.6 Write property test for operator prepare interval non-overlap
    - **Property 2: Operator Prepare Interval Non-Overlap**
    - **Validates: Requirements 3.2, 5.3, 5.4**

  - [ ]* 5.7 Write property test for machine port time exclusivity
    - **Property 3: Machine Port Time Exclusivity**
    - **Validates: Requirements 5.1**

  - [ ]* 5.8 Write property test for freeze dryer capacity invariant
    - **Property 4: Freeze Dryer Capacity Invariant**
    - **Validates: Requirements 5.2**

  - [ ]* 5.9 Write property test for base rule resource compliance
    - **Property 5: Base Rule Resource Compliance**
    - **Validates: Requirements 5.8, 2.2, 2.3, 2.4**

  - [ ]* 5.10 Write property test for scheduling priority ordering
    - **Property 16: Scheduling Priority Ordering**
    - **Validates: Requirements 5.6**

- [x] 6. Checkpoint - Ensure scheduling engine and tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Conflict Detector
  - [x] 7.1 Implement `ai_schedule/conflict_detector.py` — all conflict types
    - Implement `ConflictDetector.__init__(self, rules)` with loaded rules
    - Implement `detect_all(schedule_entries, rules)`: orchestrate all checks, return list of Conflict objects
    - Implement `_check_machine_port_overlap(entries)`: find pairs on same port with overlapping time
    - Implement `_check_dryer_capacity(entries, rules)`: find time points where dryer usage exceeds max_concurrent
    - Implement `_check_operator_overlap(entries)`: find same-operator prepare intervals that overlap
    - Implement `_check_production_flow(entries)`: verify dispensing→titration→freeze ordering per batch
    - Implement `_check_base_rule_compliance(entries, rules)`: verify assigned resources are in Base_Rule_Tables
    - Set `conflict_flag=True` and populate `conflict_reason` for each detected conflict
    - _Requirements: 6.3, 6.4, 3.5, 5.1, 5.2, 5.3, 5.8_

  - [x] 7.2 Wire Conflict Detector into `POST /validate` endpoint
    - Implement route handler: accept entry_ids, load entries, run ConflictDetector
    - Return per-entry validation results with valid flag and conflicts array
    - _Requirements: 11.6_

  - [ ]* 7.3 Write property test for conflict detection completeness
    - **Property 10: Conflict Detection Completeness**
    - **Validates: Requirements 6.3**

- [x] 8. Implement Version Management, Confirm Flow, and Audit Trail
  - [x] 8.1 Implement `GET /preview` endpoint with version filtering
    - Query `generated_schedule` by week_code and/or schedule_run_id
    - Support filtering by status, sorting by date/priority
    - Return paginated results with conflict information
    - _Requirements: 11.3, 14.4_

  - [x] 8.2 Implement `PUT /update/{id}` endpoint with re-validation
    - Accept field updates (date, start_time, end_time, machine_port, freeze_dryer, operator)
    - After update, run ConflictDetector on the modified entry
    - Update conflict_flag and conflict_reason accordingly
    - _Requirements: 11.4, 7.3_

  - [x] 8.3 Implement `POST /confirm` endpoint with RDS write and audit logging
    - Implement confirm logic: write approved entries to `DropletSchedule` (official)
    - Support `mode: "all"` (all non-conflict entries) and `mode: "selected"` (specific entry_ids)
    - Handle force_confirm with reason recording
    - Mark confirmed run as 'approved', other same-week runs as 'superseded'
    - Create `AIScheduleAuditLog` entry with schedule_run_id, confirmed_by, entries_count, details (official IDs)
    - Record `confirmed_official_id` linkage in generated_schedule
    - Support rollback: mark status='rollback' + timestamp (no data deletion)
    - _Requirements: 11.5, 7.4, 7.5, 7.6, 14.3, 14.5, 15.1, 15.2, 15.3, 15.4, 15.5_

  - [ ]* 8.4 Write property test for version isolation
    - **Property 11: Version Isolation**
    - **Validates: Requirements 14.3, 14.5**

  - [ ]* 8.5 Write property test for audit trail completeness
    - **Property 14: Audit Trail Completeness**
    - **Validates: Requirements 15.2, 15.3, 15.5**

- [x] 9. Implement Excel Sync Service
  - [x] 9.1 Implement `ai_schedule/excel_sync_service.py` — template finding and sheet operations
    - Implement `ExcelSyncService.__init__()` with EXCEL_PATH constant
    - Implement `_find_closest_template_sheet(wb, target_week)`: find sheets matching `26排程表-wXX` (ignore `(*)` suffix), return closest to target_week
    - Implement `_copy_and_rename_sheet(wb, source_name, target_week)`: copy template, name as `26排程表-w{XX}`
    - Implement `_fill_day_dates(ws, target_week)`: find H column "日期:" separators, fill I column with weekday dates, J column with day names
    - Use openpyxl for .xlsm manipulation (preserve macros with keep_vba=True)
    - _Requirements: 12.4, 12.5, 12.6, 12.10_

  - [x] 9.2 Implement Excel data writing — schedule entries to columns
    - Implement `_fill_day_sections(ws, entries_by_date)`: for each day section between separators, write entries
    - Implement `_map_entry_to_columns(entry)`: map fields to H=滴定機, I=Marker, J=凍乾機台, K=formula, L=數量, M=配藥同仁, N=日期, O=RD時間, P=滴定時間, Q=結束, R=工單, S=Lot, T=備註
    - Implement dynamic row management: insert rows if entries > template rows, delete if fewer
    - Preserve rows 1-98 (statistics area) untouched
    - _Requirements: 12.7, 12.8, 12.9_

  - [x] 9.3 Implement `sync_to_excel()` orchestrator and integrate with confirm flow
    - Implement `sync_to_excel(schedule_entries, target_week)`: open workbook → find template → copy → fill → save
    - Return `SyncResult` with status (success/failed) and error message if applicable
    - Integrate into `POST /confirm` endpoint: call after RDS commit, capture errors without rollback
    - If Excel file doesn't exist or write fails, log error and record sync_status=failed
    - _Requirements: 12.1, 12.2, 12.3, 12.11_

  - [ ]* 9.4 Write property test for Excel sync transaction isolation
    - **Property 12: Excel Sync Transaction Isolation**
    - **Validates: Requirements 12.1, 12.2, 12.3**

  - [ ]* 9.5 Write property test for Excel template row preservation
    - **Property 13: Excel Template Row Preservation**
    - **Validates: Requirements 12.9**

  - [ ]* 9.6 Write property test for Excel column mapping correctness
    - **Property 18: Excel Column Mapping Correctness**
    - **Validates: Requirements 12.7**

- [x] 10. Checkpoint - Ensure backend is complete and all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement AI Advisor and Validation Report
  - [x] 11.1 Implement `ai_schedule/ai_advisor.py` — LLM-based conflict analysis
    - Implement `AIAdvisor.__init__(self, db_session)` with LLM client configuration
    - Implement `get_suggestions(entry_id)`: load entry + conflict info, generate alternative suggestions (machine swap, time shift, operator change)
    - Implement `explain_conflict(conflict)`: produce natural language explanation of conflict cause
    - Implement `get_strategy_recommendations(historical_patterns)`: suggest scheduling strategies based on patterns
    - AI advisor only provides advice; scheduling decisions remain with Scheduling_Engine
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 11.2 Wire AI Advisor into `GET /suggestions/{id}` and `GET /validation-report` endpoints
    - Implement `GET /suggestions/{id}`: call AIAdvisor.get_suggestions(), return suggestions array with confidence scores
    - Implement `GET /validation-report`: call RuleValidator.generate_validation_report(), return latest consistency report
    - _Requirements: 11.7, 11.8_

- [x] 12. Implement Frontend — AI Schedule Preview Page
  - [x] 12.1 Add 'ai-schedule' view to Sidebar and routing
    - Add new `NavItem` in `Sidebar.tsx`: `{ id: 'ai-schedule', label: 'AI 排程分析', sublabel: 'AI Schedule', icon: <Brain/>, group: 'Bead 排程', color: '#9C27B0' }`
    - Update `ViewMode` type to include `'ai-schedule'`
    - Add routing in `App.tsx` to render `AISchedulePreview` component when view is 'ai-schedule'
    - _Requirements: 13.3_

  - [x] 12.2 Create `frontend/components/AISchedulePreview.tsx` — main preview page
    - Implement schedule table with columns: 日期, Marker, 機台, 凍乾機, 操作員, R&D時間, 開始, 結束, 數量, Batch, 工單, 備註, 狀態
    - Red row highlighting for entries with `conflict_flag=true`, show conflict_reason tooltip
    - Version selector dropdown (schedule_run_id list from API)
    - "Generate Schedule" button → calls `POST /generate`
    - "Confirm All" and "Confirm Selected" buttons → calls `POST /confirm`
    - Inline editing for date, time, machine, dryer, operator fields → calls `PUT /update/{id}`
    - Fetch data from `GET /preview` with week_code filter
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 14.4_

  - [x] 12.3 Create `frontend/components/ScheduleConflictPanel.tsx` — conflict details
    - Display conflict_reason in natural language
    - Show AI suggestions from `GET /suggestions/{id}` with confidence scores
    - "Apply Suggestion" button → calls `PUT /update/{id}` with suggested changes, then re-validates
    - _Requirements: 7.2, 8.1, 8.2_

  - [x] 12.4 Create `frontend/components/VersionCompare.tsx` — version comparison
    - Side-by-side display of two schedule versions for same week
    - Highlight added/removed/modified entries with color coding
    - Version selector for each side
    - _Requirements: 14.4_

  - [x] 12.5 Create `frontend/components/RuleAnalysisPanel.tsx` — rule analysis UI
    - "Trigger Analysis" button → calls `POST /analyze-rules`
    - Display analysis summary: markers analyzed, rules created, insufficient data markers
    - Display validation report: passed count, conflicts found, auto-corrected items
    - Show detailed conflict list with base rule references
    - _Requirements: 1.7, 2.7, 11.1, 11.8_

  - [x] 12.6 Create `frontend/services/aiScheduleApi.ts` — API client service
    - Implement typed API functions for all 8 endpoints
    - Type definitions matching backend response shapes
    - Error handling with user-friendly messages
    - _Requirements: 11.1-11.8_

- [x] 13. Checkpoint - Ensure frontend integrates with backend
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Integration wiring and final validation
  - [x] 14.1 Wire complete generate→preview→confirm→excel workflow
    - Verify end-to-end: POST /generate creates entries → GET /preview returns them → POST /confirm writes to DropletSchedule + Excel
    - Ensure ConflictDetector runs both during generation and on manual updates
    - Ensure ExcelSyncService is called after RDS commit with proper error isolation
    - _Requirements: 6.1, 7.4, 12.1, 12.2_

  - [x] 14.2 Ensure system isolation and non-destructive behavior
    - Verify no existing API endpoints are modified
    - Verify no existing database tables are altered
    - Verify Base_Rule_Tables are only read, never written
    - Verify error in ai_schedule module doesn't crash other API routes
    - _Requirements: 13.1, 13.2, 13.4, 13.5, 13.6_

  - [ ]* 14.3 Write integration tests for full workflow
    - Test analyze-rules → generate → preview → update → validate → confirm pipeline
    - Test force_confirm with conflict entries
    - Test rollback mechanism
    - Test Excel sync failure doesn't affect RDS data
    - _Requirements: 6.1, 7.4, 7.5, 12.2, 15.4_

- [x] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (18 total)
- Unit tests validate specific examples and edge cases
- The `hypothesis` library is used for property-based testing (Python)
- Backend uses Flask + SQLAlchemy + OR-Tools CP-SAT (matching existing project patterns)
- Frontend uses React + TypeScript with Tailwind CSS (matching existing project patterns)
- All new tables are in `P01_formualte_schedule` schema — no existing tables modified
- Excel operations use `openpyxl` with `keep_vba=True` for .xlsm macro preservation

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.4"] },
    { "id": 2, "tasks": ["1.3"] },
    { "id": 3, "tasks": ["3.1", "4.1"] },
    { "id": 4, "tasks": ["3.2", "3.4", "4.2", "4.3", "4.4"] },
    { "id": 5, "tasks": ["3.3", "3.5", "3.6", "5.1"] },
    { "id": 6, "tasks": ["5.2"] },
    { "id": 7, "tasks": ["5.3"] },
    { "id": 8, "tasks": ["5.4", "7.1"] },
    { "id": 9, "tasks": ["5.5", "5.6", "5.7", "5.8", "5.9", "5.10", "7.2", "7.3"] },
    { "id": 10, "tasks": ["8.1", "8.2", "9.1"] },
    { "id": 11, "tasks": ["8.3", "9.2"] },
    { "id": 12, "tasks": ["8.4", "8.5", "9.3"] },
    { "id": 13, "tasks": ["9.4", "9.5", "9.6", "11.1"] },
    { "id": 14, "tasks": ["11.2", "12.6"] },
    { "id": 15, "tasks": ["12.1"] },
    { "id": 16, "tasks": ["12.2", "12.3", "12.4", "12.5"] },
    { "id": 17, "tasks": ["14.1", "14.2"] },
    { "id": 18, "tasks": ["14.3"] }
  ]
}
```
