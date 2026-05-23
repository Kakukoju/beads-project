# Implementation Plan: Tutti Production Tab

## Overview

This plan implements the "Tutti-Beads 預建線 . 工單" tab feature across three layers: database schema creation, Flask backend CRUD endpoints, and a React + AG Grid frontend component. Each task builds incrementally, starting with the data layer and ending with full integration and wiring.

## Tasks

- [x] 1. Set up database schema and backend CRUD endpoints
  - [x] 1.1 Create database schema and table via Flask initialization
    - Add `panel_production` to the SQLAlchemy `search_path` in `mrpFlask_5.py` engine options
    - Add a schema/table creation route or startup logic that creates `panel_production` schema and `tutti_production` table with all columns, constraints, and defaults as specified in the design
    - Include CHECK constraint on `well_position` (1-10), DEFAULT 0 for `defect_quantity` and `qa_inspection`, DEFAULT NOW() for timestamps
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 1.2 Implement GET endpoint for tutti production records
    - Add `GET /api/tutti-production` route to `mrpFlask_5.py`
    - Return all rows from `panel_production.tutti_production` ordered by `created_at` DESC as JSON array
    - Support optional `work_order` query parameter to filter by `work_order_number`
    - _Requirements: 3.1, 3.2_

  - [x] 1.3 Implement POST endpoint for creating records
    - Add `POST /api/tutti-production` route to `mrpFlask_5.py`
    - Validate required fields (`lot_no`, `work_order_number`); return 400 if missing
    - Calculate `storage_quantity` as `production_quantity - defect_quantity - qa_inspection` when `production_quantity` is provided
    - Insert row and return the created record with generated `id`
    - _Requirements: 3.3, 3.7, 6.1, 6.2_

  - [x] 1.4 Implement PUT endpoint for updating records
    - Add `PUT /api/tutti-production/<id>` route to `mrpFlask_5.py`
    - Return 404 if record not found
    - Update only provided fields, set `updated_at` to current timestamp
    - Recalculate `storage_quantity` if any of the three source fields changed
    - Return the updated record
    - _Requirements: 3.4, 3.6, 6.1, 6.2_

  - [x] 1.5 Implement DELETE endpoint for removing records
    - Add `DELETE /api/tutti-production/<id>` route to `mrpFlask_5.py`
    - Return 404 if record not found
    - Delete the row and return success confirmation
    - _Requirements: 3.5, 3.6_

  - [ ]* 1.6 Write property tests for backend CRUD (Hypothesis)
    - **Property 1: Ordering Invariant** — Generate random records, verify GET returns them ordered by `created_at` DESC
    - **Property 2: Filter Correctness** — Generate records with varied `work_order_number`, verify filter returns exact matches
    - **Property 3: Create Round-Trip** — Generate valid record data, POST then GET by id, verify field equality
    - **Property 4: Update Correctness** — Create record, generate partial updates, verify updated fields and preserved non-updated fields
    - **Property 5: Delete Removes Record** — Create then delete, verify absence in subsequent GET
    - **Property 6: Storage Quantity Calculation** — Generate random P/D/Q values, verify `storage_quantity = P - D - Q`
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 6.1, 6.2**

- [x] 2. Checkpoint - Backend verification
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Create frontend API layer and TypeScript interfaces
  - [x] 3.1 Define TypeScript interface for TuttiProductionRecord
    - Create `frontend/services/tuttiApi.ts` (or `frontend/src/api/tutti.ts` depending on project convention)
    - Define `TuttiProductionRecord` interface with all 26 fields matching the database schema
    - _Requirements: 4.1_

  - [x] 3.2 Implement API functions for CRUD operations
    - Implement `fetchTuttiProduction(workOrder?: string)` — GET with optional filter
    - Implement `createTuttiProduction(data)` — POST new record
    - Implement `updateTuttiProduction(id, data)` — PUT partial update
    - Implement `deleteTuttiProduction(id)` — DELETE record
    - Use the existing `API_BASE` pattern from `App.tsx`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 4. Implement TuttiProductionGrid component
  - [x] 4.1 Create TuttiProductionGrid component with AG Grid setup
    - Create `frontend/components/TuttiProductionGrid.tsx`
    - Import AG Grid Community modules (`ClientSideRowModelModule`, `@ag-grid-community/react`, styles)
    - Set up AG Grid with column definitions organized into four column groups: "工單資訊", "填充/熔接製程", "生產記錄", "後製程"
    - Configure all columns with Chinese headers, editable flags, and appropriate widths
    - Mark `storage_quantity`, `id`, `created_at`, `updated_at` as read-only
    - Include checkbox selection column
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.5, 5.6_

  - [x] 4.2 Implement data fetching and loading state
    - Fetch data from `/api/tutti-production` on component mount
    - Display loading indicator while data is being fetched
    - Handle empty state with "無資料" message
    - _Requirements: 10.1, 10.4_

  - [x] 4.3 Implement inline editing with auto-save
    - Handle `onCellValueChanged` event to trigger PUT request with updated field
    - On success, update the row data (including recalculated `storage_quantity`)
    - On failure, revert cell to previous value and show error toast notification
    - Compute `storage_quantity` optimistically on the frontend for immediate UI feedback
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.3_

  - [x] 4.4 Implement toolbar with Add, Delete, Refresh, and Filter
    - Add "新增" button that inserts a new empty row at the top with defaults
    - Add "刪除" button that deletes selected rows after confirmation dialog
    - Add "重新整理" button that re-fetches all data
    - Add work order filter input with Enter key trigger and record count display
    - Handle POST on new row when required fields are filled; remove row if validation fails
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.2, 9.3, 9.4, 10.2, 10.3_

  - [ ]* 4.5 Write unit tests for TuttiProductionGrid component
    - Test column group configuration and header names
    - Test toolbar button rendering and click handlers
    - Test error notification display and auto-dismiss
    - Test cell revert on failed save
    - _Requirements: 4.2, 4.7, 5.4, 7.1, 8.2_

- [x] 5. Integrate Tutti tab into App.tsx navigation
  - [x] 5.1 Extend viewMode state and add navigation button
    - Extend `viewMode` type to `'analysis' | 'board' | 'tutti'`
    - Add "Tutti-Beads 預建線 . 工單" button to the navigation bar after "執行看板"
    - Persist `viewMode` to localStorage (existing pattern)
    - Conditionally render `<TuttiProductionGrid />` when `viewMode === 'tutti'`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 5.2 Write unit tests for navigation integration
    - Test tab button renders in correct position
    - Test click switches viewMode to 'tutti'
    - Test localStorage persistence of 'tutti' viewMode
    - Test TuttiProductionGrid renders when viewMode is 'tutti'
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 6. Final checkpoint - Full integration verification
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The backend uses Python (Flask + SQLAlchemy) and the frontend uses TypeScript (React + AG Grid Community)
- AG Grid packages are already installed in the frontend project

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5"] },
    { "id": 2, "tasks": ["1.6", "3.1"] },
    { "id": 3, "tasks": ["3.2"] },
    { "id": 4, "tasks": ["4.1"] },
    { "id": 5, "tasks": ["4.2", "4.3", "4.4"] },
    { "id": 6, "tasks": ["4.5", "5.1"] },
    { "id": 7, "tasks": ["5.2"] }
  ]
}
```
