# Requirements Document

## Introduction

This feature implements **建線 status tracking at the analyze_item batch level** for the Tutti Beads Pre-Assignment system. Currently, "Confirm Build Line" creates `panel_dispatch` and baseline `assay_process_records`, but there is no structured status tracking that groups analyze items by their batch classification (d_lot, bigD_lot, u_lot). This feature ensures that all lot_codes sharing the same analyze_item batch display a consistent 建線 status, and that status transitions (未建線 → 已建線 → 已改線(n)) are tracked with a modification counter.

## Glossary

- **Build_Line_Status_Service**: The backend service responsible for determining, storing, and returning the 建線 status for each analyze_item batch
- **Batch_Classifier**: The logic module that classifies a well's reagents into d_lot (batch1 from reagentName1 starting with lowercase `t`), bigD_lot (batch1 from reagentName1 NOT starting with lowercase `t`), or u_lot (batch2 from reagentName2)
- **Batch_Key**: A unique identifier for a specific analyze_item batch, composed of the batch number combined with its classification type (d_lot, bigD_lot, or u_lot)
- **Status_Tracker**: The database table and associated logic that persists 建線 status transitions and modification counts per Batch_Key
- **Frontend_Status_Display**: The React UI component responsible for rendering the 建線 status consistently across all lot_codes that share a Batch_Key
- **Analyze_Item**: A specific reagent marker (e.g., ALB, GGT, CRE) derived from reagentName after removing suffixes and prefixes per the mapping rules
- **Lot_Code**: A 12-digit disc-level identifier in format `{LineNumber}{SubPanelType}{YYMMDDBB}`
- **Batch_Number**: The value in `batch1` or `batch2` fields from the work order's well data, representing the physical reagent lot used
- **Modification_Count**: An integer counter starting at 0 (未建線), set to 0 on first build (已建線), incremented by 1 on each subsequent line modification (已改線(n))

## Requirements

### Requirement 1: Batch Classification

**User Story:** As a production operator, I want the system to correctly classify each well's reagent batches into d_lot, bigD_lot, or u_lot categories, so that 建線 status is tracked at the correct batch granularity.

#### Acceptance Criteria

1. WHEN a well's `reagentName1` starts with lowercase `t`, THE Batch_Classifier SHALL classify `batch1` as d_lot
2. WHEN a well's `reagentName1` does NOT start with lowercase `t`, THE Batch_Classifier SHALL classify `batch1` as bigD_lot
3. WHEN a well has a non-empty `reagentName2`, THE Batch_Classifier SHALL classify `batch2` as u_lot
4. THE Batch_Classifier SHALL derive the Batch_Key by combining the batch number value with its classification type (d_lot, bigD_lot, or u_lot)
5. WHEN multiple lot_codes contain wells that reference the same Batch_Key, THE Batch_Classifier SHALL return the same Batch_Key for all of them

### Requirement 2: Status Persistence

**User Story:** As a production supervisor, I want 建線 status to be persisted per batch so that status is consistent across all lot_codes sharing the same batch, and survives system restarts.

#### Acceptance Criteria

1. THE Status_Tracker SHALL store 建線 status records keyed by Batch_Key (batch_number + classification_type)
2. WHEN a Batch_Key has no existing status record, THE Status_Tracker SHALL report the status as "未建線" (not built) with Modification_Count of 0
3. WHEN the confirm-build-line action is performed for a Batch_Key with status "未建線", THE Status_Tracker SHALL transition the status to "已建線" (built) and set Modification_Count to 0
4. WHEN a line modification is performed for a Batch_Key with status "已建線" or "已改線(n)", THE Status_Tracker SHALL increment the Modification_Count by 1 and set the status to "已改線({Modification_Count})"
5. THE Status_Tracker SHALL include a timestamp for each status transition
6. THE Status_Tracker SHALL record which user performed each status transition

### Requirement 3: Status Query API

**User Story:** As a frontend developer, I want an API endpoint that returns the 建線 status for all analyze_item batches associated with a given work order or lot_code, so that the UI can display consistent status information.

#### Acceptance Criteria

1. WHEN the frontend requests 建線 status for a work order (by lot_no or work_order_no), THE Build_Line_Status_Service SHALL return the status for every Batch_Key referenced by that work order's well data
2. THE Build_Line_Status_Service SHALL return each Batch_Key's current status label ("未建線", "已建線", or "已改線(n)"), Modification_Count, and last transition timestamp
3. WHEN multiple lot_codes within a work order share the same Batch_Key, THE Build_Line_Status_Service SHALL return identical status information for all of them
4. IF the requested work order or lot_code does not exist, THEN THE Build_Line_Status_Service SHALL return an HTTP 404 response with a descriptive error message

### Requirement 4: Status Transition on Confirm Build Line

**User Story:** As a production operator, I want the existing confirm-build-line flow to automatically update the batch-level 建線 status, so that I do not need to perform separate status tracking actions.

#### Acceptance Criteria

1. WHEN the `/api/tutti-production/confirm-build-line` endpoint is called successfully, THE Build_Line_Status_Service SHALL extract all Batch_Keys from the dispatched panels' well assignments
2. WHEN a Batch_Key extracted from the confirm-build-line request has status "未建線", THE Build_Line_Status_Service SHALL transition that Batch_Key to "已建線"
3. WHEN a Batch_Key extracted from the confirm-build-line request has status "已建線" or "已改線(n)", THE Build_Line_Status_Service SHALL increment the Modification_Count and transition to "已改線({new_count})"
4. IF the status transition fails for any Batch_Key, THEN THE Build_Line_Status_Service SHALL log the error and continue processing remaining Batch_Keys without rolling back the panel_dispatch records

### Requirement 5: Frontend Status Display

**User Story:** As a production operator viewing the work order grid, I want to see the 建線 status for each analyze_item batch displayed in the TuttiProductionGrid, so that I can quickly identify which batches have been built or modified.

#### Acceptance Criteria

1. THE Frontend_Status_Display SHALL show a status badge for each analyze_item batch (d_lot, bigD_lot, u_lot) in the work order tracking grid
2. WHEN the status is "未建線", THE Frontend_Status_Display SHALL render the badge with a gray background and the text "未建線"
3. WHEN the status is "已建線", THE Frontend_Status_Display SHALL render the badge with a green background and the text "已建線"
4. WHEN the status is "已改線(n)", THE Frontend_Status_Display SHALL render the badge with an orange background and the text "已改線(n)" where n is the Modification_Count
5. WHEN the user views different lot_codes that share the same Batch_Key, THE Frontend_Status_Display SHALL show the same status badge for all of them
6. WHEN the 建線 status changes (after confirm-build-line), THE Frontend_Status_Display SHALL reflect the updated status without requiring a full page reload

### Requirement 6: Batch Status History

**User Story:** As a production supervisor, I want to view the history of status transitions for a specific batch, so that I can audit when and by whom each build or modification was performed.

#### Acceptance Criteria

1. THE Build_Line_Status_Service SHALL provide an API endpoint to query the full status transition history for a given Batch_Key
2. THE Build_Line_Status_Service SHALL return each history entry with: previous status, new status, timestamp, and operator identifier
3. WHEN the history is requested for a Batch_Key with no transitions, THE Build_Line_Status_Service SHALL return an empty history array with the current status "未建線"
4. THE Frontend_Status_Display SHALL provide a clickable interaction on the status badge that opens the transition history for that Batch_Key
