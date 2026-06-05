"""
Unit tests for ai_schedule/batch_splitter.py

Tests the batch splitting logic, batch number generation, and work order
generation without requiring a real database connection.
"""

import sys
import os
from unittest.mock import MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock the mrpFlask_5 module before importing batch_splitter
# (since models.py imports from mrpFlask_5)
sys.modules['mrpFlask_5'] = MagicMock()

from ai_schedule.batch_splitter import (
    BatchSplitter,
    MarkerDemand,
    Batch,
    _SEQ_CHARS,
)


class FakeDBSession:
    """Fake DB session that returns empty results for all queries."""

    def execute(self, *args, **kwargs):
        return []


class TestBatchSplitterInit:
    """Test BatchSplitter initialization."""

    def test_init_stores_db_session(self):
        db = FakeDBSession()
        splitter = BatchSplitter(db)
        assert splitter.db is db


class TestSplitDemands:
    """Test the split_demands method."""

    def setup_method(self):
        self.splitter = BatchSplitter(FakeDBSession())

    def test_single_batch_when_demand_less_than_limit(self):
        """demand_qty < batch_size → single batch with demand_qty."""
        demands = [MarkerDemand(marker="tCREA-D", pn="5714400180", quantity=500,
                                year=2026, week=24, month=6)]
        limits = {"tCREA-D": 1300}

        batches = self.splitter.split_demands(demands, limits)

        assert len(batches) == 1
        assert batches[0].quantity == 500
        assert batches[0].marker == "tCREA-D"

    def test_exact_division(self):
        """demand_qty divisible by batch_size → equal batches."""
        demands = [MarkerDemand(marker="tCREA-D", pn="5714400180", quantity=3900,
                                year=2026, week=24, month=6)]
        limits = {"tCREA-D": 1300}

        batches = self.splitter.split_demands(demands, limits)

        assert len(batches) == 3
        assert all(b.quantity == 1300 for b in batches)

    def test_remainder_in_last_batch(self):
        """demand_qty not divisible → remainder in last batch."""
        demands = [MarkerDemand(marker="GGT", pn="5714400132", quantity=2600,
                                year=2026, week=24, month=6)]
        limits = {"GGT": 1000}

        batches = self.splitter.split_demands(demands, limits)

        assert len(batches) == 3
        assert batches[0].quantity == 1000
        assert batches[1].quantity == 1000
        assert batches[2].quantity == 600

    def test_sum_of_quantities_equals_demand(self):
        """Sum of all batch quantities must equal original demand."""
        demands = [MarkerDemand(marker="X", pn="1234567890", quantity=4567,
                                year=2026, week=10, month=3)]
        limits = {"X": 1300}

        batches = self.splitter.split_demands(demands, limits)

        total = sum(b.quantity for b in batches)
        assert total == 4567

    def test_no_batch_exceeds_limit(self):
        """No batch should exceed the configured limit."""
        demands = [MarkerDemand(marker="ABC", pn="1234567890", quantity=5000,
                                year=2026, week=5, month=2)]
        limits = {"ABC": 1300}

        batches = self.splitter.split_demands(demands, limits)

        for b in batches:
            assert b.quantity <= 1300

    def test_missing_limit_uses_full_demand(self):
        """When marker is not in limits dict, use full demand as batch_size."""
        demands = [MarkerDemand(marker="Unknown", pn="9999999999", quantity=2000,
                                year=2026, week=1, month=1)]
        limits = {}  # No limit for "Unknown"

        batches = self.splitter.split_demands(demands, limits)

        assert len(batches) == 1
        assert batches[0].quantity == 2000

    def test_zero_quantity_demand_skipped(self):
        """Demand with quantity 0 produces no batches."""
        demands = [MarkerDemand(marker="X", pn="1234567890", quantity=0,
                                year=2026, week=1, month=1)]
        limits = {"X": 1000}

        batches = self.splitter.split_demands(demands, limits)
        assert len(batches) == 0

    def test_multiple_demands(self):
        """Multiple demands produce correct number of total batches."""
        demands = [
            MarkerDemand(marker="A", pn="1110000001", quantity=2600,
                         year=2026, week=24, month=6),
            MarkerDemand(marker="B", pn="2220000002", quantity=1300,
                         year=2026, week=24, month=6),
        ]
        limits = {"A": 1300, "B": 1300}

        batches = self.splitter.split_demands(demands, limits)

        a_batches = [b for b in batches if b.marker == "A"]
        b_batches = [b for b in batches if b.marker == "B"]
        assert len(a_batches) == 2
        assert len(b_batches) == 1

    def test_priority_preserved(self):
        """Batch inherits priority from demand."""
        demands = [MarkerDemand(marker="X", pn="1234567890", quantity=1000,
                                priority=3, year=2026, week=1, month=1)]
        limits = {"X": 1000}

        batches = self.splitter.split_demands(demands, limits)
        assert batches[0].priority == 3


class TestGenerateBatchNumber:
    """Test the _generate_batch_number method."""

    def setup_method(self):
        self.splitter = BatchSplitter(FakeDBSession())

    def test_basic_format(self):
        """Batch number format: PN末三碼 + 年末兩碼 + 週數(2碼) + 序號."""
        result = self.splitter._generate_batch_number(
            pn="5714400180", year=2026, week=24, seq=0, existing_batches=set()
        )
        # PN last 3: "180", year last 2: "26", week: "24", seq 0 → "0"
        # Total: "180" + "26" + "24" + "0" = "18026240"
        assert result == "18026240"

    def test_seq_characters(self):
        """Sequence goes 0-9, A-Z."""
        for i, expected_char in enumerate(_SEQ_CHARS):
            result = self.splitter._generate_batch_number(
                pn="5714400180", year=2026, week=24, seq=i,
                existing_batches=set()
            )
            assert result.endswith(expected_char)

    def test_uniqueness_skips_existing(self):
        """If seq=0 batch already exists, increment to seq=1."""
        existing = {"18026240"}  # seq char '0' taken

        result = self.splitter._generate_batch_number(
            pn="5714400180", year=2026, week=24, seq=0,
            existing_batches=existing
        )
        assert result == "18026241"  # Next available: seq char '1'

    def test_uniqueness_skips_multiple(self):
        """Skip multiple taken sequences."""
        existing = {"18026240", "18026241", "18026242"}

        result = self.splitter._generate_batch_number(
            pn="5714400180", year=2026, week=24, seq=0,
            existing_batches=existing
        )
        assert result == "18026243"

    def test_short_pn_padded(self):
        """PN shorter than 3 chars is zero-padded."""
        result = self.splitter._generate_batch_number(
            pn="12", year=2026, week=1, seq=0, existing_batches=set()
        )
        # Padded to "012", year="26", week="01", seq="0"
        # = "012" + "26" + "01" + "0" = "01226010"
        assert result == "01226010"

    def test_week_zero_padded(self):
        """Week number < 10 is zero-padded to 2 digits."""
        result = self.splitter._generate_batch_number(
            pn="5714400180", year=2026, week=3, seq=0, existing_batches=set()
        )
        # "180" + "26" + "03" + "0" = "18026030"
        assert result == "18026030"

    def test_raises_when_exhausted(self):
        """ValueError raised when all 36 sequences are used."""
        # Format: "180" + "26" + "24" + char = "1802624" + char
        existing = {f"1802624{char}" for char in _SEQ_CHARS}

        try:
            self.splitter._generate_batch_number(
                pn="5714400180", year=2026, week=24, seq=0,
                existing_batches=existing
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "exhausted" in str(e)


class TestGenerateWorkOrder:
    """Test the _generate_work_order method."""

    def setup_method(self):
        self.splitter = BatchSplitter(FakeDBSession())

    def test_basic_format(self):
        """Work order format: TMRA + 年末兩碼 + 三碼月序號."""
        result = self.splitter._generate_work_order(
            year=2026, month=6, existing_max_seq=0
        )
        assert result == "TMRA26001"

    def test_increments_from_existing(self):
        """Sequence is existing_max_seq + 1."""
        result = self.splitter._generate_work_order(
            year=2026, month=6, existing_max_seq=5
        )
        assert result == "TMRA26006"

    def test_three_digit_padding(self):
        """Sequence is zero-padded to 3 digits."""
        result = self.splitter._generate_work_order(
            year=2026, month=1, existing_max_seq=99
        )
        assert result == "TMRA26100"

    def test_year_suffix(self):
        """Different years produce different suffixes."""
        result_26 = self.splitter._generate_work_order(year=2026, month=1, existing_max_seq=0)
        result_27 = self.splitter._generate_work_order(year=2027, month=1, existing_max_seq=0)

        assert result_26.startswith("TMRA26")
        assert result_27.startswith("TMRA27")


class TestBatchNumbersInSplitDemands:
    """Test that split_demands produces unique batch numbers."""

    def setup_method(self):
        self.splitter = BatchSplitter(FakeDBSession())

    def test_all_batch_numbers_unique(self):
        """All batches in a single split_demands call have unique numbers."""
        demands = [
            MarkerDemand(marker="A", pn="5714400180", quantity=5200,
                         year=2026, week=24, month=6),
        ]
        limits = {"A": 1300}

        batches = self.splitter.split_demands(demands, limits)

        batch_nums = [b.batch for b in batches]
        assert len(batch_nums) == len(set(batch_nums))

    def test_work_orders_monotonic(self):
        """Work orders within a call are monotonically increasing."""
        demands = [
            MarkerDemand(marker="A", pn="5714400180", quantity=3900,
                         year=2026, week=24, month=6),
        ]
        limits = {"A": 1300}

        batches = self.splitter.split_demands(demands, limits)

        for i in range(1, len(batches)):
            prev_seq = int(batches[i - 1].work_order[6:])
            curr_seq = int(batches[i].work_order[6:])
            assert curr_seq > prev_seq
