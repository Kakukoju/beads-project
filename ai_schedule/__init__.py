"""
ai_schedule — AI 排程分析與自動排程模組

This package provides rule analysis, automatic scheduling (CP-SAT),
conflict detection, Excel sync, and AI advisory capabilities for
Marker production scheduling.
"""
from ai_schedule.routes import ai_schedule_bp

__all__ = ['ai_schedule_bp']
