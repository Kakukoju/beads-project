# Tech Stack

## Core
- React 18 with TypeScript (strict mode)
- Vite 7 (dev server on port 5174)
- Tailwind CSS 3 with `tailwindcss-animate` plugin
- shadcn/ui (new-york style, CSS variables, no RSC)

## Key Libraries
- recharts — bar charts, line charts, tooltips
- @nivo/heatmap — heatmap visualizations
- lucide-react — icons
- class-variance-authority (cva) — component variants
- clsx + tailwind-merge — className composition via `cn()` utility
- socket.io-client — real-time WebSocket connections
- axios — HTTP client (though most code uses native `fetch`)

## Path Aliases
- `@/*` maps to `src/*` (configured in tsconfig.json and vite)

## Build & Dev Commands
- `npm run dev` — start Vite dev server (port 5174)
- `npm run build` — `tsc && vite build` (type-check then bundle)
- `npm run preview` — preview production build

## Backend Integration
The frontend proxies API calls to multiple Python backend services:
- Port 5100 — Ops, abnormal monitoring, titration status, mobile API
- Port 5011 — Droplet/titration condition records
- Port 8505 — Scheduling, forms, work orders, IPQC, WIP, dashboard data

API base URL is configurable via `VITE_API_BASE` env var (defaults to empty string for proxy).

## TypeScript Config
- Target: ES2020, strict mode enabled
- `noUnusedLocals` and `noUnusedParameters` are on
- Module resolution: bundler
