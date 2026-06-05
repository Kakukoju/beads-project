"""
Scheduling Engine — 使用 OR-Tools CP-SAT 求解器產生排程

Responsibilities:
- Load scheduling rules (derived tables preferred, Base_Rule_Tables fallback)
- Build CP-SAT constraint model with per-batch variables
- Add production flow, resource exclusivity, and capacity constraints
- Solve and extract schedule results
- Integrate with ConflictDetector for post-solve validation
- Orchestrate full generate pipeline (load rules → split → solve → detect → write)

Uses 30-min grids matching existing scheduler_api.py:
  START_HOUR = 10, MINS_PER_GRID = 30, GRIDS_PER_DAY = 31
  Grid 0 = 10:00, Grid 30 = 25:30 (01:30 next day)
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from ortools.sat.python import cp_model
from sqlalchemy import text
from sqlalchemy.orm import Session

from ai_schedule.batch_splitter import Batch, BatchSplitter, MarkerDemand
from ai_schedule.conflict_detector import ConflictDetector


# ---------------------------------------------------------------------------
# Constants — matching scheduler_api.py
# ---------------------------------------------------------------------------

START_HOUR = 10          # 10:00 = grid 0
MINS_PER_GRID = 30       # each grid = 30 minutes
GRIDS_PER_DAY = 31       # 31 grids: 10:00 ~ 25:30

# Solver defaults
SOLVER_MAX_TIME_SECONDS = 30
SOLVER_NUM_WORKERS = 4


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MarkerRuleInfo:
    """Rule information for a single Marker (from derived or base tables)."""
    marker_name: str
    pn: Optional[str] = None
    allowed_machines: list[str] = field(default_factory=list)
    allowed_dryers: list[str] = field(default_factory=list)
    allowed_operators: list[str] = field(default_factory=list)
    avg_duration_minutes: Optional[int] = None
    avg_start_time: Optional[str] = None
    avg_end_time: Optional[str] = None
    common_quantities: list[int] = field(default_factory=list)
    special_notes: list[str] = field(default_factory=list)
    port_count: int = 1          # number of TECAN ports used per batch
    batch_qty: int = 0           # quantity produced per batch


@dataclass
class MachineCapacityInfo:
    """Capacity rule for a single machine (port or dryer)."""
    machine_id: str
    machine_type: str  # 'port' or 'dryer'
    max_concurrent: int = 1
    available_hours_start: Optional[str] = None
    available_hours_end: Optional[str] = None


@dataclass
class OperatorInfo:
    """Rule information for a single operator."""
    operator_name: str
    capable_markers: list[str] = field(default_factory=list)
    max_concurrent_tasks: int = 1
    available_days: list[int] = field(default_factory=list)
    shift_start: Optional[str] = None
    shift_end: Optional[str] = None


@dataclass
class ScheduleRules:
    """Aggregated scheduling rules loaded from database."""
    marker_rules: dict[str, MarkerRuleInfo] = field(default_factory=dict)
    machine_capacities: dict[str, MachineCapacityInfo] = field(default_factory=dict)
    operator_rules: dict[str, OperatorInfo] = field(default_factory=dict)
    all_machines: list[str] = field(default_factory=list)
    all_dryers: list[str] = field(default_factory=list)
    all_operators: list[str] = field(default_factory=list)
    source: str = 'derived'  # 'derived' or 'base'


@dataclass
class BatchVars:
    """CP-SAT variables for a single batch."""
    batch: Batch
    day: cp_model.IntVar
    start_grid: cp_model.IntVar
    machine_idx: cp_model.IntVar
    dryer_idx: cp_model.IntVar
    operator_idx: cp_model.IntVar
    # Allowed resource lists (indices into all_* lists)
    allowed_machine_indices: list[int] = field(default_factory=list)
    allowed_dryer_indices: list[int] = field(default_factory=list)
    allowed_operator_indices: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SchedulingEngine
# ---------------------------------------------------------------------------

class SchedulingEngine:
    """使用 OR-Tools CP-SAT 求解器產生排程。"""

    def __init__(self, db_session: Session):
        """
        Initialize SchedulingEngine with a database session.

        Sets up the solver configuration and prepares for model construction.

        Args:
            db_session: SQLAlchemy session for querying rules and writing results.
        """
        self.db = db_session
        self.model: Optional[cp_model.CpModel] = None
        self.solver: Optional[cp_model.CpSolver] = None
        self._rules: Optional[ScheduleRules] = None

        logging.info("[SchedulingEngine] Initialized with CP-SAT solver.")

    # ------------------------------------------------------------------
    # Rule Loading
    # ------------------------------------------------------------------

    def _load_rules(self) -> ScheduleRules:
        """
        載入規則（衍生規則優先，fallback 至基準規則）。

        Priority:
        1. Load from derived rule tables (marker_rule, machine_capacity_rule,
           operator_rule) where base_rule_validated = true
        2. If derived tables are empty or all records have
           base_rule_validated = false, fallback to Base_Rule_Tables
           (freezer_rules, "pump No.", 配藥限制)

        Returns:
            ScheduleRules with all loaded rules aggregated.
        """
        rules = ScheduleRules()

        # Attempt to load derived rules
        derived_loaded = self._load_derived_rules(rules)

        if not derived_loaded:
            logging.info("[SchedulingEngine] Derived rules empty/invalid, "
                         "falling back to Base_Rule_Tables.")
            self._load_base_rules(rules)
            rules.source = 'base'
        else:
            rules.source = 'derived'

        # Build global resource lists from loaded rules
        self._build_global_resource_lists(rules)

        logging.info(
            f"[SchedulingEngine] Rules loaded (source={rules.source}): "
            f"{len(rules.marker_rules)} markers, "
            f"{len(rules.all_machines)} machines, "
            f"{len(rules.all_dryers)} dryers, "
            f"{len(rules.all_operators)} operators."
        )

        self._rules = rules
        return rules

    def _load_derived_rules(self, rules: ScheduleRules) -> bool:
        """
        Load rules from derived rule tables (marker_rule, machine_capacity_rule,
        operator_rule) where base_rule_validated = true.

        Args:
            rules: ScheduleRules object to populate.

        Returns:
            True if at least one valid marker rule was loaded, False otherwise.
        """
        # Load marker_rule where base_rule_validated = true
        try:
            result = self.db.execute(text("""
                SELECT marker_name, pn, common_machines, common_dryers,
                       common_operators, avg_start_time, avg_end_time,
                       avg_duration_minutes, common_quantities, special_notes
                FROM "P01_formualte_schedule".marker_rule
                WHERE base_rule_validated = true
            """))
            for row in result:
                mr = MarkerRuleInfo(
                    marker_name=row[0],
                    pn=row[1],
                    allowed_machines=row[2] if row[2] else [],
                    allowed_dryers=row[3] if row[3] else [],
                    allowed_operators=row[4] if row[4] else [],
                    avg_start_time=str(row[5]) if row[5] else None,
                    avg_end_time=str(row[6]) if row[6] else None,
                    avg_duration_minutes=row[7],
                    common_quantities=row[8] if row[8] else [],
                    special_notes=row[9] if row[9] else [],
                )
                rules.marker_rules[mr.marker_name] = mr
        except Exception as e:
            logging.warning(f"[SchedulingEngine] Failed to load marker_rule: {e}")
            self.db.rollback()

        if not rules.marker_rules:
            return False

        # Load machine_capacity_rule where base_rule_validated = true
        try:
            result = self.db.execute(text("""
                SELECT machine_id, machine_type, max_concurrent,
                       available_hours_start, available_hours_end
                FROM "P01_formualte_schedule".machine_capacity_rule
                WHERE base_rule_validated = true
            """))
            for row in result:
                mc = MachineCapacityInfo(
                    machine_id=row[0],
                    machine_type=row[1] or 'port',
                    max_concurrent=row[2] or 1,
                    available_hours_start=str(row[3]) if row[3] else None,
                    available_hours_end=str(row[4]) if row[4] else None,
                )
                rules.machine_capacities[mc.machine_id] = mc
        except Exception as e:
            logging.warning(
                f"[SchedulingEngine] Failed to load machine_capacity_rule: {e}"
            )
            self.db.rollback()

        # Load operator_rule where base_rule_validated = true
        try:
            result = self.db.execute(text("""
                SELECT operator_name, capable_markers, max_concurrent_tasks,
                       available_days, shift_start, shift_end
                FROM "P01_formualte_schedule".operator_rule
                WHERE base_rule_validated = true
            """))
            for row in result:
                op = OperatorInfo(
                    operator_name=row[0],
                    capable_markers=row[1] if row[1] else [],
                    max_concurrent_tasks=row[2] or 1,
                    available_days=row[3] if row[3] else [],
                    shift_start=str(row[4]) if row[4] else None,
                    shift_end=str(row[5]) if row[5] else None,
                )
                rules.operator_rules[op.operator_name] = op
        except Exception as e:
            logging.warning(
                f"[SchedulingEngine] Failed to load operator_rule: {e}"
            )
            self.db.rollback()

        return True

    def _load_base_rules(self, rules: ScheduleRules) -> None:
        """
        Fallback: load rules from Base_Rule_Tables.

        Data sources:
        - "P01_formualte_schedule".freezer_rules → Marker → allowed dryers (cols with 'v')
        - "P01_formualte_schedule"."pump No." → port→markers, reversed to marker→ports
        - schedule."配藥限制" → Name, Port數, 數量, 配藥人-1/-2/-3, 凍乾時間

        Args:
            rules: ScheduleRules object to populate.
        """
        # ────────────────────────────────────────────────────────────────
        # 1. Load freezer_rules → marker → allowed dryers
        # Columns: Marker, No. 3 ~ No. 12, 小台 (indices 1..11)
        # Value 'v' means the dryer is allowed for this marker
        # ────────────────────────────────────────────────────────────────
        marker_dryers: dict[str, list[str]] = {}
        dryer_cols = ['No. 3', 'No. 4', 'No. 5', 'No. 6', 'No. 7',
                      'No. 8', 'No. 9', 'No. 10', 'No. 11', 'No. 12', '小台']
        try:
            result = self.db.execute(text("""
                SELECT "Marker", "No. 3", "No. 4", "No. 5", "No. 6", "No. 7",
                       "No. 8", "No. 9", "No. 10", "No. 11", "No. 12", "小台"
                FROM "P01_formualte_schedule".freezer_rules
                WHERE "Marker" IS NOT NULL
            """))
            for row in result:
                marker = str(row[0]).strip()
                if not marker:
                    continue
                allowed = []
                for i, col_name in enumerate(dryer_cols):
                    val = row[i + 1]
                    if val and str(val).strip().lower() == 'v':
                        allowed.append(col_name)
                if allowed:
                    # Merge if marker appears multiple times (different qty rows)
                    if marker in marker_dryers:
                        for d in allowed:
                            if d not in marker_dryers[marker]:
                                marker_dryers[marker].append(d)
                    else:
                        marker_dryers[marker] = allowed
        except Exception as e:
            logging.warning(f"[SchedulingEngine] Failed to load freezer_rules: {e}")
            self.db.rollback()

        # ────────────────────────────────────────────────────────────────
        # 2. Skip pump No. table — all markers use Port 1~12 (Na* uses IVEK)
        # ────────────────────────────────────────────────────────────────

        # Physical TECAN ports (odd first for scheduling preference)
        TECAN_PORTS = ['1', '3', '5', '7', '9', '11', '2', '4', '6', '8', '10', '12']
        IVEK_PORTS  = ['IVEK-1', 'IVEK-2']

        # ────────────────────────────────────────────────────────────────
        # 3. Load 配藥限制 → marker info (operators, port count, qty)
        # Columns: Name, Port數, 數量, 配藥人-1, 配藥人-2, 配藥人-3
        # ────────────────────────────────────────────────────────────────
        marker_operators: dict[str, list[str]] = {}
        marker_port_count: dict[str, int] = {}
        marker_batch_qty: dict[str, int] = {}
        operator_markers: dict[str, list[str]] = {}
        try:
            result = self.db.execute(text("""
                SELECT "Name", "Port數", "數量", "配藥人-1", "配藥人-2", "配藥人-3"
                FROM "schedule"."配藥限制"
                WHERE "Name" IS NOT NULL
            """))
            for row in result:
                marker = str(row[0]).strip()
                if not marker:
                    continue
                # Port數
                try:
                    port_count = int(row[1]) if row[1] else 1
                except (ValueError, TypeError):
                    port_count = 1
                marker_port_count[marker] = port_count

                # 數量 (batch size)
                try:
                    qty_raw = row[2]
                    if isinstance(qty_raw, str):
                        qty_raw = qty_raw.split(' ')[0].replace(',', '')
                    batch_qty = int(float(qty_raw)) if qty_raw else 0
                except (ValueError, TypeError):
                    batch_qty = 0
                if batch_qty > 0:
                    marker_batch_qty[marker] = batch_qty

                # Operators (配藥人-1/-2/-3)
                ops = []
                for i in range(3, 6):
                    op = row[i]
                    if op and str(op).strip():
                        ops.append(str(op).strip())
                if ops:
                    marker_operators[marker] = ops
                    # Also build reverse map
                    for op in ops:
                        operator_markers.setdefault(op, [])
                        if marker not in operator_markers[op]:
                            operator_markers[op].append(marker)
        except Exception as e:
            logging.warning(f"[SchedulingEngine] Failed to load 配藥限制: {e}")
            self.db.rollback()

        # ────────────────────────────────────────────────────────────────
        # 4. Build MarkerRuleInfo — all markers use Port 1~12
        #    Na* markers use IVEK-1/IVEK-2 instead
        # ────────────────────────────────────────────────────────────────
        all_markers_set = set(marker_dryers.keys()) | set(marker_operators.keys())

        for marker in all_markers_set:
            port_count = marker_port_count.get(marker, 1)

            # Na* → IVEK, everything else → TECAN Port 1~12
            if 'Na' in marker or 'QNA' in marker.upper():
                allowed_ports = IVEK_PORTS
            else:
                allowed_ports = TECAN_PORTS

            mr = MarkerRuleInfo(
                marker_name=marker,
                allowed_machines=allowed_ports,
                allowed_dryers=marker_dryers.get(marker, []),
                allowed_operators=marker_operators.get(marker, []),
                port_count=port_count,
                batch_qty=marker_batch_qty.get(marker, 0),
            )
            batch_qty = marker_batch_qty.get(marker, 0)
            if port_count > 0 and batch_qty > 0:
                titration_hrs = batch_qty / port_count / 1700
                mr.avg_duration_minutes = max(30, int(titration_hrs * 60))
            rules.marker_rules[marker] = mr

        # Build OperatorInfo from base tables
        for operator, capable in operator_markers.items():
            rules.operator_rules[operator] = OperatorInfo(
                operator_name=operator,
                capable_markers=capable,
            )

    def _build_global_resource_lists(self, rules: ScheduleRules) -> None:
        """
        Build global resource lists for CP-SAT index-based variable domains.

        Machines: fixed 14 physical ports — P1~P12 (odd first) + IVEK-1/IVEK-2
        Dryers/Operators: union across all marker rules.
        """
        # Fixed physical ports — indices 0~13
        # Odd first (scheduler preference), then even, then IVEK
        rules.all_machines = [
            '1', '3', '5', '7', '9', '11',   # idx 0-5
            '2', '4', '6', '8', '10', '12',   # idx 6-11
            'IVEK-1', 'IVEK-2',               # idx 12-13
        ]

        dryers_set: set[str] = set()
        operators_set: set[str] = set()
        for mr in rules.marker_rules.values():
            dryers_set.update(mr.allowed_dryers)
            operators_set.update(mr.allowed_operators)

        rules.all_dryers = sorted(dryers_set)
        rules.all_operators = sorted(operators_set)

    # ------------------------------------------------------------------
    # CP-SAT Model Construction
    # ------------------------------------------------------------------

    def _build_cp_model(
        self,
        batches: list[Batch],
        rules: ScheduleRules,
        horizon_days: int,
    ) -> tuple[cp_model.CpModel, list[BatchVars]]:
        """
        建構 CP-SAT 約束模型。

        Creates a CpModel with variables per batch:
          - day: IntVar [0, horizon_days-1]
          - start_grid: IntVar [0, GRIDS_PER_DAY-1] (30-min grids, 10:00~25:30)
          - machine_idx: IntVar within allowed machines for this Marker
          - dryer_idx: IntVar within allowed dryers for this Marker
          - operator_idx: IntVar within allowed operators for this Marker

        The grid system matches existing scheduler_api.py:
          Grid 0 = 10:00, Grid 1 = 10:30, ..., Grid 30 = 25:30
          grids_per_day = 31

        Args:
            batches: List of Batch objects to schedule.
            rules: Loaded ScheduleRules with resource information.
            horizon_days: Number of days in the scheduling horizon.

        Returns:
            Tuple of (CpModel, list of BatchVars for each batch).
        """
        model = cp_model.CpModel()
        grids_per_day = GRIDS_PER_DAY
        batch_vars_list: list[BatchVars] = []

        for i, batch in enumerate(batches):
            prefix = f"b{i}_{batch.marker[:8]}"

            # Get marker-specific rule (or default allowing all resources)
            marker_rule = rules.marker_rules.get(batch.marker)

            # --- Day variable ---
            day_var = model.new_int_var(0, horizon_days - 1, f"{prefix}_day")

            # --- Start grid variable ---
            # Work window 09:00~01:00 = 32 grids of 30min from START_HOUR=9
            # Max start = grid 28 (22:00) to allow ~4 grids titration before 01:00
            WORK_GRIDS = 32  # 09:00 ~ 01:00 next day
            start_grid_var = model.new_int_var(
                0, WORK_GRIDS - 1, f"{prefix}_start_grid"
            )

            # --- Machine index variable ---
            # Determine allowed machine indices for this batch
            if marker_rule and marker_rule.allowed_machines:
                allowed_machine_indices = [
                    idx for idx, m in enumerate(rules.all_machines)
                    if m in marker_rule.allowed_machines
                ]
            else:
                # No specific rule — allow all machines
                allowed_machine_indices = list(range(len(rules.all_machines)))

            if allowed_machine_indices:
                machine_idx_var = model.new_int_var(
                    0, len(rules.all_machines) - 1, f"{prefix}_machine_idx"
                )
                # Constrain to allowed machines only
                model.add_allowed_assignments(
                    [machine_idx_var],
                    [[idx] for idx in allowed_machine_indices]
                )
            else:
                # Fallback: single dummy index if no machines defined
                machine_idx_var = model.new_int_var(0, 0, f"{prefix}_machine_idx")
                allowed_machine_indices = [0]

            # --- Dryer index variable ---
            if marker_rule and marker_rule.allowed_dryers:
                allowed_dryer_indices = [
                    idx for idx, d in enumerate(rules.all_dryers)
                    if d in marker_rule.allowed_dryers
                ]
            else:
                allowed_dryer_indices = list(range(len(rules.all_dryers)))

            if allowed_dryer_indices:
                dryer_idx_var = model.new_int_var(
                    0, len(rules.all_dryers) - 1, f"{prefix}_dryer_idx"
                )
                model.add_allowed_assignments(
                    [dryer_idx_var],
                    [[idx] for idx in allowed_dryer_indices]
                )
            else:
                dryer_idx_var = model.new_int_var(0, 0, f"{prefix}_dryer_idx")
                allowed_dryer_indices = [0]

            # --- Operator index variable ---
            if marker_rule and marker_rule.allowed_operators:
                allowed_operator_indices = [
                    idx for idx, o in enumerate(rules.all_operators)
                    if o in marker_rule.allowed_operators
                ]
            else:
                allowed_operator_indices = list(range(len(rules.all_operators)))

            if allowed_operator_indices:
                operator_idx_var = model.new_int_var(
                    0, len(rules.all_operators) - 1, f"{prefix}_operator_idx"
                )
                model.add_allowed_assignments(
                    [operator_idx_var],
                    [[idx] for idx in allowed_operator_indices]
                )
            else:
                operator_idx_var = model.new_int_var(0, 0, f"{prefix}_operator_idx")
                allowed_operator_indices = [0]

            # Store variables for this batch
            bv = BatchVars(
                batch=batch,
                day=day_var,
                start_grid=start_grid_var,
                machine_idx=machine_idx_var,
                dryer_idx=dryer_idx_var,
                operator_idx=operator_idx_var,
                allowed_machine_indices=allowed_machine_indices,
                allowed_dryer_indices=allowed_dryer_indices,
                allowed_operator_indices=allowed_operator_indices,
            )
            batch_vars_list.append(bv)

        self.model = model
        logging.info(
            f"[SchedulingEngine] CP-SAT model built: "
            f"{len(batches)} batches, horizon={horizon_days} days, "
            f"grids_per_day={grids_per_day}."
        )

        return model, batch_vars_list

    # ------------------------------------------------------------------
    # Constraint Functions
    # ------------------------------------------------------------------

    def _add_production_flow_constraints(
        self,
        model: cp_model.CpModel,
        batch_vars_list: list[BatchVars],
        rules: ScheduleRules,
    ) -> None:
        """
        配藥→滴定→凍乾順序約束。

        For each batch, enforces:
          dispensing_end_grid <= titration_start_grid (= start_grid)
          titration_end_grid <= freeze_start_grid

        Phase durations (in grids, 30-min each):
          - Dispensing: derived from avg_duration_minutes in marker_rule,
            or default 2 grids (60 min)
          - Titration: derived similarly, default 4 grids (120 min)
          - Freeze-drying: downstream; constraint only requires titration
            ends before freeze starts

        The batch's start_grid represents the titration phase start.
        Dispensing happens before start_grid; freeze-drying happens after
        titration ends.

        Args:
            model: The CpModel to add constraints to.
            batch_vars_list: List of BatchVars for all batches.
            rules: Loaded ScheduleRules with marker duration info.
        """
        # Default durations in grids (each grid = 30 min)
        DEFAULT_DISPENSING_GRIDS = 2   # 60 min default dispensing
        DEFAULT_TITRATION_GRIDS = 4    # 120 min default titration

        for i, bv in enumerate(batch_vars_list):
            prefix = f"flow_b{i}"
            marker_rule = rules.marker_rules.get(bv.batch.marker)

            # Determine dispensing duration in grids
            if marker_rule and marker_rule.avg_duration_minutes:
                # Use avg_duration as total production time; dispensing ~ 1/3
                total_grids = max(1, marker_rule.avg_duration_minutes // MINS_PER_GRID)
                dispensing_grids = max(1, total_grids // 3)
                titration_grids = max(1, total_grids // 3)
            else:
                dispensing_grids = DEFAULT_DISPENSING_GRIDS
                titration_grids = DEFAULT_TITRATION_GRIDS

            # start_grid represents titration start
            # dispensing_start = start_grid - dispensing_grids (must be >= 0)
            # Constraint 1: dispensing ends before titration starts
            # dispensing_end = dispensing_start + dispensing_grids = start_grid
            # This is implicit since start_grid IS the titration start.
            # But we must ensure dispensing fits within the day:
            # start_grid >= dispensing_grids (dispensing happens before titration)
            model.add(bv.start_grid >= dispensing_grids).with_name(
                f"{prefix}_dispensing_before_titration"
            )

            # Constraint 2: titration ends before freeze-drying starts
            # titration_end_grid = start_grid + titration_grids
            # freeze_start_grid >= titration_end_grid
            # Since freeze_start must fit within the day:
            # start_grid + titration_grids <= GRIDS_PER_DAY - 1
            # (This ensures freeze-drying can start on the same day)
            titration_end = model.new_int_var(
                0, GRIDS_PER_DAY - 1, f"{prefix}_titration_end"
            )
            model.add(titration_end == bv.start_grid + titration_grids)

            # Freeze-drying start must be >= titration end
            # (implicitly satisfied since freeze starts at titration_end)
            # Ensure titration_end doesn't exceed day boundary
            model.add(
                bv.start_grid + titration_grids <= GRIDS_PER_DAY - 1
            ).with_name(f"{prefix}_titration_fits_in_day")

        logging.info(
            f"[SchedulingEngine] Added production flow constraints for "
            f"{len(batch_vars_list)} batches."
        )

    def _add_machine_port_constraints(
        self,
        model: cp_model.CpModel,
        batch_vars_list: list[BatchVars],
        rules: ScheduleRules,
    ) -> None:
        """
        Machine_Port 時間互斥約束：NoOverlap2D for IntervalVars.

        Two batches cannot use the same machine port at overlapping times.
        Uses a 2D no-overlap constraint where:
          - X-axis = time (day * GRIDS_PER_DAY + start_grid)
          - Y-axis = machine index

        Each batch occupies a rectangle in (time, machine) space. The
        NoOverlap2D constraint prevents any two rectangles from overlapping.

        Args:
            model: The CpModel to add constraints to.
            batch_vars_list: List of BatchVars for all batches.
            rules: Loaded ScheduleRules with marker duration info.
        """
        DEFAULT_TITRATION_GRIDS = 4  # 120 min default
        num_machines = len(rules.all_machines)

        if num_machines == 0 or len(batch_vars_list) == 0:
            return

        x_intervals = []  # Time intervals
        y_intervals = []  # Machine intervals (size=1 each)

        for i, bv in enumerate(batch_vars_list):
            prefix = f"mach_b{i}"
            marker_rule = rules.marker_rules.get(bv.batch.marker)

            # Determine titration duration
            if marker_rule and marker_rule.avg_duration_minutes:
                total_grids = max(1, marker_rule.avg_duration_minutes // MINS_PER_GRID)
                titration_grids = max(1, total_grids // 3)
            else:
                titration_grids = DEFAULT_TITRATION_GRIDS

            # Compute absolute start: day * GRIDS_PER_DAY + start_grid
            horizon_grids = GRIDS_PER_DAY * 7  # Assume max 7 days for domain
            abs_start = model.new_int_var(0, horizon_grids, f"{prefix}_abs_start")
            model.add(
                abs_start == bv.day * GRIDS_PER_DAY + bv.start_grid
            )

            # Time interval: [abs_start, abs_start + titration_grids)
            x_interval = model.new_interval_var(
                abs_start, titration_grids, abs_start + titration_grids,
                f"{prefix}_x_interval"
            )
            x_intervals.append(x_interval)

            # Machine interval: [machine_idx, machine_idx + 1)
            # Size=1 so each batch occupies exactly one machine slot
            machine_end = model.new_int_var(0, num_machines, f"{prefix}_mach_end")
            model.add(machine_end == bv.machine_idx + 1)

            y_interval = model.new_interval_var(
                bv.machine_idx, 1, machine_end,
                f"{prefix}_y_interval"
            )
            y_intervals.append(y_interval)

        # NoOverlap2D: no two rectangles can overlap
        model.add_no_overlap_2d(x_intervals, y_intervals)

        logging.info(
            f"[SchedulingEngine] Added machine port NoOverlap2D constraint "
            f"for {len(batch_vars_list)} batches across {num_machines} machines."
        )

    def _add_dryer_capacity_constraints(
        self,
        model: cp_model.CpModel,
        batch_vars_list: list[BatchVars],
        rules: ScheduleRules,
        horizon_days: int,
    ) -> None:
        """
        Freeze_Dryer 容量約束：per dryer per day count ≤ max_concurrent.

        Uses BoolVars to indicate whether a batch is assigned to a specific
        dryer on a specific day. Then constrains the sum per (dryer, day)
        to not exceed the dryer's max_concurrent capacity.

        Args:
            model: The CpModel to add constraints to.
            batch_vars_list: List of BatchVars for all batches.
            rules: Loaded ScheduleRules with capacity info.
            horizon_days: Number of days in the scheduling horizon.
        """
        num_dryers = len(rules.all_dryers)
        if num_dryers == 0 or len(batch_vars_list) == 0:
            return

        # For each (dryer_index, day), collect BoolVars indicating assignment
        # assignment[d][day] = list of BoolVars, one per batch
        for d_idx in range(num_dryers):
            dryer_id = rules.all_dryers[d_idx]

            # Get max_concurrent from machine_capacity_rule
            cap_info = rules.machine_capacities.get(dryer_id)
            max_concurrent = cap_info.max_concurrent if cap_info else 1

            for day in range(horizon_days):
                # Collect BoolVars: is batch i assigned to dryer d_idx on this day?
                day_dryer_bools: list[cp_model.IntVar] = []

                for i, bv in enumerate(batch_vars_list):
                    # Only consider batches that CAN use this dryer
                    if d_idx not in bv.allowed_dryer_indices:
                        continue

                    # BoolVar: batch i is on this dryer AND on this day
                    b_var = model.new_bool_var(
                        f"dryer_{d_idx}_day_{day}_b{i}"
                    )

                    # b_var == 1 iff (dryer_idx == d_idx) AND (day_var == day)
                    # Use reification:
                    # b_var => dryer_idx == d_idx
                    # b_var => day_var == day
                    # (dryer_idx == d_idx) AND (day_var == day) => b_var
                    is_dryer = model.new_bool_var(
                        f"is_dryer_{d_idx}_b{i}_d{day}"
                    )
                    is_day = model.new_bool_var(
                        f"is_day_{day}_b{i}_d{d_idx}"
                    )

                    model.add(bv.dryer_idx == d_idx).only_enforce_if(is_dryer)
                    model.add(bv.dryer_idx != d_idx).only_enforce_if(~is_dryer)
                    model.add(bv.day == day).only_enforce_if(is_day)
                    model.add(bv.day != day).only_enforce_if(~is_day)

                    # b_var = is_dryer AND is_day
                    model.add_bool_and([is_dryer, is_day]).only_enforce_if(b_var)
                    model.add_bool_or([~is_dryer, ~is_day]).only_enforce_if(~b_var)

                    day_dryer_bools.append(b_var)

                # Sum of assignments for this dryer/day <= max_concurrent
                if day_dryer_bools:
                    model.add(
                        sum(day_dryer_bools) <= max_concurrent
                    ).with_name(f"dryer_cap_{d_idx}_day_{day}")

        logging.info(
            f"[SchedulingEngine] Added dryer capacity constraints for "
            f"{num_dryers} dryers over {horizon_days} days."
        )

    def _add_operator_constraints(
        self,
        model: cp_model.CpModel,
        batch_vars_list: list[BatchVars],
        rules: ScheduleRules,
    ) -> None:
        """
        Operator 準備區間互斥約束：NoOverlap for Operator_Prepare_Intervals.

        The Operator_Prepare_Interval is defined as:
          [operator_prepare_start, DrugGivenAt]

        Where operator_prepare_start = batch start (start_grid) minus
        preparation duration. After DrugGivenAt, the operator is released.

        For simplicity, prep_start = start_grid - prep_duration (default 2 grids).
        The prepare interval is [prep_start, start_grid] in absolute time.

        Per operator: NoOverlap across all batches assigned to that operator.

        Args:
            model: The CpModel to add constraints to.
            batch_vars_list: List of BatchVars for all batches.
            rules: Loaded ScheduleRules with operator info.
        """
        num_operators = len(rules.all_operators)
        if num_operators == 0 or len(batch_vars_list) == 0:
            return

        # Default preparation duration in grids (dispensing phase = operator prep)
        DEFAULT_PREP_GRIDS = 2  # 60 min prep before DrugGivenAt

        # Use NoOverlap2D similar to machine ports:
        # X-axis = absolute time, Y-axis = operator index
        # Each batch occupies [abs_prep_start, abs_prep_start + prep_duration)
        # on the operator axis at [operator_idx, operator_idx + 1)

        x_intervals = []  # Time intervals (prep period)
        y_intervals = []  # Operator intervals (size=1)

        horizon_grids = GRIDS_PER_DAY * 7  # max horizon

        for i, bv in enumerate(batch_vars_list):
            prefix = f"op_b{i}"
            marker_rule = rules.marker_rules.get(bv.batch.marker)

            # Determine preparation duration
            if marker_rule and marker_rule.avg_duration_minutes:
                total_grids = max(1, marker_rule.avg_duration_minutes // MINS_PER_GRID)
                prep_grids = max(1, total_grids // 3)  # dispensing ~ 1/3
            else:
                prep_grids = DEFAULT_PREP_GRIDS

            # Absolute prep start: day * GRIDS_PER_DAY + (start_grid - prep_grids)
            # start_grid is the titration start = DrugGivenAt
            # Operator prepares from (start_grid - prep_grids) to start_grid
            abs_prep_start = model.new_int_var(
                0, horizon_grids, f"{prefix}_abs_prep_start"
            )
            model.add(
                abs_prep_start == bv.day * GRIDS_PER_DAY + bv.start_grid - prep_grids
            )

            # Prep end = abs_prep_start + prep_grids (= day*GPD + start_grid)
            x_interval = model.new_interval_var(
                abs_prep_start, prep_grids, abs_prep_start + prep_grids,
                f"{prefix}_prep_x_interval"
            )
            x_intervals.append(x_interval)

            # Operator interval: [operator_idx, operator_idx + 1)
            op_end = model.new_int_var(
                0, num_operators, f"{prefix}_op_end"
            )
            model.add(op_end == bv.operator_idx + 1)

            y_interval = model.new_interval_var(
                bv.operator_idx, 1, op_end,
                f"{prefix}_op_y_interval"
            )
            y_intervals.append(y_interval)

        # NoOverlap2D: no two operator prep rectangles overlap
        model.add_no_overlap_2d(x_intervals, y_intervals)

        logging.info(
            f"[SchedulingEngine] Added operator prepare interval NoOverlap2D "
            f"constraint for {len(batch_vars_list)} batches across "
            f"{num_operators} operators."
        )

    def _add_base_rule_resource_constraints(
        self,
        model: cp_model.CpModel,
        batch_vars_list: list[BatchVars],
        rules: ScheduleRules,
    ) -> None:
        """
        資源分配限制在 Base_Rule_Tables 允許範圍。

        This method enforces additional cross-batch resource constraints
        beyond the per-batch allowed_assignments already added in
        _build_cp_model. Specifically:

        1. Ensures that if rules source is 'base', the constraint is
           strictly enforced (no relaxation).
        2. Adds joint constraints if a marker has both machine and dryer
           restrictions that are correlated (e.g., certain machines must
           pair with certain dryers).

        Note: The primary per-batch domain restrictions (machine_idx in
        allowed set, dryer_idx in allowed set, operator_idx in allowed set)
        are already handled via add_allowed_assignments in _build_cp_model.
        This method adds any supplementary constraints needed.

        Args:
            model: The CpModel to add constraints to.
            batch_vars_list: List of BatchVars for all batches.
            rules: Loaded ScheduleRules with base rule information.
        """
        # The per-batch allowed_assignments constraints are already set in
        # _build_cp_model. This method validates and adds any additional
        # constraints that may arise from correlations between resources.

        for i, bv in enumerate(batch_vars_list):
            prefix = f"base_b{i}"
            marker_rule = rules.marker_rules.get(bv.batch.marker)

            if not marker_rule:
                continue

            # Reinforcement: ensure allowed indices are strictly from base rules
            # This is already done in _build_cp_model via add_allowed_assignments,
            # but we add redundant constraints as safety nets if using base source.
            if rules.source == 'base':
                # Machine constraint: re-enforce allowed machine indices
                if bv.allowed_machine_indices and len(rules.all_machines) > 1:
                    # Ensure machine_idx is in the allowed set
                    allowed_machine_bools = []
                    for m_idx in bv.allowed_machine_indices:
                        b = model.new_bool_var(f"{prefix}_mach_allowed_{m_idx}")
                        model.add(bv.machine_idx == m_idx).only_enforce_if(b)
                        allowed_machine_bools.append(b)
                    if allowed_machine_bools:
                        model.add_at_least_one(allowed_machine_bools).with_name(
                            f"{prefix}_machine_in_base_rules"
                        )

                # Dryer constraint: re-enforce allowed dryer indices
                if bv.allowed_dryer_indices and len(rules.all_dryers) > 1:
                    allowed_dryer_bools = []
                    for d_idx in bv.allowed_dryer_indices:
                        b = model.new_bool_var(f"{prefix}_dryer_allowed_{d_idx}")
                        model.add(bv.dryer_idx == d_idx).only_enforce_if(b)
                        allowed_dryer_bools.append(b)
                    if allowed_dryer_bools:
                        model.add_at_least_one(allowed_dryer_bools).with_name(
                            f"{prefix}_dryer_in_base_rules"
                        )

                # Operator constraint: re-enforce allowed operator indices
                if bv.allowed_operator_indices and len(rules.all_operators) > 1:
                    allowed_op_bools = []
                    for o_idx in bv.allowed_operator_indices:
                        b = model.new_bool_var(f"{prefix}_op_allowed_{o_idx}")
                        model.add(bv.operator_idx == o_idx).only_enforce_if(b)
                        allowed_op_bools.append(b)
                    if allowed_op_bools:
                        model.add_at_least_one(allowed_op_bools).with_name(
                            f"{prefix}_operator_in_base_rules"
                        )

        logging.info(
            f"[SchedulingEngine] Added base rule resource constraints for "
            f"{len(batch_vars_list)} batches (source={rules.source})."
        )

    # ------------------------------------------------------------------
    # Port Time-Based Capacity (no overlap on same port)
    # ------------------------------------------------------------------

    def _add_daily_batch_limit(
        self,
        model: cp_model.CpModel,
        batch_vars_list: list[BatchVars],
        horizon_days: int,
        max_per_day: int = 36,
    ) -> None:
        """
        Port no-overlap constraint using NoOverlap2D.

        Two batches cannot use the same port at overlapping times.
        X-axis = absolute time (day * GRIDS_PER_DAY + start_grid)
        Y-axis = port index (0~13)

        Each batch occupies a rectangle in (time × port) space.
        NoOverlap2D prevents any two rectangles from overlapping.
        """
        if not batch_vars_list:
            return

        DEFAULT_TITRATION_GRIDS = 4
        horizon_grids = horizon_days * GRIDS_PER_DAY
        NUM_PORTS = len(batch_vars_list[0].allowed_machine_indices or range(14))

        x_intervals = []  # time intervals
        y_intervals = []  # port intervals (size=1)

        for i, bv in enumerate(batch_vars_list):
            marker_rule = self._rules.marker_rules.get(bv.batch.marker) if self._rules else None

            # Duration in grids
            if marker_rule and marker_rule.avg_duration_minutes:
                dur = max(1, marker_rule.avg_duration_minutes // MINS_PER_GRID)
            else:
                dur = DEFAULT_TITRATION_GRIDS

            # Absolute start = day * GRIDS_PER_DAY + start_grid
            abs_start = model.new_int_var(0, horizon_grids - dur, f"abs_s{i}")
            model.add(abs_start == bv.day * GRIDS_PER_DAY + bv.start_grid)

            abs_end = model.new_int_var(dur, horizon_grids, f"abs_e{i}")
            model.add(abs_end == abs_start + dur)

            # X interval: time
            x_iv = model.new_interval_var(abs_start, dur, abs_end, f"x_iv{i}")
            x_intervals.append(x_iv)

            # Y interval: port (size=1, each batch occupies one port slot)
            num_machines = len(batch_vars_list[0].allowed_machine_indices) if batch_vars_list else 14
            port_end = model.new_int_var(0, 14, f"port_e{i}")
            model.add(port_end == bv.machine_idx + 1)
            y_iv = model.new_interval_var(bv.machine_idx, 1, port_end, f"y_iv{i}")
            y_intervals.append(y_iv)

        # No two batches can occupy the same (time, port) rectangle
        model.add_no_overlap_2d(x_intervals, y_intervals)

        logging.info(
            f"[SchedulingEngine] Added port NoOverlap2D: "
            f"{len(batch_vars_list)} batches, {horizon_days} days."
        )

    # ------------------------------------------------------------------
    # Objective Function
    # ------------------------------------------------------------------

    def _add_objective(
        self,
        model: cp_model.CpModel,
        batch_vars_list: list[BatchVars],
    ) -> None:
        """
        Add minimization objective to the model.

        Objective: Minimize sum of (batch.priority * 2000 + day * 100 + start_grid)
        across all batches.

        This prioritizes:
          1. Higher-priority (lower number) batches scheduled first
          2. Earlier days preferred
          3. Earlier start times within a day preferred

        Args:
            model: The CpModel to add the objective to.
            batch_vars_list: List of BatchVars for all batches.
        """
        objective_terms = []

        for bv in batch_vars_list:
            # Priority weight: lower priority number = more urgent
            priority_weight = bv.batch.priority * 2000

            # day * 100: prefer earlier days
            # start_grid: prefer earlier start within a day
            # Total cost per batch = priority * 2000 + day * 100 + start_grid
            # Since priority is constant per batch, we add it as a fixed offset
            # via a scaled variable or direct expression.
            cost = model.new_int_var(
                0, priority_weight + (GRIDS_PER_DAY * 100) + GRIDS_PER_DAY,
                f"cost_{bv.batch.marker}_{bv.batch.batch}"
            )
            model.add(cost == priority_weight + bv.day * 100 + bv.start_grid)
            objective_terms.append(cost)

        if objective_terms:
            model.minimize(sum(objective_terms))

        logging.info(
            f"[SchedulingEngine] Added priority objective for "
            f"{len(batch_vars_list)} batches: "
            f"minimize(priority*2000 + day*100 + start_grid)."
        )

    # ------------------------------------------------------------------
    # Solver Execution
    # ------------------------------------------------------------------

    def _solve(
        self,
        model: cp_model.CpModel,
    ) -> tuple[cp_model.CpSolver, int]:
        """
        Execute CP-SAT solver with configured time limit and worker count.

        Creates a CpSolver instance with:
          - max_time_in_seconds = 30
          - num_workers = 4

        Args:
            model: The CpModel to solve.

        Returns:
            Tuple of (solver instance, status code).
            Status codes from cp_model:
              OPTIMAL = 4
              FEASIBLE = 2
              INFEASIBLE = 3
              MODEL_INVALID = 1
              UNKNOWN = 0
        """
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = SOLVER_MAX_TIME_SECONDS
        solver.parameters.num_workers = SOLVER_NUM_WORKERS

        logging.info(
            f"[SchedulingEngine] Solving CP-SAT model "
            f"(max_time={SOLVER_MAX_TIME_SECONDS}s, workers={SOLVER_NUM_WORKERS})..."
        )

        status = solver.solve(model)

        status_name = solver.status_name(status)
        logging.info(
            f"[SchedulingEngine] Solver finished: status={status_name} "
            f"(code={status}), "
            f"wall_time={solver.wall_time:.2f}s, "
            f"objective={solver.objective_value if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else 'N/A'}."
        )

        self.solver = solver
        return solver, status

    # ------------------------------------------------------------------
    # Solution Extraction
    # ------------------------------------------------------------------

    def _extract_solution(
        self,
        solver: cp_model.CpSolver,
        batch_vars_list: list[BatchVars],
        rules: ScheduleRules,
    ) -> list[dict]:
        """
        Convert solver variable values to schedule entry dictionaries.

        For each batch, extracts:
          - day (int): the day index in the horizon
          - start_grid (int): grid slot within the day
          - machine_idx → machine name from rules.all_machines
          - dryer_idx → dryer name from rules.all_dryers
          - operator_idx → operator name from rules.all_operators

        Converts grids to actual times:
          minutes_since_midnight = grid * 30 + 10 * 60
          (Grid 0 = 10:00, Grid 1 = 10:30, etc.)

        Also computes end_time based on marker avg_duration or default
        titration duration (4 grids = 120 min).

        Args:
            solver: The solved CpSolver instance.
            batch_vars_list: List of BatchVars for all batches.
            rules: Loaded ScheduleRules for resource name lookups.

        Returns:
            List of schedule entry dicts suitable for generated_schedule table.
        """
        entries: list[dict] = []

        DEFAULT_TITRATION_GRIDS = 4  # 120 min default
        DEFAULT_DISPENSING_GRIDS = 2  # 60 min default

        for bv in batch_vars_list:
            # Extract variable values
            day = solver.value(bv.day)
            start_grid = solver.value(bv.start_grid)
            machine_idx = solver.value(bv.machine_idx)
            dryer_idx = solver.value(bv.dryer_idx)
            operator_idx = solver.value(bv.operator_idx)

            # Map indices to resource names with display format
            raw_machine = (
                rules.all_machines[machine_idx]
                if machine_idx < len(rules.all_machines)
                else None
            )
            # Format port display: "1" → "P1", "IVEK-1" → "IVEK-1"
            if raw_machine and not raw_machine.startswith('IVEK'):
                machine_name = f"P{raw_machine}"
            else:
                machine_name = raw_machine
            dryer_name = (
                rules.all_dryers[dryer_idx]
                if dryer_idx < len(rules.all_dryers)
                else None
            )
            operator_name = (
                rules.all_operators[operator_idx]
                if operator_idx < len(rules.all_operators)
                else None
            )

            # Determine titration duration (grids)
            marker_rule = rules.marker_rules.get(bv.batch.marker)
            if marker_rule and marker_rule.avg_duration_minutes:
                total_grids = max(
                    1, marker_rule.avg_duration_minutes // MINS_PER_GRID
                )
                titration_grids = max(1, total_grids // 3)
                dispensing_grids = max(1, total_grids // 3)
            else:
                titration_grids = DEFAULT_TITRATION_GRIDS
                dispensing_grids = DEFAULT_DISPENSING_GRIDS

            # Convert grids to times (minutes since START_HOUR)
            # Work window: 09:00 ~ 01:00 next day = 16 hrs = 32 grids
            WORK_START_HOUR = 9   # 09:00
            WORK_END_MINUTES = (24 + 1) * 60  # 01:00 next day = 25:00 = 1500 min

            start_minutes = start_grid * MINS_PER_GRID + WORK_START_HOUR * 60
            end_raw = (start_grid + titration_grids) * MINS_PER_GRID + WORK_START_HOUR * 60
            end_minutes = min(end_raw, WORK_END_MINUTES)

            rd_minutes = start_minutes

            def fmt_time(m: int) -> str:
                h = m // 60
                mm = m % 60
                # Times after midnight shown as 24:xx, 25:xx etc (keep as-is up to 01:00)
                # But DB stores as TIME, cap at 23:59 for SQL compatibility
                # Use next-day indicator in notes if needed
                if h >= 24:
                    h = 23
                    mm = 59
                return f"{h:02d}:{mm:02d}"

            start_time_str = fmt_time(start_minutes)
            end_time_str   = fmt_time(end_minutes)
            rd_time_str    = fmt_time(rd_minutes)

            entry = {
                "day_index": day,
                "marker": bv.batch.marker,
                "pn": bv.batch.pn,
                "machine_port": machine_name,
                "freeze_dryer": dryer_name,
                "operator": operator_name,
                "rd_time": rd_time_str,
                "start_time": start_time_str,
                "end_time": end_time_str,
                "quantity": bv.batch.quantity,
                "batch": bv.batch.batch,
                "work_order": bv.batch.work_order,
                "priority": bv.batch.priority,
                "notes": None,
                "conflict_flag": False,
                "conflict_reason": None,
                "status": "draft",
            }
            entries.append(entry)

        logging.info(
            f"[SchedulingEngine] Extracted {len(entries)} schedule entries "
            f"from solver solution."
        )

        return entries

    # ------------------------------------------------------------------
    # Degradation Retry Logic
    # ------------------------------------------------------------------

    def _solve_with_degradation(
        self,
        batches: list[Batch],
        rules: ScheduleRules,
        horizon_days: int,
    ) -> tuple[list[dict] | None, str]:
        """
        Solve with degradation retry: if INFEASIBLE and batches span
        multiple priority levels (W1+W2), retry with only W1 batches.

        Degradation strategy:
          1. First attempt: all batches (W1 + W2 + W3)
          2. If INFEASIBLE and W2/W3 batches exist: retry with W1 + W2 only
          3. If still INFEASIBLE and W2 batches exist: retry with W1 only
          4. If all attempts fail: return None

        Args:
            batches: Full list of batches to schedule.
            rules: Loaded ScheduleRules.
            horizon_days: Number of days in scheduling horizon.

        Returns:
            Tuple of (schedule entries or None, degradation note string).
            The note indicates which priority levels were included.
        """
        # Determine which priority levels exist
        priorities = sorted(set(b.priority for b in batches))
        max_priority = max(priorities) if priorities else 1

        # Build degradation levels (from most inclusive to least)
        # Priority 1 = W1 (most urgent), 2 = W2, 3 = W3
        attempts = []
        if max_priority >= 3:
            attempts.append((priorities, "W1+W2+W3"))
            attempts.append(([p for p in priorities if p <= 2], "W1+W2"))
            attempts.append(([1], "W1 only"))
        elif max_priority >= 2:
            attempts.append((priorities, "W1+W2"))
            attempts.append(([1], "W1 only"))
        else:
            attempts.append(([1], "W1 only"))

        for included_priorities, label in attempts:
            # Filter batches to included priorities
            filtered_batches = [
                b for b in batches if b.priority in included_priorities
            ]

            if not filtered_batches:
                continue

            logging.info(
                f"[SchedulingEngine] Attempting solve with {label}: "
                f"{len(filtered_batches)} batches."
            )

            # Build model with filtered batches
            model, batch_vars_list = self._build_cp_model(
                filtered_batches, rules, horizon_days
            )

            # Add constraints
            self._add_production_flow_constraints(model, batch_vars_list, rules)
            # Daily port capacity: 12 ports × ~3 rounds = 36 port-slots/day
            self._add_daily_batch_limit(model, batch_vars_list, horizon_days, max_per_day=36)

            # Add objective
            self._add_objective(model, batch_vars_list)

            # Solve
            solver, status = self._solve(model)

            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                entries = self._extract_solution(solver, batch_vars_list, rules)
                logging.info(
                    f"[SchedulingEngine] Solution found with {label}."
                )
                return entries, label

            logging.warning(
                f"[SchedulingEngine] Solve failed with {label} "
                f"(status={solver.status_name(status)}). "
                f"Trying degradation..."
            )

        # All attempts failed
        logging.error(
            "[SchedulingEngine] All degradation attempts INFEASIBLE. "
            "No solution found."
        )
        return None, "all_failed"

    # ------------------------------------------------------------------
    # Full Pipeline Orchestrator
    # ------------------------------------------------------------------

    def generate(
        self,
        week_code: str,
        demands: list[dict],
        resource_config: dict | None = None,
    ) -> dict:
        """
        完整排程產生流程 — 從需求到排程結果。

        Orchestrates:
          1. Generate unique schedule_run_id (UUID)
          2. Load scheduling rules (_load_rules)
          3. Load dispensing limits for batch splitting
          4. Split demands into batches (BatchSplitter)
          5. Build CP-SAT model and add constraints
          6. Solve with degradation retry (_solve_with_degradation)
          7. Assign concrete dates based on week_code and resource_config
          8. Run ConflictDetector on results
          9. Write results to generated_schedule table
          10. Return results with schedule_run_id

        Args:
            week_code: Week identifier (e.g. "2026-W24").
            demands: List of demand dicts, each containing:
                - marker (str): Marker name
                - pn (str): Product number
                - quantity (int): Total quantity demanded
                - priority (int, optional): Priority level (default 1)
                - week (int, optional): ISO week number
                - month (int, optional): Month number
                - year (int, optional): Year
            resource_config: Optional resource configuration dict:
                - holidays (list[str]): Day names to exclude (e.g. ["六", "日"])
                - dryerMaintenance (list): Dryers under maintenance
                - staffOffDays (dict): Operator → list of off days

        Returns:
            Dict with keys:
                - schedule_run_id (str): UUID for this run
                - entries (list[dict]): Generated schedule entries
                - conflicts_summary (dict): Conflict statistics
                - degradation_note (str): Which priority levels were included

        Raises:
            ValueError: If demands is empty or week_code is invalid.
            RuntimeError: If solver cannot find any feasible solution.
        """
        # --- 1. Generate unique schedule_run_id ---
        schedule_run_id = uuid.uuid4()
        logging.info(
            f"[SchedulingEngine.generate] Starting run {schedule_run_id} "
            f"for week_code={week_code}, {len(demands)} demands."
        )

        # --- 2. Parse week_code to derive year/week/dates ---
        year, week_num = self._parse_week_code(week_code)

        # Determine scheduling horizon (workdays in the week)
        resource_config = resource_config or {}
        holidays = resource_config.get('holidays', ['六', '日'])
        horizon_days = self._compute_horizon_days(year, week_num, holidays)

        # --- 3. Load scheduling rules ---
        rules = self._load_rules()

        # --- 4. Load dispensing limits for batch splitting ---
        limits = self._load_dispensing_limits()

        # --- 5. Convert demand dicts to MarkerDemand and split into batches ---
        marker_demands = []
        for d in demands:
            md = MarkerDemand(
                marker=d['marker'],
                pn=d['pn'],
                quantity=d['quantity'],
                priority=d.get('priority', 1),
                year=year,
                week=week_num,
                month=d.get('month') or self._week_to_month(year, week_num),
            )
            marker_demands.append(md)

        splitter = BatchSplitter(self.db)
        batches = splitter.split_demands(marker_demands, limits)

        if not batches:
            logging.warning("[SchedulingEngine.generate] No batches after splitting.")
            return {
                "schedule_run_id": str(schedule_run_id),
                "entries": [],
                "conflicts_summary": {"total": 0, "by_type": {}},
                "degradation_note": "no_batches",
            }

        logging.info(
            f"[SchedulingEngine.generate] Split into {len(batches)} batches."
        )

        # --- 6. Solve with degradation ---
        entries, degradation_note = self._solve_with_degradation(
            batches, rules, horizon_days
        )

        if entries is None:
            raise RuntimeError(
                f"Solver could not find feasible solution for week {week_code}. "
                f"All degradation attempts failed."
            )

        # --- 7. Assign concrete dates based on week_code ---
        workdays = self._get_workdays(year, week_num, holidays)
        for entry in entries:
            day_idx = entry.get('day_index', 0)
            if day_idx < len(workdays):
                entry['date'] = workdays[day_idx]
            else:
                entry['date'] = workdays[-1] if workdays else date.today()

        # --- 8. Run ConflictDetector ---
        detector = ConflictDetector(rules)
        conflicts = detector.detect_all(entries)

        # Build conflicts summary
        conflicts_by_type: dict[str, int] = defaultdict(int)
        for c in conflicts:
            conflicts_by_type[c.conflict_type] += 1
        # Count unique entries with conflicts (not double-count)
        conflicting_entry_ids = set(c.entry_id for c in conflicts)
        conflicts_summary = {
            "total": len(conflicting_entry_ids),
            "by_type": dict(conflicts_by_type),
        }

        # --- 9. Write results to generated_schedule ---
        self._write_to_generated_schedule(
            entries, schedule_run_id, week_code
        )

        logging.info(
            f"[SchedulingEngine.generate] Run {schedule_run_id} complete: "
            f"{len(entries)} entries, {conflicts_summary['total']} conflicts, "
            f"degradation={degradation_note}."
        )

        # --- 10. Return results ---
        return {
            "schedule_run_id": str(schedule_run_id),
            "entries": entries,
            "conflicts_summary": conflicts_summary,
            "degradation_note": degradation_note,
        }

    # ------------------------------------------------------------------
    # Generate Helper Methods
    # ------------------------------------------------------------------

    def _parse_week_code(self, week_code: str) -> tuple[int, int]:
        """
        Parse week_code string (e.g. "2026-W24") to (year, week_number).

        Args:
            week_code: String in format "YYYY-WNN".

        Returns:
            Tuple of (year, week_number).

        Raises:
            ValueError: If format is invalid.
        """
        try:
            parts = week_code.split('-W')
            if len(parts) != 2:
                raise ValueError
            year = int(parts[0])
            week_num = int(parts[1])
            if week_num < 1 or week_num > 53:
                raise ValueError
            return year, week_num
        except (ValueError, IndexError):
            raise ValueError(
                f"Invalid week_code format: '{week_code}'. "
                f"Expected format: 'YYYY-WNN' (e.g. '2026-W24')."
            )

    def _compute_horizon_days(
        self, year: int, week_num: int, holidays: list[str]
    ) -> int:
        """
        Compute the number of working days in the week (horizon for solver).

        Maps Chinese day names to weekday indices and excludes them.
        Default: exclude Saturday (六) and Sunday (日) → 5 workdays.

        Args:
            year: Calendar year.
            week_num: ISO week number.
            holidays: List of day names to exclude (e.g. ["六", "日"]).

        Returns:
            Number of working days (solver horizon).
        """
        day_name_to_weekday = {
            '一': 0, '二': 1, '三': 2, '四': 3,
            '五': 4, '六': 5, '日': 6,
        }
        excluded_weekdays = set()
        for h in holidays:
            if h in day_name_to_weekday:
                excluded_weekdays.add(day_name_to_weekday[h])

        # Count working days in a 7-day week
        workdays = 7 - len(excluded_weekdays)
        return max(1, workdays)

    def _get_workdays(
        self, year: int, week_num: int, holidays: list[str]
    ) -> list[date]:
        """
        Get ordered list of working day dates for the given week.

        Args:
            year: Calendar year.
            week_num: ISO week number.
            holidays: Day names to exclude.

        Returns:
            List of date objects for each working day.
        """
        day_name_to_weekday = {
            '一': 0, '二': 1, '三': 2, '四': 3,
            '五': 4, '六': 5, '日': 6,
        }
        excluded_weekdays = set()
        for h in holidays:
            if h in day_name_to_weekday:
                excluded_weekdays.add(day_name_to_weekday[h])

        # ISO week: Monday of the given ISO week
        # Python's date.fromisocalendar(year, week, day) where day=1 is Monday
        workdays = []
        for weekday in range(7):  # 0=Mon, 6=Sun
            if weekday not in excluded_weekdays:
                d = date.fromisocalendar(year, week_num, weekday + 1)
                workdays.append(d)

        return workdays

    def _week_to_month(self, year: int, week_num: int) -> int:
        """
        Determine the month for a given ISO week (uses the Thursday rule).

        Args:
            year: Calendar year.
            week_num: ISO week number.

        Returns:
            Month number (1-12).
        """
        # Thursday of the ISO week determines the month
        thursday = date.fromisocalendar(year, week_num, 4)
        return thursday.month

    def _load_dispensing_limits(self) -> dict[str, int]:
        """
        Load 配藥限制 quantity limits for batch splitting.

        Reads the 數量 column from schedule.配藥限制 table, keyed by Marker.

        Returns:
            Dict mapping marker name → max batch size (int).
        """
        limits: dict[str, int] = {}
        try:
            result = self.db.execute(text("""
                SELECT "Marker", "數量"
                FROM "schedule"."配藥限制"
                WHERE "Marker" IS NOT NULL AND "數量" IS NOT NULL
            """))
            for row in result:
                marker = str(row[0]).strip()
                qty = row[1]
                if marker and qty:
                    # Handle "2700 or 11000" style values — take the first number
                    if isinstance(qty, str):
                        qty_str = qty.split(' ')[0].replace(',', '')
                        try:
                            limits[marker] = int(float(qty_str))
                        except (ValueError, TypeError):
                            pass
                    else:
                        limits[marker] = int(qty)
        except Exception as e:
            logging.warning(
                f"[SchedulingEngine] Failed to load 配藥限制 quantity: {e}"
            )
            self.db.rollback()

        return limits

    def _write_to_generated_schedule(
        self,
        entries: list[dict],
        schedule_run_id: uuid.UUID,
        week_code: str,
    ) -> None:
        """
        Write schedule entries to the generated_schedule table.

        Args:
            entries: List of schedule entry dicts from the solver.
            schedule_run_id: UUID for this scheduling run.
            week_code: The week code (e.g. "2026-W24").
        """
        if not entries:
            return

        for entry in entries:
            entry_date = entry.get('date')
            # Convert date to string if needed for SQL
            if isinstance(entry_date, date):
                date_str = entry_date.isoformat()
            else:
                date_str = str(entry_date) if entry_date else None

            try:
                self.db.execute(text("""
                    INSERT INTO "P01_formualte_schedule".generated_schedule
                    (schedule_run_id, week_code, date, marker, machine_port,
                     freeze_dryer, operator, rd_time, start_time, end_time,
                     quantity, pn, batch, work_order, notes,
                     conflict_flag, conflict_reason, priority, status)
                    VALUES
                    (:run_id, :week_code, :date, :marker, :machine_port,
                     :freeze_dryer, :operator, :rd_time, :start_time, :end_time,
                     :quantity, :pn, :batch, :work_order, :notes,
                     :conflict_flag, :conflict_reason, :priority, :status)
                """), {
                    "run_id": str(schedule_run_id),
                    "week_code": week_code,
                    "date": date_str,
                    "marker": entry.get('marker'),
                    "machine_port": entry.get('machine_port'),
                    "freeze_dryer": entry.get('freeze_dryer'),
                    "operator": entry.get('operator'),
                    "rd_time": entry.get('rd_time'),
                    "start_time": entry.get('start_time'),
                    "end_time": entry.get('end_time'),
                    "quantity": entry.get('quantity'),
                    "pn": entry.get('pn'),
                    "batch": entry.get('batch'),
                    "work_order": entry.get('work_order'),
                    "notes": entry.get('notes'),
                    "conflict_flag": entry.get('conflict_flag', False),
                    "conflict_reason": entry.get('conflict_reason'),
                    "priority": entry.get('priority', 1),
                    "status": entry.get('status', 'draft'),
                })
            except Exception as e:
                logging.error(
                    f"[SchedulingEngine] Failed to write entry "
                    f"(batch={entry.get('batch')}): {e}"
                )
                raise

        self.db.commit()
        logging.info(
            f"[SchedulingEngine] Wrote {len(entries)} entries to "
            f"generated_schedule (run_id={schedule_run_id})."
        )
