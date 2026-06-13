# Project Structure

## Multi-System Architecture

This project is part of a **multi-backend ecosystem**. Four services collaborate to deliver the Tutti Beads Pre-Assignment and build-line workflow.

### Backend Services

| Port | Project | Path on Disk | Tech | nginx Proxy | Role |
|------|---------|--------------|------|-------------|------|
| 3001 | beads-project | `/home/ubuntu/beads-project` | Python Flask | `/api/`, `/iot/` | MRP, scheduling, batch_build_line_status |
| 3201 | qc-web-ipqc | `/home/ubuntu/qc-web-ipqc/server` | Node Express | `/qc-web-api/api/` | IPQC, RD build-line tasks, Excel import, SSE events |
| 3000 | pre-assignment | `/home/ubuntu/pre-assignment` | Node (compiled TS) | `/qc-web-pre-api/` | Build-line candidate service, work order scan |
| 8200 | tutti-qc-assayprocess | `/home/ubuntu/qc-web-ipqc/tutti-qc-assayprocess/backend` | Python (Flask/FastAPI) | via port 3201 proxy | Baseline groups, baseline-points, prod_date lookup |

### Frontend SPAs

| URL Path | Served From | Project | Role |
|----------|-------------|---------|------|
| `/` | `beads-project/frontend/dist` | beads-project | MRP 排程 dashboard |
| `/qc-web/pre-assignment/` | `pre-assignment/pc/dist` | pre-assignment/pc | PC build-lines 建線管理 |
| `/qc-web/pre-assignment/rd-mobile` | `qc-web-ipqc/dist/rd-mobile.html` | qc-web-ipqc | RD 手機建線任務 |
| `/qc-web/` | `qc-web-ipqc/dist` | qc-web-ipqc | IPQC 管理 + Tutti monitor |

### Key Databases

| DB | Type | Location / Host | Key Tables |
|----|------|----------------|------------|
| beadsdb | PostgreSQL RDS | `database-1.cfutwrwyrxts.ap-northeast-1.rds.amazonaws.com` | `panel_production.*`, `schedule.*`, `P01_formualte_schedule.*`, `work_orders.*` |
| ipqcdrybeads.db | SQLite | `/home/ubuntu/ipqcdrybeads.db` | `drbeadinspection`, `tutti_curves`, `build_line_history`, `rd_build_line_tasks`, `rd_whitelist` |
| Tutti_QC_assayprocess.db | SQLite | `/home/ubuntu/qc-web-ipqc/tutti-qc-assayprocess/data/` | `assay_process_records` (baseline=true/false) |
| bead_ipqc_spec.db | SQLite | `/home/ubuntu/bead_ipqc_spec.db` | `csassign` (concentration specs per marker) |
| P01_formualte_schedule.db | SQLite (cache) | `/opt/beadsops/data/` | `schedule_cache` (remote sync from RDS) |

### Data Flow: Build-Line Status

```
PC build-lines → POST /qc-web-api/.../rd-build-line-tasks → qc-web-ipqc (SQLite)
    → SSE push → RD mobile receives task
    → RD completes → writeBuildLineResult()
        → SQLite: tutti_curves + build_line_history
        → RDS: assay_process_records.baseline_equation
        → RDS: batch_build_line_status (跨 lot_code 同步)
        → SSE push → PC receives completion notice
```

### Data Flow: 生產日 (prod_date) Lookup

```
baseline_service.py (port 8200):
  1. Extract batch lots from work order form_data (split multi-batch values by 8 chars)
  2. Query ipqcdrybeads.db → drbeadinspection (d_lot/bigD_lot/u_lot + d_prod_date/bigD_prod_date/u_prod_date)
  3. Fallback: RDS → P01_formualte_schedule.dropletRecord / DropletSchedule
  4. Fallback: RDS → work_orders.work_orders (日期)
  5. Result: date string, "(沒ipqc資料)", or "no data"
```

### Batch Classification Rule

Source: `panel_production.tutti_work_orders.form_data.wells.{L1,L2,...}[].{reagentName1, batch1, reagentName2, batch2}`

| Classification | Condition | Field |
|---------------|-----------|-------|
| `d_lot` (小寫) | `reagentName1` starts with lowercase `t` + uppercase (e.g., `tCRE-D`) | `batch1` |
| `bigD_lot` (大寫) | `reagentName1` does NOT start with lowercase `t` | `batch1` |
| `u_lot` (U) | `reagentName2` (any suffix: -U, -AU, -BU) | `batch2` |

### Mergeable Batches (可併批次)

- Group identified by: `drbeadinspection.bead_name` + `drbeadinspection.sheet_name`
- Condition: `batch_decision = '可併'` AND `final_decision = 'Accept'`
- Rule: 任一可併批次建線/改線 → 同 group 所有可併批次 status 一致
- API: `GET /qc-web-api/api/v1/pre-assignment/mergeable-batches?batch_number=X`

### nginx Config

File: `/etc/nginx/sites-enabled/beadsops`
- `/qc-web-api/` → port 3201 (proxy_buffering off for SSE)
- `/qc-web-pre-api/` → port 3000
- `/api/` → port 3001
- `/iot/` → port 3001
- `/qc-web/pre-assignment/rd-mobile` → qc-web-ipqc/dist/rd-mobile.html
- `/qc-web/pre-assignment/` → pre-assignment/pc/dist/
- `/qc-web/` → qc-web-ipqc/dist/

### Restart Commands

```bash
# beads-project (Flask/gunicorn)
kill -HUP $(pgrep -f "gunicorn.*mrpFlask_5" | head -1)

# qc-web-ipqc (Node Express)
kill $(pgrep -f "node.*qc-web-ipqc/server/index.js"); sleep 1
node /home/ubuntu/qc-web-ipqc/server/index.js &

# pre-assignment backend (Node compiled TS)
kill $(fuser 3000/tcp 2>/dev/null); sleep 1
node /home/ubuntu/pre-assignment/dist/server.js &

# tutti-qc-assayprocess (Python)
kill $(fuser 8200/tcp 2>/dev/null); sleep 1
/home/ubuntu/qc-web-ipqc/tutti-qc-assayprocess/backend/.venv/bin/python3 \
  /home/ubuntu/qc-web-ipqc/tutti-qc-assayprocess/backend/app.py &

# Frontend builds
cd /home/ubuntu/beads-project/frontend && npm run build
cd /home/ubuntu/pre-assignment/pc && npm run build
cd /home/ubuntu/qc-web-ipqc && npm run build

# nginx reload
sudo nginx -t && sudo systemctl reload nginx
```

---

## beads-project Internal Structure

```
beads-project/
├── mrpFlask_5.py           # Main Flask application — all API routes
├── scheduler_api.py        # CP-SAT scheduling engine (constraint solver)
├── qbi_qr_rds_sync.py     # QR lookup table sync (Excel → RDS)
├── app.py                  # Minimal DB connection test endpoint
├── migrate_to_rds.py       # One-time migration script (SQLite → RDS)
│
├── ai_schedule/            # AI scheduling module (blueprint)
│   ├── routes.py           # /api/ai-schedule/* endpoints
│   ├── scheduling_engine.py
│   ├── conflict_detector.py
│   ├── rule_analyzer.py
│   ├── excel_sync_service.py
│   └── models.py
│
├── frontend/               # React SPA (submodule)
│   ├── App.tsx             # Root component — view routing, state, API calls
│   ├── components/         # UI components (flat structure)
│   │   ├── TuttiProductionGrid.tsx  # Work order tracking + 建線狀態 display
│   │   ├── BatchStatusBadge.tsx     # 建線 status color badge
│   │   ├── BatchHistoryModal.tsx    # Status transition history modal
│   │   ├── MatrixBoard.tsx          # 2D schedule visualization
│   │   └── ...
│   ├── services/
│   │   ├── aiScheduleApi.ts         # AI schedule API client
│   │   └── batchBuildLineStatus.ts  # Batch status API client
│   └── ...
│
├── excelData/              # Uploaded Excel workbooks (VBA source)
├── exports/                # Generated schedule Excel exports
└── tests/                  # pytest tests
```

## Key Conventions

- Frontend components are flat (no nested folders), located in `frontend/components/`
- Backend uses raw SQL (`text()`) rather than ORM models for most queries
- Table and column names often use Chinese characters (e.g., `"配藥限制"`, `"限制OR插單"`)
- The `frontend/` directory is a git submodule with its own repository
- Path alias `@/` maps to the frontend root directory
- Batch numbers are always **8 characters** (e.g., `2612549Z`, `2312614W`)
- Multi-batch values in work order wells should be split by whitespace or every 8 chars
