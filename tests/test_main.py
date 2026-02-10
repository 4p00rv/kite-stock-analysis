import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

from stocks_analysis.main import run, save_holdings_to_csv
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


class TestSaveHoldingsToCsv:
    def test_creates_csv_file(self, tmp_path: Path) -> None:
        holdings = [_sample_holding()]
        path = save_holdings_to_csv(holdings, output_dir=tmp_path)
        assert path.exists()
        assert path.suffix == ".csv"

    def test_filename_has_timestamp(self, tmp_path: Path) -> None:
        holdings = [_sample_holding()]
        path = save_holdings_to_csv(holdings, output_dir=tmp_path)
        assert path.name.startswith("holdings_")
        assert path.name.endswith(".csv")

    def test_csv_has_correct_headers(self, tmp_path: Path) -> None:
        holdings = [_sample_holding()]
        path = save_holdings_to_csv(holdings, output_dir=tmp_path)
        with open(path) as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert headers == Holding.csv_headers()

    def test_csv_row_count(self, tmp_path: Path) -> None:
        holdings = [_sample_holding(), _sample_holding(instrument="TCS")]
        path = save_holdings_to_csv(holdings, output_dir=tmp_path)
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 3  # 1 header + 2 data rows

    def test_csv_row_values(self, tmp_path: Path) -> None:
        holdings = [_sample_holding()]
        path = save_holdings_to_csv(holdings, output_dir=tmp_path)
        with open(path) as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            row = next(reader)
        assert row[0] == "RELIANCE"
        assert row[1] == "10"
        assert row[9] == "NSE"

    def test_auto_creates_output_dir(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "nested" / "output"
        holdings = [_sample_holding()]
        path = save_holdings_to_csv(holdings, output_dir=output_dir)
        assert path.exists()
        assert output_dir.exists()

    def test_empty_holdings_produces_header_only(self, tmp_path: Path) -> None:
        path = save_holdings_to_csv([], output_dir=tmp_path)
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0] == Holding.csv_headers()


class TestRun:
    @patch("stocks_analysis.main.create_kite_fetcher")
    @patch("stocks_analysis.main.save_holdings_to_csv")
    def test_calls_methods_in_order(
        self, mock_save: MagicMock, mock_create: MagicMock, tmp_path: Path
    ) -> None:
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_holdings.return_value = [
            Holding(
                instrument="RELIANCE",
                quantity=10,
                avg_cost=2450.50,
                ltp=2500.00,
                current_value=25000.00,
                pnl=495.00,
                pnl_percent=2.02,
                day_change=15.00,
                day_change_percent=0.60,
            )
        ]
        mock_create.return_value.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_create.return_value.__exit__ = MagicMock(return_value=False)
        mock_save.return_value = tmp_path / "holdings_test.csv"

        run()

        mock_fetcher.open_login_page.assert_called_once()
        mock_fetcher.wait_for_login.assert_called_once()
        mock_fetcher.navigate_to_holdings.assert_called_once()
        mock_fetcher.fetch_holdings.assert_called_once()
        mock_save.assert_called_once()

    @patch("stocks_analysis.main.create_kite_fetcher")
    @patch("stocks_analysis.main.save_holdings_to_csv")
    def test_passes_holdings_to_save(
        self, mock_save: MagicMock, mock_create: MagicMock, tmp_path: Path
    ) -> None:
        mock_fetcher = MagicMock()
        holdings = [
            Holding(
                instrument="TCS",
                quantity=5,
                avg_cost=3200.00,
                ltp=3300.00,
                current_value=16500.00,
                pnl=500.00,
                pnl_percent=3.13,
                day_change=50.00,
                day_change_percent=1.54,
            )
        ]
        mock_fetcher.fetch_holdings.return_value = holdings
        mock_create.return_value.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_create.return_value.__exit__ = MagicMock(return_value=False)
        mock_save.return_value = tmp_path / "holdings_test.csv"

        run()

        mock_save.assert_called_once_with(holdings)
