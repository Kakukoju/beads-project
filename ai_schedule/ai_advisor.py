"""
AI Advisor — LLM-based 衝突分析與排程建議

Provides intelligent suggestions for resolving scheduling conflicts,
natural language explanations of conflict causes, and strategic
scheduling recommendations based on historical patterns.

Currently uses rule-based logic as a fallback. The architecture supports
plugging in an actual LLM client (e.g., OpenAI, Bedrock) by replacing
the _generate_* methods.

Requirements: 8.1, 8.2, 8.3, 8.4
"""

import logging
from dataclasses import dataclass, field
from datetime import time, timedelta, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Suggestion:
    """A single scheduling adjustment suggestion."""
    type: str  # 'machine_swap', 'time_shift', 'operator_change'
    description: str
    confidence: float  # 0.0 ~ 1.0
    proposed_changes: dict = field(default_factory=dict)


@dataclass
class StrategyRecommendation:
    """A strategic scheduling recommendation."""
    strategy: str
    rationale: str
    estimated_impact: str


# ---------------------------------------------------------------------------
# AIAdvisor
# ---------------------------------------------------------------------------

class AIAdvisor:
    """AI 輔助排程建議模組。

    Provides:
    - get_suggestions(entry_id): Generate alternative suggestions for a
      conflicting schedule entry (machine swap, time shift, operator change).
    - explain_conflict(conflict_dict): Produce a natural language explanation
      of a scheduling conflict's cause and resolution guidance.
    - get_strategy_recommendations(historical_patterns): Suggest scheduling
      strategies based on observed historical patterns.

    Design:
    - AI advisor only provides advice; scheduling decisions remain with
      Scheduling_Engine.
    - Currently rule-based; can be replaced with LLM calls by overriding
      the _generate_* methods or injecting an LLM client.
    """

    def __init__(self, db_session):
        """
        Initialize AIAdvisor.

        Args:
            db_session: SQLAlchemy session for querying schedule data,
                        marker_rule, machine_capacity_rule, operator_rule.
        """
        self.db = db_session

        # Placeholder LLM client configuration.
        # Replace with actual LLM client when credentials are available:
        #   self.llm_client = SomeLLMClient(api_key=...)
        self.llm_client = None
        self._use_llm = False  # Toggle to True when LLM is configured

        logger.info("[AIAdvisor] Initialized (rule-based mode)")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_suggestions(self, entry_id: int) -> list[dict]:
        """
        Generate alternative suggestions for a conflicting schedule entry.

        Loads the entry from generated_schedule, inspects its conflicts,
        and generates 1-3 concrete suggestions (machine swap, time shift,
        or operator change).

        Args:
            entry_id: The id of the generated_schedule entry.

        Returns:
            List of suggestion dicts, each with keys:
            - type: 'machine_swap' | 'time_shift' | 'operator_change'
            - description: Human-readable suggestion text
            - confidence: float 0.0-1.0
            - proposed_changes: dict of field -> new value
        """
        # Load the entry
        entry = self._load_entry(entry_id)
        if entry is None:
            logger.warning(f"[AIAdvisor] Entry {entry_id} not found")
            return []

        # If no conflict, no suggestions needed
        if not entry.get('conflict_flag'):
            return []

        conflict_reason = entry.get('conflict_reason', '') or ''
        marker = entry.get('marker', '')

        # Load rules for this marker
        marker_rule = self._load_marker_rule(marker)
        machine_rules = self._load_machine_capacity_rules()
        operator_rules = self._load_operator_rules()

        # Load other entries on the same date for context
        same_day_entries = self._load_same_day_entries(
            entry.get('date'), entry_id
        )

        # If LLM is available, use it
        if self._use_llm and self.llm_client:
            return self._generate_suggestions_llm(
                entry, conflict_reason, marker_rule,
                machine_rules, operator_rules, same_day_entries
            )

        # Otherwise, use rule-based logic
        return self._generate_suggestions_rules(
            entry, conflict_reason, marker_rule,
            machine_rules, operator_rules, same_day_entries
        )

    def explain_conflict(self, conflict: dict) -> str:
        """
        Produce a natural language explanation of a scheduling conflict.

        Args:
            conflict: Dict with at minimum:
                - type: conflict type string (e.g. 'machine_overlap',
                  'dryer_capacity', 'operator_overlap', 'production_flow',
                  'base_rule_violation')
                - description: existing description of the conflict

        Returns:
            Natural language explanation string including cause and
            resolution guidance.
        """
        if not conflict:
            return "無法分析：未提供衝突資訊。"

        conflict_type = conflict.get('type', '')
        description = conflict.get('description', '')

        # If LLM is available, use it for richer explanation
        if self._use_llm and self.llm_client:
            return self._explain_conflict_llm(conflict_type, description)

        # Rule-based explanation
        return self._explain_conflict_rules(conflict_type, description)

    def get_strategy_recommendations(
        self, historical_patterns: dict
    ) -> list[dict]:
        """
        Suggest scheduling strategies based on historical patterns.

        Args:
            historical_patterns: Dict containing observed patterns, e.g.:
                - frequent_conflicts: list of {type, markers, frequency}
                - peak_hours: dict of hour -> usage count
                - machine_utilization: dict of machine -> utilization %
                - operator_load: dict of operator -> avg daily tasks
                - marker_pairs: list of {markers, co_occurrence_rate}

        Returns:
            List of recommendation dicts, each with:
            - strategy: short strategy name
            - rationale: explanation of why this is recommended
            - estimated_impact: expected improvement description
        """
        if not historical_patterns:
            return []

        # If LLM is available, use it
        if self._use_llm and self.llm_client:
            return self._generate_strategy_llm(historical_patterns)

        # Rule-based strategy generation
        return self._generate_strategy_rules(historical_patterns)

    # ------------------------------------------------------------------
    # Data Loading Helpers
    # ------------------------------------------------------------------

    def _load_entry(self, entry_id: int) -> Optional[dict]:
        """Load a generated_schedule entry by ID and return as dict."""
        try:
            from ai_schedule.models import GeneratedSchedule
            entry = self.db.query(GeneratedSchedule).filter_by(id=entry_id).first()
            if entry is None:
                return None
            return {
                'id': entry.id,
                'schedule_run_id': str(entry.schedule_run_id) if entry.schedule_run_id else None,
                'week_code': entry.week_code,
                'date': entry.date,
                'marker': entry.marker,
                'machine_port': entry.machine_port,
                'freeze_dryer': entry.freeze_dryer,
                'operator': entry.operator,
                'rd_time': entry.rd_time,
                'start_time': entry.start_time,
                'end_time': entry.end_time,
                'quantity': entry.quantity,
                'pn': entry.pn,
                'batch': entry.batch,
                'work_order': entry.work_order,
                'notes': entry.notes,
                'conflict_flag': entry.conflict_flag,
                'conflict_reason': entry.conflict_reason,
                'priority': entry.priority,
                'status': entry.status,
            }
        except Exception as e:
            logger.error(f"[AIAdvisor] Error loading entry {entry_id}: {e}")
            return None

    def _load_marker_rule(self, marker_name: str) -> Optional[dict]:
        """Load marker_rule for a given marker name."""
        try:
            from ai_schedule.models import MarkerRule
            rule = self.db.query(MarkerRule).filter_by(
                marker_name=marker_name
            ).first()
            if rule is None:
                return None
            return {
                'marker_name': rule.marker_name,
                'pn': rule.pn,
                'common_machines': rule.common_machines or [],
                'common_dryers': rule.common_dryers or [],
                'common_operators': rule.common_operators or [],
                'avg_start_time': rule.avg_start_time,
                'avg_end_time': rule.avg_end_time,
                'avg_duration_minutes': rule.avg_duration_minutes,
                'common_quantities': rule.common_quantities or [],
                'special_notes': rule.special_notes or [],
            }
        except Exception as e:
            logger.error(f"[AIAdvisor] Error loading marker rule for {marker_name}: {e}")
            return None

    def _load_machine_capacity_rules(self) -> dict:
        """Load all machine_capacity_rule entries as dict keyed by machine_id."""
        try:
            from ai_schedule.models import MachineCapacityRule
            rules = self.db.query(MachineCapacityRule).all()
            return {
                r.machine_id: {
                    'machine_type': r.machine_type,
                    'max_concurrent': r.max_concurrent,
                    'available_hours_start': r.available_hours_start,
                    'available_hours_end': r.available_hours_end,
                }
                for r in rules
            }
        except Exception as e:
            logger.error(f"[AIAdvisor] Error loading machine capacity rules: {e}")
            return {}

    def _load_operator_rules(self) -> dict:
        """Load all operator_rule entries as dict keyed by operator_name."""
        try:
            from ai_schedule.models import OperatorRule
            rules = self.db.query(OperatorRule).all()
            return {
                r.operator_name: {
                    'capable_markers': r.capable_markers or [],
                    'max_concurrent_tasks': r.max_concurrent_tasks,
                    'shift_start': r.shift_start,
                    'shift_end': r.shift_end,
                }
                for r in rules
            }
        except Exception as e:
            logger.error(f"[AIAdvisor] Error loading operator rules: {e}")
            return {}

    def _load_same_day_entries(self, entry_date, exclude_id: int) -> list[dict]:
        """Load other entries on the same date (for context)."""
        try:
            from ai_schedule.models import GeneratedSchedule
            entries = self.db.query(GeneratedSchedule).filter(
                GeneratedSchedule.date == entry_date,
                GeneratedSchedule.id != exclude_id,
                GeneratedSchedule.status != 'superseded',
            ).all()
            return [
                {
                    'id': e.id,
                    'marker': e.marker,
                    'machine_port': e.machine_port,
                    'freeze_dryer': e.freeze_dryer,
                    'operator': e.operator,
                    'start_time': e.start_time,
                    'end_time': e.end_time,
                    'rd_time': e.rd_time,
                }
                for e in entries
            ]
        except Exception as e:
            logger.error(f"[AIAdvisor] Error loading same-day entries: {e}")
            return []

    # ------------------------------------------------------------------
    # Rule-Based Suggestion Logic
    # ------------------------------------------------------------------

    def _generate_suggestions_rules(
        self,
        entry: dict,
        conflict_reason: str,
        marker_rule: Optional[dict],
        machine_rules: dict,
        operator_rules: dict,
        same_day_entries: list[dict],
    ) -> list[dict]:
        """Generate suggestions using rule-based logic."""
        suggestions: list[dict] = []

        # Determine conflict types from the reason string
        conflict_types = self._parse_conflict_types(conflict_reason)

        for ctype in conflict_types:
            if ctype == 'machine_overlap':
                suggestions.extend(self._suggest_machine_swap(
                    entry, marker_rule, machine_rules, same_day_entries
                ))
                suggestions.extend(self._suggest_time_shift_for_machine(
                    entry, same_day_entries
                ))

            elif ctype == 'dryer_capacity':
                suggestions.extend(self._suggest_dryer_swap(
                    entry, marker_rule, same_day_entries
                ))
                suggestions.extend(self._suggest_day_shift(entry))

            elif ctype == 'operator_overlap':
                suggestions.extend(self._suggest_operator_change(
                    entry, marker_rule, operator_rules, same_day_entries
                ))
                suggestions.extend(self._suggest_time_shift_for_operator(
                    entry, same_day_entries
                ))

            elif ctype == 'production_flow':
                suggestions.extend(self._suggest_time_correction(entry))

            elif ctype == 'base_rule_violation':
                suggestions.extend(self._suggest_base_rule_fix(
                    entry, marker_rule
                ))

        # Deduplicate and limit to 3 suggestions
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            key = (s['type'], str(s.get('proposed_changes', {})))
            if key not in seen:
                seen.add(key)
                unique_suggestions.append(s)

        return unique_suggestions[:3]

    def _parse_conflict_types(self, conflict_reason: str) -> list[str]:
        """Extract conflict type keywords from the reason text."""
        types = []
        reason_lower = conflict_reason.lower()

        if 'machine' in reason_lower or '機台' in reason_lower or 'port' in reason_lower:
            types.append('machine_overlap')
        if 'dryer' in reason_lower or '凍乾' in reason_lower or '超容' in reason_lower:
            types.append('dryer_capacity')
        if 'operator' in reason_lower or '操作員' in reason_lower or '準備區間' in reason_lower:
            types.append('operator_overlap')
        if 'flow' in reason_lower or '流程' in reason_lower or '順序' in reason_lower:
            types.append('production_flow')
        if 'base_rule' in reason_lower or '基準規則' in reason_lower:
            types.append('base_rule_violation')

        # If no type detected, default to machine_overlap
        if not types:
            types.append('machine_overlap')

        return types

    def _suggest_machine_swap(
        self, entry: dict, marker_rule: Optional[dict],
        machine_rules: dict, same_day_entries: list[dict]
    ) -> list[dict]:
        """Suggest alternative machines from the marker's allowed set."""
        suggestions = []
        current_port = entry.get('machine_port')
        if not current_port:
            return suggestions

        # Get allowed machines for this marker
        allowed_machines = []
        if marker_rule:
            allowed_machines = marker_rule.get('common_machines', [])

        if not allowed_machines:
            # Fallback: try all known ports from machine_rules
            allowed_machines = [
                mid for mid, info in machine_rules.items()
                if info.get('machine_type') == 'port'
            ]

        # Filter out the current machine
        alternatives = [m for m in allowed_machines if m != current_port]

        # Check which alternatives are free at the entry's time
        entry_start = entry.get('start_time')
        entry_end = entry.get('end_time')
        occupied_ports = set()
        for other in same_day_entries:
            if self._times_overlap_simple(
                entry_start, entry_end,
                other.get('start_time'), other.get('end_time')
            ):
                if other.get('machine_port'):
                    occupied_ports.add(other['machine_port'])

        free_alternatives = [m for m in alternatives if m not in occupied_ports]

        for alt in free_alternatives[:2]:
            suggestions.append({
                'type': 'machine_swap',
                'description': f"改用 {alt} 機台（該時段空閒）",
                'confidence': 0.9,
                'proposed_changes': {'machine_port': alt},
            })

        # If no free alternatives, still suggest but with lower confidence
        if not free_alternatives and alternatives:
            alt = alternatives[0]
            suggestions.append({
                'type': 'machine_swap',
                'description': f"改用 {alt} 機台（需確認該時段可用性）",
                'confidence': 0.5,
                'proposed_changes': {'machine_port': alt},
            })

        return suggestions

    def _suggest_time_shift_for_machine(
        self, entry: dict, same_day_entries: list[dict]
    ) -> list[dict]:
        """Suggest shifting start time to avoid machine port overlap."""
        suggestions = []
        current_port = entry.get('machine_port')
        entry_start = entry.get('start_time')
        entry_end = entry.get('end_time')

        if not current_port or not entry_start or not entry_end:
            return suggestions

        # Find latest end_time on the same port that day
        latest_end = None
        for other in same_day_entries:
            if other.get('machine_port') == current_port:
                other_end = other.get('end_time')
                if other_end:
                    if latest_end is None or self._time_gt(other_end, latest_end):
                        latest_end = other_end

        if latest_end and self._time_gt(latest_end, entry_start):
            # Suggest starting after the latest end
            new_start = self._add_minutes_to_time(latest_end, 30)
            duration = self._time_diff_minutes(entry_start, entry_end)
            new_end = self._add_minutes_to_time(new_start, duration) if duration else None

            proposed = {'start_time': self._format_time(new_start)}
            if new_end:
                proposed['end_time'] = self._format_time(new_end)

            suggestions.append({
                'type': 'time_shift',
                'description': (
                    f"延後至 {self._format_time(new_start)} 開始"
                    f"（{current_port} 於 {self._format_time(latest_end)} 釋放）"
                ),
                'confidence': 0.7,
                'proposed_changes': proposed,
            })

        return suggestions

    def _suggest_dryer_swap(
        self, entry: dict, marker_rule: Optional[dict],
        same_day_entries: list[dict]
    ) -> list[dict]:
        """Suggest alternative dryers when capacity is exceeded."""
        suggestions = []
        current_dryer = entry.get('freeze_dryer')
        if not current_dryer:
            return suggestions

        # Get allowed dryers for this marker
        allowed_dryers = []
        if marker_rule:
            allowed_dryers = marker_rule.get('common_dryers', [])

        alternatives = [d for d in allowed_dryers if d != current_dryer]

        # Count usage of alternatives on the same day
        dryer_usage = {}
        for other in same_day_entries:
            d = other.get('freeze_dryer')
            if d:
                dryer_usage[d] = dryer_usage.get(d, 0) + 1

        for alt in alternatives[:2]:
            usage = dryer_usage.get(alt, 0)
            if usage < 2:  # Default max_concurrent for dryers
                suggestions.append({
                    'type': 'machine_swap',
                    'description': f"改用凍乾機 {alt}（當日使用量 {usage}，仍有容量）",
                    'confidence': 0.85,
                    'proposed_changes': {'freeze_dryer': alt},
                })

        return suggestions

    def _suggest_day_shift(self, entry: dict) -> list[dict]:
        """Suggest shifting to another day to reduce dryer load."""
        suggestions = []
        entry_date = entry.get('date')
        if not entry_date:
            return suggestions

        # Suggest the next weekday
        if hasattr(entry_date, 'weekday'):
            next_day = entry_date + timedelta(days=1)
            # Skip weekends
            while next_day.weekday() >= 5:  # Saturday=5, Sunday=6
                next_day += timedelta(days=1)

            suggestions.append({
                'type': 'time_shift',
                'description': f"延後至 {next_day.strftime('%Y-%m-%d')} 以減少當日凍乾機負載",
                'confidence': 0.6,
                'proposed_changes': {'date': next_day.strftime('%Y-%m-%d')},
            })

        return suggestions

    def _suggest_operator_change(
        self, entry: dict, marker_rule: Optional[dict],
        operator_rules: dict, same_day_entries: list[dict]
    ) -> list[dict]:
        """Suggest alternative operators."""
        suggestions = []
        current_operator = entry.get('operator')
        marker = entry.get('marker', '')

        if not current_operator:
            return suggestions

        # Get operators capable of this marker
        capable_operators = []
        if marker_rule:
            capable_operators = marker_rule.get('common_operators', [])

        if not capable_operators:
            # Fallback: check operator_rules for those who can handle this marker
            for op_name, op_info in operator_rules.items():
                if marker in op_info.get('capable_markers', []):
                    capable_operators.append(op_name)

        alternatives = [op for op in capable_operators if op != current_operator]

        # Check which operators are busy at the entry's prep time
        entry_rd = entry.get('rd_time') or entry.get('start_time')
        busy_operators = set()
        for other in same_day_entries:
            other_rd = other.get('rd_time') or other.get('start_time')
            if other_rd and entry_rd:
                # Simple overlap check on prep intervals (~30 min before rd_time)
                if abs(self._time_diff_minutes(entry_rd, other_rd) or 60) < 30:
                    if other.get('operator'):
                        busy_operators.add(other['operator'])

        free_operators = [op for op in alternatives if op not in busy_operators]

        for alt in free_operators[:2]:
            suggestions.append({
                'type': 'operator_change',
                'description': f"改由 {alt} 配藥（該時段無其他準備任務）",
                'confidence': 0.85,
                'proposed_changes': {'operator': alt},
            })

        if not free_operators and alternatives:
            alt = alternatives[0]
            suggestions.append({
                'type': 'operator_change',
                'description': f"改由 {alt} 配藥（需確認該時段可用性）",
                'confidence': 0.5,
                'proposed_changes': {'operator': alt},
            })

        return suggestions

    def _suggest_time_shift_for_operator(
        self, entry: dict, same_day_entries: list[dict]
    ) -> list[dict]:
        """Suggest shifting time to avoid operator overlap."""
        suggestions = []
        current_operator = entry.get('operator')
        entry_rd = entry.get('rd_time')

        if not current_operator or not entry_rd:
            return suggestions

        # Find the conflicting entry's rd_time for this operator
        conflicting_rd_times = []
        for other in same_day_entries:
            if other.get('operator') == current_operator:
                other_rd = other.get('rd_time')
                if other_rd:
                    conflicting_rd_times.append(other_rd)

        if conflicting_rd_times:
            # Suggest at least 30 min after the latest conflicting rd_time
            latest_rd = max(conflicting_rd_times, key=lambda t: (t.hour, t.minute) if t else (0, 0))
            new_rd = self._add_minutes_to_time(latest_rd, 45)

            suggestions.append({
                'type': 'time_shift',
                'description': (
                    f"將 RD 給藥時間延後至 {self._format_time(new_rd)}"
                    f"（{current_operator} 於 {self._format_time(latest_rd)} 完成前一批準備）"
                ),
                'confidence': 0.7,
                'proposed_changes': {'rd_time': self._format_time(new_rd)},
            })

        return suggestions

    def _suggest_time_correction(self, entry: dict) -> list[dict]:
        """Suggest fixing production flow ordering issues."""
        suggestions = []
        rd = entry.get('rd_time')
        start = entry.get('start_time')

        if rd and start and self._time_gt(rd, start):
            # rd_time > start_time violates flow
            new_start = self._add_minutes_to_time(rd, 30)
            suggestions.append({
                'type': 'time_shift',
                'description': (
                    f"將滴定開始時間調整為 {self._format_time(new_start)}"
                    f"（配藥需在滴定前完成）"
                ),
                'confidence': 0.95,
                'proposed_changes': {'start_time': self._format_time(new_start)},
            })

        return suggestions

    def _suggest_base_rule_fix(
        self, entry: dict, marker_rule: Optional[dict]
    ) -> list[dict]:
        """Suggest corrections for base rule violations."""
        suggestions = []

        if not marker_rule:
            return suggestions

        # Suggest first allowed machine if machine is invalid
        allowed_machines = marker_rule.get('common_machines', [])
        if allowed_machines and entry.get('machine_port') not in allowed_machines:
            suggestions.append({
                'type': 'machine_swap',
                'description': f"改用基準規則允許的機台 {allowed_machines[0]}",
                'confidence': 0.95,
                'proposed_changes': {'machine_port': allowed_machines[0]},
            })

        # Suggest first allowed dryer if dryer is invalid
        allowed_dryers = marker_rule.get('common_dryers', [])
        if allowed_dryers and entry.get('freeze_dryer') not in allowed_dryers:
            suggestions.append({
                'type': 'machine_swap',
                'description': f"改用基準規則允許的凍乾機 {allowed_dryers[0]}",
                'confidence': 0.95,
                'proposed_changes': {'freeze_dryer': allowed_dryers[0]},
            })

        # Suggest first allowed operator if operator is invalid
        allowed_operators = marker_rule.get('common_operators', [])
        if allowed_operators and entry.get('operator') not in allowed_operators:
            suggestions.append({
                'type': 'operator_change',
                'description': f"改由基準規則允許的操作員 {allowed_operators[0]} 配藥",
                'confidence': 0.95,
                'proposed_changes': {'operator': allowed_operators[0]},
            })

        return suggestions

    # ------------------------------------------------------------------
    # Rule-Based Conflict Explanation
    # ------------------------------------------------------------------

    def _explain_conflict_rules(self, conflict_type: str, description: str) -> str:
        """Generate a natural language explanation using rule-based logic."""
        explanations = {
            'machine_overlap': (
                "衝突原因：同一台滴定機台在同一時段被分配給多個批次使用。"
                "每台機台在任何時間點只能處理一個批次的滴定作業。\n\n"
                "建議解決方式：\n"
                "1. 將其中一個批次改分配至其他可用機台\n"
                "2. 將其中一個批次的開始時間延後，錯開使用時段\n"
                "3. 若同日所有機台皆滿載，考慮將批次移至其他工作日"
            ),
            'dryer_capacity': (
                "衝突原因：同一台凍乾機在同一天被分配了超過其容量上限的批次數量。"
                "凍乾機有固定的同時處理容量限制。\n\n"
                "建議解決方式：\n"
                "1. 將超出容量的批次改分配至其他凍乾機\n"
                "2. 將超出容量的批次移至凍乾機負載較低的日期\n"
                "3. 確認凍乾機的實際容量設定是否需要更新"
            ),
            'operator_overlap': (
                "衝突原因：同一位配藥操作員在同一時段被分配準備多個批次的藥品。"
                "在 DrugGivenAt（RD 給藥時間）之前的準備區間內，"
                "操作員僅能專注準備一種 Marker 的配藥。\n\n"
                "建議解決方式：\n"
                "1. 將其中一個批次改由其他具備該 Marker 配藥資格的操作員負責\n"
                "2. 錯開 RD 給藥時間，使同一操作員的準備區間不重疊\n"
                "3. 確認是否有其他操作員可分擔工作量"
            ),
            'production_flow': (
                "衝突原因：批次的排程時間違反了生產流程順序。"
                "正確順序為：配藥（Dispensing）→ 滴定（Titration）→ 凍乾（Freeze-drying），"
                "每個階段必須在前一階段完成後才能開始。\n\n"
                "建議解決方式：\n"
                "1. 調整時間使 RD 給藥時間早於滴定開始時間\n"
                "2. 確認配藥完成時間與滴定開始時間之間有足夠的銜接時間"
            ),
            'base_rule_violation': (
                "衝突原因：批次被分配了基準規則表中未允許的資源。"
                "系統中存在基準規則表（freezer_rules、pump No.、配藥限制）"
                "明確規定每個 Marker 可使用的機台、凍乾機與操作員。\n\n"
                "建議解決方式：\n"
                "1. 將分配資源改為基準規則表中允許的選項\n"
                "2. 若確需使用該資源，請先更新基準規則表"
            ),
        }

        base_explanation = explanations.get(conflict_type, '')

        if not base_explanation:
            # Generic fallback
            base_explanation = (
                f"排程衝突偵測到問題。衝突類型：{conflict_type}。\n"
                f"詳細描述：{description}\n\n"
                "建議檢查相關資源分配與時間安排是否有衝突。"
            )

        # Append the specific conflict description for context
        if description:
            full_explanation = f"{base_explanation}\n\n具體情況：{description}"
        else:
            full_explanation = base_explanation

        return full_explanation

    # ------------------------------------------------------------------
    # Rule-Based Strategy Recommendations
    # ------------------------------------------------------------------

    def _generate_strategy_rules(self, patterns: dict) -> list[dict]:
        """Generate strategy recommendations using rule-based logic."""
        recommendations: list[dict] = []

        # Analyze frequent conflicts
        frequent_conflicts = patterns.get('frequent_conflicts', [])
        for conflict in frequent_conflicts:
            ctype = conflict.get('type', '')
            markers = conflict.get('markers', [])
            freq = conflict.get('frequency', 0)

            if ctype == 'machine_overlap' and len(markers) >= 2 and freq >= 3:
                recommendations.append({
                    'strategy': f"錯開 {' 與 '.join(markers[:2])} 的排程時間",
                    'rationale': (
                        f"歷史資料顯示 {' 與 '.join(markers[:2])} "
                        f"經常在同一機台產生衝突（發生 {freq} 次）。"
                        "建議將兩者的滴定時間錯開至少 2 小時。"
                    ),
                    'estimated_impact': f"預估可減少約 {min(freq * 15, 80)}% 的機台衝突",
                })

            elif ctype == 'operator_overlap' and len(markers) >= 2:
                recommendations.append({
                    'strategy': f"為 {' 與 '.join(markers[:2])} 分配不同操作員",
                    'rationale': (
                        f"這兩個 Marker 的配藥準備時間經常重疊，"
                        f"導致操作員資源衝突。建議固定分配給不同操作員。"
                    ),
                    'estimated_impact': "預估可消除操作員準備區間衝突",
                })

        # Analyze peak hours
        peak_hours = patterns.get('peak_hours', {})
        if peak_hours:
            peak_hour = max(peak_hours, key=peak_hours.get)
            peak_count = peak_hours[peak_hour]
            if peak_count > 3:
                recommendations.append({
                    'strategy': "分散尖峰時段的排程密度",
                    'rationale': (
                        f"時段 {peak_hour}:00 的機台使用率最高（{peak_count} 批次），"
                        "容易導致資源爭奪。建議將部分批次移至離峰時段。"
                    ),
                    'estimated_impact': "預估可減少 30-50% 的時段衝突",
                })

        # Analyze machine utilization
        machine_util = patterns.get('machine_utilization', {})
        if machine_util:
            overloaded = [
                m for m, u in machine_util.items()
                if isinstance(u, (int, float)) and u > 80
            ]
            underloaded = [
                m for m, u in machine_util.items()
                if isinstance(u, (int, float)) and u < 30
            ]
            if overloaded and underloaded:
                recommendations.append({
                    'strategy': "平衡機台負載分配",
                    'rationale': (
                        f"機台 {', '.join(overloaded[:2])} 使用率偏高（>80%），"
                        f"而 {', '.join(underloaded[:2])} 使用率偏低（<30%）。"
                        "建議將部分排程從高負載機台移至低負載機台。"
                    ),
                    'estimated_impact': "預估可提升整體機台利用效率 20-30%",
                })

        # Analyze operator load
        operator_load = patterns.get('operator_load', {})
        if operator_load:
            overloaded_ops = [
                op for op, load in operator_load.items()
                if isinstance(load, (int, float)) and load > 3
            ]
            if overloaded_ops:
                recommendations.append({
                    'strategy': "重新平衡操作員工作負載",
                    'rationale': (
                        f"操作員 {', '.join(overloaded_ops[:2])} 每日平均任務數偏高，"
                        "容易產生準備區間衝突。建議將部分任務分配給其他操作員。"
                    ),
                    'estimated_impact': "預估可減少操作員排程衝突並降低工作負荷",
                })

        # Analyze marker co-occurrence patterns
        marker_pairs = patterns.get('marker_pairs', [])
        for pair in marker_pairs[:2]:
            markers = pair.get('markers', [])
            rate = pair.get('co_occurrence_rate', 0)
            if len(markers) >= 2 and rate > 0.7:
                recommendations.append({
                    'strategy': f"建立 {' + '.join(markers[:2])} 的固定排程組合",
                    'rationale': (
                        f"這兩個 Marker 有 {rate*100:.0f}% 的共同排程率，"
                        "建議建立固定的時間組合配置以減少每次排程的衝突風險。"
                    ),
                    'estimated_impact': "預估可加速排程產生時間並減少衝突",
                })

        # If no patterns yielded recommendations, provide general advice
        if not recommendations:
            recommendations.append({
                'strategy': "持續累積歷史資料以改進排程策略",
                'rationale': "目前歷史模式資料尚不足以產生具體策略建議。",
                'estimated_impact': "建議累積至少 4 週資料後重新分析",
            })

        return recommendations

    # ------------------------------------------------------------------
    # LLM-Based Methods (Placeholders for future integration)
    # ------------------------------------------------------------------

    def _generate_suggestions_llm(
        self, entry: dict, conflict_reason: str,
        marker_rule: Optional[dict], machine_rules: dict,
        operator_rules: dict, same_day_entries: list[dict]
    ) -> list[dict]:
        """Generate suggestions using LLM. Placeholder for future integration."""
        # When LLM is configured, build a prompt with context and call LLM:
        # prompt = f"Given schedule entry {entry} with conflict: {conflict_reason}..."
        # response = self.llm_client.generate(prompt)
        # return self._parse_llm_suggestions(response)
        return self._generate_suggestions_rules(
            entry, conflict_reason, marker_rule,
            machine_rules, operator_rules, same_day_entries
        )

    def _explain_conflict_llm(self, conflict_type: str, description: str) -> str:
        """Explain conflict using LLM. Placeholder for future integration."""
        # When LLM is configured:
        # prompt = f"Explain this scheduling conflict: type={conflict_type}, desc={description}"
        # return self.llm_client.generate(prompt)
        return self._explain_conflict_rules(conflict_type, description)

    def _generate_strategy_llm(self, patterns: dict) -> list[dict]:
        """Generate strategies using LLM. Placeholder for future integration."""
        # When LLM is configured:
        # prompt = f"Based on these patterns {patterns}, suggest scheduling strategies."
        # return self._parse_llm_strategies(self.llm_client.generate(prompt))
        return self._generate_strategy_rules(patterns)

    # ------------------------------------------------------------------
    # Time Utility Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _time_gt(t1, t2) -> bool:
        """Check if time t1 > t2."""
        if t1 is None or t2 is None:
            return False
        if isinstance(t1, time) and isinstance(t2, time):
            return (t1.hour * 60 + t1.minute) > (t2.hour * 60 + t2.minute)
        return False

    @staticmethod
    def _time_diff_minutes(t1, t2) -> Optional[int]:
        """Return difference in minutes: t2 - t1. Returns None if either is None."""
        if t1 is None or t2 is None:
            return None
        if isinstance(t1, time) and isinstance(t2, time):
            m1 = t1.hour * 60 + t1.minute
            m2 = t2.hour * 60 + t2.minute
            return m2 - m1
        return None

    @staticmethod
    def _add_minutes_to_time(t, minutes: int) -> Optional[time]:
        """Add minutes to a time object. Returns None if t is None."""
        if t is None:
            return None
        if isinstance(t, time):
            total = t.hour * 60 + t.minute + minutes
            # Clamp to valid time range (0-1439)
            total = max(0, min(total, 23 * 60 + 59))
            return time(total // 60, total % 60)
        return None

    @staticmethod
    def _format_time(t) -> str:
        """Format a time object as HH:MM string."""
        if t is None:
            return ''
        if isinstance(t, time):
            return t.strftime('%H:%M')
        return str(t)

    @staticmethod
    def _times_overlap_simple(start1, end1, start2, end2) -> bool:
        """Simple time overlap check."""
        def to_min(t):
            if t is None:
                return None
            if isinstance(t, time):
                return t.hour * 60 + t.minute
            return None

        s1, e1, s2, e2 = to_min(start1), to_min(end1), to_min(start2), to_min(end2)
        if any(v is None for v in [s1, e1, s2, e2]):
            return False
        return s1 < e2 and s2 < e1
