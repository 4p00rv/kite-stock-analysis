from datetime import date
from unittest.mock import MagicMock, call, patch

import gspread
import pytest

from stocks_analysis.models import PortfolioSummary
from stocks_analysis.sheets import (
    DATE_COLOR_A,
    DATE_COLOR_B,
    HEADER_BG,
    HEADER_FG,
    SheetsClient,
    _apply_alternating_date_colors,
    _col_letter,
    _format_header_row,
    _get_date_groups,
    create_sheets_client,
)
from tests.conftest import make_holding


@pytest.fixture
def mock_spreadsheet() -> MagicMock:
    return MagicMock(spec=gspread.Spreadsheet)


@pytest.fixture
def client(mock_spreadsheet: MagicMock) -> SheetsClient:
    return SheetsClient(mock_spreadsheet)


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
        mock_ws.update.assert_called_once_with("A1", [headers])

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
        mock_ws.update.assert_called_once_with("A1", [headers])


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

    @patch("stocks_analysis.sheets._apply_alternating_date_colors")
    @patch("stocks_analysis.sheets._format_header_row")
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
            patch("stocks_analysis.sheets._format_header_row") as mock_fmt_header,
            patch("stocks_analysis.sheets._apply_alternating_date_colors") as mock_fmt_colors,
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


class TestUploadSummary:
    def test_uploads_summary_row(self, client: SheetsClient, mock_spreadsheet: MagicMock) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = ["date"] + PortfolioSummary.csv_headers()
        mock_ws.col_values.return_value = ["date"]
        mock_spreadsheet.worksheet.return_value = mock_ws

        summary = PortfolioSummary.from_holdings([make_holding()])
        client.upload_summary(summary, date_str="2024-01-15")

        mock_ws.append_rows.assert_called_once()
        rows = mock_ws.append_rows.call_args[0][0]
        assert len(rows) == 1
        assert rows[0][0] == "2024-01-15"

    @patch("stocks_analysis.sheets._apply_alternating_date_colors")
    @patch("stocks_analysis.sheets._format_header_row")
    def test_applies_formatting_after_upload(
        self,
        mock_fmt_header: MagicMock,
        mock_fmt_colors: MagicMock,
        client: SheetsClient,
        mock_spreadsheet: MagicMock,
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = ["date"] + PortfolioSummary.csv_headers()
        mock_ws.col_values.return_value = ["date"]
        mock_spreadsheet.worksheet.return_value = mock_ws

        summary = PortfolioSummary.from_holdings([make_holding()])
        client.upload_summary(summary, date_str="2024-01-15")
        num_cols = 1 + len(PortfolioSummary.csv_headers())
        mock_fmt_header.assert_called_once_with(mock_ws, num_cols)
        mock_fmt_colors.assert_called_once_with(mock_ws, num_cols)

    def test_dedup_deletes_existing_date_rows(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = ["date"] + PortfolioSummary.csv_headers()
        mock_ws.col_values.return_value = ["date", "2024-01-15"]
        mock_spreadsheet.worksheet.return_value = mock_ws

        summary = PortfolioSummary.from_holdings([make_holding()])
        client.upload_summary(summary, date_str="2024-01-15")
        mock_ws.delete_rows.assert_called_once_with(2)


class TestColLetter:
    def test_single_letter(self) -> None:
        assert _col_letter(1) == "A"
        assert _col_letter(11) == "K"
        assert _col_letter(26) == "Z"

    def test_double_letter(self) -> None:
        assert _col_letter(27) == "AA"


class TestFormatHeaderRow:
    def test_applies_correct_style_and_range(self) -> None:
        mock_ws = MagicMock()
        _format_header_row(mock_ws, num_cols=11)
        mock_ws.format.assert_called_once()
        args, kwargs = mock_ws.format.call_args
        assert args[0] == "A1:K1"
        fmt = args[1]
        assert fmt["textFormat"]["bold"] is True
        assert fmt["textFormat"]["foregroundColorStyle"]["rgbColor"] == HEADER_FG
        assert fmt["backgroundColor"] == HEADER_BG
        assert fmt["horizontalAlignment"] == "CENTER"

    def test_freezes_header_row(self) -> None:
        mock_ws = MagicMock()
        _format_header_row(mock_ws, num_cols=3)
        mock_ws.freeze.assert_called_once_with(rows=1)

    def test_small_column_count(self) -> None:
        mock_ws = MagicMock()
        _format_header_row(mock_ws, num_cols=2)
        args, _ = mock_ws.format.call_args
        assert args[0] == "A1:B1"


class TestGetDateGroups:
    def test_consecutive_grouping(self) -> None:
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = [
            "date",
            "2024-01-15",
            "2024-01-15",
            "2024-01-16",
            "2024-01-16",
            "2024-01-16",
        ]
        result = _get_date_groups(mock_ws)
        assert result == [
            ("2024-01-15", 2, 3),
            ("2024-01-16", 4, 6),
        ]

    def test_single_row(self) -> None:
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = ["date", "2024-01-15"]
        result = _get_date_groups(mock_ws)
        assert result == [("2024-01-15", 2, 2)]

    def test_empty_sheet(self) -> None:
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = ["date"]
        result = _get_date_groups(mock_ws)
        assert result == []

    def test_non_contiguous_same_dates(self) -> None:
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = [
            "date",
            "2024-01-15",
            "2024-01-16",
            "2024-01-15",
        ]
        result = _get_date_groups(mock_ws)
        assert result == [
            ("2024-01-15", 2, 2),
            ("2024-01-16", 3, 3),
            ("2024-01-15", 4, 4),
        ]


class TestApplyAlternatingDateColors:
    def test_batch_format_args_for_two_groups(self) -> None:
        mock_ws = MagicMock()
        # 2 dates, 2 rows each, 3 columns
        mock_ws.col_values.return_value = [
            "date",
            "2024-01-15",
            "2024-01-15",
            "2024-01-16",
            "2024-01-16",
        ]
        _apply_alternating_date_colors(mock_ws, num_cols=3)
        mock_ws.batch_format.assert_called_once()
        fmt_list = mock_ws.batch_format.call_args[0][0]
        assert len(fmt_list) == 2
        # First group: DATE_COLOR_A (no fill)
        assert fmt_list[0]["range"] == "A2:C3"
        assert fmt_list[0]["format"]["backgroundColor"] is DATE_COLOR_A
        # Second group: DATE_COLOR_B
        assert fmt_list[1]["range"] == "A4:C5"
        assert fmt_list[1]["format"]["backgroundColor"] == DATE_COLOR_B

    def test_no_op_on_empty(self) -> None:
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = ["date"]
        _apply_alternating_date_colors(mock_ws, num_cols=3)
        mock_ws.batch_format.assert_not_called()

    def test_three_group_alternation(self) -> None:
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = [
            "date",
            "2024-01-15",
            "2024-01-16",
            "2024-01-17",
        ]
        _apply_alternating_date_colors(mock_ws, num_cols=2)
        fmt_list = mock_ws.batch_format.call_args[0][0]
        assert len(fmt_list) == 3
        # Alternates: A, B, A
        assert fmt_list[0]["format"]["backgroundColor"] is DATE_COLOR_A
        assert fmt_list[1]["format"]["backgroundColor"] == DATE_COLOR_B
        assert fmt_list[2]["format"]["backgroundColor"] is DATE_COLOR_A


class TestCreateSheetsClient:
    @patch.dict(
        "os.environ",
        {"GOOGLE_SHEETS_CREDENTIALS": "/tmp/creds.json", "GOOGLE_SHEET_ID": "abc123"},
    )
    @patch("stocks_analysis.sheets.gspread.service_account")
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
