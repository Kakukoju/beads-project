# Project Structure

```
beads-project/
├── mrpFlask_5.py           # Main Flask application — all API routes
├── scheduler_api.py        # CP-SAT scheduling engine (constraint solver)
├── qbi_qr_rds_sync.py     # QR lookup table sync (Excel → RDS)
├── app.py                  # Minimal DB connection test endpoint
├── migrate_to_rds.py       # One-time migration script (SQLite → RDS)
│
├── frontend/               # React SPA (submodule)
│   ├── App.tsx             # Root component — view routing, state, API calls
│   ├── index.tsx           # Entry point
│   ├── types.ts            # Shared TypeScript interfaces
│   ├── constants.ts        # App-wide constants
│   ├── components/         # UI components (flat structure)
│   │   ├── BeadResource.tsx       # Resource config modal (holidays, staff, machines)
│   │   ├── BOMCard.tsx            # Beads demand analysis results display
│   │   ├── MatrixBoard.tsx        # 2D schedule visualization (Gantt-style)
│   │   ├── InsertWorkOrder.tsx    # Rush order editing grid
│   │   ├── TuttiProductionGrid.tsx # Work order tracking (AG Grid)
│   │   ├── PanelBOM.tsx           # Panel BOM calculator
│   │   ├── Homepage.tsx           # Dashboard landing page
│   │   ├── Sidebar.tsx            # Navigation sidebar
│   │   └── ...
│   ├── services/           # API service layer (if used)
│   ├── tests/              # Playwright E2E tests
│   ├── dist/               # Production build output
│   ├── vite.config.ts      # Vite configuration
│   ├── tailwind.config.js  # Tailwind configuration
│   └── package.json        # Frontend dependencies
│
├── excelData/              # Uploaded Excel workbooks (VBA source)
│   ├── beads_inventory.xlsm
│   ├── production_plan.xlsm
│   ├── panel_detail.xlsm
│   ├── schedule_limit.xlsm
│   └── titration_limit.xlsm
│
├── exports/                # Generated schedule Excel exports
├── outputs/                # Intermediate calculation outputs
├── calculation/            # (Reserved for calculation scripts)
├── temp/                   # Temporary files and logs
│
├── venv/                   # Python virtual environment
├── .env.production         # Production environment config
├── .gitignore
└── .gitmodules             # frontend/ is a git submodule
```

## Architecture Pattern

- **Monolithic backend**: Single Flask app (`mrpFlask_5.py`) serves all API routes
- **Modular solver**: Scheduling logic isolated in `scheduler_api.py`, imported and reloaded at startup
- **SPA frontend**: React app served separately (Vite dev / static build), communicates via REST
- **Excel-driven data pipeline**: Shop floor Excel → VBA upload → Flask sync → PostgreSQL → Frontend display

## Key Conventions

- Frontend components are flat (no nested folders), located in `frontend/components/`
- Backend uses raw SQL (`text()`) rather than ORM models for most queries
- Table and column names often use Chinese characters (e.g., `"配藥限制"`, `"限制OR插單"`)
- The `frontend/` directory is a git submodule with its own repository
- Path alias `@/` maps to the frontend root directory
