"""
Data Models — SQLAlchemy model definitions for ai_schedule tables

All tables reside in the `P01_formualte_schedule` schema.
Uses the shared `db` instance from `mrpFlask_5.py`.
"""
import uuid
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Time,
    Text, Index, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

# Import the shared db instance from the main Flask app
from mrpFlask_5 import db


class GeneratedSchedule(db.Model):
    """AI 排程引擎產生的排程結果"""
    __tablename__ = 'generated_schedule'
    __table_args__ = (
        Index('idx_gs_run_id', 'schedule_run_id'),
        Index('idx_gs_week_code', 'week_code'),
        Index('idx_gs_status', 'status'),
        {'schema': 'P01_formualte_schedule'}
    )

    id = Column(Integer, primary_key=True)
    schedule_run_id = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    week_code = Column(String(10), nullable=False)
    date = Column(Date, nullable=False)
    marker = Column(String(100), nullable=False)
    machine_port = Column(String(20))
    freeze_dryer = Column(String(20))
    operator = Column(String(50))
    rd_time = Column(Time)
    start_time = Column(Time)
    end_time = Column(Time)
    quantity = Column(Integer)
    pn = Column(String(20))
    batch = Column(String(30), unique=True)
    work_order = Column(String(30))
    notes = Column(Text)
    conflict_flag = Column(Boolean, default=False)
    conflict_reason = Column(Text)
    priority = Column(Integer, default=1)
    status = Column(String(20), default='draft')
    confirmed_official_id = Column(Integer)
    created_by = Column(String(50))
    created_at = Column(DateTime, server_default=db.text('NOW()'))
    updated_at = Column(DateTime, server_default=db.text('NOW()'))

    def __repr__(self):
        return f'<GeneratedSchedule id={self.id} marker={self.marker} batch={self.batch}>'


class MarkerRule(db.Model):
    """Marker 衍生規則 — 從歷史排程分析萃取"""
    __tablename__ = 'marker_rule'
    __table_args__ = {'schema': 'P01_formualte_schedule'}

    id = Column(Integer, primary_key=True)
    marker_name = Column(String(100), nullable=False, unique=True)
    pn = Column(String(20))
    common_machines = Column(JSONB, server_default='[]')
    common_dryers = Column(JSONB, server_default='[]')
    common_operators = Column(JSONB, server_default='[]')
    avg_start_time = Column(Time)
    avg_end_time = Column(Time)
    avg_duration_minutes = Column(Integer)
    common_quantities = Column(JSONB, server_default='[]')
    special_notes = Column(JSONB, server_default='[]')
    data_confidence = Column(
        String(10),
        CheckConstraint("data_confidence IN ('high', 'medium', 'low')", name='ck_marker_rule_confidence')
    )
    base_rule_validated = Column(Boolean, default=False)
    last_analyzed_at = Column(DateTime)

    def __repr__(self):
        return f'<MarkerRule marker_name={self.marker_name}>'


class MachineCapacityRule(db.Model):
    """機台容量規則 — 各機台的排程限制"""
    __tablename__ = 'machine_capacity_rule'
    __table_args__ = {'schema': 'P01_formualte_schedule'}

    id = Column(Integer, primary_key=True)
    machine_id = Column(String(20), nullable=False, unique=True)
    machine_type = Column(
        String(10),
        CheckConstraint("machine_type IN ('port', 'dryer')", name='ck_machine_capacity_type')
    )
    max_concurrent = Column(Integer, default=1)
    available_hours_start = Column(Time)
    available_hours_end = Column(Time)
    maintenance_schedule = Column(JSONB, server_default='{}')
    base_rule_validated = Column(Boolean, default=False)
    last_updated_at = Column(DateTime, server_default=db.text('NOW()'))

    def __repr__(self):
        return f'<MachineCapacityRule machine_id={self.machine_id}>'


class OperatorRule(db.Model):
    """操作員規則 — 各操作員的排程限制"""
    __tablename__ = 'operator_rule'
    __table_args__ = {'schema': 'P01_formualte_schedule'}

    id = Column(Integer, primary_key=True)
    operator_name = Column(String(50), nullable=False, unique=True)
    capable_markers = Column(JSONB, server_default='[]')
    max_concurrent_tasks = Column(Integer, default=1)
    available_days = Column(JSONB, server_default='[]')
    shift_start = Column(Time)
    shift_end = Column(Time)
    base_rule_validated = Column(Boolean, default=False)
    last_updated_at = Column(DateTime, server_default=db.text('NOW()'))

    def __repr__(self):
        return f'<OperatorRule operator_name={self.operator_name}>'


class AIScheduleAuditLog(db.Model):
    """AI 排程稽核日誌 — 記錄確認/回復操作"""
    __tablename__ = 'ai_schedule_audit_log'
    __table_args__ = (
        Index('idx_audit_run_id', 'schedule_run_id'),
        {'schema': 'P01_formualte_schedule'}
    )

    id = Column(Integer, primary_key=True)
    schedule_run_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(20), nullable=False)
    confirmed_by = Column(String(50))
    confirmed_at = Column(DateTime, server_default=db.text('NOW()'))
    entries_count = Column(Integer)
    force_confirm_reason = Column(Text)
    rollback_at = Column(DateTime)
    rollback_by = Column(String(50))
    details = Column(JSONB, server_default='{}')
    created_at = Column(DateTime, server_default=db.text('NOW()'))

    def __repr__(self):
        return f'<AIScheduleAuditLog id={self.id} action={self.action}>'
