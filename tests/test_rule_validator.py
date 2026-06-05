"""
Unit tests for ai_schedule/rule_validator.py

Tests the rule validation logic, conflict detection, and auto-correction
without requiring a real database connection.
"""

import sys
import os
import json
from unittest.mock import MagicMock, patch, call

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock the mrpFlask_5 module before importing rule_validator
sys.modules['mrpFlask_5'] = MagicMock()

from ai_schedule.rule_validator import (
    RuleValidator,
    RuleConflict,
    CorrectionResult,
    ValidationReport,
    _parse_jsonb,
    _parse_quantity_range,
    _quantity_in_range,
)


# ---------------------------------------------------------------------------
# Helper: Fake DB session that can be configured with data
# ---------------------------------------------------------------------------

class FakeResult:
    """Fake SQLAlchemy result set."""

    def __init__(self, rows, columns):
        self._rows = rows
        self._columns = columns

    def fetchall(self):
        return self._rows

    def keys(self):
        return self._columns


class FakeDBSession:
    """Fake DB session that returns configurable results based on query text."""

    def __init__(self):
        self.query_results = {}
        self.executed_queries = []
        self.committed = False
        self.rolled_back = False

    def execute(self, query, params=None):
        self.executed_queries.append((str(query), params))
        query_str = str(query)

        # Match based on table name in query
        for key, result in self.query_results.items():
            if key in query_str:
                return result

        # Default: empty result
        return FakeResult([], [])

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


# ---------------------------------------------------------------------------
# Tests for helper functions
# ---------------------------------------------------------------------------

class TestParseJsonb:
    """Test _parse_jsonb helper."""

    def test_none_returns_empty(self):
        assert _parse_jsonb(None) == []

    def test_list_passthrough(self):
        assert _parse_jsonb(["P3", "P5"]) == ["P3", "P5"]

    def test_json_string(self):
        assert _parse_jsonb('["P3", "P5"]') == ["P3", "P5"]

    def test_invalid_string(self):
        assert _parse_jsonb("not json") == []

    def test_empty_list(self):
        assert _parse_jsonb([]) == []

    def test_json_empty_list_string(self):
        assert _parse_jsonb("[]") == []


class TestParseQuantityRange:
    """Test _parse_quantity_range helper."""

    def test_none_returns_empty(self):
        assert _parse_quantity_range(None) == []

    def test_single_int(self):
        assert _parse_quantity_range(2700) == [2700]

    def test_single_int_string(self):
        assert _parse_quantity_range("2700") == [2700]

    def test_or_format(self):
        result = _parse_quantity_range("2700 or 11000")
        assert 2700 in result
        assert 11000 in result

    def test_range_format(self):
        result = _parse_quantity_range("1300-2700")
        assert result == [1300, 2700]

    def test_nan_returns_empty(self):
        assert _parse_quantity_range("nan") == []

    def test_zero_returns_empty(self):
        assert _parse_quantity_range("0") == []


class TestQuantityInRange:
    """Test _quantity_in_range helper."""

    def test_empty_range_passes(self):
        assert _quantity_in_range(5000, []) is True

    def test_zero_quantity_passes(self):
        assert _quantity_in_range(0, [1300, 2700]) is True

    def test_within_range(self):
        assert _quantity_in_range(1500, [1300, 2700]) is True

    def test_at_range_boundaries(self):
        assert _quantity_in_range(1300, [1300, 2700]) is True
        assert _quantity_in_range(2700, [1300, 2700]) is True

    def test_outside_range(self):
        assert _quantity_in_range(5000, [1300, 2700]) is False

    def test_exact_match_set(self):
        # Three values don't look like a range, so exact match with tolerance
        assert _quantity_in_range(2700, [2700, 11000, 1300]) is True

    def test_near_match_within_tolerance(self):
        # 10% tolerance: 2700 ± 270 = [2430, 2970]
        assert _quantity_in_range(2650, [2700]) is True

    def test_outside_tolerance(self):
        # 10% tolerance: 2700 ± 270 = [2430, 2970]
        assert _quantity_in_range(2000, [2700]) is False


# ---------------------------------------------------------------------------
# Tests for RuleValidator
# ---------------------------------------------------------------------------

class TestValidateMarkerRules:
    """Test validate_marker_rules method."""

    def setup_method(self):
        self.db = FakeDBSession()
        self.validator = RuleValidator(self.db)

    def _setup_base_rules(self, freezer_rules=None, pump_no=None, dispensing_limit=None):
        """Directly set base rules to avoid DB calls."""
        self.validator._base_rules = {
            'freezer_rules': freezer_rules or {},
            'pump_no': pump_no or {},
            'dispensing_limit': dispensing_limit or {},
            'operator_markers': {},
        }

    def test_no_conflicts_when_subset(self):
        """No conflicts when derived rules are subset of base rules."""
        self._setup_base_rules(
            freezer_rules={'tCREA-D': {'dryers': ['3', '5', '7'], 'quantity': 2700}},
            pump_no={'tCREA-D': ['P3', 'P5', 'P7']},
        )
        # Mock marker_rule query
        self.db.query_results['marker_rule'] = FakeResult(
            rows=[(1, 'tCREA-D', '5714400180', json.dumps(['P3', 'P5']),
                   json.dumps(['5', '7']), json.dumps([]),
                   json.dumps([2700]), False)],
            columns=['id', 'marker_name', 'pn', 'common_machines',
                     'common_dryers', 'common_operators', 'common_quantities',
                     'base_rule_validated']
        )

        conflicts = self.validator.validate_marker_rules()
        assert len(conflicts) == 0

    def test_dryer_conflict_detected(self):
        """Conflict detected when common_dryers contains invalid dryer."""
        self._setup_base_rules(
            freezer_rules={'tCREA-D': {'dryers': ['3', '5'], 'quantity': None}},
            pump_no={'tCREA-D': ['P3', 'P5']},
        )
        self.db.query_results['marker_rule'] = FakeResult(
            rows=[(1, 'tCREA-D', '5714400180', json.dumps(['P3']),
                   json.dumps(['5', '9']), json.dumps([]),
                   json.dumps([]), False)],
            columns=['id', 'marker_name', 'pn', 'common_machines',
                     'common_dryers', 'common_operators', 'common_quantities',
                     'base_rule_validated']
        )

        conflicts = self.validator.validate_marker_rules()
        assert len(conflicts) == 1
        assert conflicts[0].field == 'common_dryers'
        assert '9' in conflicts[0].conflicting_values

    def test_machine_conflict_detected(self):
        """Conflict detected when common_machines contains invalid machine."""
        self._setup_base_rules(
            freezer_rules={'GGT': {'dryers': ['3'], 'quantity': None}},
            pump_no={'GGT': ['P1', 'P2']},
        )
        self.db.query_results['marker_rule'] = FakeResult(
            rows=[(1, 'GGT', '5714400132', json.dumps(['P1', 'P3']),
                   json.dumps(['3']), json.dumps([]),
                   json.dumps([]), False)],
            columns=['id', 'marker_name', 'pn', 'common_machines',
                     'common_dryers', 'common_operators', 'common_quantities',
                     'base_rule_validated']
        )

        conflicts = self.validator.validate_marker_rules()
        assert len(conflicts) == 1
        assert conflicts[0].field == 'common_machines'
        assert 'P3' in conflicts[0].conflicting_values

    def test_quantity_conflict_detected(self):
        """Conflict detected when common_quantities outside range."""
        self._setup_base_rules(
            freezer_rules={'tCREA-D': {'dryers': [], 'quantity': '1300-2700'}},
            pump_no={},
        )
        self.db.query_results['marker_rule'] = FakeResult(
            rows=[(1, 'tCREA-D', '5714400180', json.dumps([]),
                   json.dumps([]), json.dumps([]),
                   json.dumps([1300, 5000]), False)],
            columns=['id', 'marker_name', 'pn', 'common_machines',
                     'common_dryers', 'common_operators', 'common_quantities',
                     'base_rule_validated']
        )

        conflicts = self.validator.validate_marker_rules()
        assert len(conflicts) == 1
        assert conflicts[0].field == 'common_quantities'
        assert 5000 in conflicts[0].conflicting_values

    def test_no_base_rule_no_conflict(self):
        """No conflict when marker has no base rule entry (no constraint)."""
        self._setup_base_rules(
            freezer_rules={},  # No entry for this marker
            pump_no={},
        )
        self.db.query_results['marker_rule'] = FakeResult(
            rows=[(1, 'NewMarker', None, json.dumps(['P1']),
                   json.dumps(['5']), json.dumps([]),
                   json.dumps([1000]), False)],
            columns=['id', 'marker_name', 'pn', 'common_machines',
                     'common_dryers', 'common_operators', 'common_quantities',
                     'base_rule_validated']
        )

        conflicts = self.validator.validate_marker_rules()
        assert len(conflicts) == 0


class TestValidateOperatorRules:
    """Test validate_operator_rules method."""

    def setup_method(self):
        self.db = FakeDBSession()
        self.validator = RuleValidator(self.db)

    def test_no_conflicts_when_valid(self):
        """No conflicts when capable_markers match base rules."""
        self.validator._base_rules = {
            'freezer_rules': {},
            'pump_no': {},
            'dispensing_limit': {},
            'operator_markers': {'張三': ['tCREA-D', 'GGT', 'UA']},
        }
        self.db.query_results['operator_rule'] = FakeResult(
            rows=[(1, '張三', json.dumps(['tCREA-D', 'GGT']), False)],
            columns=['id', 'operator_name', 'capable_markers', 'base_rule_validated']
        )

        conflicts = self.validator.validate_operator_rules()
        assert len(conflicts) == 0

    def test_conflict_when_marker_not_allowed(self):
        """Conflict when capable_markers contains a marker not in 配藥限制."""
        self.validator._base_rules = {
            'freezer_rules': {},
            'pump_no': {},
            'dispensing_limit': {},
            'operator_markers': {'張三': ['tCREA-D', 'GGT']},
        }
        self.db.query_results['operator_rule'] = FakeResult(
            rows=[(1, '張三', json.dumps(['tCREA-D', 'GGT', 'InvalidMarker']), False)],
            columns=['id', 'operator_name', 'capable_markers', 'base_rule_validated']
        )

        conflicts = self.validator.validate_operator_rules()
        assert len(conflicts) == 1
        assert conflicts[0].field == 'capable_markers'
        assert 'InvalidMarker' in conflicts[0].conflicting_values

    def test_no_conflict_for_unknown_operator(self):
        """No conflict when operator not in base rules (no constraint)."""
        self.validator._base_rules = {
            'freezer_rules': {},
            'pump_no': {},
            'dispensing_limit': {},
            'operator_markers': {},  # No mapping for this operator
        }
        self.db.query_results['operator_rule'] = FakeResult(
            rows=[(1, '新人', json.dumps(['tCREA-D']), False)],
            columns=['id', 'operator_name', 'capable_markers', 'base_rule_validated']
        )

        conflicts = self.validator.validate_operator_rules()
        assert len(conflicts) == 0


class TestCorrectConflicts:
    """Test _correct_conflicts method."""

    def setup_method(self):
        self.db = FakeDBSession()
        self.validator = RuleValidator(self.db)

    def test_correct_dryer_conflict(self):
        """Dryer conflict corrected to intersection with base rules."""
        conflict = RuleConflict(
            rule_type='marker_rule',
            rule_name='tCREA-D',
            field='common_dryers',
            derived_values=['3', '5', '9'],
            allowed_values=['3', '5', '7'],
            conflicting_values=['9'],
            description='test',
        )

        corrections = self.validator._correct_conflicts([conflict])

        assert len(corrections) == 1
        assert corrections[0].corrected_values == ['3', '5']
        assert corrections[0].removed_values == ['9']

    def test_correct_machine_conflict(self):
        """Machine conflict corrected to intersection."""
        conflict = RuleConflict(
            rule_type='marker_rule',
            rule_name='GGT',
            field='common_machines',
            derived_values=['P1', 'P3', 'P5'],
            allowed_values=['P1', 'P2'],
            conflicting_values=['P3', 'P5'],
            description='test',
        )

        corrections = self.validator._correct_conflicts([conflict])

        assert len(corrections) == 1
        assert corrections[0].corrected_values == ['P1']
        assert set(corrections[0].removed_values) == {'P3', 'P5'}

    def test_correct_operator_conflict(self):
        """Operator capable_markers conflict corrected."""
        conflict = RuleConflict(
            rule_type='operator_rule',
            rule_name='張三',
            field='capable_markers',
            derived_values=['tCREA-D', 'GGT', 'Invalid'],
            allowed_values=['tCREA-D', 'GGT', 'UA'],
            conflicting_values=['Invalid'],
            description='test',
        )

        corrections = self.validator._correct_conflicts([conflict])

        assert len(corrections) == 1
        assert corrections[0].corrected_values == ['tCREA-D', 'GGT']
        assert corrections[0].removed_values == ['Invalid']

    def test_correct_quantity_conflict(self):
        """Quantity conflict keeps only in-range values."""
        conflict = RuleConflict(
            rule_type='marker_rule',
            rule_name='tCREA-D',
            field='common_quantities',
            derived_values=[1300, 2700, 5000],
            allowed_values=[1300, 2700],  # range
            conflicting_values=[5000],
            description='test',
        )

        corrections = self.validator._correct_conflicts([conflict])

        assert len(corrections) == 1
        assert 1300 in corrections[0].corrected_values
        assert 2700 in corrections[0].corrected_values
        assert 5000 not in corrections[0].corrected_values

    def test_db_update_called(self):
        """Database UPDATE is called during correction."""
        conflict = RuleConflict(
            rule_type='marker_rule',
            rule_name='tCREA-D',
            field='common_dryers',
            derived_values=['5', '9'],
            allowed_values=['3', '5'],
            conflicting_values=['9'],
            description='test',
        )

        self.validator._correct_conflicts([conflict])

        # Verify an UPDATE query was executed
        update_queries = [
            q for q, _ in self.db.executed_queries
            if 'UPDATE' in q
        ]
        assert len(update_queries) >= 1


class TestGenerateValidationReport:
    """Test generate_validation_report method."""

    def setup_method(self):
        self.db = FakeDBSession()
        self.validator = RuleValidator(self.db)

    def test_report_with_no_conflicts(self):
        """Report shows all passed when no conflicts exist."""
        # Set up base rules with no conflicts
        self.validator._base_rules = {
            'freezer_rules': {'tCREA-D': {'dryers': ['3', '5'], 'quantity': None}},
            'pump_no': {'tCREA-D': ['P3', 'P5']},
            'dispensing_limit': {},
            'operator_markers': {},
        }

        # marker_rule returns rules that are valid
        marker_rule_result = FakeResult(
            rows=[(1, 'tCREA-D', '5714400180', json.dumps(['P3']),
                   json.dumps(['5']), json.dumps([]),
                   json.dumps([]), False)],
            columns=['id', 'marker_name', 'pn', 'common_machines',
                     'common_dryers', 'common_operators', 'common_quantities',
                     'base_rule_validated']
        )
        operator_rule_result = FakeResult(
            rows=[],
            columns=['id', 'operator_name', 'capable_markers', 'base_rule_validated']
        )

        self.db.query_results['marker_rule'] = marker_rule_result
        self.db.query_results['operator_rule'] = operator_rule_result

        report = self.validator.generate_validation_report()

        assert isinstance(report, ValidationReport)
        assert report.conflicts_found == 0
        assert report.auto_corrected == 0
        assert report.passed == 1  # 1 marker_rule + 0 operator_rule, all passed

    def test_report_with_conflicts(self):
        """Report correctly counts conflicts and corrections."""
        # Set up DB results for base rule loading AND derived rule loading
        # freezer_rules
        self.db.query_results['freezer_rules'] = FakeResult(
            rows=[('tCREA-D', '3,5', None)],
            columns=['Marker', '可用凍乾機', '數量']
        )
        # pump No.
        self.db.query_results['pump No.'] = FakeResult(
            rows=[('tCREA-D', 'P3')],
            columns=['Marker', 'Pump']
        )
        # 配藥限制
        self.db.query_results['配藥限制'] = FakeResult(
            rows=[],
            columns=['Name', '配藥人-1', '配藥人-2', '配藥人-3', '數量', 'PN', '可用凍乾機']
        )
        # marker_rule with conflicts (P9 not in pump No., 9 not in freezer_rules)
        self.db.query_results['marker_rule'] = FakeResult(
            rows=[(1, 'tCREA-D', '5714400180', json.dumps(['P3', 'P9']),
                   json.dumps(['5', '9']), json.dumps([]),
                   json.dumps([]), False)],
            columns=['id', 'marker_name', 'pn', 'common_machines',
                     'common_dryers', 'common_operators', 'common_quantities',
                     'base_rule_validated']
        )
        # operator_rule: empty
        self.db.query_results['operator_rule'] = FakeResult(
            rows=[],
            columns=['id', 'operator_name', 'capable_markers', 'base_rule_validated']
        )

        report = self.validator.generate_validation_report()

        assert report.conflicts_found == 2  # dryer + machine conflict
        assert report.auto_corrected == 2
        assert len(report.conflict_details) == 2

    def test_report_commit_called(self):
        """Validation commits flag updates to database."""
        self.validator._base_rules = {
            'freezer_rules': {},
            'pump_no': {},
            'dispensing_limit': {},
            'operator_markers': {},
        }
        self.db.query_results['marker_rule'] = FakeResult(
            rows=[], columns=['id', 'marker_name', 'pn', 'common_machines',
                              'common_dryers', 'common_operators',
                              'common_quantities', 'base_rule_validated']
        )
        self.db.query_results['operator_rule'] = FakeResult(
            rows=[], columns=['id', 'operator_name', 'capable_markers',
                              'base_rule_validated']
        )

        self.validator.generate_validation_report()

        assert self.db.committed is True
