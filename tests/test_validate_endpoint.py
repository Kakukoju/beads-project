"""
Unit tests for the POST /api/ai-schedule/validate endpoint.

Tests the route handler logic: accepting entry_ids, loading entries,
running ConflictDetector, updating DB entries, and returning results.
"""

import sys
import os
from unittest.mock import MagicMock, patch
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


class TestValidateEndpointInputValidation:
    """Test request validation (400 errors)."""

    def test_no_json_body_returns_400(self, client):
        """Non-JSON body returns 400 error."""
        resp = client.post(
            '/api/ai-schedule/validate',
            data='not json',
            content_type='text/plain',
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'JSON' in data['error']

    def test_missing_entry_ids_returns_400(self, client):
        """Missing entry_ids field returns 400 error."""
        resp = client.post(
            '/api/ai-schedule/validate',
            json={},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'entry_ids' in data['error']

    def test_empty_entry_ids_returns_400(self, client):
        """Empty entry_ids array returns 400 error."""
        resp = client.post(
            '/api/ai-schedule/validate',
            json={"entry_ids": []},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'entry_ids' in data['error']

    def test_non_integer_entry_id_returns_400(self, client):
        """Non-integer value in entry_ids returns 400 error."""
        resp = client.post(
            '/api/ai-schedule/validate',
            json={"entry_ids": [1, "abc", 3]},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'entry_ids[1]' in data['error']
        assert 'integer' in data['error']


def _make_mock_entry(id, marker='tCREA-D', machine_port='P3',
                     freeze_dryer='5', operator='Operator1',
                     date_val=None, rd_time_val=None,
                     start_time_val=None, end_time_val=None):
    """Helper to create a mock GeneratedSchedule ORM entry."""
    entry = MagicMock()
    entry.id = id
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
    entry.conflict_flag = False
    entry.conflict_reason = None
    return entry


class TestValidateEndpointSuccess:
    """Test successful validation flow."""

    def _do_validate_request(self, client, entry_ids, mock_entries, mock_conflicts):
        """Helper to execute a validate request with proper mocking.

        The deferred imports in the validate route import from specific modules.
        We need to patch the actual module-level objects that get imported.
        """
        # Patch GeneratedSchedule at the models module level
        mock_gs_class = MagicMock()
        mock_gs_class.query.filter.return_value.all.return_value = mock_entries

        # Patch SchedulingEngine
        mock_engine_instance = MagicMock()
        mock_engine_instance._load_rules.return_value = {}

        # Patch ConflictDetector to return specified conflicts
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
            resp = client.post(
                '/api/ai-schedule/validate',
                json={"entry_ids": entry_ids},
            )

        return resp, mock_db_session

    def test_valid_entries_no_conflicts(self, client):
        """Entries with no conflicts return valid=True and empty conflicts."""
        mock_entry = _make_mock_entry(1)
        resp, _ = self._do_validate_request(client, [1], [mock_entry], [])

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert len(data['results']) == 1
        assert data['results'][0]['id'] == 1
        assert data['results'][0]['valid'] is True
        assert data['results'][0]['conflicts'] == []
        assert data['summary']['total_entries'] == 1
        assert data['summary']['valid_count'] == 1
        assert data['summary']['conflict_count'] == 0

    def test_entries_with_conflicts(self, client):
        """Entries with conflicts return valid=False with conflict details."""
        mock_entry1 = _make_mock_entry(1)
        mock_entry2 = _make_mock_entry(2, marker='GGT')

        conflict1 = Conflict(
            entry_id=1,
            conflict_type='machine_overlap',
            description='P3 時段重疊',
            severity='error',
        )
        conflict2 = Conflict(
            entry_id=2,
            conflict_type='machine_overlap',
            description='P3 時段重疊',
            severity='error',
        )

        resp, _ = self._do_validate_request(
            client, [1, 2], [mock_entry1, mock_entry2], [conflict1, conflict2]
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert len(data['results']) == 2

        # Entry 1: has conflict
        assert data['results'][0]['id'] == 1
        assert data['results'][0]['valid'] is False
        assert len(data['results'][0]['conflicts']) == 1
        assert data['results'][0]['conflicts'][0]['type'] == 'machine_overlap'
        assert data['results'][0]['conflicts'][0]['description'] == 'P3 時段重疊'
        assert data['results'][0]['conflicts'][0]['severity'] == 'error'

        # Entry 2: has conflict
        assert data['results'][1]['id'] == 2
        assert data['results'][1]['valid'] is False

        # Summary
        assert data['summary']['total_entries'] == 2
        assert data['summary']['valid_count'] == 0
        assert data['summary']['conflict_count'] == 2

    def test_mixed_valid_and_conflict_entries(self, client):
        """Mix of valid and conflicting entries returns correct results."""
        mock_entry1 = _make_mock_entry(1)
        mock_entry2 = _make_mock_entry(2, marker='GGT')

        # Only entry 2 has a conflict
        conflict = Conflict(
            entry_id=2,
            conflict_type='base_rule_violation',
            description='GGT 分配機台 P3 不在允許清單中',
            severity='warning',
        )

        resp, _ = self._do_validate_request(
            client, [1, 2], [mock_entry1, mock_entry2], [conflict]
        )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True

        # Entry 1: valid
        assert data['results'][0]['id'] == 1
        assert data['results'][0]['valid'] is True
        assert data['results'][0]['conflicts'] == []

        # Entry 2: conflict
        assert data['results'][1]['id'] == 2
        assert data['results'][1]['valid'] is False
        assert data['results'][1]['conflicts'][0]['severity'] == 'warning'

        # Summary
        assert data['summary']['total_entries'] == 2
        assert data['summary']['valid_count'] == 1
        assert data['summary']['conflict_count'] == 1


class TestValidateEndpointResponseFormat:
    """Test that response format matches the design spec."""

    def test_response_uses_id_not_entry_id(self, client):
        """Results use 'id' key, not 'entry_id', matching design spec."""
        mock_gs_class = MagicMock()
        mock_gs_class.query.filter.return_value.all.return_value = []

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
            resp = client.post(
                '/api/ai-schedule/validate',
                json={"entry_ids": [1, 2]},
            )

        assert resp.status_code == 200
        data = resp.get_json()

        # Top-level keys
        assert 'ok' in data
        assert 'results' in data
        assert 'summary' in data

        # Summary keys
        assert 'total_entries' in data['summary']
        assert 'valid_count' in data['summary']
        assert 'conflict_count' in data['summary']

        # Results use 'id' not 'entry_id'
        for result in data['results']:
            assert 'id' in result
            assert 'valid' in result
            assert 'conflicts' in result
            assert 'entry_id' not in result

    def test_conflict_objects_have_type_description_severity(self, client):
        """Conflict objects in results include type, description, and severity."""
        mock_entry = _make_mock_entry(1)
        mock_gs_class = MagicMock()
        mock_gs_class.query.filter.return_value.all.return_value = [mock_entry]

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
            resp = client.post(
                '/api/ai-schedule/validate',
                json={"entry_ids": [1]},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        conflict_obj = data['results'][0]['conflicts'][0]
        assert 'type' in conflict_obj
        assert 'description' in conflict_obj
        assert 'severity' in conflict_obj
        # Should NOT have 'reason' key (old format)
        assert 'reason' not in conflict_obj
