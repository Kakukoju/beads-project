"""
Unit tests for the PUT /api/ai-schedule/update/<id> endpoint.

Tests the route handler logic: accepting field updates, loading the entry,
applying updates, running ConflictDetector on all entries in the same
schedule_run_id, updating conflict_flag/conflict_reason, and returning results.
"""

import sys
import os
import uuid
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import date, time

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock mrpFlask_5 before importing any ai_schedule modules
from sqlalchemy import text as sa_text
from sqlalchemy.orm import DeclarativeBase


class MockBase(DeclarativeBase):
    pass


mock_mrpFlask = MagicMock()
mock_db_instance = MagicMock()
mock_db_instance.text = sa_text
mock_db_instance.Model = MockBase
mock_mrpFlask.db = mock_db_instance
sys.modules['mrpFlask_5'] = mock_mrpFlask

import pytest
from flask import Flask
from ai_schedule.routes import ai_schedule_bp
from ai_schedule.conflict_detector import Conflict, ConflictDetector
from ai_schedule import models as ai_models


@pytest.fixture
def app():
    """Create a Flask test app with the ai_schedule blueprint."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(ai_schedule_bp)
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


def _make_mock_entry(id, marker='tCREA-D', machine_port='P3',
                     freeze_dryer='5', operator='Operator1',
                     date_val=None, rd_time_val=None,
                     start_time_val=None, end_time_val=None,
                     schedule_run_id=None):
    """Helper to create a mock GeneratedSchedule ORM entry."""
    entry = MagicMock()
    entry.id = id
    entry.schedule_run_id = schedule_run_id or uuid.uuid4()
    entry.week_code = '2026-W24'
    entry.date = date_val or date(2026, 6, 8)
    entry.marker = marker
    entry.machine_port = machine_port
    entry.freeze_dryer = freeze_dryer
    entry.operator = operator
    entry.rd_time = rd_time_val or time(14, 0)
    entry.start_time = start_time_val or time(14, 30)
    entry.end_time = end_time_val or time(18, 0)
    entry.quantity = 1300
    entry.pn = '5714400180'
    entry.batch = f'18026024{id}'
    entry.work_order = f'TMRA26{id:03d}'
    entry.notes = None
    entry.conflict_flag = False
    entry.conflict_reason = None
    entry.priority = 1
    entry.status = 'draft'
    return entry


class TestUpdateEndpointInputValidation:
    """Test request validation (400 errors)."""

    def test_no_json_body_returns_400(self, client):
        """Non-JSON body returns 400 error."""
        resp = client.put(
            '/api/ai-schedule/update/1',
            data='not json',
            content_type='text/plain',
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'JSON' in data['error']

    def test_empty_body_returns_400(self, client):
        """Empty JSON object returns 400 error."""
        resp = client.put(
            '/api/ai-schedule/update/1',
            json={},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'non-empty' in data['error']

    def test_unknown_field_returns_400(self, client):
        """Unknown field in request body returns 400 error."""
        resp = client.put(
            '/api/ai-schedule/update/1',
            json={"unknown_field": "value"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'Unknown fields' in data['error']

    def test_invalid_date_format_returns_400(self, client):
        """Invalid date format returns 400 error."""
        resp = client.put(
            '/api/ai-schedule/update/1',
            json={"date": "06-08-2026"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'date' in data['error'].lower()

    def test_invalid_time_format_returns_400(self, client):
        """Invalid time format returns 400 error."""
        resp = client.put(
            '/api/ai-schedule/update/1',
            json={"start_time": "25:99"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'start_time' in data['error']

    def test_invalid_priority_type_returns_400(self, client):
        """Non-integer priority returns 400 error."""
        resp = client.put(
            '/api/ai-schedule/update/1',
            json={"priority": "high"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'priority' in data['error']

    def test_invalid_machine_port_type_returns_400(self, client):
        """Non-string machine_port returns 400 error."""
        resp = client.put(
            '/api/ai-schedule/update/1',
            json={"machine_port": 123},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'machine_port' in data['error']


class TestUpdateEndpointNotFound:
    """Test 404 response when entry not found."""

    def test_nonexistent_entry_returns_404(self, client):
        """Non-existent entry ID returns 404 error."""
        mock_gs_class = MagicMock()
        mock_gs_class.query.get.return_value = None

        with patch.object(ai_models, 'GeneratedSchedule', mock_gs_class), \
             patch.dict(sys.modules['mrpFlask_5'].__dict__,
                        {'db': MagicMock(session=MagicMock())}):
            resp = client.put(
                '/api/ai-schedule/update/999',
                json={"machine_port": "P5"},
            )

        assert resp.status_code == 404
        data = resp.get_json()
        assert data['ok'] is False
        assert '999' in data['error']


class TestUpdateEndpointSuccess:
    """Test successful update flow."""

    def _do_update_request(self, client, entry_id, body, mock_entry,
                           mock_run_entries, mock_conflicts):
        """Helper to execute an update request with proper mocking."""
        mock_gs_class = MagicMock()
        mock_gs_class.query.get.return_value = mock_entry
        mock_gs_class.query.filter_by.return_value.all.return_value = mock_run_entries

        mock_engine_instance = MagicMock()
        mock_engine_instance._load_rules.return_value = {}

        mock_detector_instance = MagicMock()
        mock_detector_instance.detect_all.return_value = mock_conflicts

        mock_db_session = MagicMock()

        with patch.object(ai_models, 'GeneratedSchedule', mock_gs_class), \
             patch('ai_schedule.scheduling_engine.SchedulingEngine',
                   return_value=mock_engine_instance), \
             patch('ai_schedule.conflict_detector.ConflictDetector',
                   return_value=mock_detector_instance), \
             patch.dict(sys.modules['mrpFlask_5'].__dict__,
                        {'db': MagicMock(session=mock_db_session)}):
            resp = client.put(
                f'/api/ai-schedule/update/{entry_id}',
                json=body,
            )

        return resp, mock_db_session

    def test_update_machine_port_no_conflicts(self, client):
        """Update machine_port returns ok with no conflicts."""
        run_id = uuid.uuid4()
        mock_entry = _make_mock_entry(1, schedule_run_id=run_id)
        mock_run_entries = [mock_entry]

        resp, _ = self._do_update_request(
            client, 1, {"machine_port": "P5"},
            mock_entry, mock_run_entries, []
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'entry' in data
        assert 'conflicts' in data
        assert data['conflicts'] == []

    def test_update_applies_field_changes(self, client):
        """Update applies field changes to the ORM entry."""
        run_id = uuid.uuid4()
        mock_entry = _make_mock_entry(1, schedule_run_id=run_id)
        mock_run_entries = [mock_entry]

        resp, _ = self._do_update_request(
            client, 1, {"machine_port": "P5", "operator": "李四"},
            mock_entry, mock_run_entries, []
        )

        assert resp.status_code == 200
        # Verify setattr was called (mocked object captures attribute sets)
        assert mock_entry.machine_port == "P5"
        assert mock_entry.operator == "李四"

    def test_update_with_conflicts_returned(self, client):
        """Update that introduces conflicts returns them in response."""
        run_id = uuid.uuid4()
        mock_entry = _make_mock_entry(1, schedule_run_id=run_id)
        mock_entry2 = _make_mock_entry(2, schedule_run_id=run_id)
        mock_run_entries = [mock_entry, mock_entry2]

        conflict = Conflict(
            entry_id=1,
            conflict_type='machine_overlap',
            description='P5 時段重疊',
            severity='error',
        )

        resp, _ = self._do_update_request(
            client, 1, {"machine_port": "P5"},
            mock_entry, mock_run_entries, [conflict]
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert len(data['conflicts']) == 1
        assert data['conflicts'][0]['type'] == 'machine_overlap'
        assert data['conflicts'][0]['description'] == 'P5 時段重疊'
        assert data['conflicts'][0]['severity'] == 'error'

    def test_update_date_field(self, client):
        """Update date field with valid YYYY-MM-DD string."""
        run_id = uuid.uuid4()
        mock_entry = _make_mock_entry(1, schedule_run_id=run_id)
        mock_run_entries = [mock_entry]

        resp, _ = self._do_update_request(
            client, 1, {"date": "2026-06-10"},
            mock_entry, mock_run_entries, []
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

    def test_update_time_fields(self, client):
        """Update time fields with valid HH:MM strings."""
        run_id = uuid.uuid4()
        mock_entry = _make_mock_entry(1, schedule_run_id=run_id)
        mock_run_entries = [mock_entry]

        resp, _ = self._do_update_request(
            client, 1,
            {"start_time": "15:00", "end_time": "19:30", "rd_time": "14:30"},
            mock_entry, mock_run_entries, []
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

    def test_update_null_values_accepted(self, client):
        """Null values are accepted for nullable fields."""
        run_id = uuid.uuid4()
        mock_entry = _make_mock_entry(1, schedule_run_id=run_id)
        mock_run_entries = [mock_entry]

        resp, _ = self._do_update_request(
            client, 1,
            {"notes": None, "machine_port": None, "priority": None},
            mock_entry, mock_run_entries, []
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

    def test_db_commit_called(self, client):
        """Database commit is called after update."""
        run_id = uuid.uuid4()
        mock_entry = _make_mock_entry(1, schedule_run_id=run_id)
        mock_run_entries = [mock_entry]

        resp, mock_db_session = self._do_update_request(
            client, 1, {"machine_port": "P5"},
            mock_entry, mock_run_entries, []
        )

        assert resp.status_code == 200
        mock_db_session.commit.assert_called_once()


class TestUpdateEndpointResponseFormat:
    """Test that response format matches the design spec."""

    def test_response_has_required_keys(self, client):
        """Response includes ok, entry, and conflicts keys."""
        run_id = uuid.uuid4()
        mock_entry = _make_mock_entry(1, schedule_run_id=run_id)
        mock_run_entries = [mock_entry]

        mock_gs_class = MagicMock()
        mock_gs_class.query.get.return_value = mock_entry
        mock_gs_class.query.filter_by.return_value.all.return_value = mock_run_entries

        mock_engine = MagicMock()
        mock_engine._load_rules.return_value = {}

        mock_detector = MagicMock()
        mock_detector.detect_all.return_value = []

        with patch.object(ai_models, 'GeneratedSchedule', mock_gs_class), \
             patch('ai_schedule.scheduling_engine.SchedulingEngine',
                   return_value=mock_engine), \
             patch('ai_schedule.conflict_detector.ConflictDetector',
                   return_value=mock_detector), \
             patch.dict(sys.modules['mrpFlask_5'].__dict__,
                        {'db': MagicMock(session=MagicMock())}):
            resp = client.put(
                '/api/ai-schedule/update/1',
                json={"machine_port": "P5"},
            )

        assert resp.status_code == 200
        data = resp.get_json()

        # Top-level keys
        assert 'ok' in data
        assert 'entry' in data
        assert 'conflicts' in data
        assert data['ok'] is True

    def test_entry_object_has_all_fields(self, client):
        """Entry object in response has all expected schedule fields."""
        run_id = uuid.uuid4()
        mock_entry = _make_mock_entry(1, schedule_run_id=run_id)
        mock_run_entries = [mock_entry]

        mock_gs_class = MagicMock()
        mock_gs_class.query.get.return_value = mock_entry
        mock_gs_class.query.filter_by.return_value.all.return_value = mock_run_entries

        mock_engine = MagicMock()
        mock_engine._load_rules.return_value = {}

        mock_detector = MagicMock()
        mock_detector.detect_all.return_value = []

        with patch.object(ai_models, 'GeneratedSchedule', mock_gs_class), \
             patch('ai_schedule.scheduling_engine.SchedulingEngine',
                   return_value=mock_engine), \
             patch('ai_schedule.conflict_detector.ConflictDetector',
                   return_value=mock_detector), \
             patch.dict(sys.modules['mrpFlask_5'].__dict__,
                        {'db': MagicMock(session=MagicMock())}):
            resp = client.put(
                '/api/ai-schedule/update/1',
                json={"operator": "王五"},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        entry = data['entry']

        # Verify all expected fields present
        expected_fields = [
            'id', 'schedule_run_id', 'week_code', 'date', 'marker',
            'machine_port', 'freeze_dryer', 'operator', 'rd_time',
            'start_time', 'end_time', 'quantity', 'pn', 'batch',
            'work_order', 'notes', 'conflict_flag', 'conflict_reason',
            'priority', 'status',
        ]
        for field in expected_fields:
            assert field in entry, f"Missing field: {field}"

    def test_conflict_objects_have_type_description_severity(self, client):
        """Conflict objects include type, description, and severity."""
        run_id = uuid.uuid4()
        mock_entry = _make_mock_entry(1, schedule_run_id=run_id)
        mock_run_entries = [mock_entry]

        mock_gs_class = MagicMock()
        mock_gs_class.query.get.return_value = mock_entry
        mock_gs_class.query.filter_by.return_value.all.return_value = mock_run_entries

        mock_engine = MagicMock()
        mock_engine._load_rules.return_value = {}

        conflict = Conflict(
            entry_id=1,
            conflict_type='dryer_capacity',
            description='凍乾機超容',
            severity='error',
        )
        mock_detector = MagicMock()
        mock_detector.detect_all.return_value = [conflict]

        with patch.object(ai_models, 'GeneratedSchedule', mock_gs_class), \
             patch('ai_schedule.scheduling_engine.SchedulingEngine',
                   return_value=mock_engine), \
             patch('ai_schedule.conflict_detector.ConflictDetector',
                   return_value=mock_detector), \
             patch.dict(sys.modules['mrpFlask_5'].__dict__,
                        {'db': MagicMock(session=MagicMock())}):
            resp = client.put(
                '/api/ai-schedule/update/1',
                json={"freeze_dryer": "3"},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['conflicts']) == 1
        conflict_obj = data['conflicts'][0]
        assert 'type' in conflict_obj
        assert 'description' in conflict_obj
        assert 'severity' in conflict_obj
