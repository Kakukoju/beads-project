# Tech Stack & Build System

## Backend (Python / Flask)

- **Runtime**: Python 3.12
- **Framework**: Flask with Flask-CORS and Flask-SQLAlchemy
- **Database**: PostgreSQL on AWS RDS (`beadsdb`)
  - Schemas: `schedule`, `panel_production`, `qbi_qr`, `public`
  - ORM: SQLAlchemy (primarily raw SQL via `text()`)
- **Scheduling Engine**: Google OR-Tools CP-SAT constraint programming solver (`scheduler_api.py`)
- **Data Processing**: pandas, openpyxl
- **File Watching**: watchdog (for Excel file auto-sync)
- **Production Server**: Gunicorn (port 3001)
- **Deployment**: AWS EC2 (Ubuntu), direct process management

## Frontend (React / TypeScript)

- **Framework**: React 19 with TypeScript 5.8
- **Build Tool**: Vite 6
- **Styling**: Tailwind CSS 4 with PostCSS
- **Data Grid**: AG Grid Community (v32)
- **Icons**: Lucide React
- **AI Integration**: Google Generative AI (Gemini) — client-side API calls
- **Excel Export**: xlsx / xlsx-js-style
- **QR Codes**: qrcode.react
- **Testing**: Playwright (E2E)

## Common Commands

### Frontend
```bash
cd frontend
npm run dev        # Start dev server on port 3000
npm run build      # Production build to dist/
npm run preview    # Preview production build
```

### Backend
```bash
# Activate virtualenv
source venv/bin/activate

# Run development server
python mrpFlask_5.py  # Starts on port 3001

# Production (Gunicorn)
gunicorn -b 0.0.0.0:3001 mrpFlask_5:app
```

### Testing
```bash
cd frontend
npx playwright test   # Run E2E tests
```

## API Communication

- Frontend → Backend: REST API at `API_BASE` (default `http://localhost:3001`, production via sslip.io reverse proxy)
- All API routes prefixed with `/api/`
- Backend → Database: SQLAlchemy engine with connection pooling (`pool_pre_ping`, `pool_recycle=300`)

## Key Environment Variables

- `VITE_API_URL` — Backend API URL for frontend (set in `.env.production`)
- `GEMINI_API_KEY` — Google AI API key (exposed to frontend via Vite define)
- `UPLOAD_API_KEY` — API key for VBA Excel upload endpoint (default: `beadsops-upload-key`)
- `QBI_QR_EXCEL_PATH` — Path to Qbi QR lookup workbook
- `QBI_QR_WATCH_ENABLED` — Enable/disable file watcher (`1`/`0`)
