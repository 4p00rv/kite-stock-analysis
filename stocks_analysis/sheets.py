from __future__ import annotations

import os
from datetime import date

import gspread
from gspread.utils import rowcol_to_a1

from stocks_analysis.models import Holding, PortfolioSummary, Transaction

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
        """Find existing charts by title → chartId mapping."""
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
        """Create Prices sheet with pivot formulas (date x instrument → LTP)."""
        ws = self._get_or_create_plain_worksheet("Prices", rows=1000, cols=104)
        sheet_id = ws.id

        # Header row and date column
        ws.update("A1", "date", raw=False)
        ws.update(
            "B1",
            '=TRANSPOSE(SORT(UNIQUE(FILTER(Holdings!B2:B, Holdings!B2:B<>""))))',
            raw=False,
        )
        ws.update(
            "A2",
            '=SORT(UNIQUE(FILTER(Holdings!A2:A, Holdings!A2:A<>"")))',
            raw=False,
        )
        # B2: lookup formula
        b2_formula = (
            '=IF(OR($A2="", B$1=""), "",'
            " IFERROR(INDEX(FILTER("
            "Holdings!E:E, Holdings!A:A=$A2, Holdings!B:B=B$1"
            '), 1), ""))'
        )
        ws.update("B2", b2_formula, raw=False)

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

        ws.update("A1:H1", [headers])

        ws.update(
            "A2",
            '=SORT(UNIQUE(FILTER(Holdings!A$2:A, Holdings!A$2:A<>"")))',
            raw=False,
        )
        ws.update(
            "B2",
            '=IF($A2="", "", SUMPRODUCT((Holdings!A$2:A=$A2)*Holdings!F$2:F))',
            raw=False,
        )
        ws.update(
            "C2",
            '=IF($A2="", "", SUMPRODUCT((Holdings!A$2:A=$A2)*Holdings!D$2:D*Holdings!C$2:C))',
            raw=False,
        )
        ws.update("D2", '=IF($A2="", "", B2-C2)', raw=False)
        ws.update("E2", '=IF(OR($A2="", C2=0), "", D2/C2*100)', raw=False)
        ws.update("F2", '=IF($A2="", "", COUNTIF(Holdings!A$2:A, $A2))', raw=False)
        ws.update("G2", '=IF($A2="", "", MAX(B$2:B2))', raw=False)
        ws.update(
            "H2",
            '=IF(OR($A2="", G2=0), "", (1-B2/G2)*100)',
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
        """Create Allocation sheet with latest-snapshot weight formulas."""
        headers = ["instrument", "current_value", "weight_pct"]
        ws = self._get_or_create_plain_worksheet("Allocation")

        ws.update("A1:C1", [headers])

        # Helper cells for latest date / total value
        ws.update("E1", "latest_date")
        ws.update("E2", "=MAX(Holdings!A2:A)", raw=False)
        ws.update("E3", "total_value")
        ws.update(
            "E4",
            "=SUMPRODUCT((Holdings!A2:A=$E$2)*Holdings!F2:F)",
            raw=False,
        )

        # Sorted allocation
        ws.update(
            "A2",
            "=SORT(FILTER({Holdings!B2:B, Holdings!F2:F}, Holdings!A2:A=$E$2), 2, FALSE)",
            raw=False,
        )
        ws.update(
            "C2",
            '=IF(A2="", "", B2/$E$4*100)',
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
        ws.update("A1:A14", labels[:14])

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
            ['=IFERROR(SUMPRODUCT(FILTER(Allocation!C2:C, Allocation!C2:C<>"")^2/10000), "")'],
            [
                "=IFERROR(SUM(LARGE("
                'FILTER(Allocation!C2:C, Allocation!C2:C<>""), {1,2,3,4,5})),'
                ' IFERROR(SUM(FILTER(Allocation!C2:C, Allocation!C2:C<>"")), ""))'
            ],
        ]
        ws.update("B1:B14", formulas[:14], raw=False)

        _format_header_row(ws, 2)
        ws.freeze(rows=1)
        print("Dashboard sheet configured.")

    def setup_charts(self) -> None:
        """Create or update formula-based charts via Sheets API batchUpdate."""
        ph_id = self._get_sheet_id("Portfolio History")
        al_id = self._get_sheet_id("Allocation")
        dash_id = self._get_sheet_id("Dashboard")
        if ph_id is None or al_id is None or dash_id is None:
            return

        existing = self._find_existing_charts()
        requests: list[dict] = []

        chart_specs = [
            self._portfolio_value_vs_cost_spec(ph_id),
            self._drawdown_formula_spec(ph_id),
            self._pnl_over_time_spec(ph_id),
            self._allocation_formula_spec(al_id),
        ]

        for title, spec, anchor_sheet_id, anchor_col in chart_specs:
            if title in existing:
                requests.append(
                    {
                        "updateChartSpec": {
                            "chartId": existing[title],
                            "spec": spec,
                        }
                    }
                )
            else:
                requests.append(
                    {
                        "addChart": {
                            "chart": {
                                "spec": spec,
                                "position": {
                                    "overlayPosition": {
                                        "anchorCell": {
                                            "sheetId": anchor_sheet_id,
                                            "rowIndex": 0,
                                            "columnIndex": anchor_col,
                                        }
                                    }
                                },
                            }
                        }
                    }
                )

        if requests:
            self._spreadsheet.batch_update({"requests": requests})
        print("Charts configured.")

    @staticmethod
    def _portfolio_value_vs_cost_spec(sheet_id: int) -> tuple[str, dict, int, int]:
        title = "Portfolio Value vs Cost"
        spec = {
            "title": title,
            "basicChart": {
                "chartType": "LINE",
                "legendPosition": "BOTTOM_LEGEND",
                "domains": [
                    {
                        "domain": {
                            "sourceRange": {
                                "sources": [
                                    {
                                        "sheetId": sheet_id,
                                        "startRowIndex": 0,
                                        "endRowIndex": 1000,
                                        "startColumnIndex": 0,
                                        "endColumnIndex": 1,
                                    }
                                ]
                            }
                        }
                    }
                ],
                "series": [
                    {
                        "series": {
                            "sourceRange": {
                                "sources": [
                                    {
                                        "sheetId": sheet_id,
                                        "startRowIndex": 0,
                                        "endRowIndex": 1000,
                                        "startColumnIndex": 1,
                                        "endColumnIndex": 2,
                                    }
                                ]
                            }
                        },
                        "targetAxis": "LEFT_AXIS",
                    },
                    {
                        "series": {
                            "sourceRange": {
                                "sources": [
                                    {
                                        "sheetId": sheet_id,
                                        "startRowIndex": 0,
                                        "endRowIndex": 1000,
                                        "startColumnIndex": 2,
                                        "endColumnIndex": 3,
                                    }
                                ]
                            }
                        },
                        "targetAxis": "LEFT_AXIS",
                    },
                ],
                "headerCount": 1,
            },
        }
        return title, spec, sheet_id, 9

    @staticmethod
    def _drawdown_formula_spec(sheet_id: int) -> tuple[str, dict, int, int]:
        title = "Drawdown"
        spec = {
            "title": title,
            "basicChart": {
                "chartType": "AREA",
                "legendPosition": "BOTTOM_LEGEND",
                "domains": [
                    {
                        "domain": {
                            "sourceRange": {
                                "sources": [
                                    {
                                        "sheetId": sheet_id,
                                        "startRowIndex": 0,
                                        "endRowIndex": 1000,
                                        "startColumnIndex": 0,
                                        "endColumnIndex": 1,
                                    }
                                ]
                            }
                        }
                    }
                ],
                "series": [
                    {
                        "series": {
                            "sourceRange": {
                                "sources": [
                                    {
                                        "sheetId": sheet_id,
                                        "startRowIndex": 0,
                                        "endRowIndex": 1000,
                                        "startColumnIndex": 7,
                                        "endColumnIndex": 8,
                                    }
                                ]
                            }
                        },
                        "targetAxis": "LEFT_AXIS",
                        "colorStyle": {"rgbColor": {"red": 0.8, "green": 0.0, "blue": 0.0}},
                    }
                ],
                "headerCount": 1,
            },
        }
        return title, spec, sheet_id, 9

    @staticmethod
    def _pnl_over_time_spec(sheet_id: int) -> tuple[str, dict, int, int]:
        title = "P&L Over Time"
        spec = {
            "title": title,
            "basicChart": {
                "chartType": "LINE",
                "legendPosition": "BOTTOM_LEGEND",
                "domains": [
                    {
                        "domain": {
                            "sourceRange": {
                                "sources": [
                                    {
                                        "sheetId": sheet_id,
                                        "startRowIndex": 0,
                                        "endRowIndex": 1000,
                                        "startColumnIndex": 0,
                                        "endColumnIndex": 1,
                                    }
                                ]
                            }
                        }
                    }
                ],
                "series": [
                    {
                        "series": {
                            "sourceRange": {
                                "sources": [
                                    {
                                        "sheetId": sheet_id,
                                        "startRowIndex": 0,
                                        "endRowIndex": 1000,
                                        "startColumnIndex": 3,
                                        "endColumnIndex": 4,
                                    }
                                ]
                            }
                        },
                        "targetAxis": "LEFT_AXIS",
                    }
                ],
                "headerCount": 1,
            },
        }
        return title, spec, sheet_id, 9

    @staticmethod
    def _allocation_formula_spec(sheet_id: int) -> tuple[str, dict, int, int]:
        title = "Allocation"
        spec = {
            "title": title,
            "pieChart": {
                "legendPosition": "RIGHT_LEGEND",
                "domain": {
                    "sourceRange": {
                        "sources": [
                            {
                                "sheetId": sheet_id,
                                "startRowIndex": 0,
                                "endRowIndex": 1000,
                                "startColumnIndex": 0,
                                "endColumnIndex": 1,
                            }
                        ]
                    }
                },
                "series": {
                    "sourceRange": {
                        "sources": [
                            {
                                "sheetId": sheet_id,
                                "startRowIndex": 0,
                                "endRowIndex": 1000,
                                "startColumnIndex": 2,
                                "endColumnIndex": 3,
                            }
                        ]
                    }
                },
                "pieHole": 0.4,
            },
        }
        return title, spec, sheet_id, 4

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
