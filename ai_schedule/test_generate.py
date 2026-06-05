"""
Unit tests for ai_schedule generate functionality:
- POST /api/ai-schedule/generate endpoint validation & happy path
- SchedulingEngine.generate() orchestrator method
"""
import sys
import uuid
from datetime import date
from unittest.mock import MagicMock, patch, call

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


@pytest.fixture
def valid_request_body():
    """Standard valid request body for POST /generate."""
    return {
        "week_code": "2026-W24",
        "demands": [
            {"marker": "tCREA-D", "pn": "5714400180", "quantity": 3900, "priority": 1},
            {"marker": "GGT", "pn": "5714400132", "quantity": 2600, "priority": 2},
        ],
        "resource_config": {
            "holidays": ["六", "日"],
            "dryerMaintenance": [],
            "staffOffDays": {},
        },
    }


# ---------------------------------------------------------------------------
# Route Validation Tests
# ---------------------------------------------------------------------------

class TestGenerateEndpointValidation:
    """Tests for POST /api/ai-schedule/generate request validation."""

    def test_missing_json_body_returns_400(self, client):
        """Request without JSON body returns 400."""
        mock_db = MagicMock()
        with patch.dict('sys.modules', {'mrpFlask_5': MagicMock(db=mock_db)}):
            response = client.post(
                '/api/ai-schedule/generate',
                data='not json',
                content_type='text/plain',
            )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'JSON' in data['error']

    def test_missing_week_code_returns_400(self, client):
        """Missing week_code field returns 400."""
        mock_db = MagicMock()
        with patch.dict('sys.modules', {'mrpFlask_5': MagicMock(db=mock_db)}):
            response = client.post(
                '/api/ai-schedule/generate',
                json={"demands": [{"marker": "A", "pn": "123", "quantity": 100}]},
            )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'week_code' in data['error']

    def test_missing_demands_returns_400(self, client):
        """Missing demands field returns 400."""
        mock_db = MagicMock()
        with patch.dict('sys.modules', {'mrpFlask_5': MagicMock(db=mock_db)}):
            response = client.post(
                '/api/ai-schedule/generate',
                json={"week_code": "2026-W24"},
            )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'demands' in data['error']

    def test_empty_demands_returns_400(self, client):
        """Empty demands array returns 400."""
        mock_db = MagicMock()
        with patch.dict('sys.modules', {'mrpFlask_5': MagicMock(db=mock_db)}):
            response = client.post(
                '/api/ai-schedule/generate',
                json={"week_code": "2026-W24", "demands": []},
            )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'demands' in data['error']

    def test_demand_missing_marker_returns_400(self, client):
        """Demand entry missing 'marker' returns 400."""
        mock_db = MagicMock()
        with patch.dict('sys.modules', {'mrpFlask_5': MagicMock(db=mock_db)}):
            response = client.post(
                '/api/ai-schedule/generate',
                json={
                    "week_code": "2026-W24",
                    "demands": [{"pn": "123", "quantity": 100}],
                },
            )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'marker' in data['error']

    def test_demand_negative_quantity_returns_400(self, client):
        """Demand with negative quantity returns 400."""
        mock_db = MagicMock()
        with patch.dict('sys.modules', {'mrpFlask_5': MagicMock(db=mock_db)}):
            response = client.post(
                '/api/ai-schedule/generate',
                json={
                    "week_code": "2026-W24",
                    "demands": [{"marker": "A", "pn": "123", "quantity": -5}],
                },
            )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'positive' in data['error']

    def test_demand_zero_quantity_returns_400(self, client):
        """Demand with zero quantity returns 400."""
        mock_db = MagicMock()
        with patch.dict('sys.modules', {'mrpFlask_5': MagicMock(db=mock_db)}):
            response = client.post(
                '/api/ai-schedule/generate',
                json={
                    "week_code": "2026-W24",
                    "demands": [{"marker": "A", "pn": "123", "quantity": 0}],
                },
            )
        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'positive' in data['error']


class TestGenerateEndpointHappyPath:
    """Tests for POST /api/ai-schedule/generate successful execution."""

    def test_success_returns_200_with_results(self, client, valid_request_body):
        """Happy path: valid request returns 200 with expected shape."""
        mock_engine = MagicMock()
        mock_engine.generate.return_value = {
            "schedule_run_id": "test-uuid-123",
            "entries": [
                {"marker": "tCREA-D", "batch": "180260240", "quantity": 1300},
            ],
            "conflicts_summary": {"total": 0, "by_type": {}},
            "degradation_note": "W1+W2",
        }

        mock_engine_cls = MagicMock(return_value=mock_engine)
        mock_db = MagicMock()
        mock_mrp = MagicMock(db=mock_db)

        with patch.dict('sys.modules', {'mrpFlask_5': mock_mrp}):
            with patch('ai_schedule.scheduling_engine.SchedulingEngine', mock_engine_cls):
                response = client.post(
                    '/api/ai-schedule/generate',
                    json=valid_request_body,
                )

        assert response.status_code == 200
        data = response.get_json()
        assert data['ok'] is True
        assert data['schedule_run_id'] == "test-uuid-123"
        assert len(data['data']) == 1
        assert data['conflicts_summary']['total'] == 0

    def test_engine_receives_correct_args(self, client, valid_request_body):
        """Engine.generate() is called with correct parameters."""
        mock_engine = MagicMock()
        mock_engine.generate.return_value = {
            "schedule_run_id": "uuid",
            "entries": [],
            "conflicts_summary": {"total": 0, "by_type": {}},
            "degradation_note": "W1",
        }

        mock_engine_cls = MagicMock(return_value=mock_engine)
        mock_db = MagicMock()
        mock_mrp = MagicMock(db=mock_db)

        with patch.dict('sys.modules', {'mrpFlask_5': mock_mrp}):
            with patch('ai_schedule.scheduling_engine.SchedulingEngine', mock_engine_cls):
                client.post('/api/ai-schedule/generate', json=valid_request_body)

        mock_engine.generate.assert_called_once_with(
            week_code="2026-W24",
            demands=valid_request_body["demands"],
            resource_config=valid_request_body["resource_config"],
        )

    def test_value_error_returns_400(self, client, valid_request_body):
        """ValueError from engine returns 400."""
        mock_engine = MagicMock()
        mock_engine.generate.side_effect = ValueError("Invalid week_code format")

        mock_engine_cls = MagicMock(return_value=mock_engine)
        mock_db = MagicMock()
        mock_mrp = MagicMock(db=mock_db)

        with patch.dict('sys.modules', {'mrpFlask_5': mock_mrp}):
            with patch('ai_schedule.scheduling_engine.SchedulingEngine', mock_engine_cls):
                response = client.post(
                    '/api/ai-schedule/generate', json=valid_request_body
                )

        assert response.status_code == 400
        data = response.get_json()
        assert data['ok'] is False
        assert 'Invalid week_code format' in data['error']

    def test_runtime_error_returns_500(self, client, valid_request_body):
        """RuntimeError from engine returns 500."""
        mock_engine = MagicMock()
        mock_engine.generate.side_effect = RuntimeError("Solver failed")

        mock_engine_cls = MagicMock(return_value=mock_engine)
        mock_db = MagicMock()
        mock_mrp = MagicMock(db=mock_db)

        with patch.dict('sys.modules', {'mrpFlask_5': mock_mrp}):
            with patch('ai_schedule.scheduling_engine.SchedulingEngine', mock_engine_cls):
                response = client.post(
                    '/api/ai-schedule/generate', json=valid_request_body
                )

        assert response.status_code == 500
        data = response.get_json()
        assert data['ok'] is False
        assert 'Solver failed' in data['error']

    def test_resource_config_optional(self, client):
        """resource_config is optional — defaults to empty dict."""
        mock_engine = MagicMock()
        mock_engine.generate.return_value = {
            "schedule_run_id": "uuid",
            "entries": [],
            "conflicts_summary": {"total": 0, "by_type": {}},
            "degradation_note": "W1",
        }

        mock_engine_cls = MagicMock(return_value=mock_engine)
        mock_db = MagicMock()
        mock_mrp = MagicMock(db=mock_db)

        with patch.dict('sys.modules', {'mrpFlask_5': mock_mrp}):
            with patch('ai_schedule.scheduling_engine.SchedulingEngine', mock_engine_cls):
                response = client.post(
                    '/api/ai-schedule/generate',
                    json={
                        "week_code": "2026-W24",
                        "demands": [{"marker": "A", "pn": "123", "quantity": 100}],
                    },
                )

        assert response.status_code == 200
        # Verify resource_config defaults to empty dict
        mock_engine.generate.assert_called_once_with(
            week_code="2026-W24",
            demands=[{"marker": "A", "pn": "123", "quantity": 100}],
            resource_config={},
        )


# ---------------------------------------------------------------------------
# SchedulingEngine.generate() unit tests
# ---------------------------------------------------------------------------

class TestSchedulingEngineGenerate:
    """Unit tests for SchedulingEngine.generate() method."""

    def test_parse_week_code_valid(self):
        """_parse_week_code parses valid format correctly."""
        from ai_schedule.scheduling_engine import SchedulingEngine

        mock_session = MagicMock()
        engine = SchedulingEngine(mock_session)

        year, week = engine._parse_week_code("2026-W24")
        assert year == 2026
        assert week == 24

    def test_parse_week_code_invalid_format_raises(self):
        """_parse_week_code raises ValueError for invalid format."""
        from ai_schedule.scheduling_engine import SchedulingEngine

        mock_session = MagicMock()
        engine = SchedulingEngine(mock_session)

        with pytest.raises(ValueError, match="Invalid week_code format"):
            engine._parse_week_code("2026-24")

    def test_parse_week_code_invalid_week_number_raises(self):
        """_parse_week_code raises ValueError for week > 53."""
        from ai_schedule.scheduling_engine import SchedulingEngine

        mock_session = MagicMock()
        engine = SchedulingEngine(mock_session)

        with pytest.raises(ValueError, match="Invalid week_code format"):
            engine._parse_week_code("2026-W55")

    def test_compute_horizon_days_default(self):
        """Default holidays (六, 日) gives 5 working days."""
        from ai_schedule.scheduling_engine import SchedulingEngine

        mock_session = MagicMock()
        engine = SchedulingEngine(mock_session)

        days = engine._compute_horizon_days(2026, 24, ['六', '日'])
        assert days == 5

    def test_compute_horizon_days_no_holidays(self):
        """No holidays gives 7 working days."""
        from ai_schedule.scheduling_engine import SchedulingEngine

        mock_session = MagicMock()
        engine = SchedulingEngine(mock_session)

        days = engine._compute_horizon_days(2026, 24, [])
        assert days == 7

    def test_get_workdays_returns_correct_dates(self):
        """_get_workdays returns Mon-Fri dates for a given week."""
        from ai_schedule.scheduling_engine import SchedulingEngine

        mock_session = MagicMock()
        engine = SchedulingEngine(mock_session)

        workdays = engine._get_workdays(2026, 24, ['六', '日'])
        assert len(workdays) == 5
        # All should be date objects
        for d in workdays:
            assert isinstance(d, date)
        # Monday should be first
        assert workdays[0].isoweekday() == 1  # Monday
        assert workdays[-1].isoweekday() == 5  # Friday

    def test_week_to_month(self):
        """_week_to_month returns correct month for a week."""
        from ai_schedule.scheduling_engine import SchedulingEngine

        mock_session = MagicMock()
        engine = SchedulingEngine(mock_session)

        # Week 24 of 2026: Thursday is June 11, so month = 6
        month = engine._week_to_month(2026, 24)
        assert month == 6
