from __future__ import annotations

import os
from datetime import date

import gspread
from gspread.utils import rowcol_to_a1

from stocks_analysis.models import Holding, PortfolioSummary

# Formatting colors (RGB dicts for gspread)
HEADER_BG: dict[str, float] = {"red": 0.235, "green": 0.275, "blue": 0.349}  # #3C4659
HEADER_FG: dict[str, float] = {"red": 1.0, "green": 1.0, "blue": 1.0}  # white
DATE_COLOR_A: dict[str, float] | None = None  # white / no fill
DATE_COLOR_B: dict[str, float] = {"red": 0.929, "green": 0.941, "blue": 0.957}  # #EDF0F4


def _col_letter(col: int) -> str:
    """Convert a 1-indexed column number to a column letter (e.g. 1 -> 'A', 27 -> 'AA')."""
    return rowcol_to_a1(1, col).rstrip("1")


def _format_header_row(worksheet: gspread.Worksheet, num_cols: int) -> None:
    """Apply bold white-on-dark styling to row 1 and freeze it."""
    end_col = _col_letter(num_cols)
    worksheet.format(
        f"A1:{end_col}1",
        {
            "textFormat": {
                "bold": True,
                "foregroundColorStyle": {"rgbColor": HEADER_FG},
            },
            "backgroundColor": HEADER_BG,
            "horizontalAlignment": "CENTER",
        },
    )
    worksheet.freeze(rows=1)


def _get_date_groups(worksheet: gspread.Worksheet) -> list[tuple[str, int, int]]:
    """Scan column A and group consecutive rows by date value.

    Returns a list of (date_str, start_row, end_row) tuples.
    Rows are 1-indexed; row 1 (header) is skipped.
    """
    col_values = worksheet.col_values(1)
    groups: list[tuple[str, int, int]] = []
    if len(col_values) <= 1:
        return groups

    current_date = col_values[1]
    start_row = 2  # 1-indexed, skip header

    for i in range(2, len(col_values)):
        val = col_values[i]
        if val != current_date:
            groups.append((current_date, start_row, i))  # i is 1-indexed end row
            current_date = val
            start_row = i + 1
        # else: continue the current group

    # Append the last group
    groups.append((current_date, start_row, len(col_values)))
    return groups


def _apply_alternating_date_colors(worksheet: gspread.Worksheet, num_cols: int) -> None:
    """Apply alternating background colors to rows grouped by date."""
    groups = _get_date_groups(worksheet)
    if not groups:
        return

    end_col = _col_letter(num_cols)
    colors = [DATE_COLOR_A, DATE_COLOR_B]
    formats = []
    for i, (_date_str, start_row, end_row) in enumerate(groups):
        formats.append(
            {
                "range": f"A{start_row}:{end_col}{end_row}",
                "format": {"backgroundColor": colors[i % 2]},
            }
        )
    worksheet.batch_format(formats)


class SheetsClient:
    def __init__(self, spreadsheet: gspread.Spreadsheet) -> None:
        self._spreadsheet = spreadsheet

    def _get_or_create_worksheet(self, title: str, headers: list[str]) -> gspread.Worksheet:
        try:
            ws = self._spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self._spreadsheet.add_worksheet(title=title, rows=1000, cols=20)
        self._ensure_headers(ws, headers)
        return ws

    def _ensure_headers(self, worksheet: gspread.Worksheet, headers: list[str]) -> None:
        existing = worksheet.row_values(1)
        if existing != headers:
            worksheet.update("A1", [headers])

    def _delete_rows_for_date(self, worksheet: gspread.Worksheet, date_str: str) -> None:
        col_values = worksheet.col_values(1)
        # Collect 1-indexed row numbers that match, skipping header (row 1)
        matching_rows = [i + 1 for i, val in enumerate(col_values) if val == date_str and i > 0]
        # Delete in reverse order to preserve indices
        for row_num in reversed(matching_rows):
            worksheet.delete_rows(row_num)

    def upload_holdings(self, holdings: list[Holding], date_str: str | None = None) -> int:
        if not holdings:
            return 0

        date_str = date_str or date.today().isoformat()
        headers = ["date", *Holding.csv_headers()]
        ws = self._get_or_create_worksheet("Holdings", headers)
        self._delete_rows_for_date(ws, date_str)

        rows = [[date_str, *h.to_csv_row()] for h in holdings]
        ws.append_rows(rows)
        _format_header_row(ws, len(headers))
        _apply_alternating_date_colors(ws, len(headers))
        return len(rows)

    def upload_summary(self, summary: PortfolioSummary, date_str: str | None = None) -> None:
        date_str = date_str or date.today().isoformat()
        headers = ["date", *PortfolioSummary.csv_headers()]
        ws = self._get_or_create_worksheet("Summary", headers)
        self._delete_rows_for_date(ws, date_str)

        ws.append_rows([[date_str, *summary.to_csv_row()]])
        _format_header_row(ws, len(headers))
        _apply_alternating_date_colors(ws, len(headers))


def create_sheets_client() -> SheetsClient:
    creds_path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_path:
        raise ValueError("GOOGLE_SHEETS_CREDENTIALS environment variable is not set")

    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise ValueError("GOOGLE_SHEET_ID environment variable is not set")

    gc = gspread.service_account(filename=creds_path)
    spreadsheet = gc.open_by_key(sheet_id)
    return SheetsClient(spreadsheet)
