"""
Batch Splitter — 根據配藥限制將需求拆分為批次

Responsibilities:
- Split MarkerDemand into batches based on 配藥限制 quantity limits
- Generate unique Batch numbers: PN末三碼 + 年末兩碼 + 週數(2碼) + 序號(0-9,A-Z)
- Generate Work Order numbers: TMRA + 年末兩碼 + 三碼月序號
- Ensure uniqueness across DropletSchedule, generated_schedule, dropletRecord
"""

import math
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MarkerDemand:
    """Input demand for a single Marker in a given week."""
    marker: str
    pn: str
    quantity: int
    priority: int = 1
    year: int = 2026
    week: int = 1
    month: int = 1


@dataclass
class Batch:
    """A single batch produced by the splitter."""
    marker: str
    pn: str
    quantity: int
    batch: str
    work_order: str
    priority: int = 1
    year: int = 2026
    week: int = 1
    month: int = 1


# ---------------------------------------------------------------------------
# Sequence characters: 0-9 then A-Z (36 total)
# ---------------------------------------------------------------------------

_SEQ_CHARS = [str(i) for i in range(10)] + [chr(c) for c in range(ord('A'), ord('Z') + 1)]


# ---------------------------------------------------------------------------
# BatchSplitter
# ---------------------------------------------------------------------------

class BatchSplitter:
    """根據配藥限制將需求拆分為批次，並產生唯一的 Batch 與工單編號。"""

    def __init__(self, db_session: Session):
        """
        Initialize BatchSplitter with a database session for existing
        batch/order lookups.

        Args:
            db_session: SQLAlchemy session for querying existing records.
        """
        self.db = db_session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def split_demands(
        self,
        demands: list[MarkerDemand],
        limits: dict[str, int],
    ) -> list[Batch]:
        """
        Split each MarkerDemand by 配藥限制 quantity into individual batches.

        Algorithm:
        1. Get batch_size from limits for the marker
        2. num_batches = ceil(demand_qty / batch_size)
        3. First N-1 batches get batch_size, last batch gets remainder
        4. If remainder == 0, last batch also gets batch_size
        5. If demand_qty < batch_size, single batch with demand_qty

        Args:
            demands: List of MarkerDemand objects to split.
            limits: Dict mapping marker name → max batch size from 配藥限制.

        Returns:
            List of Batch objects with generated batch numbers and work orders.
        """
        # Pre-load existing batch numbers for uniqueness checks
        existing_batches = self._load_existing_batches()

        # Track work order sequences per (year, month) to avoid duplicates
        # within the same split_demands call
        work_order_seq_cache: dict[tuple[int, int], int] = {}

        batches: list[Batch] = []

        for demand in demands:
            batch_size = limits.get(demand.marker, demand.quantity)
            # Guard against invalid batch_size
            if batch_size is None or batch_size <= 0:
                batch_size = demand.quantity

            # Calculate number of batches needed
            if demand.quantity <= 0:
                continue

            num_batches = math.ceil(demand.quantity / batch_size)

            for i in range(num_batches):
                # Determine quantity for this batch
                if i < num_batches - 1:
                    qty = batch_size
                else:
                    # Last batch gets the remainder
                    remainder = demand.quantity - batch_size * (num_batches - 1)
                    qty = remainder if remainder > 0 else batch_size

                # Generate unique batch number
                batch_num = self._generate_batch_number(
                    pn=demand.pn,
                    year=demand.year,
                    week=demand.week,
                    seq=i,
                    existing_batches=existing_batches,
                )
                # Add to existing set to prevent duplicates within same run
                existing_batches.add(batch_num)

                # Generate work order number
                cache_key = (demand.year, demand.month)
                if cache_key not in work_order_seq_cache:
                    work_order_seq_cache[cache_key] = self._get_existing_max_work_order_seq(
                        demand.year, demand.month
                    )
                work_order_seq_cache[cache_key] += 1
                work_order = self._generate_work_order(
                    year=demand.year,
                    month=demand.month,
                    existing_max_seq=work_order_seq_cache[cache_key] - 1,
                )
                # Update cache to track used sequence
                # (already incremented above, work_order uses existing_max_seq + 1)

                batches.append(Batch(
                    marker=demand.marker,
                    pn=demand.pn,
                    quantity=qty,
                    batch=batch_num,
                    work_order=work_order,
                    priority=demand.priority,
                    year=demand.year,
                    week=demand.week,
                    month=demand.month,
                ))

        return batches

    # ------------------------------------------------------------------
    # Batch Number Generation
    # ------------------------------------------------------------------

    def _generate_batch_number(
        self,
        pn: str,
        year: int,
        week: int,
        seq: int,
        existing_batches: set[str],
    ) -> str:
        """
        Generate a unique Batch number.

        Format: PN末三碼 + 年末兩碼 + 週數(2碼) + 序號(2碼, 00-ZZ)
        Example: 18026240A, 18026241B...

        Two-character sequence (36²=1296 combinations) to avoid exhaustion.
        """
        pn_suffix  = pn[-3:] if len(pn) >= 3 else pn.zfill(3)
        year_suffix = str(year % 100).zfill(2)
        week_str    = str(week).zfill(2)

        # Two-char sequence: first char from seq // 36, second from seq % 36
        total = len(_SEQ_CHARS) * len(_SEQ_CHARS)  # 1296

        for attempt in range(total):
            actual_seq = (seq + attempt) % total
            c1 = _SEQ_CHARS[actual_seq // len(_SEQ_CHARS)]
            c2 = _SEQ_CHARS[actual_seq % len(_SEQ_CHARS)]
            batch_num = f"{pn_suffix}{year_suffix}{week_str}{c1}{c2}"
            if batch_num not in existing_batches:
                return batch_num

        raise ValueError(
            f"All {total} batch number slots exhausted for "
            f"PN={pn}, year={year}, week={week}. Cannot generate unique batch number."
        )

    # ------------------------------------------------------------------
    # Work Order Generation
    # ------------------------------------------------------------------

    def _generate_work_order(
        self,
        year: int,
        month: int,
        existing_max_seq: int,
    ) -> str:
        """
        Generate a work order number.

        Format: TMRA + 年末兩碼 + 三碼月序號
        Example: TMRA26001, TMRA26002, ...

        The sequence is the next integer after existing_max_seq for the
        given year+month across DropletSchedule and generated_schedule.

        Args:
            year: Calendar year (e.g. 2026).
            month: Month number (1-12). Used for grouping but the sequence
                   is month-based (3-digit sequential within the month).
            existing_max_seq: The maximum existing sequence number for this
                             year/month combination. Next order will be +1.

        Returns:
            Work order string in TMRA format.
        """
        year_suffix = str(year % 100).zfill(2)
        next_seq = existing_max_seq + 1
        seq_str = str(next_seq).zfill(3)

        return f"TMRA{year_suffix}{seq_str}"

    # ------------------------------------------------------------------
    # Database lookups
    # ------------------------------------------------------------------

    def _load_existing_batches(self) -> set[str]:
        """
        Load all existing batch numbers from DropletSchedule,
        generated_schedule, and dropletRecord for uniqueness checking.

        Returns:
            Set of existing batch number strings.
        """
        existing: set[str] = set()

        # Query DropletSchedule (column: "Lot")
        try:
            result = self.db.execute(
                text("""
                    SELECT "Lot" FROM "P01_formualte_schedule"."DropletSchedule"
                    WHERE "Lot" IS NOT NULL AND "Lot" != ''
                """)
            )
            for row in result:
                existing.add(str(row[0]).strip())
        except Exception:
            self.db.rollback()

        # Query generated_schedule (column: batch)
        try:
            result = self.db.execute(
                text("""
                    SELECT batch FROM "P01_formualte_schedule".generated_schedule
                    WHERE batch IS NOT NULL AND batch != ''
                """)
            )
            for row in result:
                existing.add(str(row[0]).strip())
        except Exception:
            self.db.rollback()

        # Query dropletRecord (column: "Lot")
        try:
            result = self.db.execute(
                text("""
                    SELECT "Lot" FROM "P01_formualte_schedule"."dropletRecord"
                    WHERE "Lot" IS NOT NULL AND "Lot" != ''
                """)
            )
            for row in result:
                existing.add(str(row[0]).strip())
        except Exception:
            self.db.rollback()

        return existing

    def _get_existing_max_work_order_seq(self, year: int, month: int) -> int:
        """
        Query the maximum existing TMRA work order sequence number for a
        given year/month across DropletSchedule and generated_schedule.

        Work order format: TMRA + YY + NNN
        We extract NNN (the 3-digit sequence) from matching work orders.

        Args:
            year: Calendar year.
            month: Month number (currently the sequence is per-month based
                   on the TMRA + YY + NNN format from the design spec).

        Returns:
            Maximum existing sequence number (0 if none found).
        """
        year_suffix = str(year % 100).zfill(2)
        prefix = f"TMRA{year_suffix}"
        max_seq = 0

        # Query DropletSchedule
        try:
            result = self.db.execute(
                text("""
                    SELECT "WorkOrder" FROM "P01_formualte_schedule"."DropletSchedule"
                    WHERE "WorkOrder" IS NOT NULL
                      AND "WorkOrder" LIKE :prefix_pattern
                """),
                {"prefix_pattern": f"{prefix}%"}
            )
            for row in result:
                wo = str(row[0]).strip()
                seq_part = wo[len(prefix):]
                if seq_part.isdigit():
                    max_seq = max(max_seq, int(seq_part))
        except Exception:
            self.db.rollback()

        # Query generated_schedule
        try:
            result = self.db.execute(
                text("""
                    SELECT work_order FROM "P01_formualte_schedule".generated_schedule
                    WHERE work_order IS NOT NULL
                      AND work_order LIKE :prefix_pattern
                """),
                {"prefix_pattern": f"{prefix}%"}
            )
            for row in result:
                wo = str(row[0]).strip()
                seq_part = wo[len(prefix):]
                if seq_part.isdigit():
                    max_seq = max(max_seq, int(seq_part))
        except Exception:
            self.db.rollback()

        return max_seq
