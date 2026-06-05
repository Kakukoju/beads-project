"""
Unit tests for the POST /api/ai-schedule/confirm endpoint.

Tests the route handler logic: request validation, mode handling (all/selected/rollback),
force_confirm, writing to DropletSchedule, audit logging, and superseding other runs.
"""

import sys
import os
import uuid
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import date, time, datetime

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


def _make_entry(id, schedule_run_id, conflict_flag=False, status='draft',
                marker='tCREA-D', week_code='2026-W24'):
    """Helper to create a mock GeneratedSchedule entry."""
    entry = MagicMock()
    entry.id = id
    entry.schedule_run_id = schedule_run_id
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
    entry.batch = f'180260240{id}'
    entry.work_order = f'TMRA2600{id}'
    entry.notes = None
    entry.conflict_flag = conflict_flag
    entry.conflict_reason = 'P3 overlap' if conflict_flag else None
    entry.priority = 1
    entry.status = status
    entry.confirmed_official_id = None
    entry.updated_at = None
    return entry


class TestConfirmEndpointInputValidation:
    """Test request validation (400 errors)."""

    def test_no_json_body_returns_400(self, client):
        """Non-JSON body returns 400 error."""
        resp = client.post(
            '/api/ai-schedule/confirm',
            data='not json',
            content_type='text/plain',
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'JSON' in data['error']

    def test_missing_schedule_run_id_returns_400(self, client):
        """Missing schedule_run_id returns 400."""
        resp = client.post(
            '/api/ai-schedule/confirm',
            json={"mode": "all"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'schedule_run_id' in data['error']

    def test_invalid_uuid_returns_400(self, client):
        """Invalid UUID format returns 400."""
        resp = client.post(
            '/api/ai-schedule/confirm',
            json={"schedule_run_id": "not-a-uuid", "mode": "all"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'UUID' in data['error']

    def test_missing_mode_returns_400(self, client):
        """Missing mode field returns 400."""
        resp = client.post(
            '/api/ai-schedule/confirm',
            json={"schedule_run_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'mode' in data['error']

    def test_invalid_mode_returns_400(self, client):
        """Invalid mode value returns 400."""
        resp = client.post(
            '/api/ai-schedule/confirm',
            json={"schedule_run_id": str(uuid.uuid4()), "mode": "invalid"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'mode' in data['error']

    def test_selected_mode_without_entry_ids_returns_400(self, client):
        """mode='selected' without entry_ids returns 400."""
        resp = client.post(
            '/api/ai-schedule/confirm',
            json={
                "schedule_run_id": str(uuid.uuid4()),
                "mode": "selected",
            },
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'entry_ids' in data['error']

    def test_selected_mode_with_empty_entry_ids_returns_400(self, client):
        """mode='selected' with empty entry_ids returns 400."""
        resp = client.post(
            '/api/ai-schedule/confirm',
            json={
                "schedule_run_id": str(uuid.uuid4()),
                "mode": "selected",
                "entry_ids": [],
            },
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'entry_ids' in data['error']

    def test_force_confirm_without_reason_returns_400(self, client):
        """force_confirm=true without force_confirm_reason returns 400."""
        resp = client.post(
            '/api/ai-schedule/confirm',
            json={
                "schedule_run_id": str(uuid.uuid4()),
                "mode": "all",
                "force_confirm": True,
            },
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert 'force_confirm_reason' in data['error']


class TestConfirmEndpointModeAll:
    """Test mode='all' confirm logic."""

    def test_run_not_found_returns_404(self, client):
        """Non-existent schedule_run_id returns 404."""
        run_id = str(uuid.uuid4())

        mock_gs_class = MagicMock()
        mock_gs_class.query.filter_by.return_value.all.return_value = []

        with patch.object(ai_models, 'GeneratedSchedule', mock_gs_class), \
             patch.dict(sys.modules['mrpFlask_5'].__dict__, {'db': mock_db_instance}):
            resp = client.post(
                '/api/ai-schedule/confirm',
                json={"schedule_run_id": run_id, "mode": "all"},
            )

        assert resp.status_code == 404
        data = resp.get_json()
        assert data['ok'] is False
        assert 'not found' in data['error']

    def test_mode_all_confirms_non_conflict_entries(self, client):
        """mode='all' confirms entries without conflict_flag."""
        run_id = uuid.uuid4()
        entries = [
            _make_entry(1, run_id, conflict_flag=False),
            _make_entry(2, run_id, conflict_flag=False),
            _make_entry(3, run_id, conflict_flag=True),  # conflict
        ]

        mock_gs_class = MagicMock()
        mock_gs_class.query.filter_by.return_value.all.return_value = entries
        mock_gs_class.query.filter.return_value.all.return_value = []

        # Mock the INSERT RETURNING result
        mock_scalar_results = iter([101, 102])
        mock_execute_result = MagicMock()
        mock_execute_result.scalar.side_effect = lambda: next(mock_scalar_results)
        mock_db_instance.session.execute.return_value = mock_execute_result
        mock_db_instance.session.add = MagicMock()
        mock_db_instance.session.commit = MagicMock()

        mock_audit_log = MagicMock()
        mock_audit_log.id = 99

        with patch.object(ai_models, 'GeneratedSchedule', mock_gs_class), \
             patch.object(ai_models, 'AIScheduleAuditLog', return_value=mock_audit_log), \
             patch('sqlalchemy.text', sa_text), \
             patch.dict(sys.modules['mrpFlask_5'].__dict__, {'db': mock_db_instance}):
            resp = client.post(
                '/api/ai-schedule/confirm',
                json={
                    "schedule_run_id": str(run_id),
                    "mode": "all",
                    "confirmed_by": "admin",
                },
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['confirmed_count'] == 2
        assert data['official_ids'] == [101, 102]
        assert data['audit_log_id'] == 99

    def test_mode_all_returns_409_when_selected_has_conflicts(self, client):
        """mode='all' with all entries having conflicts and no force returns 400."""
        run_id = uuid.uuid4()
        # All entries have conflicts
        entries = [
            _make_entry(1, run_id, conflict_flag=True),
            _make_entry(2, run_id, conflict_flag=True),
        ]

        mock_gs_class = MagicMock()
        mock_gs_class.query.filter_by.return_value.all.return_value = entries

        with patch.object(ai_models, 'GeneratedSchedule', mock_gs_class), \
             patch.dict(sys.modules['mrpFlask_5'].__dict__, {'db': mock_db_instance}):
            resp = client.post(
                '/api/ai-schedule/confirm',
                json={"schedule_run_id": str(run_id), "mode": "all"},
            )

        # No non-conflict entries → 400 (no entries to confirm)
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False

    def test_mode_all_force_confirm_includes_conflict_entries(self, client):
        """mode='all' with force_confirm=true includes conflicting entries."""
        run_id = uuid.uuid4()
        entries = [
            _make_entry(1, run_id, conflict_flag=True),
            _make_entry(2, run_id, conflict_flag=False),
        ]

        mock_gs_class = MagicMock()
        mock_gs_class.query.filter_by.return_value.all.return_value = entries
        mock_gs_class.query.filter.return_value.all.return_value = []

        mock_scalar_results = iter([201, 202])
        mock_execute_result = MagicMock()
        mock_execute_result.scalar.side_effect = lambda: next(mock_scalar_results)
        mock_db_instance.session.execute.return_value = mock_execute_result
        mock_db_instance.session.add = MagicMock()
        mock_db_instance.session.commit = MagicMock()

        mock_audit_log = MagicMock()
        mock_audit_log.id = 100

        with patch.object(ai_models, 'GeneratedSchedule', mock_gs_class), \
             patch.object(ai_models, 'AIScheduleAuditLog', return_value=mock_audit_log), \
             patch('sqlalchemy.text', sa_text), \
             patch.dict(sys.modules['mrpFlask_5'].__dict__, {'db': mock_db_instance}):
            resp = client.post(
                '/api/ai-schedule/confirm',
                json={
                    "schedule_run_id": str(run_id),
                    "mode": "all",
                    "force_confirm": True,
                    "force_confirm_reason": "Manager override",
                    "confirmed_by": "manager",
                },
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['confirmed_count'] == 2  # Both entries confirmed


class TestConfirmEndpointModeSelected:
    """Test mode='selected' confirm logic."""

    def test_mode_selected_confirms_only_specified_ids(self, client):
        """mode='selected' only confirms entries with matching IDs."""
        run_id = uuid.uuid4()
        entries = [
            _make_entry(1, run_id, conflict_flag=False),
            _make_entry(2, run_id, conflict_flag=False),
            _make_entry(3, run_id, conflict_flag=False),
        ]

        mock_gs_class = MagicMock()
        mock_gs_class.query.filter_by.return_value.all.return_value = entries
        mock_gs_class.query.filter.return_value.all.return_value = []

        mock_scalar_results = iter([301])
        mock_execute_result = MagicMock()
        mock_execute_result.scalar.side_effect = lambda: next(mock_scalar_results)
        mock_db_instance.session.execute.return_value = mock_execute_result
        mock_db_instance.session.add = MagicMock()
        mock_db_instance.session.commit = MagicMock()

        mock_audit_log = MagicMock()
        mock_audit_log.id = 50

        with patch.object(ai_models, 'GeneratedSchedule', mock_gs_class), \
             patch.object(ai_models, 'AIScheduleAuditLog', return_value=mock_audit_log), \
             patch('sqlalchemy.text', sa_text), \
             patch.dict(sys.modules['mrpFlask_5'].__dict__, {'db': mock_db_instance}):
            resp = client.post(
                '/api/ai-schedule/confirm',
                json={
                    "schedule_run_id": str(run_id),
                    "mode": "selected",
                    "entry_ids": [1],
                },
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['confirmed_count'] == 1
        assert data['official_ids'] == [301]

    def test_mode_selected_returns_409_for_conflict_entries(self, client):
        """mode='selected' with conflict entries and no force returns 409."""
        run_id = uuid.uuid4()
        entries = [
            _make_entry(1, run_id, conflict_flag=True),
            _make_entry(2, run_id, conflict_flag=False),
        ]

        mock_gs_class = MagicMock()
        mock_gs_class.query.filter_by.return_value.all.return_value = entries

        with patch.object(ai_models, 'GeneratedSchedule', mock_gs_class), \
             patch.dict(sys.modules['mrpFlask_5'].__dict__, {'db': mock_db_instance}):
            resp = client.post(
                '/api/ai-schedule/confirm',
                json={
                    "schedule_run_id": str(run_id),
                    "mode": "selected",
                    "entry_ids": [1],
                },
            )

        assert resp.status_code == 409
        data = resp.get_json()
        assert data['ok'] is False
        assert 'conflict' in data['error'].lower()

    def test_mode_selected_missing_ids_returns_400(self, client):
        """mode='selected' with entry_ids not in run returns 400."""
        run_id = uuid.uuid4()
        entries = [
            _make_entry(1, run_id, conflict_flag=False),
        ]

        mock_gs_class = MagicMock()
        mock_gs_class.query.filter_by.return_value.all.return_value = entries

        with patch.object(ai_models, 'GeneratedSchedule', mock_gs_class), \
             patch.dict(sys.modules['mrpFlask_5'].__dict__, {'db': mock_db_instance}):
            resp = client.post(
                '/api/ai-schedule/confirm',
                json={
                    "schedule_run_id": str(run_id),
                    "mode": "selected",
                    "entry_ids": [1, 999],
                },
            )

        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert '999' in data['error']


class TestConfirmEndpointRollback:
    """Test mode='rollback' logic."""

    def test_rollback_marks_entries_and_creates_audit(self, client):
        """mode='rollback' marks all entries as rollback and creates audit log."""
        run_id = uuid.uuid4()
        entries = [
            _make_entry(1, run_id, status='approved'),
            _make_entry(2, run_id, status='approved'),
        ]

        mock_gs_class = MagicMock()
        mock_gs_class.query.filter_by.return_value.all.return_value = entries

        mock_audit_log = MagicMock()
        mock_audit_log.id = 77
        mock_db_instance.session.add = MagicMock()
        mock_db_instance.session.commit = MagicMock()

        with patch.object(ai_models, 'GeneratedSchedule', mock_gs_class), \
             patch.object(ai_models, 'AIScheduleAuditLog', return_value=mock_audit_log), \
             patch.dict(sys.modules['mrpFlask_5'].__dict__, {'db': mock_db_instance}):
            resp = client.post(
                '/api/ai-schedule/confirm',
                json={
                    "schedule_run_id": str(run_id),
                    "mode": "rollback",
                    "confirmed_by": "admin",
                },
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['confirmed_count'] == 0
        assert data['official_ids'] == []
        assert data['audit_log_id'] == 77
        assert data['rollback'] is True
        assert data['rollback_entries_count'] == 2

        # Verify entries were marked as rollback
        for entry in entries:
            assert entry.status == 'rollback'
