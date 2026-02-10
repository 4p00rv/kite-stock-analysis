from __future__ import annotations

import os
from datetime import date

import gspread

from stocks_analysis.models import Holding, PortfolioSummary


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
        return len(rows)

    def upload_summary(self, summary: PortfolioSummary, date_str: str | None = None) -> None:
        date_str = date_str or date.today().isoformat()
        headers = ["date", *PortfolioSummary.csv_headers()]
        ws = self._get_or_create_worksheet("Summary", headers)
        self._delete_rows_for_date(ws, date_str)

        ws.append_rows([[date_str, *summary.to_csv_row()]])


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
