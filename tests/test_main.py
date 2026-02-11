import csv
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from stocks_analysis.main import (
    _extract_date_from_filename,
    _scrape,
    load_holdings_from_csv,
    run,
    save_holdings_to_csv,
)
from stocks_analysis.models import Holding
from tests.conftest import make_holding


class TestSaveHoldingsToCsv:
    def test_creates_csv_file(self, tmp_path: Path) -> None:
        holdings = [make_holding()]
        path = save_holdings_to_csv(holdings, output_dir=tmp_path)
        assert path.exists()
        assert path.suffix == ".csv"

    def test_filename_has_timestamp(self, tmp_path: Path) -> None:
        holdings = [make_holding()]
        path = save_holdings_to_csv(holdings, output_dir=tmp_path)
        assert path.name.startswith("holdings_")
        assert path.name.endswith(".csv")

    def test_csv_has_correct_headers(self, tmp_path: Path) -> None:
        holdings = [make_holding()]
        path = save_holdings_to_csv(holdings, output_dir=tmp_path)
        with open(path) as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert headers == Holding.csv_headers()

    def test_csv_row_count(self, tmp_path: Path) -> None:
        holdings = [make_holding(), make_holding(instrument="TCS")]
        path = save_holdings_to_csv(holdings, output_dir=tmp_path)
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 3  # 1 header + 2 data rows

    def test_csv_row_values(self, tmp_path: Path) -> None:
        holdings = [make_holding()]
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
        holdings = [make_holding()]
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


class TestLoadHoldingsFromCsv:
    def test_reads_csv_and_returns_holdings(self, tmp_path: Path) -> None:
        holdings = [make_holding(), make_holding(instrument="TCS")]
        csv_path = save_holdings_to_csv(holdings, output_dir=tmp_path)
        loaded = load_holdings_from_csv(csv_path)
        assert len(loaded) == 2
        assert loaded[0].instrument == "RELIANCE"
        assert loaded[1].instrument == "TCS"

    def test_round_trip_preserves_data(self, tmp_path: Path) -> None:
        original = [make_holding()]
        csv_path = save_holdings_to_csv(original, output_dir=tmp_path)
        loaded = load_holdings_from_csv(csv_path)
        assert loaded == original

    def test_empty_csv_returns_empty_list(self, tmp_path: Path) -> None:
        csv_path = save_holdings_to_csv([], output_dir=tmp_path)
        loaded = load_holdings_from_csv(csv_path)
        assert loaded == []


class TestScrape:
    @patch("stocks_analysis.main._upload_to_sheets_if_configured")
    @patch("stocks_analysis.main.create_kite_fetcher")
    @patch("stocks_analysis.main.save_holdings_to_csv")
    def test_calls_methods_in_order(
        self, mock_save: MagicMock, mock_create: MagicMock, mock_upload: MagicMock, tmp_path: Path
    ) -> None:
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_holdings.return_value = [make_holding()]
        mock_create.return_value.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_create.return_value.__exit__ = MagicMock(return_value=False)
        mock_save.return_value = tmp_path / "holdings_test.csv"

        _scrape()

        mock_fetcher.open_login_page.assert_called_once()
        mock_fetcher.wait_for_login.assert_called_once()
        mock_fetcher.navigate_to_holdings.assert_called_once()
        mock_fetcher.fetch_holdings.assert_called_once()
        mock_save.assert_called_once()

    @patch("stocks_analysis.main._upload_to_sheets_if_configured")
    @patch("stocks_analysis.main.create_kite_fetcher")
    @patch("stocks_analysis.main.save_holdings_to_csv")
    def test_passes_holdings_to_save(
        self, mock_save: MagicMock, mock_create: MagicMock, mock_upload: MagicMock, tmp_path: Path
    ) -> None:
        mock_fetcher = MagicMock()
        holdings = [make_holding(instrument="TCS")]
        mock_fetcher.fetch_holdings.return_value = holdings
        mock_create.return_value.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_create.return_value.__exit__ = MagicMock(return_value=False)
        mock_save.return_value = tmp_path / "holdings_test.csv"

        _scrape()

        mock_save.assert_called_once_with(holdings)


class TestExtractDateFromFilename:
    def test_extracts_date_from_standard_filename(self) -> None:
        path = Path("holdings_20240115_120000.csv")
        assert _extract_date_from_filename(path) == "2024-01-15"

    def test_falls_back_to_today_for_non_matching_filename(self) -> None:
        path = Path("random.csv")
        assert _extract_date_from_filename(path) == date.today().isoformat()

    def test_nested_path_extracts_from_stem(self) -> None:
        path = Path("/some/dir/holdings_20240115_120000.csv")
        assert _extract_date_from_filename(path) == "2024-01-15"


class TestUploadCsvToSheets:
    @patch("stocks_analysis.main.create_sheets_client")
    def test_loads_and_uploads(self, mock_create_client: MagicMock, tmp_path: Path) -> None:
        from stocks_analysis.main import _upload_csv_to_sheets

        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_client.upload_holdings.return_value = 2
        mock_client.read_all_holdings_rows.return_value = []

        holdings = [make_holding(), make_holding(instrument="TCS")]
        csv_path = save_holdings_to_csv(holdings, output_dir=tmp_path)
        expected_date = _extract_date_from_filename(csv_path)

        _upload_csv_to_sheets(csv_path)

        mock_create_client.assert_called_once()
        mock_client.upload_holdings.assert_called_once()
        uploaded = mock_client.upload_holdings.call_args[0][0]
        assert len(uploaded) == 2
        assert uploaded[0].instrument == "RELIANCE"
        assert uploaded[1].instrument == "TCS"
        assert mock_client.upload_holdings.call_args[1]["date_str"] == expected_date
        mock_client.upload_summary.assert_called_once()
        assert mock_client.upload_summary.call_args[1]["date_str"] == expected_date

    @patch("stocks_analysis.main.create_sheets_client")
    def test_raises_when_env_vars_missing(
        self, mock_create_client: MagicMock, tmp_path: Path
    ) -> None:
        import pytest

        from stocks_analysis.main import _upload_csv_to_sheets

        mock_create_client.side_effect = ValueError("GOOGLE_SHEETS_CREDENTIALS not set")
        csv_path = save_holdings_to_csv([make_holding()], output_dir=tmp_path)

        with pytest.raises(ValueError, match="GOOGLE_SHEETS_CREDENTIALS"):
            _upload_csv_to_sheets(csv_path)

    @patch("stocks_analysis.main.infer_transactions")
    @patch("stocks_analysis.main.parse_snapshots_from_rows")
    @patch("stocks_analysis.main.create_sheets_client")
    def test_upload_also_writes_transactions(
        self,
        mock_create_client: MagicMock,
        mock_parse: MagicMock,
        mock_infer: MagicMock,
        tmp_path: Path,
    ) -> None:
        from stocks_analysis.main import _upload_csv_to_sheets

        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_client.upload_holdings.return_value = 1
        mock_client.read_all_holdings_rows.return_value = [
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

        mock_parse.return_value = [MagicMock()]
        mock_txns = [MagicMock()]
        mock_infer.return_value = mock_txns

        csv_path = save_holdings_to_csv([make_holding()], output_dir=tmp_path)
        _upload_csv_to_sheets(csv_path)

        mock_client.read_all_holdings_rows.assert_called_once()
        mock_parse.assert_called_once()
        mock_infer.assert_called_once()
        mock_client.upload_transactions.assert_called_once_with(mock_txns)


class TestRunWithSubcommands:
    @patch("stocks_analysis.main._upload_csv_to_sheets")
    def test_upload_subcommand_dispatches(self, mock_upload: MagicMock, tmp_path: Path) -> None:
        csv_path = save_holdings_to_csv([make_holding()], output_dir=tmp_path)
        with patch("sys.argv", ["prog", "upload", str(csv_path)]):
            run()
        mock_upload.assert_called_once()
        assert mock_upload.call_args[0][0] == csv_path

    @patch("stocks_analysis.main._scrape")
    def test_scrape_subcommand_dispatches(self, mock_scrape: MagicMock) -> None:
        with patch("sys.argv", ["prog", "scrape"]):
            run()
        mock_scrape.assert_called_once()

    @patch("stocks_analysis.main._scrape")
    def test_no_subcommand_defaults_to_scrape(self, mock_scrape: MagicMock) -> None:
        with patch("sys.argv", ["prog"]):
            run()
        mock_scrape.assert_called_once()


class TestScrapeAutoFill:
    @patch("stocks_analysis.main._upload_to_sheets_if_configured")
    @patch("stocks_analysis.main.create_kite_fetcher")
    @patch("stocks_analysis.main.save_holdings_to_csv")
    @patch.dict("os.environ", {"KITE_USER_ID": "AB1234", "KITE_PASSWORD": "secret123"}, clear=False)
    def test_calls_fill_login_credentials_when_env_vars_set(
        self, mock_save: MagicMock, mock_create: MagicMock, mock_upload: MagicMock, tmp_path: Path
    ) -> None:
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_holdings.return_value = [make_holding()]
        mock_create.return_value.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_create.return_value.__exit__ = MagicMock(return_value=False)
        mock_save.return_value = tmp_path / "holdings_test.csv"

        _scrape()

        mock_fetcher.fill_login_credentials.assert_called_once_with("AB1234", "secret123")

    @patch("stocks_analysis.main._upload_to_sheets_if_configured")
    @patch("stocks_analysis.main.create_kite_fetcher")
    @patch("stocks_analysis.main.save_holdings_to_csv")
    @patch.dict("os.environ", {}, clear=True)
    def test_skips_fill_when_env_vars_missing(
        self, mock_save: MagicMock, mock_create: MagicMock, mock_upload: MagicMock, tmp_path: Path
    ) -> None:
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_holdings.return_value = [make_holding()]
        mock_create.return_value.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_create.return_value.__exit__ = MagicMock(return_value=False)
        mock_save.return_value = tmp_path / "holdings_test.csv"

        _scrape()

        mock_fetcher.fill_login_credentials.assert_not_called()

    @patch("stocks_analysis.main._upload_to_sheets_if_configured")
    @patch("stocks_analysis.main.create_kite_fetcher")
    @patch("stocks_analysis.main.save_holdings_to_csv")
    @patch.dict("os.environ", {"KITE_USER_ID": "AB1234"}, clear=True)
    def test_skips_fill_when_only_user_id_set(
        self, mock_save: MagicMock, mock_create: MagicMock, mock_upload: MagicMock, tmp_path: Path
    ) -> None:
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_holdings.return_value = [make_holding()]
        mock_create.return_value.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_create.return_value.__exit__ = MagicMock(return_value=False)
        mock_save.return_value = tmp_path / "holdings_test.csv"

        _scrape()

        mock_fetcher.fill_login_credentials.assert_not_called()


class TestRunLoadsDotenv:
    @patch("stocks_analysis.main._scrape")
    @patch("stocks_analysis.main.load_dotenv")
    def test_run_calls_load_dotenv(self, mock_dotenv: MagicMock, mock_scrape: MagicMock) -> None:
        with patch("sys.argv", ["prog"]):
            run()
        mock_dotenv.assert_called_once()


class TestUploadToSheetsIfConfigured:
    @patch("stocks_analysis.main.create_sheets_client")
    @patch.dict("os.environ", {"GOOGLE_SHEETS_CREDENTIALS": "/tmp/c.json", "GOOGLE_SHEET_ID": "x"})
    def test_uploads_when_configured(self, mock_create_client: MagicMock) -> None:
        from stocks_analysis.main import _upload_to_sheets_if_configured

        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_client.upload_holdings.return_value = 1

        holdings = [make_holding()]
        _upload_to_sheets_if_configured(holdings)

        mock_create_client.assert_called_once()
        mock_client.upload_holdings.assert_called_once_with(holdings)
        mock_client.upload_summary.assert_called_once()

    @patch.dict("os.environ", {}, clear=True)
    def test_silently_skips_when_not_configured(self) -> None:
        from stocks_analysis.main import _upload_to_sheets_if_configured

        # Should not raise
        _upload_to_sheets_if_configured([make_holding()])

    @patch("stocks_analysis.main.create_sheets_client")
    @patch.dict("os.environ", {"GOOGLE_SHEETS_CREDENTIALS": "/tmp/c.json", "GOOGLE_SHEET_ID": "x"})
    def test_logs_warning_on_failure(self, mock_create_client: MagicMock) -> None:
        from stocks_analysis.main import _upload_to_sheets_if_configured

        mock_create_client.side_effect = Exception("connection failed")

        with patch("stocks_analysis.main.logger") as mock_logger:
            _upload_to_sheets_if_configured([make_holding()])
            mock_logger.warning.assert_called_once()

    @patch("stocks_analysis.main._upload_to_sheets_if_configured")
    @patch("stocks_analysis.main.create_kite_fetcher")
    @patch("stocks_analysis.main.save_holdings_to_csv")
    def test_scrape_calls_upload(
        self, mock_save: MagicMock, mock_create: MagicMock, mock_upload: MagicMock, tmp_path: Path
    ) -> None:
        mock_fetcher = MagicMock()
        holdings = [make_holding()]
        mock_fetcher.fetch_holdings.return_value = holdings
        mock_create.return_value.__enter__ = MagicMock(return_value=mock_fetcher)
        mock_create.return_value.__exit__ = MagicMock(return_value=False)
        mock_save.return_value = tmp_path / "holdings_test.csv"

        _scrape()

        mock_upload.assert_called_once_with(holdings)


class TestSetupSubcommand:
    @patch("stocks_analysis.main._setup")
    def test_setup_subcommand_dispatches(self, mock_setup: MagicMock) -> None:
        with patch("sys.argv", ["prog", "setup"]):
            run()
        mock_setup.assert_called_once()


class TestSetup:
    @patch("stocks_analysis.main.create_sheets_client")
    def test_setup_calls_setup_all(self, mock_create_client: MagicMock) -> None:
        from stocks_analysis.main import _setup

        mock_client = MagicMock()
        mock_create_client.return_value = mock_client

        _setup()

        mock_create_client.assert_called_once()
        mock_client.setup_all.assert_called_once()
