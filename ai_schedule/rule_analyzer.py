"""
Rule Analyzer — 從歷史排程資料萃取 Marker 生產規則

Responsibilities:
- Load historical data from DropletSchedule (2026), dropletRecord, worker_order
- Analyze each Marker to extract production patterns (machines, dryers, operators, times, quantities)
- Write derived rules to marker_rule, machine_capacity_rule, operator_rule tables
- Mark low-confidence Markers (< 3 records) and fallback to Base_Rule_Tables
- Return analysis summary with markers_analyzed, rules_created, insufficient_data_markers
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MarkerRuleData:
    """Intermediate analysis result for a single Marker."""
    marker_name: str
    pn: Optional[str] = None
    common_machines: list[str] = field(default_factory=list)
    common_dryers: list[str] = field(default_factory=list)
    common_operators: list[str] = field(default_factory=list)
    avg_start_time: Optional[time] = None
    avg_end_time: Optional[time] = None
    avg_duration_minutes: Optional[int] = None
    common_quantities: list[int] = field(default_factory=list)
    special_notes: list[str] = field(default_factory=list)
    data_confidence: str = 'medium'
    record_count: int = 0


@dataclass
class AnalysisSummary:
    """Result summary returned by analyze_all()."""
    markers_analyzed: int = 0
    rules_created: int = 0
    insufficient_data_markers: list[str] = field(default_factory=list)
    data_sources: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Minimum record threshold for sufficient data
# ---------------------------------------------------------------------------

MIN_RECORDS_THRESHOLD = 3


# ---------------------------------------------------------------------------
# RuleAnalyzer
# ---------------------------------------------------------------------------

class RuleAnalyzer:
    """從歷史排程資料萃取 Marker 生產規則並寫入衍生規則表。"""

    def __init__(self, db_session: Session):
        """
        Initialize RuleAnalyzer with a database session.

        Args:
            db_session: SQLAlchemy session for querying and writing data.
        """
        self.db = db_session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_all(self) -> AnalysisSummary:
        """
        主入口：分析所有 Marker 規則並寫入衍生規則表。

        Flow:
        1. Load historical data (DropletSchedule, dropletRecord, worker_order)
        2. Load Base Rule Tables for fallback (freezer_rules, pump No., 配藥限制)
        3. Analyze each Marker's patterns
        4. Write results to marker_rule, machine_capacity_rule, operator_rule
        5. Return AnalysisSummary

        Returns:
            AnalysisSummary with markers_analyzed, rules_created, and
            insufficient_data_markers list.
        """
        summary = AnalysisSummary()

        # Step 1: Load historical data
        df_schedule, df_records, df_work_orders = self._load_historical_data()

        # Record data source coverage
        summary.data_sources = {
            'droplet_schedule_records': len(df_schedule),
            'droplet_record_records': len(df_records),
            'worker_order_records': len(df_work_orders),
        }

        # Step 2: Load Base Rule Tables for fallback
        base_rules = self._load_base_rules()

        # Step 3: Merge data sources for analysis
        # Combine DropletSchedule and dropletRecord for comprehensive analysis
        merged = self._merge_data_sources(df_schedule, df_records, df_work_orders)

        # Step 4: Get unique markers from merged data
        all_markers = merged['marker'].dropna().unique().tolist()
        logging.info(f"[RuleAnalyzer] Found {len(all_markers)} unique markers to analyze.")

        # Step 5: Analyze each Marker
        marker_rules: list[MarkerRuleData] = []
        machines_seen: dict[str, dict] = {}
        operators_seen: dict[str, list[str]] = {}

        for marker_name in all_markers:
            marker_records = merged[merged['marker'] == marker_name]
            rule_data = self._analyze_marker(marker_name, marker_records, base_rules)
            marker_rules.append(rule_data)

            # Track machines and operators for capacity/operator rules
            for m in rule_data.common_machines:
                if m and m not in machines_seen:
                    machines_seen[m] = {'type': 'port', 'marker': marker_name}
            for d in rule_data.common_dryers:
                if d and d not in machines_seen:
                    machines_seen[d] = {'type': 'dryer', 'marker': marker_name}
            for op in rule_data.common_operators:
                if op:
                    if op not in operators_seen:
                        operators_seen[op] = []
                    operators_seen[op].append(marker_name)

            if rule_data.data_confidence == 'low':
                summary.insufficient_data_markers.append(marker_name)

        summary.markers_analyzed = len(marker_rules)

        # Step 6: Write to database tables
        rules_created = self._write_marker_rules(marker_rules)
        rules_created += self._write_machine_capacity_rules(machines_seen)
        rules_created += self._write_operator_rules(operators_seen)

        summary.rules_created = rules_created

        logging.info(
            f"[RuleAnalyzer] Analysis complete: "
            f"{summary.markers_analyzed} markers analyzed, "
            f"{summary.rules_created} rules created, "
            f"{len(summary.insufficient_data_markers)} insufficient data markers."
        )

        return summary

    # ------------------------------------------------------------------
    # Historical Data Loading
    # ------------------------------------------------------------------

    def _load_historical_data(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        載入 DropletSchedule (2026)、dropletRecord、worker_order 歷史資料。

        Returns:
            Tuple of (df_schedule, df_records, df_work_orders) DataFrames.
        """
        df_schedule = self._load_droplet_schedule()
        df_records = self._load_droplet_records()
        df_work_orders = self._load_worker_orders()

        return df_schedule, df_records, df_work_orders

    def _load_droplet_schedule(self) -> pd.DataFrame:
        """Load DropletSchedule table (2026 data) from P01_formualte_schedule schema."""
        try:
            result = self.db.execute(text("""
                SELECT "WorkOrder", "Marker", "Quantity", "Date",
                       "Lot", "Pump", "Lyophilizer", "DrugGivenAt"
                FROM "P01_formualte_schedule"."DropletSchedule"
                WHERE "Date" IS NOT NULL
                  AND "Date" LIKE '2026%'
                  AND "Marker" IS NOT NULL
                  AND "Marker" != ''
            """))
            rows = result.fetchall()
            columns = ['WorkOrder', 'Marker', 'Quantity', 'Date',
                       'Lot', 'Pump', 'Lyophilizer', 'DrugGivenAt']
            df = pd.DataFrame(rows, columns=columns)
            logging.info(f"[RuleAnalyzer] Loaded {len(df)} DropletSchedule records (2026).")
            return df
        except Exception as e:
            logging.warning(f"[RuleAnalyzer] Failed to load DropletSchedule: {e}")
            return pd.DataFrame(columns=['WorkOrder', 'Marker', 'Quantity', 'Date',
                                         'Lot', 'Pump', 'Lyophilizer', 'DrugGivenAt'])

    def _load_droplet_records(self) -> pd.DataFrame:
        """Load dropletRecord table from P01_formualte_schedule schema."""
        try:
            result = self.db.execute(text("""
                SELECT "WorkOrder", "marker", "lot", "titration_port",
                       "lyophilizer", "quanity", "DrugGivenAt",
                       "start_time", "end_time", "operator"
                FROM "P01_formualte_schedule"."dropletRecord"
                WHERE "marker" IS NOT NULL
                  AND "marker" != ''
            """))
            rows = result.fetchall()
            columns = ['WorkOrder', 'marker', 'lot', 'titration_port',
                       'lyophilizer', 'quanity', 'DrugGivenAt',
                       'start_time', 'end_time', 'operator']
            df = pd.DataFrame(rows, columns=columns)
            logging.info(f"[RuleAnalyzer] Loaded {len(df)} dropletRecord records.")
            return df
        except Exception as e:
            logging.warning(f"[RuleAnalyzer] Failed to load dropletRecord: {e}")
            return pd.DataFrame(columns=['WorkOrder', 'marker', 'lot', 'titration_port',
                                         'lyophilizer', 'quanity', 'DrugGivenAt',
                                         'start_time', 'end_time', 'operator'])

    def _load_worker_orders(self) -> pd.DataFrame:
        """Load worker_order table for work order scheduling patterns."""
        try:
            result = self.db.execute(text("""
                SELECT *
                FROM "worker_order"
                WHERE 1=1
            """))
            rows = result.fetchall()
            if rows:
                columns = result.keys()
                df = pd.DataFrame(rows, columns=columns)
            else:
                df = pd.DataFrame()
            logging.info(f"[RuleAnalyzer] Loaded {len(df)} worker_order records.")
            return df
        except Exception as e:
            logging.warning(f"[RuleAnalyzer] Failed to load worker_order: {e}")
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Base Rule Tables Loading (for fallback)
    # ------------------------------------------------------------------

    def _load_base_rules(self) -> dict:
        """
        Load Base Rule Tables for fallback when markers have insufficient data.

        Loads:
        - freezer_rules: Marker → allowed dryers + batch quantities
        - "pump No.": Marker → allowed machines/ports
        - 配藥限制: Marker → allowed operators + quantities

        Returns:
            Dict with keys 'freezer_rules', 'pump_no', 'dispensing_limit'
            each mapping marker names to their allowed resources.
        """
        base_rules = {
            'freezer_rules': {},
            'pump_no': {},
            'dispensing_limit': {},
        }

        # Load freezer_rules
        try:
            result = self.db.execute(text("""
                SELECT * FROM "P01_formualte_schedule"."freezer_rules"
            """))
            rows = result.fetchall()
            if rows:
                columns = list(result.keys())
                df = pd.DataFrame(rows, columns=columns)
                for _, row in df.iterrows():
                    marker_name = str(row.get('Marker', row.get('marker', ''))).strip()
                    if marker_name:
                        base_rules['freezer_rules'][marker_name] = {
                            'dryers': [d.strip() for d in str(row.get('可用凍乾機', row.get('Lyophilizer', ''))).split(',') if d.strip()],
                            'quantity': row.get('數量', row.get('Quantity', None)),
                        }
        except Exception as e:
            logging.warning(f"[RuleAnalyzer] Failed to load freezer_rules: {e}")

        # Load "pump No."
        try:
            result = self.db.execute(text("""
                SELECT * FROM "P01_formualte_schedule"."pump No."
            """))
            rows = result.fetchall()
            if rows:
                columns = list(result.keys())
                df = pd.DataFrame(rows, columns=columns)
                for _, row in df.iterrows():
                    marker_name = str(row.get('Marker', row.get('marker', ''))).strip()
                    if marker_name:
                        machines = [m.strip() for m in str(row.get('Pump', row.get('pump', ''))).split(',') if m.strip()]
                        base_rules['pump_no'][marker_name] = machines
        except Exception as e:
            logging.warning(f"[RuleAnalyzer] Failed to load pump No.: {e}")

        # Load 配藥限制
        try:
            result = self.db.execute(text("""
                SELECT * FROM "schedule"."配藥限制"
            """))
            rows = result.fetchall()
            if rows:
                columns = list(result.keys())
                df = pd.DataFrame(rows, columns=columns)
                for _, row in df.iterrows():
                    name = str(row.get('Name', '')).strip()
                    if name:
                        operators = []
                        for i in range(1, 4):
                            op = str(row.get(f'配藥人-{i}', '')).strip()
                            if op and op.lower() != 'nan':
                                operators.append(op)
                        dryers = [d.strip() for d in str(row.get('可用凍乾機', '')).split(',') if d.strip()]
                        qty_raw = str(row.get('數量', '0')).strip()
                        base_rules['dispensing_limit'][name] = {
                            'operators': operators,
                            'dryers': dryers,
                            'quantity': qty_raw,
                            'pn': str(row.get('PN', '')).strip(),
                        }
        except Exception as e:
            logging.warning(f"[RuleAnalyzer] Failed to load 配藥限制: {e}")

        return base_rules

    # ------------------------------------------------------------------
    # Data Merging
    # ------------------------------------------------------------------

    def _merge_data_sources(
        self,
        df_schedule: pd.DataFrame,
        df_records: pd.DataFrame,
        df_work_orders: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Merge DropletSchedule and dropletRecord into a unified analysis DataFrame.

        Standardizes column names for consistent downstream analysis:
        - marker: Marker name
        - machine: Machine/Port used
        - dryer: Freeze dryer used
        - operator: Operator name
        - quantity: Production quantity
        - start_time: Start time
        - end_time: End time
        - drug_given_at: R&D drug given time
        - work_order: Work order number
        - date: Production date
        - lot: Lot/Batch number
        - notes: Special notes
        """
        merged_rows = []

        # Process DropletSchedule
        for _, row in df_schedule.iterrows():
            merged_rows.append({
                'marker': str(row.get('Marker', '')).strip(),
                'machine': str(row.get('Pump', '')).strip(),
                'dryer': str(row.get('Lyophilizer', '')).strip(),
                'operator': '',  # DropletSchedule doesn't have operator column directly
                'quantity': _safe_int(row.get('Quantity')),
                'start_time': None,
                'end_time': None,
                'drug_given_at': str(row.get('DrugGivenAt', '')).strip(),
                'work_order': str(row.get('WorkOrder', '')).strip(),
                'date': str(row.get('Date', '')).strip(),
                'lot': str(row.get('Lot', '')).strip(),
                'notes': '',
                'source': 'schedule',
            })

        # Process dropletRecord (actual production data — more reliable)
        for _, row in df_records.iterrows():
            merged_rows.append({
                'marker': str(row.get('marker', '')).strip(),
                'machine': str(row.get('titration_port', '')).strip(),
                'dryer': str(row.get('lyophilizer', '')).strip(),
                'operator': str(row.get('operator', '')).strip(),
                'quantity': _safe_int(row.get('quanity')),
                'start_time': str(row.get('start_time', '')).strip(),
                'end_time': str(row.get('end_time', '')).strip(),
                'drug_given_at': str(row.get('DrugGivenAt', '')).strip(),
                'work_order': str(row.get('WorkOrder', '')).strip(),
                'date': '',
                'lot': str(row.get('lot', '')).strip(),
                'notes': '',
                'source': 'record',
            })

        df_merged = pd.DataFrame(merged_rows)

        # Clean up empty strings to NaN for easier analysis
        df_merged.replace('', pd.NA, inplace=True)
        df_merged.replace('nan', pd.NA, inplace=True)
        df_merged.replace('None', pd.NA, inplace=True)

        return df_merged

    # ------------------------------------------------------------------
    # Single Marker Analysis
    # ------------------------------------------------------------------

    def _analyze_marker(
        self,
        marker_name: str,
        records: pd.DataFrame,
        base_rules: dict,
    ) -> MarkerRuleData:
        """
        分析單一 Marker 的規則模式。

        Extracts:
        - common_machines: Most frequently used Machine_Ports
        - common_dryers: Most frequently used Freeze_Dryers
        - common_operators: Most frequently used Operators
        - avg_start_time / avg_end_time: Average production times
        - avg_duration_minutes: Average duration
        - common_quantities: Common production quantities
        - special_notes: Any special rules from notes

        Args:
            marker_name: The Marker name to analyze.
            records: DataFrame of merged records for this Marker.
            base_rules: Base rule tables for fallback.

        Returns:
            MarkerRuleData with extracted patterns.
        """
        rule_data = MarkerRuleData(marker_name=marker_name)
        rule_data.record_count = len(records)

        # Determine data confidence
        if rule_data.record_count < MIN_RECORDS_THRESHOLD:
            rule_data.data_confidence = 'low'
            # Use base rules as defaults
            rule_data = self._apply_base_rule_defaults(rule_data, marker_name, base_rules)
            return rule_data
        elif rule_data.record_count < 10:
            rule_data.data_confidence = 'medium'
        else:
            rule_data.data_confidence = 'high'

        # Extract P/N (first non-null lot prefix or from base rules)
        pn = self._extract_pn(marker_name, records, base_rules)
        rule_data.pn = pn

        # Extract common machines
        machines = records['machine'].dropna().tolist()
        rule_data.common_machines = _top_values(machines, min_count=1)

        # Extract common dryers
        dryers = records['dryer'].dropna().tolist()
        rule_data.common_dryers = _top_values(dryers, min_count=1)

        # Extract common operators
        operators = records['operator'].dropna().tolist()
        rule_data.common_operators = _top_values(operators, min_count=1)

        # Extract average times
        rule_data.avg_start_time = _compute_avg_time(records['start_time'].dropna().tolist())
        rule_data.avg_end_time = _compute_avg_time(records['end_time'].dropna().tolist())

        # Compute average duration
        if rule_data.avg_start_time and rule_data.avg_end_time:
            start_minutes = rule_data.avg_start_time.hour * 60 + rule_data.avg_start_time.minute
            end_minutes = rule_data.avg_end_time.hour * 60 + rule_data.avg_end_time.minute
            if end_minutes > start_minutes:
                rule_data.avg_duration_minutes = end_minutes - start_minutes

        # Extract common quantities
        quantities = records['quantity'].dropna().tolist()
        rule_data.common_quantities = _top_int_values(quantities)

        # Extract special notes
        notes = records['notes'].dropna().tolist()
        rule_data.special_notes = list(set(str(n) for n in notes if str(n).strip()))

        # Extract drug_given_at patterns (for scheduling reference)
        drug_times = records['drug_given_at'].dropna().tolist()
        if drug_times:
            avg_drug_time = _compute_avg_time(drug_times)
            if avg_drug_time and not rule_data.avg_start_time:
                rule_data.avg_start_time = avg_drug_time

        return rule_data

    def _apply_base_rule_defaults(
        self,
        rule_data: MarkerRuleData,
        marker_name: str,
        base_rules: dict,
    ) -> MarkerRuleData:
        """
        Apply Base_Rule_Tables defaults for markers with insufficient data.

        When a Marker has fewer than MIN_RECORDS_THRESHOLD records, use
        freezer_rules, pump No., and 配藥限制 as default values.
        """
        # Try to find in dispensing_limit (配藥限制) by name
        disp_rule = base_rules['dispensing_limit'].get(marker_name, {})
        if disp_rule:
            rule_data.pn = disp_rule.get('pn')
            rule_data.common_operators = disp_rule.get('operators', [])
            rule_data.common_dryers = disp_rule.get('dryers', [])
            qty_raw = disp_rule.get('quantity', '')
            if qty_raw:
                rule_data.common_quantities = _parse_quantity_options(qty_raw)

        # Try freezer_rules
        freezer_rule = base_rules['freezer_rules'].get(marker_name, {})
        if freezer_rule:
            if freezer_rule.get('dryers') and not rule_data.common_dryers:
                rule_data.common_dryers = freezer_rule['dryers']

        # Try pump No.
        pump_rule = base_rules['pump_no'].get(marker_name, [])
        if pump_rule:
            rule_data.common_machines = pump_rule

        return rule_data

    def _extract_pn(
        self,
        marker_name: str,
        records: pd.DataFrame,
        base_rules: dict,
    ) -> Optional[str]:
        """Extract P/N for a marker from records or base rules."""
        # Try from base rules first (most reliable)
        disp_rule = base_rules['dispensing_limit'].get(marker_name, {})
        if disp_rule and disp_rule.get('pn'):
            return disp_rule['pn']

        # Try to extract from lot numbers (lot format: PN末三碼 + ...)
        # This is less reliable, so prefer base rules
        return None

    # ------------------------------------------------------------------
    # Database Writing
    # ------------------------------------------------------------------

    def _write_marker_rules(self, marker_rules: list[MarkerRuleData]) -> int:
        """
        Write analyzed marker rules to the marker_rule table.

        Uses UPSERT logic: update existing rules or insert new ones.

        Returns:
            Number of rules written.
        """
        count = 0
        now = datetime.utcnow()

        for rule_data in marker_rules:
            try:
                # Check if rule already exists
                existing = self.db.execute(
                    text("""
                        SELECT id FROM "P01_formualte_schedule".marker_rule
                        WHERE marker_name = :marker_name
                    """),
                    {"marker_name": rule_data.marker_name}
                ).fetchone()

                if existing:
                    # Update existing rule
                    self.db.execute(
                        text("""
                            UPDATE "P01_formualte_schedule".marker_rule
                            SET pn = :pn,
                                common_machines = :common_machines,
                                common_dryers = :common_dryers,
                                common_operators = :common_operators,
                                avg_start_time = :avg_start_time,
                                avg_end_time = :avg_end_time,
                                avg_duration_minutes = :avg_duration_minutes,
                                common_quantities = :common_quantities,
                                special_notes = :special_notes,
                                data_confidence = :data_confidence,
                                last_analyzed_at = :last_analyzed_at
                            WHERE marker_name = :marker_name
                        """),
                        {
                            "marker_name": rule_data.marker_name,
                            "pn": rule_data.pn,
                            "common_machines": _to_json_list(rule_data.common_machines),
                            "common_dryers": _to_json_list(rule_data.common_dryers),
                            "common_operators": _to_json_list(rule_data.common_operators),
                            "avg_start_time": rule_data.avg_start_time.isoformat() if rule_data.avg_start_time else None,
                            "avg_end_time": rule_data.avg_end_time.isoformat() if rule_data.avg_end_time else None,
                            "avg_duration_minutes": rule_data.avg_duration_minutes,
                            "common_quantities": _to_json_list(rule_data.common_quantities),
                            "special_notes": _to_json_list(rule_data.special_notes),
                            "data_confidence": rule_data.data_confidence,
                            "last_analyzed_at": now,
                        }
                    )
                else:
                    # Insert new rule
                    self.db.execute(
                        text("""
                            INSERT INTO "P01_formualte_schedule".marker_rule
                                (marker_name, pn, common_machines, common_dryers,
                                 common_operators, avg_start_time, avg_end_time,
                                 avg_duration_minutes, common_quantities, special_notes,
                                 data_confidence, base_rule_validated, last_analyzed_at)
                            VALUES
                                (:marker_name, :pn, :common_machines, :common_dryers,
                                 :common_operators, :avg_start_time, :avg_end_time,
                                 :avg_duration_minutes, :common_quantities, :special_notes,
                                 :data_confidence, false, :last_analyzed_at)
                        """),
                        {
                            "marker_name": rule_data.marker_name,
                            "pn": rule_data.pn,
                            "common_machines": _to_json_list(rule_data.common_machines),
                            "common_dryers": _to_json_list(rule_data.common_dryers),
                            "common_operators": _to_json_list(rule_data.common_operators),
                            "avg_start_time": rule_data.avg_start_time.isoformat() if rule_data.avg_start_time else None,
                            "avg_end_time": rule_data.avg_end_time.isoformat() if rule_data.avg_end_time else None,
                            "avg_duration_minutes": rule_data.avg_duration_minutes,
                            "common_quantities": _to_json_list(rule_data.common_quantities),
                            "special_notes": _to_json_list(rule_data.special_notes),
                            "data_confidence": rule_data.data_confidence,
                            "last_analyzed_at": now,
                        }
                    )
                count += 1
            except Exception as e:
                logging.error(f"[RuleAnalyzer] Failed to write marker_rule for {rule_data.marker_name}: {e}")

        # Commit all marker rules at once
        try:
            self.db.commit()
        except Exception as e:
            logging.error(f"[RuleAnalyzer] Failed to commit marker_rules: {e}")
            self.db.rollback()

        return count

    def _write_machine_capacity_rules(self, machines_seen: dict[str, dict]) -> int:
        """
        Write machine capacity rules to machine_capacity_rule table.

        Creates entries for each unique machine/dryer discovered during analysis.

        Returns:
            Number of rules written.
        """
        count = 0
        now = datetime.utcnow()

        for machine_id, info in machines_seen.items():
            if not machine_id:
                continue
            try:
                existing = self.db.execute(
                    text("""
                        SELECT id FROM "P01_formualte_schedule".machine_capacity_rule
                        WHERE machine_id = :machine_id
                    """),
                    {"machine_id": machine_id}
                ).fetchone()

                machine_type = info.get('type', 'port')
                # Dryers can handle multiple batches concurrently; ports are exclusive
                max_concurrent = 2 if machine_type == 'dryer' else 1

                if existing:
                    self.db.execute(
                        text("""
                            UPDATE "P01_formualte_schedule".machine_capacity_rule
                            SET machine_type = :machine_type,
                                max_concurrent = :max_concurrent,
                                last_updated_at = :last_updated_at
                            WHERE machine_id = :machine_id
                        """),
                        {
                            "machine_id": machine_id,
                            "machine_type": machine_type,
                            "max_concurrent": max_concurrent,
                            "last_updated_at": now,
                        }
                    )
                else:
                    self.db.execute(
                        text("""
                            INSERT INTO "P01_formualte_schedule".machine_capacity_rule
                                (machine_id, machine_type, max_concurrent,
                                 base_rule_validated, last_updated_at)
                            VALUES
                                (:machine_id, :machine_type, :max_concurrent,
                                 false, :last_updated_at)
                        """),
                        {
                            "machine_id": machine_id,
                            "machine_type": machine_type,
                            "max_concurrent": max_concurrent,
                            "last_updated_at": now,
                        }
                    )
                count += 1
            except Exception as e:
                logging.error(f"[RuleAnalyzer] Failed to write machine_capacity_rule for {machine_id}: {e}")

        try:
            self.db.commit()
        except Exception as e:
            logging.error(f"[RuleAnalyzer] Failed to commit machine_capacity_rules: {e}")
            self.db.rollback()

        return count

    def _write_operator_rules(self, operators_seen: dict[str, list[str]]) -> int:
        """
        Write operator rules to operator_rule table.

        Creates entries for each unique operator discovered during analysis,
        recording their capable_markers.

        Returns:
            Number of rules written.
        """
        count = 0
        now = datetime.utcnow()

        for operator_name, capable_markers in operators_seen.items():
            if not operator_name:
                continue
            try:
                existing = self.db.execute(
                    text("""
                        SELECT id FROM "P01_formualte_schedule".operator_rule
                        WHERE operator_name = :operator_name
                    """),
                    {"operator_name": operator_name}
                ).fetchone()

                # Deduplicate capable markers
                unique_markers = list(set(capable_markers))

                if existing:
                    self.db.execute(
                        text("""
                            UPDATE "P01_formualte_schedule".operator_rule
                            SET capable_markers = :capable_markers,
                                last_updated_at = :last_updated_at
                            WHERE operator_name = :operator_name
                        """),
                        {
                            "operator_name": operator_name,
                            "capable_markers": _to_json_list(unique_markers),
                            "last_updated_at": now,
                        }
                    )
                else:
                    self.db.execute(
                        text("""
                            INSERT INTO "P01_formualte_schedule".operator_rule
                                (operator_name, capable_markers, max_concurrent_tasks,
                                 base_rule_validated, last_updated_at)
                            VALUES
                                (:operator_name, :capable_markers, 1,
                                 false, :last_updated_at)
                        """),
                        {
                            "operator_name": operator_name,
                            "capable_markers": _to_json_list(unique_markers),
                            "last_updated_at": now,
                        }
                    )
                count += 1
            except Exception as e:
                logging.error(f"[RuleAnalyzer] Failed to write operator_rule for {operator_name}: {e}")

        try:
            self.db.commit()
        except Exception as e:
            logging.error(f"[RuleAnalyzer] Failed to commit operator_rules: {e}")
            self.db.rollback()

        return count


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _safe_int(value) -> Optional[int]:
    """Safely convert a value to int, returning None on failure."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(float(str(value).replace(',', '')))
    except (ValueError, TypeError):
        return None


def _top_values(values: list, min_count: int = 1, max_items: int = 5) -> list[str]:
    """
    Return the most common non-empty values from a list.

    Args:
        values: List of raw values (may contain None/NaN).
        min_count: Minimum occurrence count to be included.
        max_items: Maximum number of items to return.

    Returns:
        List of most common values sorted by frequency.
    """
    cleaned = [str(v).strip() for v in values
               if v is not None and str(v).strip() and str(v).strip().lower() != 'nan']
    if not cleaned:
        return []

    counter = Counter(cleaned)
    # Return items that appear at least min_count times, sorted by frequency
    common = counter.most_common(max_items)
    return [item for item, count in common if count >= min_count]


def _top_int_values(values: list, max_items: int = 5) -> list[int]:
    """
    Return the most common integer values from a list.

    Args:
        values: List of raw values.
        max_items: Maximum number of items to return.

    Returns:
        List of most common integer values sorted by frequency.
    """
    ints = []
    for v in values:
        parsed = _safe_int(v)
        if parsed is not None and parsed > 0:
            ints.append(parsed)

    if not ints:
        return []

    counter = Counter(ints)
    common = counter.most_common(max_items)
    return [item for item, _ in common]


def _compute_avg_time(time_strings: list) -> Optional[time]:
    """
    Compute the average time from a list of time strings.

    Supports formats: HH:MM, HH:MM:SS, and time objects.

    Returns:
        Average time as a datetime.time object, or None if no valid times.
    """
    total_minutes = 0
    count = 0

    for t in time_strings:
        minutes = _parse_time_to_minutes(t)
        if minutes is not None:
            total_minutes += minutes
            count += 1

    if count == 0:
        return None

    avg_minutes = int(total_minutes / count)
    hours = avg_minutes // 60
    mins = avg_minutes % 60

    # Clamp to valid time range (0-23:59)
    if hours >= 24:
        hours = 23
        mins = 59
    elif hours < 0:
        hours = 0
        mins = 0

    return time(hour=hours, minute=mins)


def _parse_time_to_minutes(t) -> Optional[int]:
    """Parse a time value (string or time object) to total minutes since midnight."""
    if t is None:
        return None

    if isinstance(t, time):
        return t.hour * 60 + t.minute

    t_str = str(t).strip()
    if not t_str or t_str.lower() == 'nan' or t_str.lower() == 'none':
        return None

    # Try HH:MM or HH:MM:SS format
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            parsed = datetime.strptime(t_str, fmt)
            return parsed.hour * 60 + parsed.minute
        except ValueError:
            continue

    # Try just a number (could be hours as float)
    try:
        hours_float = float(t_str)
        if 0 <= hours_float < 30:  # Allow up to 30 for late-night shifts
            return int(hours_float * 60)
    except ValueError:
        pass

    return None


def _parse_quantity_options(qty_raw: str) -> list[int]:
    """Parse a quantity string (e.g. '2700 or 11000') into a list of ints."""
    parts = qty_raw.lower().replace('or', ',').split(',')
    result = []
    for part in parts:
        val = _safe_int(part.strip())
        if val and val > 0:
            result.append(val)
    return result


def _to_json_list(values: list) -> str:
    """Convert a Python list to a JSON string for JSONB columns."""
    return json.dumps(values, ensure_ascii=False)
