"""
Tests for AIAdvisor — rule-based conflict analysis and suggestions.
"""
import sys
import os
from datetime import date, time
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Fixture: mock db_session
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """Create a mock db session."""
    return MagicMock()


@pytest.fixture
def advisor(mock_db):
    """Create AIAdvisor instance with mocked DB."""
    with patch('ai_schedule.ai_advisor.logger'):
        from ai_schedule.ai_advisor import AIAdvisor
        return AIAdvisor(mock_db)


# ---------------------------------------------------------------------------
# Test __init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_stores_db_session(self, advisor, mock_db):
        assert advisor.db is mock_db

    def test_llm_client_is_none(self, advisor):
        assert advisor.llm_client is None

    def test_use_llm_is_false(self, advisor):
        assert advisor._use_llm is False


# ---------------------------------------------------------------------------
# Test explain_conflict
# ---------------------------------------------------------------------------

class TestExplainConflict:
    def test_machine_overlap_explanation(self, advisor):
        conflict = {
            'type': 'machine_overlap',
            'description': 'P3 在 14:00-16:00 已被佔用'
        }
        result = advisor.explain_conflict(conflict)
        assert '滴定機台' in result
        assert '時段' in result
        assert 'P3' in result

    def test_dryer_capacity_explanation(self, advisor):
        conflict = {
            'type': 'dryer_capacity',
            'description': 'Freeze_Dryer 5 超容'
        }
        result = advisor.explain_conflict(conflict)
        assert '凍乾機' in result
        assert '容量' in result

    def test_operator_overlap_explanation(self, advisor):
        conflict = {
            'type': 'operator_overlap',
            'description': '張三 準備區間重疊'
        }
        result = advisor.explain_conflict(conflict)
        assert '操作員' in result or '配藥' in result
        assert '準備' in result

    def test_production_flow_explanation(self, advisor):
        conflict = {
            'type': 'production_flow',
            'description': '配藥時間晚於滴定開始時間'
        }
        result = advisor.explain_conflict(conflict)
        assert '流程' in result or '順序' in result

    def test_base_rule_violation_explanation(self, advisor):
        conflict = {
            'type': 'base_rule_violation',
            'description': 'Marker X 分配機台不在允許清單中'
        }
        result = advisor.explain_conflict(conflict)
        assert '基準規則' in result

    def test_empty_conflict(self, advisor):
        result = advisor.explain_conflict({})
        assert '無法分析' in result

    def test_none_conflict(self, advisor):
        result = advisor.explain_conflict(None)
        assert '無法分析' in result

    def test_unknown_type_fallback(self, advisor):
        conflict = {
            'type': 'unknown_type',
            'description': 'Some issue'
        }
        result = advisor.explain_conflict(conflict)
        assert 'unknown_type' in result
        assert 'Some issue' in result


# ---------------------------------------------------------------------------
# Test get_suggestions (rule-based)
# ---------------------------------------------------------------------------

class TestGetSuggestions:
    def _setup_entry_with_conflict(self, advisor, mock_db, conflict_type):
        """Helper to set up a mocked entry with a specific conflict."""
        from ai_schedule.ai_advisor import AIAdvisor

        # Mock the internal loading methods
        entry = {
            'id': 1,
            'schedule_run_id': 'uuid-123',
            'week_code': '2026-W24',
            'date': date(2026, 6, 8),
            'marker': 'tCREA-D',
            'machine_port': 'P3',
            'freeze_dryer': '5',
            'operator': '張三',
            'rd_time': time(14, 0),
            'start_time': time(14, 30),
            'end_time': time(18, 0),
            'quantity': 1300,
            'pn': '5714400180',
            'batch': '180260240',
            'work_order': 'TMRA26001',
            'notes': None,
            'conflict_flag': True,
            'conflict_reason': conflict_type,
            'priority': 1,
            'status': 'draft',
        }

        marker_rule = {
            'marker_name': 'tCREA-D',
            'pn': '5714400180',
            'common_machines': ['P3', 'P5', 'P7'],
            'common_dryers': ['5', '6', '7'],
            'common_operators': ['張三', '李四', '王五'],
            'avg_start_time': time(14, 0),
            'avg_end_time': time(18, 0),
            'avg_duration_minutes': 240,
        }

        same_day_entries = [
            {
                'id': 2,
                'marker': 'GGT',
                'machine_port': 'P3',
                'freeze_dryer': '5',
                'operator': '張三',
                'start_time': time(14, 0),
                'end_time': time(16, 0),
                'rd_time': time(13, 30),
            },
        ]

        advisor._load_entry = MagicMock(return_value=entry)
        advisor._load_marker_rule = MagicMock(return_value=marker_rule)
        advisor._load_machine_capacity_rules = MagicMock(return_value={})
        advisor._load_operator_rules = MagicMock(return_value={})
        advisor._load_same_day_entries = MagicMock(return_value=same_day_entries)

        return entry

    def test_machine_overlap_suggestions(self, advisor, mock_db):
        self._setup_entry_with_conflict(
            advisor, mock_db, 'Machine_Port P3 時段重疊'
        )
        suggestions = advisor.get_suggestions(1)

        assert len(suggestions) > 0
        assert len(suggestions) <= 3

        # Should have at least one machine_swap or time_shift
        types = [s['type'] for s in suggestions]
        assert 'machine_swap' in types or 'time_shift' in types

        # Verify structure
        for s in suggestions:
            assert 'type' in s
            assert 'description' in s
            assert 'confidence' in s
            assert 'proposed_changes' in s
            assert 0.0 <= s['confidence'] <= 1.0

    def test_operator_overlap_suggestions(self, advisor, mock_db):
        self._setup_entry_with_conflict(
            advisor, mock_db, 'Operator 張三 準備區間重疊'
        )
        suggestions = advisor.get_suggestions(1)

        assert len(suggestions) > 0
        types = [s['type'] for s in suggestions]
        assert 'operator_change' in types or 'time_shift' in types

    def test_dryer_capacity_suggestions(self, advisor, mock_db):
        self._setup_entry_with_conflict(
            advisor, mock_db, 'Freeze_Dryer 5 凍乾超容'
        )
        suggestions = advisor.get_suggestions(1)

        assert len(suggestions) > 0
        # Should suggest dryer swap or day shift
        types = [s['type'] for s in suggestions]
        assert 'machine_swap' in types or 'time_shift' in types

    def test_no_conflict_returns_empty(self, advisor, mock_db):
        entry = {
            'id': 1,
            'conflict_flag': False,
            'conflict_reason': None,
        }
        advisor._load_entry = MagicMock(return_value=entry)
        suggestions = advisor.get_suggestions(1)
        assert suggestions == []

    def test_entry_not_found_returns_empty(self, advisor, mock_db):
        advisor._load_entry = MagicMock(return_value=None)
        suggestions = advisor.get_suggestions(999)
        assert suggestions == []

    def test_suggestions_capped_at_3(self, advisor, mock_db):
        self._setup_entry_with_conflict(
            advisor, mock_db,
            'Machine_Port P3 時段重疊; Operator 張三 準備區間重疊; 凍乾超容'
        )
        suggestions = advisor.get_suggestions(1)
        assert len(suggestions) <= 3


# ---------------------------------------------------------------------------
# Test get_strategy_recommendations
# ---------------------------------------------------------------------------

class TestGetStrategyRecommendations:
    def test_frequent_machine_conflicts(self, advisor):
        patterns = {
            'frequent_conflicts': [
                {'type': 'machine_overlap', 'markers': ['tCREA-D', 'GGT'], 'frequency': 5},
            ],
        }
        recs = advisor.get_strategy_recommendations(patterns)

        assert len(recs) > 0
        assert 'strategy' in recs[0]
        assert 'rationale' in recs[0]
        assert 'estimated_impact' in recs[0]
        assert 'tCREA-D' in recs[0]['strategy'] or 'GGT' in recs[0]['strategy']

    def test_peak_hours_recommendation(self, advisor):
        patterns = {
            'peak_hours': {14: 5, 15: 4, 10: 1, 11: 2},
        }
        recs = advisor.get_strategy_recommendations(patterns)

        assert len(recs) > 0
        assert '尖峰' in recs[0]['strategy'] or '分散' in recs[0]['strategy']

    def test_machine_utilization_imbalance(self, advisor):
        patterns = {
            'machine_utilization': {'P3': 95, 'P5': 20, 'P7': 15},
        }
        recs = advisor.get_strategy_recommendations(patterns)

        assert len(recs) > 0
        assert '負載' in recs[0]['strategy'] or '平衡' in recs[0]['strategy']

    def test_operator_overload(self, advisor):
        patterns = {
            'operator_load': {'張三': 5, '李四': 1},
        }
        recs = advisor.get_strategy_recommendations(patterns)

        assert len(recs) > 0
        assert '操作員' in recs[0]['strategy'] or '負載' in recs[0]['strategy']

    def test_marker_co_occurrence(self, advisor):
        patterns = {
            'marker_pairs': [
                {'markers': ['tCREA-D', 'GGT'], 'co_occurrence_rate': 0.85},
            ],
        }
        recs = advisor.get_strategy_recommendations(patterns)

        assert len(recs) > 0
        assert 'tCREA-D' in recs[0]['strategy'] or 'GGT' in recs[0]['strategy']

    def test_empty_patterns_gives_generic(self, advisor):
        recs = advisor.get_strategy_recommendations({})
        assert recs == []

    def test_combined_patterns(self, advisor):
        patterns = {
            'frequent_conflicts': [
                {'type': 'machine_overlap', 'markers': ['A', 'B'], 'frequency': 4},
            ],
            'peak_hours': {14: 6},
            'machine_utilization': {'P1': 90, 'P2': 10},
        }
        recs = advisor.get_strategy_recommendations(patterns)

        # Should generate multiple recommendations
        assert len(recs) >= 2


# ---------------------------------------------------------------------------
# Test time utility helpers
# ---------------------------------------------------------------------------

class TestTimeHelpers:
    def test_time_gt(self, advisor):
        assert advisor._time_gt(time(15, 0), time(14, 0)) is True
        assert advisor._time_gt(time(14, 0), time(15, 0)) is False
        assert advisor._time_gt(time(14, 0), time(14, 0)) is False
        assert advisor._time_gt(None, time(14, 0)) is False

    def test_time_diff_minutes(self, advisor):
        assert advisor._time_diff_minutes(time(14, 0), time(16, 30)) == 150
        assert advisor._time_diff_minutes(time(14, 0), time(14, 0)) == 0
        assert advisor._time_diff_minutes(None, time(14, 0)) is None

    def test_add_minutes_to_time(self, advisor):
        result = advisor._add_minutes_to_time(time(14, 0), 30)
        assert result == time(14, 30)

        result = advisor._add_minutes_to_time(time(23, 50), 30)
        assert result == time(23, 59)  # Clamped to max

        assert advisor._add_minutes_to_time(None, 30) is None

    def test_format_time(self, advisor):
        assert advisor._format_time(time(14, 30)) == '14:30'
        assert advisor._format_time(None) == ''

    def test_times_overlap_simple(self, advisor):
        assert advisor._times_overlap_simple(
            time(14, 0), time(16, 0), time(15, 0), time(17, 0)
        ) is True
        assert advisor._times_overlap_simple(
            time(14, 0), time(15, 0), time(15, 0), time(16, 0)
        ) is False
        assert advisor._times_overlap_simple(
            time(14, 0), time(16, 0), None, time(17, 0)
        ) is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
