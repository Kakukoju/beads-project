# Product Overview

MRP Intelligence Engine — an internal manufacturing planning tool for a biomedical/veterinary diagnostics company (SkyLai Cloud / Qbi). The system manages bead reagent production scheduling, inventory tracking, and material requirements planning (MRP).

## Core Capabilities

- **Beads Demand Analysis**: Calculates weekly bead reagent needs based on production plans, safety stock levels, and current inventory
- **Production Scheduling (滴定排程)**: Uses OR-Tools CP-SAT constraint solver to optimally assign titration/freeze-dry jobs across machines, ports, staff, and time slots
- **Excel ↔ RDS Sync**: Ingests Excel workbooks (uploaded via VBA macros from shop floor) into PostgreSQL for centralized data access
- **Rush Order Management (插單)**: Supports forced/pinned scheduling for urgent orders with fixed time slots and machine assignments
- **Tutti Production Records**: Work order tracking with QR-based lot management
- **Panel BOM Management**: Bill-of-materials breakdown for reagent panels

## Domain Context

- The product is used by a production planning team in Taiwan (UI is bilingual Chinese/English)
- "Beads" refers to freeze-dried reagent beads used in veterinary diagnostic panels
- "Markers" are specific reagent types (e.g., ALB, GGT, tCREA) identified by 10-digit part numbers (PN)
- "Titration" (滴定) is the liquid dispensing step before freeze-drying
- Scheduling must respect complex constraints: machine compatibility, staff availability, reagent pairing rules, contamination avoidance, and IVEK dispensing requirements
