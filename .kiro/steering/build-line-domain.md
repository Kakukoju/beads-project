# Build-Line Domain and System Map

This file is persistent project context. Apply these rules in every session that
touches Tutti production, PC build-lines, RD mobile, batch status, or related
APIs. Do not infer status from `lot_code` when batch-level data is available.

## Batch Build-Line Status

### Domain Invariants

- Build-line status belongs to a **batch**, not a `lot_code`.
- Different `lot_code` values can reference the same d/D/U batch and must show
  the same status.
- Status progression is:
  `未建線 -> 已建線 -> 已改線(1) -> 已改線(2) -> ...`
- A build count of 1 means `已建線`; a count greater than 1 means
  `已改線(count - 1)`.

### Persistence

| Purpose | RDS Table |
|---------|-----------|
| Current state | `panel_production.batch_build_line_status` |
| Audit trail | `panel_production.batch_build_line_history` |

`batch_key` format:

```text
{batch_number}::{classification_type}
```

Example: `2612549Z::bigD_lot`

### Batch Classification

Classification comes from
`panel_production.tutti_work_orders.form_data.wells`:

| Classification | Rule | Batch Field |
|----------------|------|-------------|
| `d_lot` | `reagentName1` starts with lowercase `t` followed by uppercase, for example `tCRE-D` | `batch1` |
| `bigD_lot` | Other `reagentName1` values, for example `ALP-D` or `QGGT-AD` | `batch1` |
| `u_lot` | `reagentName2`, including `-U`, `-AU`, or `-BU` | `batch2` |

Batch numbers are 8 characters. Multi-batch values must be split on whitespace,
or into 8-character chunks when no whitespace exists.

### Status APIs

The APIs are served by `beads-project` on port 3001:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/tutti-production/batch-status?lot_no=X` | All batch statuses for a work order |
| GET | `/api/tutti-production/batch-status/history?batch_key=X` | Audit history for one batch key |
| GET | `/api/tutti-production/batch-status/by-batch?batch_number=X` | Cross-`lot_code` status lookup |

Prefer `/by-batch` when rendering or reconciling status across work orders.

## System Architecture

### Backend Services

| Port | Project | Path | Responsibility | nginx Proxy |
|------|---------|------|----------------|-------------|
| 3001 | beads-project | `/home/ubuntu/beads-project` | Flask MRP, scheduling, batch status | `/api/` |
| 3201 | qc-web-ipqc | `/home/ubuntu/qc-web-ipqc/server` | Express RD tasks, IPQC, Excel import, SSE | `/qc-web-api/api/` |
| 3000 | pre-assignment | `/home/ubuntu/pre-assignment` | Node PC build-lines backend | `/qc-web-pre-api/` |
| 8200 | tutti-qc-assayprocess | `/home/ubuntu/qc-web-ipqc/tutti-qc-assayprocess/backend` | Python baseline groups, points, production dates | Via port 3201 |

### PC Build-Lines Flow

```text
PC build-lines (/qc-web/pre-assignment/build-lines)
  -> baseline-groups (port 8200 via /api/assayprocess/)
  -> baseline-group detail (port 8200 via /api/assayprocess/)
     -> prod_date: ipqcdrybeads.db, then RDS P01_formualte_schedule fallbacks
  -> fetchRdTaskStatuses (port 3201 via /qc-web-api/)
     -> batch status (port 3001 /api/tutti-production/batch-status/by-batch)
     -> mergeable batches (port 3201 /qc-web-api/)
  -> send RD task:
     POST /qc-web-api/api/v1/pre-assignment/rd-build-line-tasks
```

### RD Mobile Flow

```text
RD mobile (/qc-web/pre-assignment/rd-mobile)
  -> SSE:
     GET /qc-web-api/api/v1/pre-assignment/rd-build-line-events
  -> tasks:
     GET /qc-web-api/api/v1/pre-assignment/rd-build-line-tasks
  -> complete:
     POST .../direct-write or .../save-adjusted-fit
       -> writeBuildLineResult()
          -> SQLite tutti_curves + build_line_history
          -> RDS assay_process_records (baseline_equation)
          -> notifyBatchStatusTransition()
             -> RDS batch_build_line_status
       -> sendPcBuildLineCompletionEvent()
```

The nginx `/qc-web-api/` location must keep `proxy_buffering off` and
`proxy_cache off` so SSE completion events reach the PC immediately.

### Mergeable Batch Rule

- Group key: `drbeadinspection.bead_name + drbeadinspection.sheet_name`.
- Eligible rows require `batch_decision = '可併'` and
  `final_decision = 'Accept'`.
- Building or rebuilding any eligible batch must synchronize status to all
  eligible sibling batches in the group.
- Lookup API:
  `GET /api/v1/pre-assignment/mergeable-batches?batch_number=X`

