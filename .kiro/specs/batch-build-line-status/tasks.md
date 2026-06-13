# Implementation Plan: Batch Build-Line Status

## Overview

This implementation plan covers the full-stack development of batch-level 建線 status tracking for the Tutti Beads Pre-Assignment system. The work spans database schema creation, backend classifier and transition logic, REST API endpoints, and React frontend components integrated into the existing TuttiProductionGrid.

## Tasks

- [x] 1. Database Schema Setup
  - [x] 1.1 Create `panel_production.batch_build_line_status` table
    - Columns: id, batch_key (UNIQUE), classification, batch_number, status, modification_count, last_transition_at, last_operator, created_at, updated_at
    - _Requirements: 2.1_

  - [x] 1.2 Create `panel_production.batch_build_line_history` table
    - Columns: id, batch_key, previous_status, new_status, modification_count, transitioned_at, operator, work_order_no, lot_no, created_at
    - _Requirements: 2.5, 2.6, 6.1, 6.2_

  - [x] 1.3 Create indexes for performance
    - `idx_batch_status_key`, `idx_batch_status_batch_number`, `idx_batch_history_key`
    - _Requirements: 3.1_

  - [x] 1.4 Add table initialization to `mrpFlask_5.py` startup
    - Use `CREATE TABLE IF NOT EXISTS` pattern consistent with existing tables
    - _Requirements: 2.1_

- [x] 2. Batch Classifier Implementation
  - [x] 2.1 Implement `classify_batch` function
    - Implement `classify_batch(reagent_name1, batch1, reagent_name2, batch2)` in `mrpFlask_5.py`
    - Returns list of `{batch_key, classification, batch_number}` dicts
    - Classification logic: reagentName1 starting with lowercase `t` (followed by uppercase) → `d_lot`; otherwise → `bigD_lot`; reagentName2 → always `u_lot`
    - Batch_Key format: `{batch_number}::{classification_type}`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x]* 2.2 Write property test for classify_batch determinism
    - **Property 1: Batch Classification Determinism**
    - **Validates: Requirements 1.4, 1.5**

  - [x]* 2.3 Write property test for classification partition completeness
    - **Property 2: Classification Partition Completeness**
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [x]* 2.4 Write property test for lowercase t detection rule
    - **Property 6: Classification Rule — lowercase t detection**
    - **Validates: Requirements 1.1, 1.2**

- [x] 3. Status Transition Logic
  - [x] 3.1 Implement `transition_batch_status` function
    - Implement `transition_batch_status(batch_key, classification, batch_number, operator, work_order_no, lot_no)`
    - Handle first transition: no existing record → INSERT with status "已建線", modification_count=0
    - Handle subsequent transitions: existing record → UPDATE to "已改線(n)" with incremented modification_count
    - Write history record on every transition
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x]* 3.2 Write property test for state machine correctness
    - **Property 3: Status Transition State Machine**
    - **Validates: Requirements 2.3, 2.4**

  - [x]* 3.3 Write property test for history count matches transitions
    - **Property 4: History Count Matches Transitions**
    - **Validates: Requirements 6.1, 6.2**

- [x] 4. Checkpoint - Verify core backend logic
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Modify confirm-build-line Endpoint
  - [x] 5.1 Extract Batch_Keys from well assignments after successful dispatch
    - After successful panel_dispatch and baseline record creation, extract all Batch_Keys using `classify_batch`
    - Deduplicate Batch_Keys across all panels in the request
    - _Requirements: 4.1_

  - [x] 5.2 Call `transition_batch_status` for each unique Batch_Key
    - Handle status transition errors gracefully (log error, continue with remaining keys, do not rollback dispatch)
    - _Requirements: 4.2, 4.3, 4.4_

  - [x] 5.3 Include `status_transitions` array in success response
    - Show which batch_keys were transitioned and their new statuses
    - _Requirements: 4.1_

- [x] 6. Status Query API
  - [x] 6.1 Implement `GET /api/tutti-production/batch-status` endpoint
    - Accept `lot_no` or `work_order_no` query parameter
    - Look up work order from `tutti_work_orders`
    - Parse `form_data.wells` to extract reagentName1/batch1/reagentName2/batch2 combinations
    - Run `classify_batch` on each well to determine all Batch_Keys
    - _Requirements: 3.1, 3.2_

  - [x] 6.2 Query and return batch status data
    - Query `batch_build_line_status` for each Batch_Key (default to "未建線" if no record)
    - Return response with batches array including status, modification_count, analyze_items, last_transition_at, last_operator
    - Return 404 for non-existent work orders, 400 for missing parameters
    - _Requirements: 3.2, 3.3, 3.4_

  - [x]* 6.3 Write property test for batch consistency across lot_codes
    - **Property 5: Batch Consistency Across Lot Codes**
    - **Validates: Requirements 3.3, 5.5**

- [x] 7. History Query API
  - [x] 7.1 Implement `GET /api/tutti-production/batch-status/history` endpoint
    - Accept `batch_key` query parameter
    - Query `batch_build_line_history` ordered by transitioned_at DESC
    - Return history array with previous_status, new_status, transitioned_at, operator, work_order_no, lot_no
    - Return empty history array with current_status "未建線" for batch_keys with no records
    - Return 400 for missing batch_key parameter
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 8. Checkpoint - Verify all backend endpoints
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Frontend API Layer
  - [x] 9.1 Create `frontend/services/batchBuildLineStatus.ts`
    - Implement `fetchBatchStatuses(lotNo: string)` and `fetchBatchHistory(batchKey: string)` functions
    - Define TypeScript interfaces: `BatchStatus`, `BatchHistoryEntry`
    - Handle error responses (404, 400, 500) with appropriate fallback values
    - _Requirements: 5.1, 5.6_

- [x] 10. Frontend BatchStatusBadge Component
  - [x] 10.1 Create `frontend/components/BatchStatusBadge.tsx`
    - Implement color mapping: gray for "未建線", green for "已建線", orange for "已改線(n)"
    - Show classification prefix label (d / D / U)
    - Add click handler with cursor pointer styling for opening history
    - Style with Tailwind CSS consistent with project's dark theme
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 11. Frontend BatchHistoryModal Component
  - [x] 11.1 Create `frontend/components/BatchHistoryModal.tsx`
    - Display batch_key header, current status badge, and classification label
    - Render timeline of transitions (newest first) with timestamp, operator, work_order_no
    - Handle loading and error states
    - Add close button and backdrop click-to-dismiss
    - _Requirements: 6.4_

- [x] 12. Integrate Status Display into TuttiProductionGrid
  - [x] 12.1 Add "建線狀態" column group to grid
    - Add sub-columns for d/D batch and U batch
    - Implement custom cell renderer using `BatchStatusBadge`
    - _Requirements: 5.1_

  - [x] 12.2 Fetch and wire batch status data
    - Fetch batch statuses on grid data load (per lot_no)
    - Wire badge click → open `BatchHistoryModal` with correct batch_key
    - Handle case where lot_no has no batch data (show "—" placeholder)
    - _Requirements: 5.5, 5.6_

  - [x] 12.3 Refresh statuses after confirm-build-line
    - After confirm-build-line success, refetch batch statuses to update badges without page reload
    - _Requirements: 5.6_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The implementation uses Python (Flask) for backend and TypeScript (React) for frontend, matching the existing project stack
- Status transition errors during confirm-build-line are non-blocking — core dispatch always succeeds

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3"] },
    { "id": 4, "tasks": ["5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3"] },
    { "id": 6, "tasks": ["6.1", "7.1"] },
    { "id": 7, "tasks": ["6.2", "6.3"] },
    { "id": 8, "tasks": ["9.1"] },
    { "id": 9, "tasks": ["10.1", "11.1"] },
    { "id": 10, "tasks": ["12.1"] },
    { "id": 11, "tasks": ["12.2", "12.3"] }
  ]
}
```
