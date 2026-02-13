from __future__ import annotations

import os
from datetime import date

import gspread

from stocks_analysis.models import Holding, Transaction
from stocks_analysis.sheets.formatting import (
    _apply_alternating_date_colors,
    _format_header_row,
)


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
            worksheet.update([headers], range_name="A1")

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

    def read_all_holdings_rows(self) -> list[list[str]]:
        """Read all rows from the Holdings worksheet, skipping the header."""
        ws = self._spreadsheet.worksheet("Holdings")
        all_values = ws.get_all_values()
        if len(all_values) <= 1:
            return []
        return all_values[1:]

    def upload_transactions(self, transactions: list[Transaction]) -> None:
        """Upload inferred transactions to the Transactions sheet."""
        headers = ["date", "instrument", "type", "quantity", "price", "amount"]
        ws = self._get_or_create_worksheet("Transactions", headers)
        ws.batch_clear(["A2:F1000"])

        if not transactions:
            return

        rows = [
            [
                t.date.isoformat(),
                t.instrument,
                t.type,
                t.quantity,
                t.price,
                t.amount,
            ]
            for t in transactions
        ]
        ws.append_rows(rows)

    # ------------------------------------------------------------------
    # Charts helpers
    # ------------------------------------------------------------------

    def _get_sheet_id(self, title: str) -> int | None:
        """Get the sheet ID for a worksheet by title."""
        for ws in self._spreadsheet.worksheets():
            if ws.title == title:
                return ws.id
        return None

    def _find_existing_charts(self) -> dict[str, int]:
        """Find existing charts by title -> chartId mapping."""
        chart_map: dict[str, int] = {}
        metadata = self._spreadsheet.fetch_sheet_metadata()
        for sheet in metadata.get("sheets", []):
            for chart in sheet.get("charts", []):
                title = chart.get("spec", {}).get("title", "")
                if title:
                    chart_map[title] = chart["chartId"]
        return chart_map

    # ------------------------------------------------------------------
    # Formula-based setup (thin wrappers delegating to setup.py / charts.py)
    # ------------------------------------------------------------------

    def setup_prices_sheet(self) -> None:
        """Create Prices sheet with pivot formulas (date x instrument -> LTP)."""
        from stocks_analysis.sheets.setup import setup_prices_sheet

        setup_prices_sheet(self)

    def setup_portfolio_history_sheet(self) -> None:
        """Create Portfolio History sheet with per-snapshot aggregation formulas."""
        from stocks_analysis.sheets.setup import setup_portfolio_history_sheet

        setup_portfolio_history_sheet(self)

    def setup_allocation_sheet(self) -> None:
        """Create Allocation sheet with latest-snapshot weight and performance formulas."""
        from stocks_analysis.sheets.setup import setup_allocation_sheet

        setup_allocation_sheet(self)

    def setup_dashboard_sheet(self) -> None:
        """Create Dashboard sheet with key metrics formulas."""
        from stocks_analysis.sheets.setup import setup_dashboard_sheet

        setup_dashboard_sheet(self)

    def setup_charts(self) -> None:
        """Create or update formula-based charts via Sheets API batchUpdate."""
        from stocks_analysis.sheets.charts import setup_charts

        setup_charts(self)

    def setup_all(self) -> None:
        """Run all setup methods to create formula-based sheets and charts."""
        self.setup_prices_sheet()
        self.setup_portfolio_history_sheet()
        self.setup_allocation_sheet()
        self.setup_dashboard_sheet()
        self.setup_charts()
        print("All formula sheets and charts configured.")


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
