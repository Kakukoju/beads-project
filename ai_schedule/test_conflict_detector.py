"""
Tests for ConflictDetector — verifies all conflict detection types.
"""

import pytest
from datetime import date, time

from ai_schedule.conflict_detector import (
    Conflict,
    ConflictDetector,
    _parse_time,
    _parse_date,
    _times_overlap,
    _time_to_minutes,
)


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------

class TestParseTime:
    def test_none(self):
        assert _parse_time(None) is None

    def test_time_object(self):
        t = time(14, 30)
        assert _parse_time(t) == time(14, 30)

    def test_string_hhmm(self):
        assert _parse_time("14:30") == time(14, 30)

    def test_string_hhmmss(self):
        assert _parse_time("14:30:00") == time(14, 30, 0)

    def test_empty_string(self):
        assert _parse_time("") is None
        assert _parse_time("  ") is None


class TestParseDate:
    def test_none(self):
        assert _parse_date(None) is None

    def test_date_object(self):
        d = date(2026, 6, 8)
        assert _parse_date(d) == date(2026, 6, 8)

    def test_string_iso(self):
        assert _parse_date("2026-06-08") == date(2026, 6, 8)

    def test_empty_string(self):
        assert _parse_date("") is None


class TestTimesOverlap:
    def test_no_overlap(self):
        assert _times_overlap(
            time(10, 0), time(12, 0),
            time(13, 0), time(15, 0)
        ) is False

    def test_overlap(self):
        assert _times_overlap(
            time(10, 0), time(13, 0),
            time(12, 0), time(15, 0)
        ) is True

    def test_adjacent_no_overlap(self):
        # [10:00, 12:00) and [12:00, 14:00) should NOT overlap
        assert _times_overlap(
            time(10, 0), time(12, 0),
            time(12, 0), time(14, 0)
        ) is False

    def test_contained(self):
        assert _times_overlap(
            time(10, 0), time(16, 0),
            time(12, 0), time(14, 0)
        ) is True

    def test_none_values(self):
        assert _times_overlap(None, time(12, 0), time(13, 0), time(15, 0)) is False


# ---------------------------------------------------------------------------
# ConflictDetector tests
# ---------------------------------------------------------------------------

class TestMachinePortOverlap:
    def test_no_overlap_different_ports(self):
        """Two entries on different ports should not conflict."""
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': 'P1',
             'freeze_dryer': None, 'operator': None, 'rd_time': None,
             'start_time': '10:00', 'end_time': '12:00', 'conflict_flag': False, 'conflict_reason': None},
            {'id': 2, 'date': '2026-06-08', 'marker': 'B', 'machine_port': 'P2',
             'freeze_dryer': None, 'operator': None, 'rd_time': None,
             'start_time': '10:00', 'end_time': '12:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector()
        conflicts = detector._check_machine_port_overlap(entries)
        assert len(conflicts) == 0

    def test_overlap_same_port_same_day(self):
        """Two entries on the same port with overlapping times should conflict."""
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': 'P3',
             'freeze_dryer': None, 'operator': None, 'rd_time': None,
             'start_time': '14:00', 'end_time': '16:00', 'conflict_flag': False, 'conflict_reason': None},
            {'id': 2, 'date': '2026-06-08', 'marker': 'B', 'machine_port': 'P3',
             'freeze_dryer': None, 'operator': None, 'rd_time': None,
             'start_time': '15:00', 'end_time': '17:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector()
        conflicts = detector._check_machine_port_overlap(entries)
        assert len(conflicts) == 2  # Both entries flagged
        assert all(c.conflict_type == 'machine_overlap' for c in conflicts)

    def test_no_overlap_same_port_different_day(self):
        """Same port but different days should not conflict."""
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': 'P3',
             'freeze_dryer': None, 'operator': None, 'rd_time': None,
             'start_time': '14:00', 'end_time': '16:00', 'conflict_flag': False, 'conflict_reason': None},
            {'id': 2, 'date': '2026-06-09', 'marker': 'B', 'machine_port': 'P3',
             'freeze_dryer': None, 'operator': None, 'rd_time': None,
             'start_time': '14:00', 'end_time': '16:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector()
        conflicts = detector._check_machine_port_overlap(entries)
        assert len(conflicts) == 0

    def test_adjacent_times_no_conflict(self):
        """Adjacent time slots (no overlap) should not conflict."""
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': 'P3',
             'freeze_dryer': None, 'operator': None, 'rd_time': None,
             'start_time': '10:00', 'end_time': '12:00', 'conflict_flag': False, 'conflict_reason': None},
            {'id': 2, 'date': '2026-06-08', 'marker': 'B', 'machine_port': 'P3',
             'freeze_dryer': None, 'operator': None, 'rd_time': None,
             'start_time': '12:00', 'end_time': '14:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector()
        conflicts = detector._check_machine_port_overlap(entries)
        assert len(conflicts) == 0


class TestDryerCapacity:
    def test_within_capacity(self):
        """Two entries on dryer with max_concurrent=2 should be fine."""
        rules = {
            'dryer_capacity': {'FD1': 2}
        }
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': None,
             'freeze_dryer': 'FD1', 'operator': None, 'rd_time': None,
             'start_time': '10:00', 'end_time': '12:00', 'conflict_flag': False, 'conflict_reason': None},
            {'id': 2, 'date': '2026-06-08', 'marker': 'B', 'machine_port': None,
             'freeze_dryer': 'FD1', 'operator': None, 'rd_time': None,
             'start_time': '10:00', 'end_time': '12:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector(rules)
        conflicts = detector._check_dryer_capacity(entries)
        assert len(conflicts) == 0

    def test_over_capacity(self):
        """Three entries on dryer with max_concurrent=2 should conflict."""
        rules = {
            'dryer_capacity': {'FD1': 2}
        }
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': None,
             'freeze_dryer': 'FD1', 'operator': None, 'rd_time': None,
             'start_time': '10:00', 'end_time': '12:00', 'conflict_flag': False, 'conflict_reason': None},
            {'id': 2, 'date': '2026-06-08', 'marker': 'B', 'machine_port': None,
             'freeze_dryer': 'FD1', 'operator': None, 'rd_time': None,
             'start_time': '10:00', 'end_time': '12:00', 'conflict_flag': False, 'conflict_reason': None},
            {'id': 3, 'date': '2026-06-08', 'marker': 'C', 'machine_port': None,
             'freeze_dryer': 'FD1', 'operator': None, 'rd_time': None,
             'start_time': '11:00', 'end_time': '13:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector(rules)
        conflicts = detector._check_dryer_capacity(entries)
        assert len(conflicts) == 3  # All 3 entries flagged
        assert all(c.conflict_type == 'dryer_capacity' for c in conflicts)

    def test_different_dates_no_conflict(self):
        """Same dryer on different dates should not exceed capacity."""
        rules = {
            'dryer_capacity': {'FD1': 1}
        }
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': None,
             'freeze_dryer': 'FD1', 'operator': None, 'rd_time': None,
             'start_time': '10:00', 'end_time': '12:00', 'conflict_flag': False, 'conflict_reason': None},
            {'id': 2, 'date': '2026-06-09', 'marker': 'B', 'machine_port': None,
             'freeze_dryer': 'FD1', 'operator': None, 'rd_time': None,
             'start_time': '10:00', 'end_time': '12:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector(rules)
        conflicts = detector._check_dryer_capacity(entries)
        assert len(conflicts) == 0


class TestOperatorOverlap:
    def test_no_overlap(self):
        """Two entries with same operator but non-overlapping prep intervals."""
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': None,
             'freeze_dryer': None, 'operator': 'OP1', 'rd_time': '10:30',
             'start_time': '11:00', 'end_time': '13:00', 'conflict_flag': False, 'conflict_reason': None},
            {'id': 2, 'date': '2026-06-08', 'marker': 'B', 'machine_port': None,
             'freeze_dryer': None, 'operator': 'OP1', 'rd_time': '14:00',
             'start_time': '14:30', 'end_time': '16:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector()
        conflicts = detector._check_operator_overlap(entries)
        assert len(conflicts) == 0

    def test_overlap(self):
        """Two entries with same operator and overlapping prep intervals."""
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': None,
             'freeze_dryer': None, 'operator': 'OP1', 'rd_time': '10:30',
             'start_time': '11:00', 'end_time': '13:00', 'conflict_flag': False, 'conflict_reason': None},
            {'id': 2, 'date': '2026-06-08', 'marker': 'B', 'machine_port': None,
             'freeze_dryer': None, 'operator': 'OP1', 'rd_time': '10:20',
             'start_time': '10:30', 'end_time': '12:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector()
        conflicts = detector._check_operator_overlap(entries)
        assert len(conflicts) == 2  # Both entries flagged
        assert all(c.conflict_type == 'operator_overlap' for c in conflicts)

    def test_different_operators_no_conflict(self):
        """Different operators should never conflict with each other."""
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': None,
             'freeze_dryer': None, 'operator': 'OP1', 'rd_time': '10:30',
             'start_time': '11:00', 'end_time': '13:00', 'conflict_flag': False, 'conflict_reason': None},
            {'id': 2, 'date': '2026-06-08', 'marker': 'B', 'machine_port': None,
             'freeze_dryer': None, 'operator': 'OP2', 'rd_time': '10:30',
             'start_time': '11:00', 'end_time': '13:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector()
        conflicts = detector._check_operator_overlap(entries)
        assert len(conflicts) == 0


class TestProductionFlow:
    def test_valid_flow(self):
        """Valid production flow: rd_time <= start_time <= end_time."""
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': None,
             'freeze_dryer': None, 'operator': None, 'rd_time': '14:00',
             'start_time': '14:30', 'end_time': '18:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector()
        conflicts = detector._check_production_flow(entries)
        assert len(conflicts) == 0

    def test_rd_after_start(self):
        """Invalid: rd_time after start_time (dispensing after titration)."""
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': None,
             'freeze_dryer': None, 'operator': None, 'rd_time': '15:00',
             'start_time': '14:30', 'end_time': '18:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector()
        conflicts = detector._check_production_flow(entries)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == 'production_flow'

    def test_start_after_end(self):
        """Invalid: start_time after end_time (within same day, not overnight)."""
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': None,
             'freeze_dryer': None, 'operator': None, 'rd_time': '14:00',
             'start_time': '18:00', 'end_time': '16:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector()
        conflicts = detector._check_production_flow(entries)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == 'production_flow'

    def test_missing_times_no_conflict(self):
        """Missing times should not produce conflicts."""
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': None,
             'freeze_dryer': None, 'operator': None, 'rd_time': None,
             'start_time': None, 'end_time': None, 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector()
        conflicts = detector._check_production_flow(entries)
        assert len(conflicts) == 0


class TestBaseRuleCompliance:
    def test_compliant(self):
        """Entry using allowed resources should not conflict."""
        rules = {
            'pump_no': {'tCREA-D': ['P3', 'P5']},
            'freezer_rules': {'tCREA-D': {'dryers': ['5', '6']}},
            'dispensing_limit': {'tCREA-D': {'operators': ['張三', '李四']}},
        }
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'tCREA-D', 'machine_port': 'P3',
             'freeze_dryer': '5', 'operator': '張三', 'rd_time': '14:00',
             'start_time': '14:30', 'end_time': '18:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector(rules)
        conflicts = detector._check_base_rule_compliance(entries)
        assert len(conflicts) == 0

    def test_non_compliant_machine(self):
        """Entry using a disallowed machine should produce a warning."""
        rules = {
            'pump_no': {'tCREA-D': ['P3', 'P5']},
            'freezer_rules': {},
            'dispensing_limit': {},
        }
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'tCREA-D', 'machine_port': 'P7',
             'freeze_dryer': None, 'operator': None, 'rd_time': None,
             'start_time': '14:30', 'end_time': '18:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector(rules)
        conflicts = detector._check_base_rule_compliance(entries)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == 'base_rule_violation'
        assert conflicts[0].severity == 'warning'

    def test_no_rules_no_conflict(self):
        """If no rules are loaded, base rule check should not produce conflicts."""
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'tCREA-D', 'machine_port': 'P7',
             'freeze_dryer': '99', 'operator': 'Unknown', 'rd_time': None,
             'start_time': '14:30', 'end_time': '18:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector()
        conflicts = detector._check_base_rule_compliance(entries)
        assert len(conflicts) == 0


class TestDetectAll:
    def test_empty_entries(self):
        """Empty entries should return no conflicts."""
        detector = ConflictDetector()
        conflicts = detector.detect_all([])
        assert conflicts == []

    def test_combined_conflicts(self):
        """detect_all should find conflicts from multiple check types."""
        rules = {
            'pump_no': {'A': ['P1']},
            'freezer_rules': {},
            'dispensing_limit': {},
        }
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': 'P3',
             'freeze_dryer': None, 'operator': None, 'rd_time': '15:00',
             'start_time': '14:30', 'end_time': '18:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector(rules)
        conflicts = detector.detect_all(entries)

        # Should have at least production_flow + base_rule_violation
        types = {c.conflict_type for c in conflicts}
        assert 'production_flow' in types
        assert 'base_rule_violation' in types

    def test_updates_entry_flags(self):
        """detect_all should update conflict_flag and conflict_reason on entries."""
        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'A', 'machine_port': 'P3',
             'freeze_dryer': None, 'operator': None, 'rd_time': '15:00',
             'start_time': '14:30', 'end_time': '18:00', 'conflict_flag': False, 'conflict_reason': None},
            {'id': 2, 'date': '2026-06-08', 'marker': 'B', 'machine_port': 'P5',
             'freeze_dryer': None, 'operator': None, 'rd_time': '10:00',
             'start_time': '10:30', 'end_time': '12:00', 'conflict_flag': False, 'conflict_reason': None},
        ]
        detector = ConflictDetector()
        detector.detect_all(entries)

        # Entry 1 should be flagged (production_flow violation)
        assert entries[0]['conflict_flag'] is True
        assert entries[0]['conflict_reason'] is not None

        # Entry 2 should not be flagged
        assert entries[1]['conflict_flag'] is False
        assert entries[1]['conflict_reason'] is None


class TestScheduleRulesFormat:
    """Test with ScheduleRules-style dataclass rules."""

    def test_with_schedule_rules_object(self):
        """ConflictDetector should work with ScheduleRules dataclass objects."""
        from ai_schedule.scheduling_engine import ScheduleRules, MarkerRuleInfo, MachineCapacityInfo

        rules = ScheduleRules(
            marker_rules={
                'tCREA-D': MarkerRuleInfo(
                    marker_name='tCREA-D',
                    allowed_machines=['P3', 'P5'],
                    allowed_dryers=['5', '6'],
                    allowed_operators=['張三'],
                ),
            },
            machine_capacities={
                '5': MachineCapacityInfo(machine_id='5', machine_type='dryer', max_concurrent=2),
            },
            all_machines=['P3', 'P5'],
            all_dryers=['5', '6'],
            all_operators=['張三'],
        )

        entries = [
            {'id': 1, 'date': '2026-06-08', 'marker': 'tCREA-D', 'machine_port': 'P3',
             'freeze_dryer': '5', 'operator': '張三', 'rd_time': '14:00',
             'start_time': '14:30', 'end_time': '18:00', 'conflict_flag': False, 'conflict_reason': None},
        ]

        detector = ConflictDetector(rules)
        conflicts = detector.detect_all(entries)
        assert len(conflicts) == 0
        assert entries[0]['conflict_flag'] is False
