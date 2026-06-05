"""
Conflict Detector — 偵測排程結果中的資源衝突

Responsibilities:
- Detect machine port time overlaps (same port, overlapping intervals)
- Detect freeze dryer over-capacity (concurrent usage exceeds max_concurrent)
- Detect operator prepare interval overlaps (same operator, overlapping prep time)
- Verify production flow ordering (dispensing → titration → freeze per batch)
- Verify base rule compliance (assigned resources within allowed sets)
- Set conflict_flag=True and populate conflict_reason for each detected conflict

Requirements: 6.3, 6.4, 3.5, 5.1, 5.2, 5.3, 5.8
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Conflict:
    """Represents a single detected conflict in the schedule."""
    entry_id: Any  # id of the schedule entry (int or UUID)
    conflict_type: str  # e.g. 'machine_overlap', 'dryer_capacity', 'operator_overlap', 'production_flow', 'base_rule_violation'
    description: str  # Human-readable description of the conflict
    severity: str = 'error'  # 'error' or 'warning'


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _parse_time(value: Any) -> Optional[time]:
    """Parse a time value from various formats into a datetime.time object."""
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        # Try common formats
        for fmt in ('%H:%M:%S', '%H:%M', '%H:%M:%S.%f'):
            try:
                return datetime.strptime(value, fmt).time()
            except ValueError:
                continue
    return None


def _parse_date(value: Any) -> Optional[date]:
    """Parse a date value from various formats into a datetime.date object."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y%m%d'):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def _get(entry: Any, key: str, default=None):
    """Get a value from a dict or object attribute."""
    if isinstance(entry, dict):
        return entry.get(key, default)
    return getattr(entry, key, default)


def _time_to_minutes(t: Optional[time]) -> Optional[int]:
    """Convert a time object to minutes since midnight."""
    if t is None:
        return None
    return t.hour * 60 + t.minute


def _times_overlap(start1: Optional[time], end1: Optional[time],
                   start2: Optional[time], end2: Optional[time]) -> bool:
    """Check if two time intervals overlap. Both must be non-None to check."""
    s1 = _time_to_minutes(start1)
    e1 = _time_to_minutes(end1)
    s2 = _time_to_minutes(start2)
    e2 = _time_to_minutes(end2)

    if any(v is None for v in [s1, e1, s2, e2]):
        return False

    # Handle overnight times (e.g. end_time past midnight = 25:30 mapping)
    # If end < start, assume it wraps past midnight
    if e1 <= s1:
        e1 += 24 * 60
    if e2 <= s2:
        e2 += 24 * 60

    # Two intervals [s1, e1) and [s2, e2) overlap if s1 < e2 and s2 < e1
    return s1 < e2 and s2 < e1


# ---------------------------------------------------------------------------
# ConflictDetector
# ---------------------------------------------------------------------------

class ConflictDetector:
    """偵測排程結果中的資源衝突。

    Orchestrates all conflict checks and returns a list of Conflict objects.
    Also updates each entry's conflict_flag and conflict_reason fields.
    """

    def __init__(self, rules: Any = None):
        """
        Initialize ConflictDetector with scheduling rules.

        Args:
            rules: A ScheduleRules dataclass or dict containing:
                - marker_rules: dict mapping marker name -> MarkerRuleInfo or dict
                - machine_capacities: dict mapping machine_id -> MachineCapacityInfo or dict
                - operator_rules: dict mapping operator_name -> OperatorInfo or dict
                - all_machines: list of all machine IDs
                - all_dryers: list of all dryer IDs
                - all_operators: list of all operator names
                Or a simpler dict with:
                - 'freezer_rules': {marker: {dryers: [...], quantity: ...}}
                - 'pump_no': {marker: [machines...]}
                - 'dispensing_limit': {marker: {operators: [...], ...}}
                - 'dryer_capacity': {dryer_id: max_concurrent}
        """
        self.rules = rules or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_all(self, schedule_entries: list) -> list[Conflict]:
        """
        偵測所有衝突類型。

        Runs all 5 check methods, updates entry conflict_flag/conflict_reason,
        and returns a consolidated list of Conflict objects.

        Args:
            schedule_entries: List of schedule entry dicts or model objects.
                Each entry should have: id, date, marker, machine_port,
                freeze_dryer, operator, rd_time, start_time, end_time,
                conflict_flag, conflict_reason.

        Returns:
            List of Conflict objects detected across all checks.
        """
        if not schedule_entries:
            return []

        all_conflicts: list[Conflict] = []

        # Run all checks
        all_conflicts.extend(self._check_machine_port_overlap(schedule_entries))
        all_conflicts.extend(self._check_dryer_capacity(schedule_entries))
        all_conflicts.extend(self._check_operator_overlap(schedule_entries))
        all_conflicts.extend(self._check_production_flow(schedule_entries))
        all_conflicts.extend(self._check_base_rule_compliance(schedule_entries))

        # Update entries with conflict information
        self._update_entries(schedule_entries, all_conflicts)

        logger.info(
            f"[ConflictDetector] Detected {len(all_conflicts)} conflicts "
            f"across {len(schedule_entries)} entries."
        )

        return all_conflicts

    # ------------------------------------------------------------------
    # Check Methods
    # ------------------------------------------------------------------

    def _check_machine_port_overlap(self, entries: list) -> list[Conflict]:
        """
        檢查 Machine_Port 時間重疊。

        For each pair of entries on the same machine_port AND same date,
        check if their time intervals [start_time, end_time) overlap.

        Returns:
            List of Conflict objects for overlapping machine port usage.
        """
        conflicts: list[Conflict] = []

        # Group entries by (machine_port, date)
        groups: dict[tuple, list] = defaultdict(list)
        for entry in entries:
            port = _get(entry, 'machine_port')
            entry_date = _parse_date(_get(entry, 'date'))
            if port and entry_date:
                groups[(port, entry_date)].append(entry)

        # Check each group for overlaps
        for (port, entry_date), group in groups.items():
            if len(group) < 2:
                continue

            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    e1 = group[i]
                    e2 = group[j]

                    start1 = _parse_time(_get(e1, 'start_time'))
                    end1 = _parse_time(_get(e1, 'end_time'))
                    start2 = _parse_time(_get(e2, 'start_time'))
                    end2 = _parse_time(_get(e2, 'end_time'))

                    if _times_overlap(start1, end1, start2, end2):
                        id1 = _get(e1, 'id')
                        id2 = _get(e2, 'id')
                        marker1 = _get(e1, 'marker', '?')
                        marker2 = _get(e2, 'marker', '?')

                        desc = (
                            f"Machine_Port {port} 在 {entry_date} "
                            f"時段重疊: {marker1}({start1}-{end1}) "
                            f"與 {marker2}({start2}-{end2})"
                        )

                        conflicts.append(Conflict(
                            entry_id=id1,
                            conflict_type='machine_overlap',
                            description=desc,
                            severity='error',
                        ))
                        conflicts.append(Conflict(
                            entry_id=id2,
                            conflict_type='machine_overlap',
                            description=desc,
                            severity='error',
                        ))

        return conflicts

    def _check_dryer_capacity(self, entries: list) -> list[Conflict]:
        """
        檢查 Freeze_Dryer 超容。

        Group entries by (freeze_dryer, date), count usage,
        and check against max_concurrent from rules.

        Returns:
            List of Conflict objects for dryer over-capacity.
        """
        conflicts: list[Conflict] = []

        # Determine max_concurrent per dryer
        max_concurrent_map = self._get_dryer_max_concurrent()

        # Group entries by (freeze_dryer, date)
        groups: dict[tuple, list] = defaultdict(list)
        for entry in entries:
            dryer = _get(entry, 'freeze_dryer')
            entry_date = _parse_date(_get(entry, 'date'))
            if dryer and entry_date:
                groups[(dryer, entry_date)].append(entry)

        # Check each group
        for (dryer, entry_date), group in groups.items():
            max_cap = max_concurrent_map.get(dryer, 2)  # default 2 for dryers

            if len(group) > max_cap:
                desc = (
                    f"Freeze_Dryer {dryer} 在 {entry_date} "
                    f"同時使用 {len(group)} 批次，超過容量上限 {max_cap}"
                )
                for entry in group:
                    conflicts.append(Conflict(
                        entry_id=_get(entry, 'id'),
                        conflict_type='dryer_capacity',
                        description=desc,
                        severity='error',
                    ))

        return conflicts

    def _check_operator_overlap(self, entries: list) -> list[Conflict]:
        """
        檢查 Operator 準備區間重疊。

        For entries with the same operator on the same day, check if their
        prepare intervals overlap. The prepare interval is defined as:
        [operator_prepare_start, rd_time (DrugGivenAt)].

        If rd_time is not available, fallback to start_time as the end
        of the prepare interval. If neither is available, skip.

        Returns:
            List of Conflict objects for overlapping operator prepare intervals.
        """
        conflicts: list[Conflict] = []

        # Group entries by (operator, date)
        groups: dict[tuple, list] = defaultdict(list)
        for entry in entries:
            operator = _get(entry, 'operator')
            entry_date = _parse_date(_get(entry, 'date'))
            if operator and entry_date:
                groups[(operator, entry_date)].append(entry)

        # Check each group for prepare interval overlaps
        for (operator, entry_date), group in groups.items():
            if len(group) < 2:
                continue

            # Compute prepare intervals for each entry
            # Prepare interval: [prep_start, drug_given_at or start_time]
            # prep_start is estimated as 30 minutes before rd_time or start_time
            prep_intervals = []
            for entry in group:
                rd = _parse_time(_get(entry, 'rd_time'))
                start = _parse_time(_get(entry, 'start_time'))

                # End of prepare interval = rd_time (DrugGivenAt) or start_time
                prep_end = rd or start
                if prep_end is None:
                    continue

                # Start of prepare interval = 30 min before prep_end (default estimate)
                prep_end_minutes = _time_to_minutes(prep_end)
                prep_start_minutes = max(0, prep_end_minutes - 30)
                prep_start = time(prep_start_minutes // 60, prep_start_minutes % 60)

                prep_intervals.append((entry, prep_start, prep_end))

            # Check pairwise overlaps
            for i in range(len(prep_intervals)):
                for j in range(i + 1, len(prep_intervals)):
                    e1, ps1, pe1 = prep_intervals[i]
                    e2, ps2, pe2 = prep_intervals[j]

                    if _times_overlap(ps1, pe1, ps2, pe2):
                        id1 = _get(e1, 'id')
                        id2 = _get(e2, 'id')
                        marker1 = _get(e1, 'marker', '?')
                        marker2 = _get(e2, 'marker', '?')

                        desc = (
                            f"Operator {operator} 在 {entry_date} "
                            f"準備區間重疊: {marker1}({ps1}-{pe1}) "
                            f"與 {marker2}({ps2}-{pe2})"
                        )

                        conflicts.append(Conflict(
                            entry_id=id1,
                            conflict_type='operator_overlap',
                            description=desc,
                            severity='error',
                        ))
                        conflicts.append(Conflict(
                            entry_id=id2,
                            conflict_type='operator_overlap',
                            description=desc,
                            severity='error',
                        ))

        return conflicts

    def _check_production_flow(self, entries: list) -> list[Conflict]:
        """
        檢查生產流程順序。

        Verify that each entry's times follow the production flow:
        dispensing → titration → freeze ordering.

        For each entry:
        - rd_time (DrugGivenAt) should be <= start_time (titration start)
        - start_time (titration start) should be <= end_time (titration end)

        The dispensing phase ends at rd_time, titration runs from start_time
        to end_time, and freeze-drying starts after end_time.

        Returns:
            List of Conflict objects for production flow violations.
        """
        conflicts: list[Conflict] = []

        for entry in entries:
            entry_id = _get(entry, 'id')
            marker = _get(entry, 'marker', '?')

            rd = _parse_time(_get(entry, 'rd_time'))
            start = _parse_time(_get(entry, 'start_time'))
            end = _parse_time(_get(entry, 'end_time'))

            # Check dispensing → titration ordering (rd_time <= start_time)
            if rd and start:
                rd_min = _time_to_minutes(rd)
                start_min = _time_to_minutes(start)
                if rd_min > start_min:
                    desc = (
                        f"生產流程順序違規: {marker} 的配藥時間(rd_time={rd}) "
                        f"晚於滴定開始時間(start_time={start})"
                    )
                    conflicts.append(Conflict(
                        entry_id=entry_id,
                        conflict_type='production_flow',
                        description=desc,
                        severity='error',
                    ))

            # Check titration ordering (start_time <= end_time)
            if start and end:
                start_min = _time_to_minutes(start)
                end_min = _time_to_minutes(end)
                # Handle overnight: if end_time < start_time and diff > 12 hours, it's likely overnight
                if end_min < start_min and (start_min - end_min) < 12 * 60:
                    desc = (
                        f"生產流程順序違規: {marker} 的滴定開始時間(start_time={start}) "
                        f"晚於結束時間(end_time={end})"
                    )
                    conflicts.append(Conflict(
                        entry_id=entry_id,
                        conflict_type='production_flow',
                        description=desc,
                        severity='error',
                    ))

        return conflicts

    def _check_base_rule_compliance(self, entries: list) -> list[Conflict]:
        """
        檢查資源分配是否符合基準規則。

        Verify that each entry's assigned machine_port, freeze_dryer,
        and operator are within the allowed sets defined in Base_Rule_Tables.

        Only produces warnings if rules are available and the assignment
        violates the allowed set.

        Returns:
            List of Conflict objects for base rule violations.
        """
        conflicts: list[Conflict] = []

        # Extract allowed resource sets from rules
        allowed_machines = self._get_allowed_machines_by_marker()
        allowed_dryers = self._get_allowed_dryers_by_marker()
        allowed_operators = self._get_allowed_operators_by_marker()

        # If no rules loaded, skip this check
        if not allowed_machines and not allowed_dryers and not allowed_operators:
            return conflicts

        for entry in entries:
            entry_id = _get(entry, 'id')
            marker = _get(entry, 'marker')
            if not marker:
                continue

            # Check machine_port
            port = _get(entry, 'machine_port')
            if port and marker in allowed_machines:
                allowed = allowed_machines[marker]
                if allowed and port not in allowed:
                    desc = (
                        f"基準規則違規: {marker} 分配機台 {port} "
                        f"不在允許清單 {allowed} 中"
                    )
                    conflicts.append(Conflict(
                        entry_id=entry_id,
                        conflict_type='base_rule_violation',
                        description=desc,
                        severity='warning',
                    ))

            # Check freeze_dryer
            dryer = _get(entry, 'freeze_dryer')
            if dryer and marker in allowed_dryers:
                allowed = allowed_dryers[marker]
                if allowed and dryer not in allowed:
                    desc = (
                        f"基準規則違規: {marker} 分配凍乾機 {dryer} "
                        f"不在允許清單 {allowed} 中"
                    )
                    conflicts.append(Conflict(
                        entry_id=entry_id,
                        conflict_type='base_rule_violation',
                        description=desc,
                        severity='warning',
                    ))

            # Check operator
            operator = _get(entry, 'operator')
            if operator and marker in allowed_operators:
                allowed = allowed_operators[marker]
                if allowed and operator not in allowed:
                    desc = (
                        f"基準規則違規: {marker} 分配操作員 {operator} "
                        f"不在允許清單 {allowed} 中"
                    )
                    conflicts.append(Conflict(
                        entry_id=entry_id,
                        conflict_type='base_rule_violation',
                        description=desc,
                        severity='warning',
                    ))

        return conflicts

    # ------------------------------------------------------------------
    # Entry Update
    # ------------------------------------------------------------------

    def _update_entries(self, entries: list, conflicts: list[Conflict]) -> None:
        """
        Update entries' conflict_flag and conflict_reason based on detected conflicts.

        Groups conflicts by entry_id and sets:
        - conflict_flag = True for entries with any conflict
        - conflict_reason = concatenated descriptions of all conflicts for that entry
        """
        # Group conflicts by entry_id
        conflicts_by_entry: dict[Any, list[str]] = defaultdict(list)
        for conflict in conflicts:
            conflicts_by_entry[conflict.entry_id].append(conflict.description)

        # Update each entry
        for entry in entries:
            entry_id = _get(entry, 'id')
            if entry_id in conflicts_by_entry:
                reasons = '; '.join(conflicts_by_entry[entry_id])
                if isinstance(entry, dict):
                    entry['conflict_flag'] = True
                    entry['conflict_reason'] = reasons
                else:
                    entry.conflict_flag = True
                    entry.conflict_reason = reasons
            else:
                # Clear conflict if no conflicts found
                if isinstance(entry, dict):
                    entry['conflict_flag'] = False
                    entry['conflict_reason'] = None
                else:
                    entry.conflict_flag = False
                    entry.conflict_reason = None

    # ------------------------------------------------------------------
    # Rules Extraction Helpers
    # ------------------------------------------------------------------

    def _get_dryer_max_concurrent(self) -> dict[str, int]:
        """
        Extract max_concurrent values per dryer from rules.

        Returns:
            Dict mapping dryer_id -> max_concurrent.
        """
        result: dict[str, int] = {}

        if not self.rules:
            return result

        # ScheduleRules dataclass format
        if hasattr(self.rules, 'machine_capacities'):
            for machine_id, cap_info in self.rules.machine_capacities.items():
                if hasattr(cap_info, 'machine_type'):
                    if cap_info.machine_type == 'dryer':
                        result[machine_id] = cap_info.max_concurrent
                elif isinstance(cap_info, dict):
                    if cap_info.get('machine_type') == 'dryer':
                        result[machine_id] = cap_info.get('max_concurrent', 2)
        # Simple dict format with 'dryer_capacity' key
        elif isinstance(self.rules, dict):
            dryer_cap = self.rules.get('dryer_capacity', {})
            if isinstance(dryer_cap, dict):
                for dryer_id, max_c in dryer_cap.items():
                    result[dryer_id] = int(max_c) if max_c else 2

        return result

    def _get_allowed_machines_by_marker(self) -> dict[str, list[str]]:
        """
        Extract allowed machine_ports per marker from rules.

        Returns:
            Dict mapping marker_name -> list of allowed machine IDs.
        """
        result: dict[str, list[str]] = {}

        if not self.rules:
            return result

        # ScheduleRules dataclass format
        if hasattr(self.rules, 'marker_rules'):
            for marker_name, info in self.rules.marker_rules.items():
                if hasattr(info, 'allowed_machines'):
                    result[marker_name] = info.allowed_machines
                elif isinstance(info, dict):
                    result[marker_name] = info.get('allowed_machines', [])
        # Simple dict format with 'pump_no' key
        elif isinstance(self.rules, dict):
            pump_no = self.rules.get('pump_no', {})
            if isinstance(pump_no, dict):
                for marker, machines in pump_no.items():
                    result[marker] = machines if isinstance(machines, list) else []

        return result

    def _get_allowed_dryers_by_marker(self) -> dict[str, list[str]]:
        """
        Extract allowed freeze_dryers per marker from rules.

        Returns:
            Dict mapping marker_name -> list of allowed dryer IDs.
        """
        result: dict[str, list[str]] = {}

        if not self.rules:
            return result

        # ScheduleRules dataclass format
        if hasattr(self.rules, 'marker_rules'):
            for marker_name, info in self.rules.marker_rules.items():
                if hasattr(info, 'allowed_dryers'):
                    result[marker_name] = info.allowed_dryers
                elif isinstance(info, dict):
                    result[marker_name] = info.get('allowed_dryers', [])
        # Simple dict format with 'freezer_rules' key
        elif isinstance(self.rules, dict):
            freezer_rules = self.rules.get('freezer_rules', {})
            if isinstance(freezer_rules, dict):
                for marker, rule in freezer_rules.items():
                    if isinstance(rule, dict):
                        result[marker] = rule.get('dryers', [])
                    elif isinstance(rule, list):
                        result[marker] = rule

        return result

    def _get_allowed_operators_by_marker(self) -> dict[str, list[str]]:
        """
        Extract allowed operators per marker from rules.

        Returns:
            Dict mapping marker_name -> list of allowed operator names.
        """
        result: dict[str, list[str]] = {}

        if not self.rules:
            return result

        # ScheduleRules dataclass format
        if hasattr(self.rules, 'marker_rules'):
            for marker_name, info in self.rules.marker_rules.items():
                if hasattr(info, 'allowed_operators'):
                    result[marker_name] = info.allowed_operators
                elif isinstance(info, dict):
                    result[marker_name] = info.get('allowed_operators', [])
        # Simple dict format with 'dispensing_limit' key
        elif isinstance(self.rules, dict):
            disp_limit = self.rules.get('dispensing_limit', {})
            if isinstance(disp_limit, dict):
                for marker, rule in disp_limit.items():
                    if isinstance(rule, dict):
                        result[marker] = rule.get('operators', [])
                    elif isinstance(rule, list):
                        result[marker] = rule

        return result
