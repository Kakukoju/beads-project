# Project Instructions

## Engineering Guidelines

Before making non-trivial changes involving data, scheduling, inventory, APIs,
databases, UI workflows, permissions, calculations, Excel files, or reports,
read and apply:

- `.kiro/steering/karpathy-guidelines.md`

In short: understand first, make the smallest relevant change, preserve existing
contracts and formats, reproduce bugs before fixing them, and verify the result.
State assumptions and unverified areas instead of presenting guesses as facts.

## Persistent Build-Line Context

Before changing Tutti production, PC build-lines, RD mobile, batch status,
baseline, production-date lookup, SSE, or related APIs, read and apply:

- `.kiro/steering/build-line-domain.md`
- `.kiro/steering/structure.md`

The first file is the canonical source for batch build-line status semantics and
the four-backend workflow. Keep it updated when those contracts change.

Critical invariants:

- Build-line status is keyed by batch and classification, not by `lot_code`.
- Shared batches across work orders must display one consistent status.
- The status sequence is
  `未建線 -> 已建線 -> 已改線(1) -> 已改線(2) -> ...`.
- Cross-work-order reads use the `/batch-status/by-batch` API.
- Mergeable, accepted batches in the same IPQC group synchronize status.
- `/qc-web-api/` must not buffer or cache SSE responses.

