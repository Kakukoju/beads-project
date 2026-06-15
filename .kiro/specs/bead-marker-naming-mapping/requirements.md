# Requirements Document

## Introduction

本功能將 bead 品項命名/映射規則整合為一個集中式、可測試的 Python 模組 (`bead_naming.py`)。目前命名規則散佈在比較腳本 (`bead_compare_manual_vs_system.py`) 與後端 MRP 計算 (`mrpFlask_5.py`) 中，存在重複邏輯且無測試覆蓋。此模組將提供統一的品名正規化 (normalization)、別名映射 (alias mapping)、D/U 配對偵測 (pair detection)、以及 CREA 特殊邏輯，供所有下游消費者使用。

## Glossary

- **Naming_Module**: 集中式品項命名模組 (`bead_naming.py`)，提供所有命名規則的 API
- **Canonical_Name**: 經正規化與別名映射後的標準品項名稱
- **Raw_Name**: 來自 Excel 或資料庫的原始品項名稱字串
- **EXACT_ALIAS**: 精確別名對照表，將特定原始名稱映射到 Canonical_Name
- **D_U_Pair**: 兩劑配對，品項具有 D 側與 U 側試劑
- **Pair_Suffix**: 表示 D/U 側的後綴 (-D, -U, -AD, -AU, -BD, -BU)
- **Version_Suffix**: 配方版本後綴 (-A, -B, -C)，不同版本視為同一品項
- **Base_Name**: 移除 Pair_Suffix 或 Version_Suffix 後的品項基礎名稱
- **Side**: D/U 配對中的側別 ("D" 或 "U")
- **CREA_Kit**: CREA 三劑特殊組合 (tCRE-D, tCREA-D, tCREA-U)
- **Inventory_Threshold**: 庫存+滴定的忽略門檻 (預設 500)，低於此值時視為 0
- **Independent_Item**: 名稱相似但不可合併的獨立品項 (如 T4 ≠ T4 DB, TG ≠ QTG)

## Requirements

### Requirement 1: 品名正規化 (Name Normalization)

**User Story:** As a 系統開發者, I want 將各種格式的原始品名轉換為統一格式, so that 後續邏輯可以一致性地處理品項比對與計算。

#### Acceptance Criteria

1. WHEN a Raw_Name is provided to the Naming_Module, THE Naming_Module SHALL convert the name to uppercase, replace underscores with hyphens, collapse multiple spaces, and normalize dash variants (em-dash, en-dash, full-width dash) to standard ASCII hyphen
2. WHEN a Raw_Name matches an entry in EXACT_ALIAS, THE Naming_Module SHALL return the corresponding Canonical_Name from the alias table
3. WHEN a Raw_Name is "T4 DB", "T4-DB", or "T4DB", THE Naming_Module SHALL return "T4 DB" as the Canonical_Name, preserving it as an Independent_Item separate from "T4"
4. WHEN a Raw_Name has a lowercase 't' prefix followed by a known base (e.g., "tCRE", "tCREA"), THE Naming_Module SHALL recognize the item as part of the CREA_Kit and return the appropriate CREA alias identifier
5. WHEN a Raw_Name has an uppercase 'Q' prefix, THE Naming_Module SHALL preserve the Q prefix, treating the item as an Independent_Item distinct from the non-Q version

### Requirement 2: 別名映射 (Alias Mapping)

**User Story:** As a 品管工程師, I want 所有已知的品名別名都被正確映射到標準名稱, so that 不同系統或人工輸入的相同品項能被正確識別與合併。

#### Acceptance Criteria

1. THE Naming_Module SHALL maintain an EXACT_ALIAS dictionary containing all known name-to-canonical mappings, including: CK→CPK, RGT→GGT, NT4→T4, TCO2→TCO-2, QTCO2→QTCO-2, GLIPA→LIPA, AMY-A→AMY, GLU-B→GLU, TAST→AST, TASTI→AST, TCREA→CREA, T-CREA→CREA, TDBIL→TBIL
2. WHEN a Raw_Name with a Pair_Suffix matches an alias pattern (e.g., "CK-AD"→"CPK-AD", "RGT-D"→"GGT-D", "NT4-D"→"T4-D"), THE Naming_Module SHALL apply the alias mapping while preserving the correct suffix
3. WHEN adding a new alias entry, THE Naming_Module SHALL provide a programmatic interface (function or class method) to register aliases without modifying the core module source code
4. IF a Raw_Name does not match any EXACT_ALIAS entry and has no special prefix handling, THEN THE Naming_Module SHALL return the uppercased and cleaned version of the name as-is

### Requirement 3: D/U 配對偵測 (Pair Detection)

**User Story:** As a MRP 計算引擎, I want 自動偵測品項是否為兩劑配對中的一側, so that 可以正確套用兩劑需求取大/庫存取小的規則。

#### Acceptance Criteria

1. WHEN a Canonical_Name ends with a recognized Pair_Suffix (-D, -U, -AD, -AU, -BD, -BU), THE Naming_Module SHALL return a tuple of (Base_Name, Side) where Side is "D" or "U"
2. WHEN a Canonical_Name ends with a Version_Suffix (-A, -B, -C) but not a Pair_Suffix, THE Naming_Module SHALL return (Base_Name_without_version, None) indicating a plain item with version stripped
3. WHEN a Canonical_Name has no recognized suffix, THE Naming_Module SHALL return (Canonical_Name, None) indicating a plain item with no pairing
4. WHEN multiple suffixes could match (e.g., "-AD" vs "-D"), THE Naming_Module SHALL match the longest suffix first to correctly identify "K-AD" as Base="K", Side="D" rather than Base="K-A", Side="D"
5. WHEN a Canonical_Name belongs to the CREA_Kit (tCRE-D, tCREA-D, tCREA-U), THE Naming_Module SHALL exclude it from standard D/U pair detection and flag it for CREA-specific handling

### Requirement 4: CREA 三劑特殊邏輯 (CREA Kit Handling)

**User Story:** As a MRP 計算引擎, I want CREA 三劑組合的特殊彙總規則被集中定義, so that 比較腳本與後端都能一致地計算 CREA 需求與庫存。

#### Acceptance Criteria

1. THE Naming_Module SHALL define CREA D-side aliases (tCRE-D, T-CRE-D, CRE-D, TCREA-D, T-CREA-D, CREA-D and space variants), U-side aliases (tCREA-U, T-CREA-U, CREA-U and space variants), and plain aliases (CREA, TCREA, T-CREA) as distinct recognizable sets
2. WHEN classifying a Canonical_Name, THE Naming_Module SHALL provide a function that returns the CREA category ("CREA_D", "CREA_U", "CREA_PLAIN", or None) for any given name
3. WHEN aggregating CREA demand, THE Naming_Module SHALL specify the rule: demand = MAX of all D-side weekly demands; tCREA-U contributes only to stock calculation
4. WHEN aggregating CREA stock, THE Naming_Module SHALL specify the rule: effective stock = MIN(max_D_stock, total_U_stock ÷ 2)

### Requirement 5: 獨立品項驗證 (Independent Item Validation)

**User Story:** As a 系統開發者, I want 能驗證兩個品項是否為獨立品項不可合併, so that 避免將 T4 與 T4 DB、TG 與 QTG 等不同品項錯誤合併。

#### Acceptance Criteria

1. THE Naming_Module SHALL maintain an explicit list of independent item pairs that must not be merged: (T4, T4 DB), (TG, QTG), (TC, QTC), (K, QK), (NA, QNA), (GGT, QGGT), (ALT, QALT), (CA, QCA), (CL, BCL)
2. WHEN two Canonical_Names are provided, THE Naming_Module SHALL provide a validation function that returns True if the two items are independent (must not be merged) and False otherwise
3. WHEN a Q-prefixed item and its non-Q counterpart are compared, THE Naming_Module SHALL always identify them as independent items
4. WHEN "T4 DB" and "T4" are compared, THE Naming_Module SHALL identify them as independent items

### Requirement 6: 庫存門檻邏輯 (Inventory Threshold Logic)

**User Story:** As a MRP 計算引擎, I want 庫存門檻的判斷邏輯被集中定義, so that 品項的庫存忽略規則在所有計算中一致。

#### Acceptance Criteria

1. WHEN an item's combined stock and titration is below the Inventory_Threshold, THE Naming_Module SHALL indicate the effective inventory should be treated as zero
2. WHEN an item's Canonical_Name contains "LIPA", THE Naming_Module SHALL exempt the item from the threshold zeroing logic regardless of its stock level
3. WHEN evaluating threshold logic, THE Naming_Module SHALL accept the threshold value as a configurable parameter (default: 500)

### Requirement 7: 兩劑彙總規則 (Two-Reagent Aggregation Rules)

**User Story:** As a MRP 計算引擎, I want 兩劑品項的需求與庫存彙總規則被統一定義, so that D/U 配對的計算邏輯在比較腳本與後端保持一致。

#### Acceptance Criteria

1. WHEN a D_U_Pair has both D-side and U-side demand values for the same week, THE Naming_Module SHALL specify the aggregation rule: weekly demand = MAX(D_demand, U_demand)
2. WHEN a D_U_Pair has both D-side and U-side stock values, THE Naming_Module SHALL specify the aggregation rule: effective stock = MIN(D_stock, U_stock)
3. WHEN a D_U_Pair has only one side present (only D or only U), THE Naming_Module SHALL use the available side's values directly without MAX/MIN operations

### Requirement 8: 命名慣例驗證 (Name Convention Validation)

**User Story:** As a 品管工程師, I want 能驗證新品項名稱是否符合命名慣例, so that 新增品項時能即時檢查格式正確性。

#### Acceptance Criteria

1. WHEN a candidate name is submitted for validation, THE Naming_Module SHALL check that it follows the pattern: optional prefix (Q or t) + uppercase alphanumeric Base_Name + optional suffix (Version_Suffix or Pair_Suffix)
2. WHEN a candidate name violates the naming convention, THE Naming_Module SHALL return a descriptive error message indicating which part of the name is non-compliant
3. WHEN a candidate name is valid, THE Naming_Module SHALL return a success indicator along with the parsed components (prefix, base, suffix type, suffix value)

### Requirement 9: 模組整合介面 (Module Integration Interface)

**User Story:** As a 系統開發者, I want 命名模組提供清晰的公共 API, so that 比較腳本與後端可以簡單地替換其內聯邏輯為模組呼叫。

#### Acceptance Criteria

1. THE Naming_Module SHALL expose a `normalize(raw_name: str) -> str` function that performs full normalization including cleanup, alias lookup, and canonical name resolution
2. THE Naming_Module SHALL expose a `parse_pair(canonical_name: str) -> Tuple[str, Optional[str]]` function that returns (base_name, side_or_none) for D/U pair detection
3. THE Naming_Module SHALL expose a `classify_crea(canonical_name: str) -> Optional[str]` function that returns the CREA category or None
4. THE Naming_Module SHALL expose an `is_independent(name_a: str, name_b: str) -> bool` function for checking independent item relationships
5. THE Naming_Module SHALL expose a `should_zero_inventory(canonical_name: str, stock_plus_titration: float, threshold: int = 500) -> bool` function for threshold logic
6. THE Naming_Module SHALL expose a `validate_name(candidate: str) -> ValidationResult` function that checks naming convention compliance
7. THE Naming_Module SHALL be importable as a standalone Python module with no dependencies beyond the standard library
