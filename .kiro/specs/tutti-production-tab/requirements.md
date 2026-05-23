# Requirements Document

## Introduction

This feature adds a "Tutti-Beads 預建線 . 工單" tab to the Gemini MRP: Advanced Planning Simulator homepage. The tab provides an AG Grid-based Excel-like table for managing Tutti panel production records, with full CRUD operations backed by a PostgreSQL RDS table (`panel_production.tutti_production`). The tab is placed after the existing "執行看板" tab in the navigation bar.

## Glossary

- **Simulator**: The Gemini MRP Advanced Planning Simulator React frontend application (App.tsx)
- **Flask_Backend**: The Flask API server (mrpFlask_5.py) that handles data persistence and business logic
- **AG_Grid**: The AG Grid Community React component used to render Excel-like editable tables
- **Production_Record**: A single row in the `panel_production.tutti_production` PostgreSQL table representing one production work order entry
- **RDS_Database**: The AWS RDS PostgreSQL instance (beadsdb) storing all application data
- **Navigation_Bar**: The tab navigation component in the Simulator header that switches between views
- **Storage_Quantity**: A derived field calculated as `production_quantity - defect_quantity - qa_inspection`

## Requirements

### Requirement 1: Tab Navigation Integration

**User Story:** As a production manager, I want to access the Tutti production records from a dedicated tab in the navigation bar, so that I can manage panel production data alongside existing planning tools.

#### Acceptance Criteria

1. THE Navigation_Bar SHALL display a "Tutti-Beads 預建線 . 工單" tab button after the "執行看板" tab button
2. WHEN the user clicks the "Tutti-Beads 預建線 . 工單" tab, THE Simulator SHALL switch the main content area to display the Tutti production grid view
3. THE Simulator SHALL persist the selected tab state using the existing `viewMode` pattern with a new value of 'tutti'
4. WHEN the Simulator loads with viewMode set to 'tutti', THE Simulator SHALL display the Tutti production grid view

### Requirement 2: Database Schema Setup

**User Story:** As a system administrator, I want the database schema and table created on the RDS instance, so that production records can be stored persistently.

#### Acceptance Criteria

1. THE Flask_Backend SHALL connect to the RDS_Database with the `panel_production` schema included in the search_path
2. THE RDS_Database SHALL contain a schema named `panel_production`
3. THE RDS_Database SHALL contain a table `panel_production.tutti_production` with the following columns: id (serial primary key), lot_no (VARCHAR 50, NOT NULL), work_order_number (VARCHAR 50, NOT NULL), product_name (VARCHAR 100), production_order_quantity (INTEGER), model_pn (VARCHAR 50), sheet_name (VARCHAR 100), line (VARCHAR 10), well_position (INTEGER, CHECK 1-10), reagent_slot (VARCHAR 50), reagent_name (VARCHAR 100), batch_number (VARCHAR 50), quantity (NUMERIC), formula_number (VARCHAR 50), welding_parameter_number (VARCHAR 50), production_quantity (INTEGER), defect_quantity (INTEGER DEFAULT 0), qa_inspection (INTEGER DEFAULT 0), storage_quantity (INTEGER), labeling_status (VARCHAR 20), diluent_box_status (VARCHAR 20), assembly_status (VARCHAR 20), packaging_status (VARCHAR 20), boxing_status (VARCHAR 20), created_at (TIMESTAMP DEFAULT NOW()), updated_at (TIMESTAMP DEFAULT NOW()), created_by (VARCHAR 50)
4. WHEN a new Production_Record is inserted without specifying defect_quantity, THEN THE RDS_Database SHALL default defect_quantity to 0
5. WHEN a new Production_Record is inserted without specifying qa_inspection, THEN THE RDS_Database SHALL default qa_inspection to 0

### Requirement 3: Backend CRUD API

**User Story:** As a frontend developer, I want RESTful API endpoints for managing production records, so that the AG Grid can read and write data to the database.

#### Acceptance Criteria

1. WHEN a GET request is sent to `/api/tutti-production`, THE Flask_Backend SHALL return all Production_Record rows as a JSON array ordered by created_at descending
2. WHEN a GET request is sent to `/api/tutti-production` with a `work_order` query parameter, THE Flask_Backend SHALL return only Production_Record rows matching the specified work_order_number
3. WHEN a POST request is sent to `/api/tutti-production` with valid Production_Record JSON data, THE Flask_Backend SHALL insert a new row into the tutti_production table and return the created record with its generated id
4. WHEN a PUT request is sent to `/api/tutti-production/<id>` with partial Production_Record JSON data, THE Flask_Backend SHALL update the specified row and set updated_at to the current timestamp
5. WHEN a DELETE request is sent to `/api/tutti-production/<id>`, THE Flask_Backend SHALL delete the specified row and return a success confirmation
6. IF a PUT or DELETE request references a non-existent id, THEN THE Flask_Backend SHALL return a 404 status code with an error message
7. IF a POST request is missing required fields (lot_no or work_order_number), THEN THE Flask_Backend SHALL return a 400 status code with a validation error message

### Requirement 4: AG Grid Data Display

**User Story:** As a production operator, I want to view all production records in an Excel-like grid, so that I can quickly scan and understand the current production status.

#### Acceptance Criteria

1. WHEN the Tutti tab is active, THE AG_Grid SHALL display all Production_Record rows fetched from the Flask_Backend
2. THE AG_Grid SHALL organize columns into four column groups: "工單資訊" (work order info), "填充/熔接製程" (filling/welding process), "生產記錄" (production records), "後製程" (post-process)
3. THE AG_Grid SHALL display the "工單資訊" group containing columns: 批號 (lot_no), 工單號碼 (work_order_number), 產品名稱 (product_name), 製令數量 (production_order_quantity), Model P/N (model_pn), 片名 (sheet_name)
4. THE AG_Grid SHALL display the "填充/熔接製程" group containing columns: 線別 (line), 卡匣位置 (well_position), 藥槽 (reagent_slot), 試劑名稱 (reagent_name), 批次號 (batch_number), 數量 (quantity), 配方編號 (formula_number), 熔接參數編號 (welding_parameter_number)
5. THE AG_Grid SHALL display the "生產記錄" group containing columns: 生產數量 (production_quantity), 不良數量 (defect_quantity), QA檢測 (qa_inspection), 入庫數量 (storage_quantity)
6. THE AG_Grid SHALL display the "後製程" group containing columns: 貼標 (labeling_status), 稀釋液盒製作 (diluent_box_status), 組裝 (assembly_status), 包裝 (packaging_status), 裝箱 (boxing_status)
7. THE AG_Grid SHALL display Chinese column headers for all columns

### Requirement 5: Inline Editing with Auto-Save

**User Story:** As a production operator, I want to edit cell values directly in the grid and have changes saved automatically, so that I can update records efficiently without a separate save step.

#### Acceptance Criteria

1. WHEN the user double-clicks or presses Enter on an editable cell, THE AG_Grid SHALL enter edit mode for that cell
2. WHEN the user finishes editing a cell (blur or Enter), THE AG_Grid SHALL send a PUT request to the Flask_Backend with the updated field value
3. WHEN the auto-save PUT request succeeds, THE AG_Grid SHALL display the updated value in the cell
4. IF the auto-save PUT request fails, THEN THE AG_Grid SHALL revert the cell to its previous value and display an error notification
5. THE AG_Grid SHALL mark the storage_quantity column as read-only since it is auto-calculated
6. THE AG_Grid SHALL mark the id, created_at, and updated_at columns as read-only

### Requirement 6: Storage Quantity Auto-Calculation

**User Story:** As a production operator, I want the storage quantity to be automatically calculated, so that I do not need to manually compute it and risk errors.

#### Acceptance Criteria

1. WHEN production_quantity, defect_quantity, or qa_inspection is updated in a Production_Record, THE Flask_Backend SHALL calculate storage_quantity as production_quantity minus defect_quantity minus qa_inspection
2. WHEN the Flask_Backend returns a Production_Record, THE Flask_Backend SHALL include the calculated storage_quantity value
3. WHEN any of the three source fields is updated via the AG_Grid, THE AG_Grid SHALL display the recalculated storage_quantity without requiring a page refresh

### Requirement 7: Record Creation

**User Story:** As a production operator, I want to add new production records to the grid, so that I can log new work orders as they begin.

#### Acceptance Criteria

1. THE Simulator SHALL display a "新增" (Add) button above the AG_Grid
2. WHEN the user clicks the "新增" button, THE AG_Grid SHALL insert a new empty row at the top of the grid with default values for defect_quantity (0) and qa_inspection (0)
3. WHEN the user fills in the required fields (lot_no and work_order_number) and leaves the row, THE AG_Grid SHALL send a POST request to the Flask_Backend to persist the new record
4. IF the user leaves the new row without filling required fields, THEN THE AG_Grid SHALL remove the unpersisted row and display a validation message

### Requirement 8: Record Deletion

**User Story:** As a production manager, I want to delete incorrect or obsolete production records, so that the data remains accurate and clean.

#### Acceptance Criteria

1. THE AG_Grid SHALL provide a row selection mechanism using checkboxes
2. THE Simulator SHALL display a "刪除" (Delete) button above the AG_Grid
3. WHEN the user selects one or more rows and clicks the "刪除" button, THE Simulator SHALL display a confirmation dialog
4. WHEN the user confirms deletion, THE AG_Grid SHALL send DELETE requests to the Flask_Backend for each selected record and remove the rows from the grid
5. IF any DELETE request fails, THEN THE AG_Grid SHALL retain the failed row and display an error notification

### Requirement 9: Work Order Filtering

**User Story:** As a production manager, I want to filter the grid by work order number, so that I can focus on a specific production batch.

#### Acceptance Criteria

1. THE Simulator SHALL display a work order filter input field above the AG_Grid
2. WHEN the user enters a work order number and triggers the filter (Enter key or filter button), THE AG_Grid SHALL request filtered data from the Flask_Backend using the `work_order` query parameter
3. WHEN the filter input is cleared, THE AG_Grid SHALL reload and display all Production_Record rows
4. THE AG_Grid SHALL display the count of currently shown records next to the filter input

### Requirement 10: Data Loading and Refresh

**User Story:** As a production operator, I want data to load automatically when I switch to the Tutti tab and have a manual refresh option, so that I always see the latest production records.

#### Acceptance Criteria

1. WHEN the user switches to the Tutti tab, THE AG_Grid SHALL fetch and display the latest Production_Record data from the Flask_Backend
2. THE Simulator SHALL display a "重新整理" (Refresh) button above the AG_Grid
3. WHEN the user clicks the "重新整理" button, THE AG_Grid SHALL re-fetch all Production_Record data from the Flask_Backend and update the display
4. WHILE data is being fetched, THE AG_Grid SHALL display a loading indicator
