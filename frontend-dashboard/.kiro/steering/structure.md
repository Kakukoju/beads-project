# Project Structure

```
src/
├── main.tsx                  # React entry point (StrictMode)
├── App.tsx                   # Main app shell — tab navigation + dashboard views
│                               Contains inline sub-views (DashboardView, DispatchView, etc.)
│                               and mock data constants
├── index.css                 # Global styles, Tailwind directives, dark theme defaults
├── type.ts                   # Shared TypeScript types (titration, pumps, IVEK)
├── types/
│   └── ops.ts                # Domain types for freeze-dryer, resources, API responses
├── lib/
│   ├── api.ts                # API_BASE constant from env
│   └── utils.ts              # cn() utility (clsx + tailwind-merge)
├── components/
│   ├── ui/                   # Reusable UI primitives (shadcn/ui style)
│   │   ├── Card.tsx          # Base card with glass-morphism styling
│   │   └── badge.tsx         # Badge component using cva variants
│   ├── utils/
│   │   └── percent.ts        # Percentage normalization helper
│   ├── FreezeDryerCard.tsx   # Freeze-dryer monitoring grid
│   ├── TitrationIvekCard.tsx # Titration pump/IVEK status
│   ├── AbnormalMonitorCard.tsx
│   ├── BeadsYield.tsx        # Production yield stats
│   ├── DropletCondition.tsx  # Titration condition table
│   ├── HeatmapChart.tsx      # Nivo heatmap wrapper
│   ├── TitrationStatistic.tsx
│   ├── ProductionQueryView.tsx
│   ├── LowYieldModal.tsx
│   └── ...
├── BeadsIPQCPage.tsx         # IPQC data page (top-level)
├── TimetableView.tsx         # Schedule timetable (top-level)
└── vite-env.d.ts
```

## Conventions
- Top-level page components live directly in `src/` (e.g., `BeadsIPQCPage.tsx`)
- Feature components live in `src/components/`
- Shared UI primitives go in `src/components/ui/` (shadcn/ui pattern)
- Utility functions go in `src/lib/` or `src/components/utils/`
- Type definitions are split between `src/type.ts` and `src/types/` folder
- Components use default exports; UI primitives use named exports
- Data fetching is done inline with `useEffect` + `fetch` + polling via `setInterval`
- No routing library — navigation is tab-based state managed in App.tsx
- `_backup` / `_back` / `_main` suffixed files are legacy snapshots (do not modify)
