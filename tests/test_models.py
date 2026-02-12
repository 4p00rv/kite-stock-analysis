from dataclasses import asdict
from datetime import date

from stocks_analysis.models import (
    Holding,
    Snapshot,
    SnapshotHolding,
    Transaction,
)
from tests.conftest import make_holding


class TestHoldingCreation:
    def test_create_with_all_fields(self) -> None:
        h = make_holding()
        assert h.instrument == "RELIANCE"
        assert h.quantity == 10
        assert h.avg_cost == 2450.50
        assert h.ltp == 2500.00
        assert h.current_value == 25000.00
        assert h.pnl == 495.00
        assert h.pnl_percent == 2.02
        assert h.day_change == 15.00
        assert h.day_change_percent == 0.60
        assert h.exchange == "NSE"

    def test_default_exchange_is_nse(self) -> None:
        h = make_holding()
        assert h.exchange == "NSE"

    def test_custom_exchange(self) -> None:
        h = make_holding(exchange="BSE")
        assert h.exchange == "BSE"

    def test_asdict(self) -> None:
        h = make_holding()
        d = asdict(h)
        assert d["instrument"] == "RELIANCE"
        assert d["quantity"] == 10
        assert d["exchange"] == "NSE"
        assert len(d) == 10


class TestHoldingCsvMethods:
    def test_csv_headers(self) -> None:
        headers = Holding.csv_headers()
        assert headers == [
            "instrument",
            "quantity",
            "avg_cost",
            "ltp",
            "current_value",
            "pnl",
            "pnl_percent",
            "day_change",
            "day_change_percent",
            "exchange",
        ]

    def test_to_csv_row(self) -> None:
        h = make_holding()
        row = h.to_csv_row()
        assert row == [
            "RELIANCE",
            10,
            2450.50,
            2500.00,
            25000.00,
            495.00,
            2.02,
            15.00,
            0.60,
            "NSE",
        ]

    def test_to_csv_row_field_order_matches_headers(self) -> None:
        h = make_holding()
        headers = Holding.csv_headers()
        row = h.to_csv_row()
        assert len(headers) == len(row)
        for header, value in zip(headers, row, strict=True):
            assert getattr(h, header) == value


class TestHoldingFromCsvRow:
    def test_round_trip(self) -> None:
        """to_csv_row → from_csv_row should reproduce the original Holding."""
        original = make_holding()
        row = [str(v) for v in original.to_csv_row()]
        restored = Holding.from_csv_row(row)
        assert restored == original

    def test_all_fields_parsed(self) -> None:
        row = ["TCS", "5", "3200.0", "3350.5", "16752.5", "752.5", "4.7", "50.0", "1.52", "BSE"]
        h = Holding.from_csv_row(row)
        assert h.instrument == "TCS"
        assert h.quantity == 5
        assert h.avg_cost == 3200.0
        assert h.ltp == 3350.5
        assert h.current_value == 16752.5
        assert h.pnl == 752.5
        assert h.pnl_percent == 4.7
        assert h.day_change == 50.0
        assert h.day_change_percent == 1.52
        assert h.exchange == "BSE"

    def test_default_exchange_when_column_missing(self) -> None:
        row = ["RELIANCE", "10", "2450.5", "2500.0", "25000.0", "495.0", "2.02", "15.0", "0.6"]
        h = Holding.from_csv_row(row)
        assert h.exchange == "NSE"


class TestSnapshotHolding:
    def test_create(self) -> None:
        sh = SnapshotHolding(
            date=date(2025, 1, 15),
            instrument="RELIANCE",
            quantity=10,
            avg_cost=2450.50,
            ltp=2500.00,
            current_value=25000.00,
            pnl=495.00,
            pnl_percent=2.02,
            day_change=15.00,
            day_change_percent=0.60,
            exchange="NSE",
        )
        assert sh.date == date(2025, 1, 15)
        assert sh.instrument == "RELIANCE"
        assert sh.quantity == 10
        assert sh.exchange == "NSE"

    def test_from_sheet_row(self) -> None:
        row = [
            "2025-01-15",
            "RELIANCE",
            "10",
            "2450.5",
            "2500.0",
            "25000.0",
            "495.0",
            "2.02",
            "15.0",
            "0.6",
            "NSE",
        ]
        sh = SnapshotHolding.from_sheet_row(row)
        assert sh.date == date(2025, 1, 15)
        assert sh.instrument == "RELIANCE"
        assert sh.quantity == 10
        assert sh.avg_cost == 2450.5
        assert sh.exchange == "NSE"

    def test_from_sheet_row_default_exchange(self) -> None:
        row = [
            "2025-01-15",
            "RELIANCE",
            "10",
            "2450.5",
            "2500.0",
            "25000.0",
            "495.0",
            "2.02",
            "15.0",
            "0.6",
        ]
        sh = SnapshotHolding.from_sheet_row(row)
        assert sh.exchange == "NSE"


class TestSnapshot:
    def test_create(self) -> None:
        sh = SnapshotHolding(
            date=date(2025, 1, 15),
            instrument="RELIANCE",
            quantity=10,
            avg_cost=2450.50,
            ltp=2500.00,
            current_value=25000.00,
            pnl=495.00,
            pnl_percent=2.02,
            day_change=15.00,
            day_change_percent=0.60,
            exchange="NSE",
        )
        snap = Snapshot(date=date(2025, 1, 15), holdings=[sh])
        assert snap.date == date(2025, 1, 15)
        assert len(snap.holdings) == 1
        assert snap.holdings[0].instrument == "RELIANCE"


class TestTransaction:
    def test_buy(self) -> None:
        t = Transaction(
            date=date(2025, 1, 15),
            instrument="RELIANCE",
            type="BUY",
            quantity=10,
            price=2450.50,
            amount=-24505.00,
        )
        assert t.type == "BUY"
        assert t.amount < 0  # cash out

    def test_sell(self) -> None:
        t = Transaction(
            date=date(2025, 2, 1),
            instrument="RELIANCE",
            type="SELL",
            quantity=5,
            price=2600.00,
            amount=13000.00,
        )
        assert t.type == "SELL"
        assert t.amount > 0  # cash in
