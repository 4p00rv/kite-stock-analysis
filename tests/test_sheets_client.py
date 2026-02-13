from datetime import date
from unittest.mock import MagicMock, call, patch

import gspread
import pytest

from stocks_analysis.models import Transaction
from stocks_analysis.sheets import (
    SheetsClient,
    create_sheets_client,
)
from tests.conftest import make_holding


class TestSheetsClientInit:
    def test_stores_spreadsheet(self, mock_spreadsheet: MagicMock) -> None:
        client = SheetsClient(mock_spreadsheet)
        assert client._spreadsheet is mock_spreadsheet


class TestGetOrCreateWorksheet:
    def test_returns_existing_worksheet(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = ["date", "instrument"]
        mock_spreadsheet.worksheet.return_value = mock_ws

        ws = client._get_or_create_worksheet("Holdings", ["date", "instrument"])
        mock_spreadsheet.worksheet.assert_called_once_with("Holdings")
        assert ws is mock_ws

    def test_creates_worksheet_when_not_found(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound("Holdings")
        mock_new_ws = MagicMock()
        mock_new_ws.row_values.return_value = []
        mock_spreadsheet.add_worksheet.return_value = mock_new_ws

        ws = client._get_or_create_worksheet("Holdings", ["date", "instrument"])
        mock_spreadsheet.add_worksheet.assert_called_once_with(title="Holdings", rows=1000, cols=20)
        assert ws is mock_new_ws


class TestEnsureHeaders:
    def test_writes_headers_when_empty(self, client: SheetsClient) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = []
        headers = ["date", "instrument"]

        client._ensure_headers(mock_ws, headers)
        mock_ws.update.assert_called_once_with([headers], range_name="A1")

    def test_no_op_when_headers_match(self, client: SheetsClient) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = ["date", "instrument"]
        headers = ["date", "instrument"]

        client._ensure_headers(mock_ws, headers)
        mock_ws.update.assert_not_called()

    def test_overwrites_when_headers_differ(self, client: SheetsClient) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = ["old_col1", "old_col2"]
        headers = ["date", "instrument"]

        client._ensure_headers(mock_ws, headers)
        mock_ws.update.assert_called_once_with([headers], range_name="A1")


class TestDeleteRowsForDate:
    def test_deletes_matching_rows_in_reverse(self, client: SheetsClient) -> None:
        mock_ws = MagicMock()
        # Row 1 = header, rows 2-4 = data; rows 2 and 4 match the date
        mock_ws.col_values.return_value = ["date", "2024-01-15", "2024-01-16", "2024-01-15"]

        client._delete_rows_for_date(mock_ws, "2024-01-15")
        # Should delete row 4 first, then row 2 (reverse order to preserve indices)
        assert mock_ws.delete_rows.call_args_list == [call(4), call(2)]

    def test_no_deletion_when_no_match(self, client: SheetsClient) -> None:
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = ["date", "2024-01-15", "2024-01-16"]

        client._delete_rows_for_date(mock_ws, "2024-01-17")
        mock_ws.delete_rows.assert_not_called()

    def test_skips_header_row(self, client: SheetsClient) -> None:
        mock_ws = MagicMock()
        # Header is "date" — should not be deleted even if it technically matches
        mock_ws.col_values.return_value = ["date", "2024-01-15"]

        client._delete_rows_for_date(mock_ws, "date")
        mock_ws.delete_rows.assert_not_called()


class TestUploadHoldings:
    def test_uploads_formatted_rows(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = ["date"] + make_holding().csv_headers()
        mock_ws.col_values.return_value = ["date"]
        mock_spreadsheet.worksheet.return_value = mock_ws

        holdings = [make_holding()]
        count = client.upload_holdings(holdings, date_str="2024-01-15")

        assert count == 1
        mock_ws.append_rows.assert_called_once()
        rows = mock_ws.append_rows.call_args[0][0]
        assert rows[0][0] == "2024-01-15"
        assert rows[0][1] == "RELIANCE"

    def test_default_date_is_today(self, client: SheetsClient, mock_spreadsheet: MagicMock) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = ["date"] + make_holding().csv_headers()
        mock_ws.col_values.return_value = ["date"]
        mock_spreadsheet.worksheet.return_value = mock_ws

        client.upload_holdings([make_holding()])

        rows = mock_ws.append_rows.call_args[0][0]
        assert rows[0][0] == date.today().isoformat()

    def test_empty_holdings_returns_zero(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = ["date"]
        mock_ws.col_values.return_value = ["date"]
        mock_spreadsheet.worksheet.return_value = mock_ws

        count = client.upload_holdings([], date_str="2024-01-15")
        assert count == 0
        mock_ws.append_rows.assert_not_called()

    def test_dedup_deletes_existing_date_rows(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = ["date"] + make_holding().csv_headers()
        mock_ws.col_values.return_value = ["date", "2024-01-15", "2024-01-16"]
        mock_spreadsheet.worksheet.return_value = mock_ws

        client.upload_holdings([make_holding()], date_str="2024-01-15")
        mock_ws.delete_rows.assert_called_once_with(2)

    @patch("stocks_analysis.sheets.client._apply_alternating_date_colors")
    @patch("stocks_analysis.sheets.client._format_header_row")
    def test_applies_formatting_after_upload(
        self,
        mock_fmt_header: MagicMock,
        mock_fmt_colors: MagicMock,
        client: SheetsClient,
        mock_spreadsheet: MagicMock,
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = ["date"] + make_holding().csv_headers()
        mock_ws.col_values.return_value = ["date"]
        mock_spreadsheet.worksheet.return_value = mock_ws

        client.upload_holdings([make_holding()], date_str="2024-01-15")
        num_cols = 1 + len(make_holding().csv_headers())
        mock_fmt_header.assert_called_once_with(mock_ws, num_cols)
        mock_fmt_colors.assert_called_once_with(mock_ws, num_cols)

    def test_no_formatting_when_empty(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        with (
            patch("stocks_analysis.sheets.client._format_header_row") as mock_fmt_header,
            patch(
                "stocks_analysis.sheets.client._apply_alternating_date_colors"
            ) as mock_fmt_colors,
        ):
            count = client.upload_holdings([], date_str="2024-01-15")
            assert count == 0
            mock_fmt_header.assert_not_called()
            mock_fmt_colors.assert_not_called()

    def test_multiple_holdings(self, client: SheetsClient, mock_spreadsheet: MagicMock) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = ["date"] + make_holding().csv_headers()
        mock_ws.col_values.return_value = ["date"]
        mock_spreadsheet.worksheet.return_value = mock_ws

        holdings = [make_holding(), make_holding(instrument="TCS")]
        count = client.upload_holdings(holdings, date_str="2024-01-15")

        assert count == 2
        rows = mock_ws.append_rows.call_args[0][0]
        assert len(rows) == 2
        assert rows[0][1] == "RELIANCE"
        assert rows[1][1] == "TCS"


class TestCreateSheetsClient:
    @patch.dict(
        "os.environ",
        {"GOOGLE_SHEETS_CREDENTIALS": "/tmp/creds.json", "GOOGLE_SHEET_ID": "abc123"},
    )
    @patch("stocks_analysis.sheets.client.gspread.service_account")
    def test_success(self, mock_sa: MagicMock) -> None:
        mock_gc = MagicMock()
        mock_sa.return_value = mock_gc
        mock_spreadsheet = MagicMock()
        mock_gc.open_by_key.return_value = mock_spreadsheet

        client = create_sheets_client()
        mock_sa.assert_called_once_with(filename="/tmp/creds.json")
        mock_gc.open_by_key.assert_called_once_with("abc123")
        assert isinstance(client, SheetsClient)

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_credentials_raises(self) -> None:
        with pytest.raises(ValueError, match="GOOGLE_SHEETS_CREDENTIALS"):
            create_sheets_client()

    @patch.dict("os.environ", {"GOOGLE_SHEETS_CREDENTIALS": "/tmp/creds.json"}, clear=True)
    def test_missing_sheet_id_raises(self) -> None:
        with pytest.raises(ValueError, match="GOOGLE_SHEET_ID"):
            create_sheets_client()


class TestReadAllHoldingsRows:
    def test_reads_all_rows_skipping_header(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = [
            [
                "date",
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
        mock_spreadsheet.worksheet.return_value = mock_ws

        rows = client.read_all_holdings_rows()
        assert len(rows) == 2
        assert rows[0][1] == "RELIANCE"
        assert rows[1][1] == "TCS"

    def test_empty_sheet(self, client: SheetsClient, mock_spreadsheet: MagicMock) -> None:
        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = [
            ["date", "instrument", "quantity"],
        ]
        mock_spreadsheet.worksheet.return_value = mock_ws

        rows = client.read_all_holdings_rows()
        assert rows == []


class TestUploadTransactions:
    def test_uploads_transactions_with_headers(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = []
        mock_spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound("Transactions")
        mock_spreadsheet.add_worksheet.return_value = mock_ws
        mock_ws.row_values.return_value = [
            "date",
            "instrument",
            "type",
            "quantity",
            "price",
            "amount",
        ]

        txns = [
            Transaction(date(2025, 1, 15), "RELIANCE", "BUY", 10, 2450.5, -24505.0),
            Transaction(date(2025, 1, 20), "TCS", "BUY", 5, 3200.0, -16000.0),
        ]
        client.upload_transactions(txns)

        # Should clear data and write new rows
        mock_ws.batch_clear.assert_called_once_with(["A2:F1000"])
        mock_ws.append_rows.assert_called_once()
        rows = mock_ws.append_rows.call_args[0][0]
        assert len(rows) == 2
        assert rows[0] == ["2025-01-15", "RELIANCE", "BUY", 10, 2450.5, -24505.0]
        assert rows[1] == ["2025-01-20", "TCS", "BUY", 5, 3200.0, -16000.0]

    def test_empty_transactions_clears_only(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = [
            "date",
            "instrument",
            "type",
            "quantity",
            "price",
            "amount",
        ]
        mock_spreadsheet.worksheet.return_value = mock_ws

        client.upload_transactions([])

        mock_ws.batch_clear.assert_called_once_with(["A2:F1000"])
        mock_ws.append_rows.assert_not_called()
