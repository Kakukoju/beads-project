"""
Unit tests for ai_schedule/routes.py — POST /api/ai-schedule/analyze-rules endpoint
"""
import sys
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, '/home/ubuntu/beads-project')


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a minimal Flask app with the ai_schedule blueprint registered."""
    from flask import Flask
    from ai_schedule.routes import ai_schedule_bp

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(ai_schedule_bp)
    return test_app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Mock data classes (matching the real dataclass shapes)
# ---------------------------------------------------------------------------

@dataclass
class MockAnalysisSummary:
    markers_analyzed: int = 5
    rules_created: int = 12
    insufficient_data_markers: list = field(default_factory=lambda: ['MarkerX'])
    data_sources: dict = field(default_factory=lambda: {
        'droplet_schedule_records': 100,
        'droplet_record_records': 80,
        'worker_order_records': 50,
    })


@dataclass
class MockValidationReport:
    passed: int = 10
    conflicts_found: int = 2
    auto_corrected: int = 2
    conflict_details: list = field(default_factory=lambda: [
        {
            'rule_type': 'marker_rule',
            'rule_name': 'TestMarker',
            'field': 'common_dryers',
            'derived_values': ['D1', 'D2', 'D3'],
            'allowed_values': ['D1', 'D2'],
            'conflicting_values': ['D3'],
            'description': 'Test conflict',
        }
    ])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAnalyzeRulesEndpoint:
    """Tests for POST /api/ai-schedule/analyze-rules"""

    @patch('ai_schedule.routes.RuleValidator')
    @patch('ai_schedule.routes.RuleAnalyzer')
    def test_success_returns_200_with_summary_and_report(
        self, mock_analyzer_cls, mock_validator_cls, client
    ):
        """Happy path: analysis and validation both succeed."""
        # Setup mocks
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_all.return_value = MockAnalysisSummary()
        mock_analyzer_cls.return_value = mock_analyzer

        mock_validator = MagicMock()
        mock_validator.generate_validation_report.return_value = MockValidationReport()
        mock_validator_cls.return_value = mock_validator

        # Mock the db import inside the route
        mock_db = MagicMock()
        with patch.dict('sys.modules', {'mrpFlask_5': MagicMock(db=mock_db)}):
            response = client.post('/api/ai-schedule/analyze-rules')

        assert response.status_code == 200
        data = response.get_json()

        assert data['ok'] is True
        assert 'analysis_summary' in data
        assert 'validation_report' in data

        # Check analysis_summary content
        summary = data['analysis_summary']
        assert summary['markers_analyzed'] == 5
        assert summary['rules_created'] == 12
        assert 'MarkerX' in summary['insufficient_data_markers']
        assert summary['data_sources']['droplet_schedule_records'] == 100

        # Check validation_report content
        report = data['validation_report']
        assert report['passed'] == 10
        assert report['conflicts_found'] == 2
        assert report['auto_corrected'] == 2
        assert len(report['conflict_details']) == 1

    @patch('ai_schedule.routes.RuleValidator')
    @patch('ai_schedule.routes.RuleAnalyzer')
    def test_analyzer_failure_returns_500_with_no_partial(
        self, mock_analyzer_cls, mock_validator_cls, client
    ):
        """When RuleAnalyzer raises, return 500 with error details and no partial results."""
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_all.side_effect = RuntimeError("DB connection lost")
        mock_analyzer_cls.return_value = mock_analyzer

        mock_db = MagicMock()
        with patch.dict('sys.modules', {'mrpFlask_5': MagicMock(db=mock_db)}):
            response = client.post('/api/ai-schedule/analyze-rules')

        assert response.status_code == 500
        data = response.get_json()

        assert data['ok'] is False
        assert 'DB connection lost' in data['error']
        assert data['error_type'] == 'RuntimeError'
        # No partial results since analyzer failed before completing
        assert 'analysis_summary' not in data
        assert 'validation_report' not in data

    @patch('ai_schedule.routes.RuleValidator')
    @patch('ai_schedule.routes.RuleAnalyzer')
    def test_validator_failure_returns_500_with_partial_analysis(
        self, mock_analyzer_cls, mock_validator_cls, client
    ):
        """When RuleValidator raises after analysis, return 500 with partial analysis_summary."""
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_all.return_value = MockAnalysisSummary()
        mock_analyzer_cls.return_value = mock_analyzer

        mock_validator = MagicMock()
        mock_validator.generate_validation_report.side_effect = ValueError("Invalid rule format")
        mock_validator_cls.return_value = mock_validator

        mock_db = MagicMock()
        with patch.dict('sys.modules', {'mrpFlask_5': MagicMock(db=mock_db)}):
            response = client.post('/api/ai-schedule/analyze-rules')

        assert response.status_code == 500
        data = response.get_json()

        assert data['ok'] is False
        assert 'Invalid rule format' in data['error']
        # Analysis completed before validator failed — partial result included
        assert 'analysis_summary' in data
        assert data['analysis_summary']['markers_analyzed'] == 5
        # Validation did not complete
        assert 'validation_report' not in data

    @patch('ai_schedule.routes.RuleValidator')
    @patch('ai_schedule.routes.RuleAnalyzer')
    def test_db_session_passed_to_both_services(
        self, mock_analyzer_cls, mock_validator_cls, client
    ):
        """Both RuleAnalyzer and RuleValidator receive db.session."""
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_all.return_value = MockAnalysisSummary()
        mock_analyzer_cls.return_value = mock_analyzer

        mock_validator = MagicMock()
        mock_validator.generate_validation_report.return_value = MockValidationReport()
        mock_validator_cls.return_value = mock_validator

        mock_db = MagicMock()
        mock_session = mock_db.session

        with patch.dict('sys.modules', {'mrpFlask_5': MagicMock(db=mock_db)}):
            response = client.post('/api/ai-schedule/analyze-rules')

        assert response.status_code == 200
        mock_analyzer_cls.assert_called_once_with(mock_session)
        mock_validator_cls.assert_called_once_with(mock_session)


# ---------------------------------------------------------------------------
# Tests for POST /api/ai-schedule/validate
# ---------------------------------------------------------------------------

class TestValidateEndpoint:
    """Tests for POST /api/ai-schedule/validate"""

    def test_missing_body_returns_400(self, client):
        """No JSON body → 400 error."""
        response = client.post(
            '/api/ai-schedule/validate',
            content_type='application/json',
            data='not json',
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'JSON' in data['error']

    def test_missing_entry_ids_returns_400(self, client):
        """Missing entry_ids field → 400 error."""
        response = client.post(
            '/api/ai-schedule/validate',
            json={},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'entry_ids' in data['error']

    def test_empty_entry_ids_returns_400(self, client):
        """Empty entry_ids array → 400 error."""
        response = client.post(
            '/api/ai-schedule/validate',
            json={"entry_ids": []},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'entry_ids' in data['error']

    def test_non_integer_entry_ids_returns_400(self, client):
        """Non-integer in entry_ids → 400 error."""
        response = client.post(
            '/api/ai-schedule/validate',
            json={"entry_ids": [1, "abc", 3]},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'integer' in data['error']

# ---------------------------------------------------------------------------
# Tests for POST /api/ai-schedule/validate
# ---------------------------------------------------------------------------

class TestValidateEndpoint:
    """Tests for POST /api/ai-schedule/validate"""

    def test_missing_body_returns_400(self, client):
        """No JSON body → 400 error."""
        response = client.post(
            '/api/ai-schedule/validate',
            content_type='application/json',
            data='not json',
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'JSON' in data['error']

    def test_missing_entry_ids_returns_400(self, client):
        """Missing entry_ids field → 400 error."""
        response = client.post(
            '/api/ai-schedule/validate',
            json={},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'entry_ids' in data['error']

    def test_empty_entry_ids_returns_400(self, client):
        """Empty entry_ids array → 400 error."""
        response = client.post(
            '/api/ai-schedule/validate',
            json={"entry_ids": []},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'entry_ids' in data['error']

    def test_non_integer_entry_ids_returns_400(self, client):
        """Non-integer in entry_ids → 400 error."""
        response = client.post(
            '/api/ai-schedule/validate',
            json={"entry_ids": [1, "abc", 3]},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'integer' in data['error']

    def test_valid_entries_no_conflicts(self, client):
        """Happy path: entries with no conflicts → all valid."""
        from datetime import date, time
        from ai_schedule.conflict_detector import Conflict

        mock_db = MagicMock()

        # Mock GeneratedSchedule entry
        mock_entry = MagicMock()
        mock_entry.id = 1
        mock_entry.date = date(2026, 6, 8)
        mock_entry.marker = 'tCREA-D'
        mock_entry.machine_port = 'P3'
        mock_entry.freeze_dryer = '5'
        mock_entry.operator = '張三'
        mock_entry.rd_time = time(14, 0)
        mock_entry.start_time = time(14, 30)
        mock_entry.end_time = time(18, 0)
        mock_entry.quantity = 1300
        mock_entry.pn = '5714400180'
        mock_entry.batch = '180260240'
        mock_entry.conflict_flag = False
        mock_entry.conflict_reason = None

        mock_gs_cls = MagicMock()
        mock_gs_cls.query.filter.return_value.all.return_value = [mock_entry]

        mock_engine = MagicMock()
        mock_engine._load_rules.return_value = MagicMock()

        mock_cd = MagicMock()
        mock_cd.detect_all.return_value = []

        mock_mrp = MagicMock(db=mock_db)

        with patch.dict('sys.modules', {'mrpFlask_5': mock_mrp}):
            with patch('ai_schedule.conflict_detector.ConflictDetector', return_value=mock_cd):
                with patch('ai_schedule.scheduling_engine.SchedulingEngine', return_value=mock_engine):
                    # Patch the local import target
                    import ai_schedule.routes as routes_mod
                    orig_validate = routes_mod.validate

                    # We need to intercept the local imports in the validate function
                    # Simplest: patch the modules that get imported
                    mock_models_mod = MagicMock()
                    mock_models_mod.GeneratedSchedule = mock_gs_cls
                    mock_se_mod = MagicMock()
                    mock_se_mod.SchedulingEngine = MagicMock(return_value=mock_engine)
                    mock_cd_mod = MagicMock()
                    mock_cd_mod.ConflictDetector = MagicMock(return_value=mock_cd)

                    with patch.dict('sys.modules', {
                        'mrpFlask_5': mock_mrp,
                        'ai_schedule.models': mock_models_mod,
                        'ai_schedule.scheduling_engine': mock_se_mod,
                        'ai_schedule.conflict_detector': mock_cd_mod,
                    }):
                        response = client.post(
                            '/api/ai-schedule/validate',
                            json={"entry_ids": [1]},
                        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['ok'] is True
        assert len(data['results']) == 1
        assert data['results'][0]['id'] == 1
        assert data['results'][0]['valid'] is True
        assert data['results'][0]['conflicts'] == []

    def test_entries_with_conflicts(self, client):
        """Entries with conflicts → valid=False with conflict details."""
        from datetime import date, time
        from ai_schedule.conflict_detector import Conflict

        mock_db = MagicMock()

        mock_entry1 = MagicMock()
        mock_entry1.id = 1
        mock_entry1.date = date(2026, 6, 8)
        mock_entry1.marker = 'tCREA-D'
        mock_entry1.machine_port = 'P3'
        mock_entry1.freeze_dryer = '5'
        mock_entry1.operator = '張三'
        mock_entry1.rd_time = time(14, 0)
        mock_entry1.start_time = time(14, 30)
        mock_entry1.end_time = time(16, 0)
        mock_entry1.quantity = 1300
        mock_entry1.pn = '5714400180'
        mock_entry1.batch = '180260240'
        mock_entry1.conflict_flag = False
        mock_entry1.conflict_reason = None

        mock_entry2 = MagicMock()
        mock_entry2.id = 2
        mock_entry2.date = date(2026, 6, 8)
        mock_entry2.marker = 'GGT'
        mock_entry2.machine_port = 'P3'
        mock_entry2.freeze_dryer = '5'
        mock_entry2.operator = '李四'
        mock_entry2.rd_time = time(15, 0)
        mock_entry2.start_time = time(15, 30)
        mock_entry2.end_time = time(17, 0)
        mock_entry2.quantity = 1300
        mock_entry2.pn = '5714400132'
        mock_entry2.batch = '132260241'
        mock_entry2.conflict_flag = False
        mock_entry2.conflict_reason = None

        mock_gs_cls = MagicMock()
        mock_gs_cls.query.filter.return_value.all.return_value = [mock_entry1, mock_entry2]

        mock_engine = MagicMock()
        mock_engine._load_rules.return_value = MagicMock()

        conflicts = [
            Conflict(
                entry_id=1,
                conflict_type='machine_overlap',
                description='P3 在 14:30-16:00 已被佔用',
            ),
            Conflict(
                entry_id=2,
                conflict_type='machine_overlap',
                description='P3 在 14:30-16:00 已被佔用',
            ),
        ]
        mock_cd = MagicMock()
        mock_cd.detect_all.return_value = conflicts

        mock_mrp = MagicMock(db=mock_db)
        mock_models_mod = MagicMock()
        mock_models_mod.GeneratedSchedule = mock_gs_cls
        mock_se_mod = MagicMock()
        mock_se_mod.SchedulingEngine = MagicMock(return_value=mock_engine)
        mock_cd_mod = MagicMock()
        mock_cd_mod.ConflictDetector = MagicMock(return_value=mock_cd)

        with patch.dict('sys.modules', {
            'mrpFlask_5': mock_mrp,
            'ai_schedule.models': mock_models_mod,
            'ai_schedule.scheduling_engine': mock_se_mod,
            'ai_schedule.conflict_detector': mock_cd_mod,
        }):
            response = client.post(
                '/api/ai-schedule/validate',
                json={"entry_ids": [1, 2]},
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data['ok'] is True
        assert len(data['results']) == 2
        assert data['results'][0]['id'] == 1
        assert data['results'][0]['valid'] is False
        assert len(data['results'][0]['conflicts']) == 1
        assert data['results'][0]['conflicts'][0]['type'] == 'machine_overlap'
        assert data['results'][1]['id'] == 2
        assert data['results'][1]['valid'] is False

    def test_server_error_returns_500(self, client):
        """Internal error during processing → 500."""
        mock_db = MagicMock()

        mock_gs_cls = MagicMock()
        mock_gs_cls.query.filter.return_value.all.side_effect = RuntimeError("DB down")

        mock_mrp = MagicMock(db=mock_db)
        mock_models_mod = MagicMock()
        mock_models_mod.GeneratedSchedule = mock_gs_cls

        with patch.dict('sys.modules', {
            'mrpFlask_5': mock_mrp,
            'ai_schedule.models': mock_models_mod,
        }):
            response = client.post(
                '/api/ai-schedule/validate',
                json={"entry_ids": [1, 2]},
            )

        assert response.status_code == 500
        data = response.get_json()
        assert data['ok'] is False
        assert 'DB down' in data['error']
        assert data['error_type'] == 'RuntimeError'


# ---------------------------------------------------------------------------
# Tests for GET /api/ai-schedule/preview
# ---------------------------------------------------------------------------

class TestPreviewEndpoint:
    """Tests for GET /api/ai-schedule/preview"""

    def _make_mock_entry(self, id=1, week_code='2026-W24', status='draft',
                         marker='tCREA-D', priority=1, conflict_flag=False):
        """Helper to create a mock GeneratedSchedule entry."""
        from datetime import date, time
        import uuid

        entry = MagicMock()
        entry.id = id
        entry.schedule_run_id = uuid.uuid4()
        entry.week_code = week_code
        entry.date = date(2026, 6, 9)
        entry.marker = marker
        entry.machine_port = 'P3'
        entry.freeze_dryer = '5'
        entry.operator = '張三'
        entry.rd_time = time(14, 0)
        entry.start_time = time(14, 30)
        entry.end_time = time(18, 0)
        entry.quantity = 1300
        entry.pn = '5714400180'
        entry.batch = f'18026024{id}'
        entry.work_order = f'TMRA2601{id}'
        entry.notes = None
        entry.conflict_flag = conflict_flag
        entry.conflict_reason = 'P3 overlap' if conflict_flag else None
        entry.priority = priority
        entry.status = status
        return entry

    def test_preview_no_filters_returns_200(self, client):
        """GET /preview with no filters returns all entries paginated."""
        mock_entry = self._make_mock_entry()

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_entry]

        mock_gs_cls = MagicMock()
        mock_gs_cls.query = mock_query
        mock_gs_cls.date = MagicMock()
        mock_gs_cls.date.asc.return_value = 'date_asc'

        mock_db = MagicMock()
        mock_mrp = MagicMock(db=mock_db)
        mock_models_mod = MagicMock()
        mock_models_mod.GeneratedSchedule = mock_gs_cls

        with patch.dict('sys.modules', {
            'mrpFlask_5': mock_mrp,
            'ai_schedule.models': mock_models_mod,
        }):
            response = client.get('/api/ai-schedule/preview')

        assert response.status_code == 200
        data = response.get_json()
        assert data['ok'] is True
        assert len(data['data']) == 1
        assert data['data'][0]['marker'] == 'tCREA-D'
        assert data['pagination']['total'] == 1
        assert data['pagination']['page'] == 1
        assert data['pagination']['per_page'] == 50
        assert data['filters_applied'] == {}

    def test_preview_with_week_code_filter(self, client):
        """GET /preview?week_code=2026-W24 applies week_code filter."""
        mock_entry = self._make_mock_entry(week_code='2026-W24')

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_entry]

        mock_gs_cls = MagicMock()
        mock_gs_cls.query = mock_query
        mock_gs_cls.week_code = MagicMock()
        mock_gs_cls.date = MagicMock()
        mock_gs_cls.date.asc.return_value = 'date_asc'

        mock_db = MagicMock()
        mock_mrp = MagicMock(db=mock_db)
        mock_models_mod = MagicMock()
        mock_models_mod.GeneratedSchedule = mock_gs_cls

        with patch.dict('sys.modules', {
            'mrpFlask_5': mock_mrp,
            'ai_schedule.models': mock_models_mod,
        }):
            response = client.get('/api/ai-schedule/preview?week_code=2026-W24')

        assert response.status_code == 200
        data = response.get_json()
        assert data['ok'] is True
        assert data['filters_applied']['week_code'] == '2026-W24'

    def test_preview_with_status_filter(self, client):
        """GET /preview?status=draft applies status filter."""
        mock_entry = self._make_mock_entry(status='draft')

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_entry]

        mock_gs_cls = MagicMock()
        mock_gs_cls.query = mock_query
        mock_gs_cls.status = MagicMock()
        mock_gs_cls.date = MagicMock()
        mock_gs_cls.date.asc.return_value = 'date_asc'

        mock_db = MagicMock()
        mock_mrp = MagicMock(db=mock_db)
        mock_models_mod = MagicMock()
        mock_models_mod.GeneratedSchedule = mock_gs_cls

        with patch.dict('sys.modules', {
            'mrpFlask_5': mock_mrp,
            'ai_schedule.models': mock_models_mod,
        }):
            response = client.get('/api/ai-schedule/preview?status=draft')

        assert response.status_code == 200
        data = response.get_json()
        assert data['ok'] is True
        assert data['filters_applied']['status'] == 'draft'

    def test_preview_pagination(self, client):
        """GET /preview?page=2&per_page=10 returns correct pagination."""
        mock_entry = self._make_mock_entry()

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.return_value = 25
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_entry]

        mock_gs_cls = MagicMock()
        mock_gs_cls.query = mock_query
        mock_gs_cls.date = MagicMock()
        mock_gs_cls.date.asc.return_value = 'date_asc'

        mock_db = MagicMock()
        mock_mrp = MagicMock(db=mock_db)
        mock_models_mod = MagicMock()
        mock_models_mod.GeneratedSchedule = mock_gs_cls

        with patch.dict('sys.modules', {
            'mrpFlask_5': mock_mrp,
            'ai_schedule.models': mock_models_mod,
        }):
            response = client.get('/api/ai-schedule/preview?page=2&per_page=10')

        assert response.status_code == 200
        data = response.get_json()
        assert data['ok'] is True
        assert data['pagination']['page'] == 2
        assert data['pagination']['per_page'] == 10
        assert data['pagination']['total'] == 25
        assert data['pagination']['pages'] == 3

    def test_preview_empty_results(self, client):
        """GET /preview returns empty data when no entries match."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []

        mock_gs_cls = MagicMock()
        mock_gs_cls.query = mock_query
        mock_gs_cls.date = MagicMock()
        mock_gs_cls.date.asc.return_value = 'date_asc'

        mock_db = MagicMock()
        mock_mrp = MagicMock(db=mock_db)
        mock_models_mod = MagicMock()
        mock_models_mod.GeneratedSchedule = mock_gs_cls

        with patch.dict('sys.modules', {
            'mrpFlask_5': mock_mrp,
            'ai_schedule.models': mock_models_mod,
        }):
            response = client.get('/api/ai-schedule/preview?week_code=2099-W01')

        assert response.status_code == 200
        data = response.get_json()
        assert data['ok'] is True
        assert data['data'] == []
        assert data['pagination']['total'] == 0
        assert data['pagination']['pages'] == 0

    def test_preview_server_error_returns_500(self, client):
        """Internal exception during query → 500 with error details."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.side_effect = RuntimeError("DB connection lost")

        mock_gs_cls = MagicMock()
        mock_gs_cls.query = mock_query
        mock_gs_cls.date = MagicMock()
        mock_gs_cls.date.asc.return_value = 'date_asc'

        mock_db = MagicMock()
        mock_mrp = MagicMock(db=mock_db)
        mock_models_mod = MagicMock()
        mock_models_mod.GeneratedSchedule = mock_gs_cls

        with patch.dict('sys.modules', {
            'mrpFlask_5': mock_mrp,
            'ai_schedule.models': mock_models_mod,
        }):
            response = client.get('/api/ai-schedule/preview')

        assert response.status_code == 500
        data = response.get_json()
        assert data['ok'] is False
        assert 'DB connection lost' in data['error']
        assert data['error_type'] == 'RuntimeError'

    def test_preview_includes_conflict_info(self, client):
        """Entries with conflict_flag=True include conflict_reason."""
        mock_entry = self._make_mock_entry(conflict_flag=True)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_entry]

        mock_gs_cls = MagicMock()
        mock_gs_cls.query = mock_query
        mock_gs_cls.date = MagicMock()
        mock_gs_cls.date.asc.return_value = 'date_asc'

        mock_db = MagicMock()
        mock_mrp = MagicMock(db=mock_db)
        mock_models_mod = MagicMock()
        mock_models_mod.GeneratedSchedule = mock_gs_cls

        with patch.dict('sys.modules', {
            'mrpFlask_5': mock_mrp,
            'ai_schedule.models': mock_models_mod,
        }):
            response = client.get('/api/ai-schedule/preview')

        assert response.status_code == 200
        data = response.get_json()
        assert data['ok'] is True
        assert data['data'][0]['conflict_flag'] is True
        assert data['data'][0]['conflict_reason'] == 'P3 overlap'
