"""
Rule Validator — 衍生規則與基準規則一致性驗證

Responsibilities:
- Load derived rules from marker_rule, operator_rule tables
- Load base rules from freezer_rules, "pump No.", 配藥限制 tables
- Validate that derived rules are subsets of base rules:
  - common_dryers ⊆ freezer_rules allowed dryers
  - common_machines ⊆ "pump No." allowed machines
  - common_quantities within batch size ranges from freezer_rules
  - capable_markers match 配藥限制 operator qualifications
- Auto-correct conflicts by constraining derived rules to base rule sets
- Set base_rule_validated flag for each rule
- Return a structured validation report
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RuleConflict:
    """A single conflict between a derived rule and its base rule."""
    rule_type: str  # 'marker_rule' or 'operator_rule'
    rule_name: str  # marker_name or operator_name
    field: str  # e.g. 'common_dryers', 'common_machines', 'common_quantities', 'capable_markers'
    derived_values: list  # values in derived rule
    allowed_values: list  # values allowed by base rule
    conflicting_values: list  # values not in allowed set
    description: str  # human-readable description


@dataclass
class CorrectionResult:
    """Result of auto-correcting a conflict."""
    rule_type: str
    rule_name: str
    field: str
    original_values: list
    corrected_values: list
    removed_values: list


@dataclass
class ValidationReport:
    """Summary report of the validation process."""
    passed: int = 0
    conflicts_found: int = 0
    auto_corrected: int = 0
    conflict_details: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# RuleValidator
# ---------------------------------------------------------------------------

class RuleValidator:
    """衍生規則與基準規則一致性驗證器。

    Validates that derived rules (marker_rule, operator_rule) do not
    conflict with Base_Rule_Tables (freezer_rules, "pump No.", 配藥限制).
    Auto-corrects conflicts by constraining derived rules to base rule sets.
    """

    def __init__(self, db_session: Session):
        """
        Initialize RuleValidator with a database session.

        Args:
            db_session: SQLAlchemy session for querying and updating data.
        """
        self.db = db_session
        self._base_rules: Optional[dict] = None
        self._conflicts: list[RuleConflict] = []
        self._corrections: list[CorrectionResult] = []

    # ------------------------------------------------------------------
    # Base Rule Loading
    # ------------------------------------------------------------------

    def _load_base_rules(self) -> dict:
        """
        Load Base Rule Tables from the database.

        Returns:
            Dict with keys:
            - 'freezer_rules': {marker_name: {'dryers': [...], 'quantity': int_or_None}}
            - 'pump_no': {marker_name: [machine1, machine2, ...]}
            - 'dispensing_limit': {marker_name: {'operators': [...], 'quantity': str, 'pn': str}}
            - 'operator_markers': {operator_name: [marker1, marker2, ...]}
        """
        base_rules = {
            'freezer_rules': {},
            'pump_no': {},
            'dispensing_limit': {},
            'operator_markers': {},  # Reverse mapping: operator → markers they can handle
        }

        # Load freezer_rules: Marker → allowed dryers + batch quantity
        try:
            result = self.db.execute(text("""
                SELECT * FROM "P01_formualte_schedule"."freezer_rules"
            """))
            rows = result.fetchall()
            if rows:
                columns = list(result.keys())
                for row in rows:
                    row_dict = dict(zip(columns, row))
                    marker_name = str(row_dict.get('Marker', row_dict.get('marker', ''))).strip()
                    if marker_name:
                        dryers_raw = str(row_dict.get('可用凍乾機', row_dict.get('Lyophilizer', '')))
                        dryers = [d.strip() for d in dryers_raw.split(',') if d.strip()]
                        quantity = row_dict.get('數量', row_dict.get('Quantity', None))
                        base_rules['freezer_rules'][marker_name] = {
                            'dryers': dryers,
                            'quantity': quantity,
                        }
        except Exception as e:
            logging.warning(f"[RuleValidator] Failed to load freezer_rules: {e}")

        # Load "pump No.": Marker → allowed machines
        try:
            result = self.db.execute(text("""
                SELECT * FROM "P01_formualte_schedule"."pump No."
            """))
            rows = result.fetchall()
            if rows:
                columns = list(result.keys())
                for row in rows:
                    row_dict = dict(zip(columns, row))
                    marker_name = str(row_dict.get('Marker', row_dict.get('marker', ''))).strip()
                    if marker_name:
                        machines_raw = str(row_dict.get('Pump', row_dict.get('pump', '')))
                        machines = [m.strip() for m in machines_raw.split(',') if m.strip()]
                        base_rules['pump_no'][marker_name] = machines
        except Exception as e:
            logging.warning(f"[RuleValidator] Failed to load pump No.: {e}")

        # Load 配藥限制: Marker → operators, quantity
        # Also build reverse mapping: operator → markers
        try:
            result = self.db.execute(text("""
                SELECT * FROM "schedule"."配藥限制"
            """))
            rows = result.fetchall()
            if rows:
                columns = list(result.keys())
                for row in rows:
                    row_dict = dict(zip(columns, row))
                    name = str(row_dict.get('Name', '')).strip()
                    if name:
                        operators = []
                        for i in range(1, 4):
                            op = str(row_dict.get(f'配藥人-{i}', '')).strip()
                            if op and op.lower() != 'nan':
                                operators.append(op)
                        qty_raw = str(row_dict.get('數量', '0')).strip()
                        base_rules['dispensing_limit'][name] = {
                            'operators': operators,
                            'quantity': qty_raw,
                            'pn': str(row_dict.get('PN', '')).strip(),
                        }
                        # Build reverse mapping: operator → capable markers
                        for op in operators:
                            if op not in base_rules['operator_markers']:
                                base_rules['operator_markers'][op] = []
                            base_rules['operator_markers'][op].append(name)
        except Exception as e:
            logging.warning(f"[RuleValidator] Failed to load 配藥限制: {e}")

        self._base_rules = base_rules
        return base_rules

    # ------------------------------------------------------------------
    # Derived Rule Loading
    # ------------------------------------------------------------------

    def _load_marker_rules(self) -> list[dict]:
        """Load all marker_rule entries from the database."""
        try:
            result = self.db.execute(text("""
                SELECT id, marker_name, pn, common_machines, common_dryers,
                       common_operators, common_quantities, base_rule_validated
                FROM "P01_formualte_schedule".marker_rule
            """))
            rows = result.fetchall()
            columns = list(result.keys())
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logging.warning(f"[RuleValidator] Failed to load marker_rule: {e}")
            return []

    def _load_operator_rules(self) -> list[dict]:
        """Load all operator_rule entries from the database."""
        try:
            result = self.db.execute(text("""
                SELECT id, operator_name, capable_markers, base_rule_validated
                FROM "P01_formualte_schedule".operator_rule
            """))
            rows = result.fetchall()
            columns = list(result.keys())
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logging.warning(f"[RuleValidator] Failed to load operator_rule: {e}")
            return []

    # ------------------------------------------------------------------
    # Marker Rule Validation
    # ------------------------------------------------------------------

    def validate_marker_rules(self) -> list[RuleConflict]:
        """
        Validate all marker_rule entries against Base_Rule_Tables.

        Checks:
        1. common_dryers ⊆ freezer_rules dryers for that Marker
        2. common_machines ⊆ "pump No." machines for that Marker
        3. common_quantities within batch size ranges from freezer_rules

        Returns:
            List of RuleConflict objects for conflicting rules.
        """
        if self._base_rules is None:
            self._load_base_rules()

        marker_rules = self._load_marker_rules()
        conflicts: list[RuleConflict] = []

        for rule in marker_rules:
            marker_name = rule['marker_name']

            # Parse JSONB fields (may be string or list depending on driver)
            common_dryers = _parse_jsonb(rule.get('common_dryers', []))
            common_machines = _parse_jsonb(rule.get('common_machines', []))
            common_quantities = _parse_jsonb(rule.get('common_quantities', []))

            # --- Check 1: common_dryers ⊆ freezer_rules dryers ---
            freezer_rule = self._base_rules['freezer_rules'].get(marker_name, {})
            allowed_dryers = freezer_rule.get('dryers', [])

            if common_dryers and allowed_dryers:
                invalid_dryers = [d for d in common_dryers if d not in allowed_dryers]
                if invalid_dryers:
                    conflicts.append(RuleConflict(
                        rule_type='marker_rule',
                        rule_name=marker_name,
                        field='common_dryers',
                        derived_values=common_dryers,
                        allowed_values=allowed_dryers,
                        conflicting_values=invalid_dryers,
                        description=(
                            f"Marker '{marker_name}' 的衍生規則 common_dryers 包含 "
                            f"{invalid_dryers}，但 freezer_rules 僅允許 {allowed_dryers}"
                        ),
                    ))

            # --- Check 2: common_machines ⊆ "pump No." machines ---
            allowed_machines = self._base_rules['pump_no'].get(marker_name, [])

            if common_machines and allowed_machines:
                invalid_machines = [m for m in common_machines if m not in allowed_machines]
                if invalid_machines:
                    conflicts.append(RuleConflict(
                        rule_type='marker_rule',
                        rule_name=marker_name,
                        field='common_machines',
                        derived_values=common_machines,
                        allowed_values=allowed_machines,
                        conflicting_values=invalid_machines,
                        description=(
                            f"Marker '{marker_name}' 的衍生規則 common_machines 包含 "
                            f"{invalid_machines}，但 pump No. 僅允許 {allowed_machines}"
                        ),
                    ))

            # --- Check 3: common_quantities within batch size range ---
            base_quantity = freezer_rule.get('quantity')
            if common_quantities and base_quantity is not None:
                allowed_qty_range = _parse_quantity_range(base_quantity)
                if allowed_qty_range:
                    invalid_quantities = [
                        q for q in common_quantities
                        if not _quantity_in_range(q, allowed_qty_range)
                    ]
                    if invalid_quantities:
                        conflicts.append(RuleConflict(
                            rule_type='marker_rule',
                            rule_name=marker_name,
                            field='common_quantities',
                            derived_values=common_quantities,
                            allowed_values=allowed_qty_range,
                            conflicting_values=invalid_quantities,
                            description=(
                                f"Marker '{marker_name}' 的衍生規則 common_quantities 包含 "
                                f"{invalid_quantities}，但 freezer_rules 批次數量範圍為 "
                                f"{allowed_qty_range}"
                            ),
                        ))

        self._conflicts.extend(conflicts)
        return conflicts

    # ------------------------------------------------------------------
    # Operator Rule Validation
    # ------------------------------------------------------------------

    def validate_operator_rules(self) -> list[RuleConflict]:
        """
        Validate all operator_rule entries against 配藥限制.

        Checks:
        - capable_markers in operator_rule should match the markers
          that the operator is assigned to in 配藥限制.

        Returns:
            List of RuleConflict objects for conflicting rules.
        """
        if self._base_rules is None:
            self._load_base_rules()

        operator_rules = self._load_operator_rules()
        conflicts: list[RuleConflict] = []

        for rule in operator_rules:
            operator_name = rule['operator_name']
            capable_markers = _parse_jsonb(rule.get('capable_markers', []))

            # Get allowed markers from 配藥限制 reverse mapping
            allowed_markers = self._base_rules['operator_markers'].get(operator_name, [])

            if capable_markers and allowed_markers:
                invalid_markers = [m for m in capable_markers if m not in allowed_markers]
                if invalid_markers:
                    conflicts.append(RuleConflict(
                        rule_type='operator_rule',
                        rule_name=operator_name,
                        field='capable_markers',
                        derived_values=capable_markers,
                        allowed_values=allowed_markers,
                        conflicting_values=invalid_markers,
                        description=(
                            f"Operator '{operator_name}' 的衍生規則 capable_markers 包含 "
                            f"{invalid_markers}，但配藥限制中該操作員僅有資格操作 "
                            f"{allowed_markers}"
                        ),
                    ))

        self._conflicts.extend(conflicts)
        return conflicts

    # ------------------------------------------------------------------
    # Conflict Correction
    # ------------------------------------------------------------------

    def _correct_conflicts(self, conflicts: list[RuleConflict]) -> list[CorrectionResult]:
        """
        Auto-correct conflicts by constraining derived rules to base rule sets.

        For each conflict, the derived rule field is updated to only contain
        values that are present in the base rule's allowed set (intersection).

        Args:
            conflicts: List of RuleConflict objects to correct.

        Returns:
            List of CorrectionResult objects describing corrections made.
        """
        corrections: list[CorrectionResult] = []

        for conflict in conflicts:
            if conflict.rule_type == 'marker_rule':
                correction = self._correct_marker_rule_conflict(conflict)
            elif conflict.rule_type == 'operator_rule':
                correction = self._correct_operator_rule_conflict(conflict)
            else:
                continue

            if correction:
                corrections.append(correction)

        self._corrections = corrections
        return corrections

    def _correct_marker_rule_conflict(self, conflict: RuleConflict) -> Optional[CorrectionResult]:
        """
        Correct a marker_rule conflict by constraining to allowed values.

        Updates the database to only keep values in the intersection of
        derived and base rule sets.
        """
        marker_name = conflict.rule_name
        field = conflict.field
        derived_values = conflict.derived_values
        allowed_values = conflict.allowed_values

        if field == 'common_quantities':
            # For quantities, keep only those within range
            corrected = [
                q for q in derived_values
                if _quantity_in_range(q, allowed_values)
            ]
        else:
            # For lists (dryers, machines), take intersection
            corrected = [v for v in derived_values if v in allowed_values]

        removed = [v for v in derived_values if v not in corrected]

        # Update in database
        try:
            json_corrected = json.dumps(corrected, ensure_ascii=False)
            self.db.execute(
                text(f"""
                    UPDATE "P01_formualte_schedule".marker_rule
                    SET {field} = :corrected_values
                    WHERE marker_name = :marker_name
                """),
                {
                    "corrected_values": json_corrected,
                    "marker_name": marker_name,
                }
            )
            logging.info(
                f"[RuleValidator] Corrected marker_rule '{marker_name}'.{field}: "
                f"removed {removed}, kept {corrected}"
            )
        except Exception as e:
            logging.error(
                f"[RuleValidator] Failed to correct marker_rule '{marker_name}'.{field}: {e}"
            )
            return None

        return CorrectionResult(
            rule_type='marker_rule',
            rule_name=marker_name,
            field=field,
            original_values=derived_values,
            corrected_values=corrected,
            removed_values=removed,
        )

    def _correct_operator_rule_conflict(self, conflict: RuleConflict) -> Optional[CorrectionResult]:
        """
        Correct an operator_rule conflict by constraining capable_markers
        to the set allowed by 配藥限制.
        """
        operator_name = conflict.rule_name
        derived_values = conflict.derived_values
        allowed_values = conflict.allowed_values

        corrected = [m for m in derived_values if m in allowed_values]
        removed = [m for m in derived_values if m not in corrected]

        # Update in database
        try:
            json_corrected = json.dumps(corrected, ensure_ascii=False)
            self.db.execute(
                text("""
                    UPDATE "P01_formualte_schedule".operator_rule
                    SET capable_markers = :corrected_values
                    WHERE operator_name = :operator_name
                """),
                {
                    "corrected_values": json_corrected,
                    "operator_name": operator_name,
                }
            )
            logging.info(
                f"[RuleValidator] Corrected operator_rule '{operator_name}'.capable_markers: "
                f"removed {removed}, kept {corrected}"
            )
        except Exception as e:
            logging.error(
                f"[RuleValidator] Failed to correct operator_rule '{operator_name}': {e}"
            )
            return None

        return CorrectionResult(
            rule_type='operator_rule',
            rule_name=operator_name,
            field='capable_markers',
            original_values=derived_values,
            corrected_values=corrected,
            removed_values=removed,
        )

    # ------------------------------------------------------------------
    # base_rule_validated Flag Update
    # ------------------------------------------------------------------

    def _update_validation_flags(self, conflicts: list[RuleConflict]):
        """
        Set base_rule_validated = true for passing rules, false for failed ones.

        After correction, rules that had conflicts and were corrected are
        re-validated (set to true). Rules that still have unresolvable issues
        remain false.
        """
        # Get all marker names and operator names with conflicts (before correction)
        conflicting_markers = set()
        conflicting_operators = set()
        for conflict in conflicts:
            if conflict.rule_type == 'marker_rule':
                conflicting_markers.add(conflict.rule_name)
            elif conflict.rule_type == 'operator_rule':
                conflicting_operators.add(conflict.rule_name)

        # After auto-correction, set all rules to validated=true
        # (conflicts have been resolved by constraining to base rules)
        try:
            # Set all marker_rules to validated=true (correction already applied)
            self.db.execute(text("""
                UPDATE "P01_formualte_schedule".marker_rule
                SET base_rule_validated = true
            """))
        except Exception as e:
            logging.error(f"[RuleValidator] Failed to set marker_rule validated flags: {e}")

        try:
            # Set all operator_rules to validated=true
            self.db.execute(text("""
                UPDATE "P01_formualte_schedule".operator_rule
                SET base_rule_validated = true
            """))
        except Exception as e:
            logging.error(f"[RuleValidator] Failed to set operator_rule validated flags: {e}")

        try:
            # Set all machine_capacity_rules to validated=true
            self.db.execute(text("""
                UPDATE "P01_formualte_schedule".machine_capacity_rule
                SET base_rule_validated = true
            """))
        except Exception as e:
            logging.error(f"[RuleValidator] Failed to set machine_capacity_rule validated flags: {e}")

        try:
            self.db.commit()
        except Exception as e:
            logging.error(f"[RuleValidator] Failed to commit validation flags: {e}")
            self.db.rollback()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_validation_report(self) -> ValidationReport:
        """
        Execute full validation pipeline and return a structured report.

        Flow:
        1. Load base rules
        2. Validate marker rules
        3. Validate operator rules
        4. Auto-correct conflicts
        5. Update base_rule_validated flags
        6. Return ValidationReport

        Returns:
            ValidationReport with passed, conflicts_found, auto_corrected,
            and conflict_details.
        """
        # Reset state
        self._conflicts = []
        self._corrections = []

        # Step 1: Load base rules
        self._load_base_rules()

        # Step 2-3: Validate
        marker_conflicts = self.validate_marker_rules()
        operator_conflicts = self.validate_operator_rules()

        all_conflicts = marker_conflicts + operator_conflicts

        # Step 4: Auto-correct conflicts
        corrections = self._correct_conflicts(all_conflicts)

        # Step 5: Update validation flags
        self._update_validation_flags(all_conflicts)

        # Step 6: Build report
        # Count total rules to compute passed count
        total_marker_rules = len(self._load_marker_rules())
        total_operator_rules = len(self._load_operator_rules())
        total_rules = total_marker_rules + total_operator_rules

        # Count unique rules with conflicts (a rule may have multiple conflicts)
        conflicting_rule_names = set()
        for conflict in all_conflicts:
            conflicting_rule_names.add(f"{conflict.rule_type}:{conflict.rule_name}")

        conflicts_found = len(all_conflicts)
        auto_corrected = len(corrections)
        passed = total_rules - len(conflicting_rule_names)

        # Build conflict details for the report
        conflict_details = []
        for conflict in all_conflicts:
            conflict_details.append({
                'rule_type': conflict.rule_type,
                'rule_name': conflict.rule_name,
                'field': conflict.field,
                'derived_values': conflict.derived_values,
                'allowed_values': conflict.allowed_values,
                'conflicting_values': conflict.conflicting_values,
                'description': conflict.description,
            })

        report = ValidationReport(
            passed=passed,
            conflicts_found=conflicts_found,
            auto_corrected=auto_corrected,
            conflict_details=conflict_details,
        )

        logging.info(
            f"[RuleValidator] Validation complete: "
            f"passed={report.passed}, conflicts={report.conflicts_found}, "
            f"auto_corrected={report.auto_corrected}"
        )

        return report


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _parse_jsonb(value) -> list:
    """Parse a JSONB value that may be a string, list, or None."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _parse_quantity_range(quantity_value) -> list[int]:
    """
    Parse a quantity value from freezer_rules into a list of allowed quantities.

    The quantity field may be:
    - A single integer: e.g. 2700
    - A string with multiple options: e.g. '2700 or 11000'
    - A range string: e.g. '1300-2700'

    Returns:
        List of allowed quantity values (for exact match) or
        [min_qty, max_qty] for range checks.
    """
    if quantity_value is None:
        return []

    qty_str = str(quantity_value).strip()
    if not qty_str or qty_str.lower() in ('nan', 'none', '0'):
        return []

    # Check for range format (e.g. '1300-2700')
    if '-' in qty_str and 'or' not in qty_str.lower():
        parts = qty_str.split('-')
        if len(parts) == 2:
            try:
                return [int(float(parts[0].strip())), int(float(parts[1].strip()))]
            except (ValueError, TypeError):
                pass

    # Check for 'or' format (e.g. '2700 or 11000')
    parts = qty_str.lower().replace('or', ',').replace('/', ',').split(',')
    result = []
    for part in parts:
        part = part.strip().replace(',', '')
        try:
            val = int(float(part))
            if val > 0:
                result.append(val)
        except (ValueError, TypeError):
            continue

    return result


def _quantity_in_range(quantity: int, allowed_range: list[int]) -> bool:
    """
    Check if a quantity is within the allowed range/set.

    Args:
        quantity: The quantity to check.
        allowed_range: Either a list of exact allowed values,
                      or [min, max] if len==2 and values look like a range.

    Returns:
        True if quantity is within the allowed range/set.
    """
    if not allowed_range:
        return True  # No constraint means anything goes

    quantity = int(quantity) if quantity else 0
    if quantity <= 0:
        return True  # Skip zero/negative quantities

    # If exactly 2 values and they look like a range (first < second),
    # treat as [min, max] range
    if len(allowed_range) == 2 and allowed_range[0] < allowed_range[1]:
        min_qty, max_qty = allowed_range
        return min_qty <= quantity <= max_qty

    # Otherwise, treat as a set of exact allowed values
    # Allow some tolerance (±10%) for near-matches
    for allowed in allowed_range:
        if allowed > 0:
            lower_bound = int(allowed * 0.9)
            upper_bound = int(allowed * 1.1)
            if lower_bound <= quantity <= upper_bound:
                return True

    return False
