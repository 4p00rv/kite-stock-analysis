from dataclasses import asdict

from stocks_analysis.models import Holding


def _sample_holding(**overrides: object) -> Holding:
    defaults = {
        "instrument": "RELIANCE",
        "quantity": 10,
        "avg_cost": 2450.50,
        "ltp": 2500.00,
        "current_value": 25000.00,
        "pnl": 495.00,
        "pnl_percent": 2.02,
        "day_change": 15.00,
        "day_change_percent": 0.60,
    }
    defaults.update(overrides)
    return Holding(**defaults)


class TestHoldingCreation:
    def test_create_with_all_fields(self) -> None:
        h = _sample_holding()
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
        h = _sample_holding()
        assert h.exchange == "NSE"

    def test_custom_exchange(self) -> None:
        h = _sample_holding(exchange="BSE")
        assert h.exchange == "BSE"

    def test_asdict(self) -> None:
        h = _sample_holding()
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
        h = _sample_holding()
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
        h = _sample_holding()
        headers = Holding.csv_headers()
        row = h.to_csv_row()
        assert len(headers) == len(row)
        for header, value in zip(headers, row, strict=True):
            assert getattr(h, header) == value
