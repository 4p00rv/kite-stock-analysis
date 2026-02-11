from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from stocks_analysis.analysis import (
    build_daily_portfolio_series,
    infer_transactions,
    parse_snapshots_from_rows,
    run_analysis,
)
from stocks_analysis.models import Snapshot, SnapshotHolding, Transaction


class TestParseSnapshotsFromRows:
    def test_single_date_single_holding(self) -> None:
        rows = [
            [
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
            ],
        ]
        snapshots = parse_snapshots_from_rows(rows)
        assert len(snapshots) == 1
        assert snapshots[0].date == date(2025, 1, 15)
        assert len(snapshots[0].holdings) == 1
        assert snapshots[0].holdings[0].instrument == "RELIANCE"

    def test_single_date_multiple_holdings(self) -> None:
        rows = [
            [
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
            ],
            [
                "2025-01-15",
                "TCS",
                "5",
                "3200.0",
                "3350.0",
                "16750.0",
                "750.0",
                "4.69",
                "50.0",
                "1.52",
                "NSE",
            ],
        ]
        snapshots = parse_snapshots_from_rows(rows)
        assert len(snapshots) == 1
        assert len(snapshots[0].holdings) == 2

    def test_multiple_dates(self) -> None:
        rows = [
            [
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
            ],
            [
                "2025-01-20",
                "RELIANCE",
                "10",
                "2450.5",
                "2550.0",
                "25500.0",
                "995.0",
                "4.06",
                "50.0",
                "2.0",
                "NSE",
            ],
            [
                "2025-01-20",
                "TCS",
                "5",
                "3200.0",
                "3350.0",
                "16750.0",
                "750.0",
                "4.69",
                "50.0",
                "1.52",
                "NSE",
            ],
        ]
        snapshots = parse_snapshots_from_rows(rows)
        assert len(snapshots) == 2
        assert snapshots[0].date == date(2025, 1, 15)
        assert len(snapshots[0].holdings) == 1
        assert snapshots[1].date == date(2025, 1, 20)
        assert len(snapshots[1].holdings) == 2

    def test_sorted_by_date(self) -> None:
        rows = [
            [
                "2025-01-20",
                "TCS",
                "5",
                "3200.0",
                "3350.0",
                "16750.0",
                "750.0",
                "4.69",
                "50.0",
                "1.52",
                "NSE",
            ],
            [
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
            ],
        ]
        snapshots = parse_snapshots_from_rows(rows)
        assert len(snapshots) == 2
        assert snapshots[0].date == date(2025, 1, 15)
        assert snapshots[1].date == date(2025, 1, 20)

    def test_empty_rows(self) -> None:
        snapshots = parse_snapshots_from_rows([])
        assert snapshots == []


def _make_snapshot_holding(
    dt: date,
    instrument: str = "RELIANCE",
    quantity: int = 10,
    avg_cost: float = 2450.5,
    ltp: float = 2500.0,
) -> SnapshotHolding:
    return SnapshotHolding(
        date=dt,
        instrument=instrument,
        quantity=quantity,
        avg_cost=avg_cost,
        ltp=ltp,
        current_value=ltp * quantity,
        pnl=(ltp - avg_cost) * quantity,
        pnl_percent=(ltp - avg_cost) / avg_cost * 100,
        day_change=0.0,
        day_change_percent=0.0,
    )


class TestInferTransactions:
    def test_first_snapshot_generates_initial_buys(self) -> None:
        """First snapshot should generate BUY for every holding at avg_cost."""
        snap = Snapshot(
            date=date(2025, 1, 15),
            holdings=[_make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 2450.5)],
        )
        txns = infer_transactions([snap])
        assert len(txns) == 1
        assert txns[0].type == "BUY"
        assert txns[0].instrument == "RELIANCE"
        assert txns[0].quantity == 10
        assert txns[0].price == 2450.5
        assert txns[0].amount == pytest.approx(-24505.0)

    def test_new_instrument_appears(self) -> None:
        """Instrument appearing in second snapshot → BUY."""
        snap1 = Snapshot(
            date=date(2025, 1, 15),
            holdings=[_make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 2450.5)],
        )
        snap2 = Snapshot(
            date=date(2025, 1, 20),
            holdings=[
                _make_snapshot_holding(date(2025, 1, 20), "RELIANCE", 10, 2450.5, 2550.0),
                _make_snapshot_holding(date(2025, 1, 20), "TCS", 5, 3200.0, 3350.0),
            ],
        )
        txns = infer_transactions([snap1, snap2])
        tcs_txns = [t for t in txns if t.instrument == "TCS"]
        assert len(tcs_txns) == 1
        assert tcs_txns[0].type == "BUY"
        assert tcs_txns[0].quantity == 5
        assert tcs_txns[0].price == 3200.0
        assert tcs_txns[0].amount == pytest.approx(-16000.0)

    def test_instrument_disappears(self) -> None:
        """Instrument disappearing from second snapshot → SELL at previous LTP."""
        snap1 = Snapshot(
            date=date(2025, 1, 15),
            holdings=[
                _make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 2450.5, 2500.0),
                _make_snapshot_holding(date(2025, 1, 15), "TCS", 5, 3200.0, 3350.0),
            ],
        )
        snap2 = Snapshot(
            date=date(2025, 1, 20),
            holdings=[
                _make_snapshot_holding(date(2025, 1, 20), "RELIANCE", 10, 2450.5, 2550.0),
            ],
        )
        txns = infer_transactions([snap1, snap2])
        tcs_sells = [t for t in txns if t.instrument == "TCS" and t.type == "SELL"]
        assert len(tcs_sells) == 1
        assert tcs_sells[0].quantity == 5
        assert tcs_sells[0].price == 3350.0  # previous LTP
        assert tcs_sells[0].amount == pytest.approx(16750.0)

    def test_quantity_increases(self) -> None:
        """Quantity increase → BUY additional at computed price."""
        snap1 = Snapshot(
            date=date(2025, 1, 15),
            holdings=[_make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 2450.5, 2500.0)],
        )
        # avg_cost changed to 2460.0 after buying 5 more
        snap2 = Snapshot(
            date=date(2025, 1, 20),
            holdings=[_make_snapshot_holding(date(2025, 1, 20), "RELIANCE", 15, 2460.0, 2550.0)],
        )
        txns = infer_transactions([snap1, snap2])
        buys = [t for t in txns if t.date == date(2025, 1, 20)]
        assert len(buys) == 1
        assert buys[0].type == "BUY"
        assert buys[0].quantity == 5
        # price = (2460*15 - 2450.5*10) / 5 = (36900 - 24505) / 5 = 2479.0
        assert buys[0].price == pytest.approx(2479.0)
        assert buys[0].amount == pytest.approx(-2479.0 * 5)

    def test_quantity_decreases(self) -> None:
        """Quantity decrease → SELL at previous LTP."""
        snap1 = Snapshot(
            date=date(2025, 1, 15),
            holdings=[_make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 2450.5, 2500.0)],
        )
        snap2 = Snapshot(
            date=date(2025, 1, 20),
            holdings=[_make_snapshot_holding(date(2025, 1, 20), "RELIANCE", 7, 2450.5, 2550.0)],
        )
        txns = infer_transactions([snap1, snap2])
        sells = [t for t in txns if t.date == date(2025, 1, 20)]
        assert len(sells) == 1
        assert sells[0].type == "SELL"
        assert sells[0].quantity == 3
        assert sells[0].price == 2500.0  # previous LTP
        assert sells[0].amount == pytest.approx(7500.0)

    def test_unchanged_position_no_transaction(self) -> None:
        """Same quantity + avg_cost → no transaction generated."""
        snap1 = Snapshot(
            date=date(2025, 1, 15),
            holdings=[_make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 2450.5, 2500.0)],
        )
        snap2 = Snapshot(
            date=date(2025, 1, 20),
            holdings=[_make_snapshot_holding(date(2025, 1, 20), "RELIANCE", 10, 2450.5, 2550.0)],
        )
        txns = infer_transactions([snap1, snap2])
        # Only initial BUY from snap1, no transactions from snap2
        assert len(txns) == 1
        assert txns[0].date == date(2025, 1, 15)

    def test_negative_estimated_price_falls_back_to_avg_cost(self) -> None:
        """If computed price is negative, fall back to curr.avg_cost."""
        snap1 = Snapshot(
            date=date(2025, 1, 15),
            holdings=[_make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 5000.0, 5100.0)],
        )
        # Extreme case: avg_cost dropped a lot with more quantity
        # price = (100*12 - 5000*10) / 2 = (1200 - 50000) / 2 = negative
        snap2 = Snapshot(
            date=date(2025, 1, 20),
            holdings=[_make_snapshot_holding(date(2025, 1, 20), "RELIANCE", 12, 100.0, 150.0)],
        )
        txns = infer_transactions([snap1, snap2])
        additional_buy = [t for t in txns if t.date == date(2025, 1, 20)]
        assert len(additional_buy) == 1
        assert additional_buy[0].price == 100.0  # falls back to curr.avg_cost

    def test_empty_snapshots(self) -> None:
        txns = infer_transactions([])
        assert txns == []

    def test_single_snapshot_multiple_holdings(self) -> None:
        snap = Snapshot(
            date=date(2025, 1, 15),
            holdings=[
                _make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 2450.5),
                _make_snapshot_holding(date(2025, 1, 15), "TCS", 5, 3200.0),
            ],
        )
        txns = infer_transactions([snap])
        assert len(txns) == 2
        assert all(t.type == "BUY" for t in txns)


class TestBuildDailyPortfolioSeries:
    def test_single_holding_with_prices(self) -> None:
        """Single holding, market prices available for all days."""
        snapshots = [
            Snapshot(
                date=date(2025, 1, 15),
                holdings=[
                    _make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 2450.5, 2500.0)
                ],
            ),
        ]
        txns = [
            Transaction(date(2025, 1, 15), "RELIANCE", "BUY", 10, 2450.5, -24505.0),
        ]
        prices = {
            "RELIANCE.NS": {
                date(2025, 1, 15): 2500.0,
                date(2025, 1, 16): 2520.0,
                date(2025, 1, 17): 2510.0,
            }
        }
        series = build_daily_portfolio_series(
            snapshots, txns, prices, date(2025, 1, 15), date(2025, 1, 17)
        )
        assert len(series) == 3
        assert series[0].date == date(2025, 1, 15)
        assert series[0].total_value == pytest.approx(25000.0)  # 10 * 2500
        assert series[1].total_value == pytest.approx(25200.0)  # 10 * 2520
        assert series[2].total_value == pytest.approx(25100.0)  # 10 * 2510

    def test_daily_return_calculation(self) -> None:
        snapshots = [
            Snapshot(
                date=date(2025, 1, 15),
                holdings=[
                    _make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 2450.5, 2500.0)
                ],
            ),
        ]
        txns = [
            Transaction(date(2025, 1, 15), "RELIANCE", "BUY", 10, 2450.5, -24505.0),
        ]
        prices = {
            "RELIANCE.NS": {
                date(2025, 1, 15): 2500.0,
                date(2025, 1, 16): 2550.0,
            }
        }
        series = build_daily_portfolio_series(
            snapshots, txns, prices, date(2025, 1, 15), date(2025, 1, 16)
        )
        assert series[0].daily_return == 0.0  # first day
        assert series[1].daily_return == pytest.approx(500.0 / 25000.0)

    def test_forward_fill_gaps(self) -> None:
        """Missing price dates should forward-fill from last known price."""
        snapshots = [
            Snapshot(
                date=date(2025, 1, 15),
                holdings=[
                    _make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 2450.5, 2500.0)
                ],
            ),
        ]
        txns = [
            Transaction(date(2025, 1, 15), "RELIANCE", "BUY", 10, 2450.5, -24505.0),
        ]
        # Gap on Jan 16 (weekend/holiday)
        prices = {
            "RELIANCE.NS": {
                date(2025, 1, 15): 2500.0,
                date(2025, 1, 17): 2510.0,
            }
        }
        series = build_daily_portfolio_series(
            snapshots, txns, prices, date(2025, 1, 15), date(2025, 1, 17)
        )
        assert len(series) == 3
        # Jan 16 should forward-fill from Jan 15
        assert series[1].total_value == pytest.approx(25000.0)

    def test_multi_holding(self) -> None:
        snapshots = [
            Snapshot(
                date=date(2025, 1, 15),
                holdings=[
                    _make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 2450.5, 2500.0),
                    _make_snapshot_holding(date(2025, 1, 15), "TCS", 5, 3200.0, 3350.0),
                ],
            ),
        ]
        txns = [
            Transaction(date(2025, 1, 15), "RELIANCE", "BUY", 10, 2450.5, -24505.0),
            Transaction(date(2025, 1, 15), "TCS", "BUY", 5, 3200.0, -16000.0),
        ]
        prices = {
            "RELIANCE.NS": {date(2025, 1, 15): 2500.0},
            "TCS.NS": {date(2025, 1, 15): 3350.0},
        }
        series = build_daily_portfolio_series(
            snapshots, txns, prices, date(2025, 1, 15), date(2025, 1, 15)
        )
        assert len(series) == 1
        assert series[0].total_value == pytest.approx(25000.0 + 16750.0)

    def test_transaction_mid_series(self) -> None:
        """BUY additional shares mid-series should reflect in values."""
        snapshots = [
            Snapshot(
                date=date(2025, 1, 15),
                holdings=[
                    _make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 2450.5, 2500.0)
                ],
            ),
            Snapshot(
                date=date(2025, 1, 17),
                holdings=[
                    _make_snapshot_holding(date(2025, 1, 17), "RELIANCE", 15, 2460.0, 2510.0)
                ],
            ),
        ]
        txns = [
            Transaction(date(2025, 1, 15), "RELIANCE", "BUY", 10, 2450.5, -24505.0),
            Transaction(date(2025, 1, 17), "RELIANCE", "BUY", 5, 2479.0, -12395.0),
        ]
        prices = {
            "RELIANCE.NS": {
                date(2025, 1, 15): 2500.0,
                date(2025, 1, 16): 2520.0,
                date(2025, 1, 17): 2510.0,
            }
        }
        series = build_daily_portfolio_series(
            snapshots, txns, prices, date(2025, 1, 15), date(2025, 1, 17)
        )
        assert len(series) == 3
        assert series[0].total_value == pytest.approx(25000.0)  # 10 * 2500
        assert series[1].total_value == pytest.approx(25200.0)  # 10 * 2520
        assert series[2].total_value == pytest.approx(37650.0)  # 15 * 2510

    def test_ltp_fallback_when_no_market_price(self) -> None:
        """When market price is unavailable, fall back to snapshot LTP."""
        snapshots = [
            Snapshot(
                date=date(2025, 1, 15),
                holdings=[
                    _make_snapshot_holding(date(2025, 1, 15), "RELIANCE", 10, 2450.5, 2500.0)
                ],
            ),
        ]
        txns = [
            Transaction(date(2025, 1, 15), "RELIANCE", "BUY", 10, 2450.5, -24505.0),
        ]
        # No market prices at all
        prices: dict[str, dict[date, float]] = {}
        series = build_daily_portfolio_series(
            snapshots, txns, prices, date(2025, 1, 15), date(2025, 1, 15)
        )
        assert len(series) == 1
        # Should fall back to LTP from snapshot (2500.0)
        assert series[0].total_value == pytest.approx(25000.0)

    def test_empty_inputs(self) -> None:
        series = build_daily_portfolio_series([], [], {}, date(2025, 1, 15), date(2025, 1, 15))
        assert series == []


class TestRunAnalysis:
    def _make_rows(self) -> list[list[str]]:
        """Build mock Holdings sheet rows spanning multiple dates."""
        return [
            [
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
            ],
            [
                "2025-01-15",
                "TCS",
                "5",
                "3200.0",
                "3350.0",
                "16750.0",
                "750.0",
                "4.69",
                "50.0",
                "1.52",
                "NSE",
            ],
            [
                "2025-01-20",
                "RELIANCE",
                "10",
                "2450.5",
                "2550.0",
                "25500.0",
                "995.0",
                "4.06",
                "50.0",
                "2.0",
                "NSE",
            ],
            [
                "2025-01-20",
                "TCS",
                "5",
                "3200.0",
                "3400.0",
                "17000.0",
                "1000.0",
                "6.25",
                "50.0",
                "1.49",
                "NSE",
            ],
        ]

    def _make_prices(self) -> dict[str, dict[date, float]]:
        """Prices for RELIANCE.NS, TCS.NS, and ^NSEI covering Jan 15-20."""
        dates = [date(2025, 1, d) for d in range(15, 21)]
        return {
            "RELIANCE.NS": {d: 2500.0 + (d.day - 15) * 10 for d in dates},
            "TCS.NS": {d: 3350.0 + (d.day - 15) * 10 for d in dates},
            "^NSEI": {d: 22000.0 + (d.day - 15) * 50 for d in dates},
        }

    @patch("stocks_analysis.analysis.MarketDataClient")
    def test_run_analysis_returns_result(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        prices = self._make_prices()
        mock_client.get_multiple_prices.return_value = {
            k: v for k, v in prices.items() if k != "^NSEI"
        }
        mock_client.get_benchmark_prices.return_value = prices["^NSEI"]

        rows = self._make_rows()
        result, daily_series, transactions = run_analysis(rows)

        assert result.start_date == date(2025, 1, 15)
        assert result.end_date == date(2025, 1, 20)
        assert isinstance(result.xirr, float)
        assert isinstance(result.sharpe, float)
        assert isinstance(result.max_drawdown, float)
        assert isinstance(result.herfindahl, float)
        assert len(daily_series) > 0
        assert len(transactions) > 0

    @patch("stocks_analysis.analysis.MarketDataClient")
    def test_run_analysis_empty_rows(self, mock_client_cls: MagicMock) -> None:
        result, daily_series, transactions = run_analysis([])
        assert result.xirr == 0.0
        assert result.sharpe == 0.0
        assert daily_series == []
        assert transactions == []
