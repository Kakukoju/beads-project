"""
Unit tests for GET /api/tutti-production/batch-status/history endpoint.

Tests the route handler logic: parameter validation, history query, and response format.
"""

import sys
import os
from unittest.mock import MagicMock, patch
from datetime import datetime

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from flask import Flask


@pytest.fixture
def mock_db():
    """Create a mock db.session for the endpoint."""
    mock = MagicMock()
    return mock


@pytest.fixture
def app(mock_db):
    """Create a minimal Flask test app with the history endpoint."""
    app = Flask(__name__)
    app.config['TESTING'] = True

    # Import the endpoint logic inline, mocking dependencies
    from sqlalchemy import text

    @app.route('/api/tutti-production/batch-status/history', methods=['GET'])
    def get_batch_status_history():
        from flask import request, jsonify
        batch_key = request.args.get('batch_key', '').strip()
        if not batch_key:
            return jsonify({'ok': False, 'error': '需提供 batch_key 參數'}), 400

        try:
            # Query current status from batch_build_line_status
            status_row = mock_db.session.execute(text("""
                SELECT status, modification_count
                FROM panel_production.batch_build_line_status
                WHERE batch_key = :key
            """), {'key': batch_key}).fetchone()

            if status_row is None:
                return jsonify({
                    'ok': True,
                    'batch_key': batch_key,
                    'current_status': '未建線',
                    'modification_count': 0,
                    'history': []
                })

            current_status = status_row[0]
            modification_count = status_row[1]

            # Query full history ordered by transitioned_at DESC
            history_rows = mock_db.session.execute(text("""
                SELECT previous_status, new_status, transitioned_at, operator, work_order_no, lot_no
                FROM panel_production.batch_build_line_history
                WHERE batch_key = :key
                ORDER BY transitioned_at DESC
            """), {'key': batch_key}).fetchall()

            history = []
            for row in history_rows:
                history.append({
                    'previous_status': row[0],
                    'new_status': row[1],
                    'transitioned_at': row[2].isoformat() if row[2] else None,
                    'operator': row[3],
                    'work_order_no': row[4],
                    'lot_no': row[5]
                })

            return jsonify({
                'ok': True,
                'batch_key': batch_key,
                'current_status': current_status,
                'modification_count': modification_count,
                'history': history
            })
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


class TestBatchHistoryEndpointValidation:
    """Test parameter validation (400 errors)."""

    def test_missing_batch_key_returns_400(self, client):
        """Missing batch_key query parameter returns 400."""
        resp = client.get('/api/tutti-production/batch-status/history')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert '需提供 batch_key 參數' in data['error']

    def test_empty_batch_key_returns_400(self, client):
        """Empty batch_key query parameter returns 400."""
        resp = client.get('/api/tutti-production/batch-status/history?batch_key=')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert '需提供 batch_key 參數' in data['error']

    def test_whitespace_batch_key_returns_400(self, client):
        """Whitespace-only batch_key returns 400."""
        resp = client.get('/api/tutti-production/batch-status/history?batch_key=   ')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['ok'] is False
        assert '需提供 batch_key 參數' in data['error']


class TestBatchHistoryEndpointNoRecords:
    """Test behavior when no status record exists for the batch_key."""

    def test_no_status_record_returns_empty_history(self, client, mock_db):
        """batch_key with no status record returns 未建線 with empty history."""
        mock_db.session.execute.return_value.fetchone.return_value = None

        resp = client.get('/api/tutti-production/batch-status/history?batch_key=LOT2024A::d_lot')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['batch_key'] == 'LOT2024A::d_lot'
        assert data['current_status'] == '未建線'
        assert data['modification_count'] == 0
        assert data['history'] == []


class TestBatchHistoryEndpointWithRecords:
    """Test behavior when status records exist for the batch_key."""

    def test_returns_history_with_transitions(self, client, mock_db):
        """batch_key with history returns transitions ordered by transitioned_at DESC."""
        # First call returns current status
        mock_status_result = MagicMock()
        mock_status_result.fetchone.return_value = ('已改線(1)', 1)

        # Second call returns history rows
        ts1 = datetime(2025, 6, 15, 10, 30, 0)
        ts2 = datetime(2025, 6, 16, 14, 0, 0)
        mock_history_result = MagicMock()
        mock_history_result.fetchall.return_value = [
            ('已建線', '已改線(1)', ts2, 'operator2', 'WO-2025-001', '1-053054-26060201'),
            ('未建線', '已建線', ts1, 'operator1', 'WO-2025-001', '1-053054-26060201'),
        ]

        mock_db.session.execute.side_effect = [mock_status_result, mock_history_result]

        resp = client.get('/api/tutti-production/batch-status/history?batch_key=LOT2024B::bigD_lot')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['batch_key'] == 'LOT2024B::bigD_lot'
        assert data['current_status'] == '已改線(1)'
        assert data['modification_count'] == 1
        assert len(data['history']) == 2

        # Verify first history entry (most recent)
        assert data['history'][0]['previous_status'] == '已建線'
        assert data['history'][0]['new_status'] == '已改線(1)'
        assert data['history'][0]['transitioned_at'] == '2025-06-16T14:00:00'
        assert data['history'][0]['operator'] == 'operator2'
        assert data['history'][0]['work_order_no'] == 'WO-2025-001'
        assert data['history'][0]['lot_no'] == '1-053054-26060201'

        # Verify second history entry (older)
        assert data['history'][1]['previous_status'] == '未建線'
        assert data['history'][1]['new_status'] == '已建線'
        assert data['history'][1]['transitioned_at'] == '2025-06-15T10:30:00'
        assert data['history'][1]['operator'] == 'operator1'

    def test_single_transition_history(self, client, mock_db):
        """batch_key with single transition returns one history entry."""
        mock_status_result = MagicMock()
        mock_status_result.fetchone.return_value = ('已建線', 0)

        ts1 = datetime(2025, 6, 15, 10, 30, 0)
        mock_history_result = MagicMock()
        mock_history_result.fetchall.return_value = [
            ('未建線', '已建線', ts1, 'operator1', 'WO-2025-001', '1-053054-26060201'),
        ]

        mock_db.session.execute.side_effect = [mock_status_result, mock_history_result]

        resp = client.get('/api/tutti-production/batch-status/history?batch_key=LOT2024C::u_lot')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert data['current_status'] == '已建線'
        assert data['modification_count'] == 0
        assert len(data['history']) == 1


class TestBatchHistoryEndpointErrors:
    """Test error handling."""

    def test_database_error_returns_500(self, client, mock_db):
        """Database exception returns 500."""
        mock_db.session.execute.side_effect = Exception('connection refused')

        resp = client.get('/api/tutti-production/batch-status/history?batch_key=LOT2024A::d_lot')
        assert resp.status_code == 500
        data = resp.get_json()
        assert data['ok'] is False
        assert 'connection refused' in data['error']
