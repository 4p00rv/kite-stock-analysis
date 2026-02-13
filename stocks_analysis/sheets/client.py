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
    # Formula-based setup (created once, auto-recalculate)
    # ------------------------------------------------------------------

    def _get_or_create_plain_worksheet(
        self, title: str, rows: int = 1000, cols: int = 20
    ) -> gspread.Worksheet:
        """Get or create a worksheet without writing headers."""
        try:
            return self._spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            return self._spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)

    def setup_prices_sheet(self) -> None:
        """Create Prices sheet with pivot formulas (date x instrument -> LTP)."""
        # Delete and recreate to ensure clean slate (copyPaste fails on stale sheets)
        try:
            old_ws = self._spreadsheet.worksheet("Prices")
            self._spreadsheet.del_worksheet(old_ws)
        except gspread.WorksheetNotFound:
            pass
        ws = self._spreadsheet.add_worksheet(title="Prices", rows=1000, cols=104)
        sheet_id = ws.id

        # Header row and date column
        ws.update([["date"]], range_name="A1")
        # Latest date via text sort (YYYY-MM-DD sorts lexicographically)
        latest_date = 'INDEX(SORT(UNIQUE(FILTER(Holdings!A2:A, Holdings!A2:A<>"")), 1, FALSE), 1)'
        b1_formula = f"=TRANSPOSE(SORT(UNIQUE(FILTER(Holdings!B2:B, Holdings!A2:A={latest_date}))))"
        ws.update([[b1_formula]], range_name="B1", raw=False)
        ws.update(
            [['=SORT(UNIQUE(FILTER(Holdings!A2:A, Holdings!A2:A<>"")))']],
            range_name="A2",
            raw=False,
        )
        # B2: lookup formula (TEXT() on both sides to avoid date/text type mismatch)
        b2_formula = (
            '=IF(OR($A2="", B$1=""), "",'
            " IFERROR(INDEX(FILTER(Holdings!$E:$E,"
            ' TEXT(Holdings!$A:$A,"YYYY-MM-DD")=TEXT($A2,"YYYY-MM-DD"),'
            " Holdings!$B:$B=B$1"
            '), 1), ""))'
        )
        ws.update([[b2_formula]], range_name="B2", raw=False)

        # Fill B2 right to CZ2, then fill B2:CZ2 down to row 1000
        self._spreadsheet.batch_update(
            {
                "requests": [
                    {
                        "copyPaste": {
                            "source": {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": 2,
                                "startColumnIndex": 1,
                                "endColumnIndex": 2,
                            },
                            "destination": {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": 2,
                                "startColumnIndex": 1,
                                "endColumnIndex": 104,
                            },
                            "pasteType": "PASTE_FORMULA",
                        }
                    },
                    {
                        "copyPaste": {
                            "source": {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": 2,
                                "startColumnIndex": 1,
                                "endColumnIndex": 104,
                            },
                            "destination": {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": 1000,
                                "startColumnIndex": 1,
                                "endColumnIndex": 104,
                            },
                            "pasteType": "PASTE_FORMULA",
                        }
                    },
                ]
            }
        )

        ws.freeze(rows=1, cols=1)
        print("Prices sheet configured.")

    def setup_portfolio_history_sheet(self) -> None:
        """Create Portfolio History sheet with per-snapshot aggregation formulas."""
        headers = [
            "date",
            "total_value",
            "total_cost",
            "total_pnl",
            "return_pct",
            "num_holdings",
            "running_max",
            "drawdown_pct",
        ]
        ws = self._get_or_create_plain_worksheet("Portfolio History")
        sheet_id = ws.id

        ws.update([headers], range_name="A1:H1")

        ws.update(
            [['=SORT(UNIQUE(FILTER(Holdings!A$2:A, Holdings!A$2:A<>"")))']],
            range_name="A2",
            raw=False,
        )
        ws.update(
            [['=IF($A2="", "", SUMPRODUCT((Holdings!A$2:A=$A2)*Holdings!F$2:F))']],
            range_name="B2",
            raw=False,
        )
        ws.update(
            [['=IF($A2="", "", SUMPRODUCT((Holdings!A$2:A=$A2)*Holdings!D$2:D*Holdings!C$2:C))']],
            range_name="C2",
            raw=False,
        )
        ws.update([['=IF($A2="", "", B2-C2)']], range_name="D2", raw=False)
        ws.update([['=IF(OR($A2="", C2=0), "", D2/C2*100)']], range_name="E2", raw=False)
        ws.update([['=IF($A2="", "", COUNTIF(Holdings!A$2:A, $A2))']], range_name="F2", raw=False)
        ws.update([['=IF($A2="", "", MAX(B$2:B2))']], range_name="G2", raw=False)
        ws.update(
            [['=IF(OR($A2="", G2=0), "", (1-B2/G2)*100)']],
            range_name="H2",
            raw=False,
        )

        # Fill B2:H2 down to row 1000
        self._spreadsheet.batch_update(
            {
                "requests": [
                    {
                        "copyPaste": {
                            "source": {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": 2,
                                "startColumnIndex": 1,
                                "endColumnIndex": 8,
                            },
                            "destination": {
                                "sheetId": sheet_id,
                                "startRowIndex": 1,
                                "endRowIndex": 1000,
                                "startColumnIndex": 1,
                                "endColumnIndex": 8,
                            },
                            "pasteType": "PASTE_FORMULA",
                        }
                    }
                ]
            }
        )

        _format_header_row(ws, len(headers))
        ws.freeze(rows=1)
        print("Portfolio History sheet configured.")

    def setup_allocation_sheet(self) -> None:
        """Create Allocation sheet with latest-snapshot weight and performance formulas."""
        headers = ["instrument", "current_value", "cost", "weight_pct", "pnl", "return_pct"]
        ws = self._get_or_create_plain_worksheet("Allocation")

        ws.update([headers], range_name="A1:F1")

        # Helper cells in column H (out of the way of data columns)
        ws.update([["latest_date"]], range_name="H1")
        ws.update([["=MAX(Holdings!A2:A)"]], range_name="H2", raw=False)
        ws.update([["total_value"]], range_name="H3")
        ws.update(
            [["=SUMPRODUCT((Holdings!A2:A=$H$2)*Holdings!F2:F)"]],
            range_name="H4",
            raw=False,
        )

        # A2:C2 spill — instrument, current_value, cost (sorted by value desc)
        ws.update(
            [
                [
                    "=SORT(FILTER("
                    "{Holdings!B2:B, Holdings!F2:F, Holdings!D2:D*Holdings!C2:C},"
                    " Holdings!A2:A=$H$2), 2, FALSE)"
                ]
            ],
            range_name="A2",
            raw=False,
        )
        # D2:F2 — weight_pct, pnl, return_pct (ARRAYFORMULA to auto-expand)
        ws.update(
            [['=ARRAYFORMULA(IF(A2:A="", "", B2:B/$H$4*100))']],
            range_name="D2",
            raw=False,
        )
        ws.update(
            [['=ARRAYFORMULA(IF(A2:A="", "", B2:B-C2:C))']],
            range_name="E2",
            raw=False,
        )
        ws.update(
            [['=ARRAYFORMULA(IF((A2:A="")+(C2:C=0), "", (B2:B-C2:C)/C2:C*100))']],
            range_name="F2",
            raw=False,
        )

        _format_header_row(ws, len(headers))
        print("Allocation sheet configured.")

    def setup_dashboard_sheet(self) -> None:
        """Create Dashboard sheet with key metrics formulas."""
        ws = self._get_or_create_plain_worksheet("Dashboard")

        labels = [
            ["Metric"],
            ["Portfolio Value"],
            ["Total Cost"],
            ["Total P&L"],
            ["Total Return %"],
            ["No. Holdings"],
            ["First Date"],
            ["Latest Date"],
            ["Days Invested"],
            ["XIRR"],
            ["Max Drawdown %"],
            ["Max Drawdown Date"],
            ["HHI"],
            ["Top 5 Concentration %"],
        ]
        ws.update(labels[:14], range_name="A1:A14")

        ph = "'Portfolio History'"

        def _latest(col: str) -> str:
            return (
                "=IFERROR(INDEX(SORT(FILTER("
                "{" + f"{ph}!A2:A, {ph}!{col}2:{col}" + "}, "
                f'{ph}!A2:A<>""), 1, FALSE), 1, 2), "")'
            )

        def _ph_filter(fn: str, c: str, fb: str) -> str:
            return f'=IFERROR({fn}(FILTER({ph}!{c}2:{c}, {ph}!{c}2:{c}<>"")), {fb})'

        formulas = [
            ["Value"],
            [_latest("B")],
            [_latest("C")],
            ['=IF(B2="", "", B2-B3)'],
            ['=IF(OR(B3="", B3=0), "", B4/B3*100)'],
            [_latest("F")],
            [_ph_filter("MIN", "A", '""')],
            [_ph_filter("MAX", "A", '""')],
            ['=IF(OR(B7="", B8=""), "", B8-B7)'],
            [
                "=IFERROR(XIRR("
                '{FILTER(Transactions!F2:F, Transactions!F2:F<>""); B2}, '
                '{FILTER(Transactions!A2:A, Transactions!F2:F<>""); B8}'
                '), "")'
            ],
            [_ph_filter("MAX", "H", "0")],
            [f'=IFERROR(INDEX(FILTER({ph}!A2:A, {ph}!H2:H=B11), 1), "")'],
            ['=IFERROR(SUMPRODUCT(FILTER(Allocation!D2:D, Allocation!D2:D<>"")^2/10000), "")'],
            [
                "=IFERROR(SUM(LARGE("
                'FILTER(Allocation!D2:D, Allocation!D2:D<>""), {1,2,3,4,5})),'
                ' IFERROR(SUM(FILTER(Allocation!D2:D, Allocation!D2:D<>"")), ""))'
            ],
        ]
        ws.update(formulas[:14], range_name="B1:B14", raw=False)

        _format_header_row(ws, 2)
        ws.freeze(rows=1)
        print("Dashboard sheet configured.")

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
