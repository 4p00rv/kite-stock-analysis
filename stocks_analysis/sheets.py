from __future__ import annotations

import os
from collections import defaultdict
from datetime import date

import gspread
from gspread.utils import rowcol_to_a1

from stocks_analysis.models import AnalysisResult, DailyPortfolioValue, Holding, PortfolioSummary

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

    def upload_daily_values(
        self,
        series: list[DailyPortfolioValue],
        benchmark_prices: dict[date, float],
    ) -> None:
        """Upload daily portfolio values with benchmark comparison and drawdown."""
        headers = ["date", "portfolio_value", "benchmark_value_rebased", "drawdown_pct"]
        ws = self._get_or_create_worksheet("Daily Values", headers)

        # Rebase benchmark to 100
        bench_dates = sorted(benchmark_prices.keys())
        first_bench = benchmark_prices[bench_dates[0]] if bench_dates else 1.0

        # Compute drawdown
        running_max = 0.0
        rows: list[list[object]] = []
        for dpv in series:
            if dpv.total_value > running_max:
                running_max = dpv.total_value
            dd_pct = (1.0 - dpv.total_value / running_max) * 100 if running_max > 0 else 0.0

            bench_val = benchmark_prices.get(dpv.date)
            bench_rebased = (bench_val / first_bench * 100) if bench_val and first_bench > 0 else ""

            # Delete existing rows for this date
            self._delete_rows_for_date(ws, dpv.date.isoformat())
            rows.append(
                [
                    dpv.date.isoformat(),
                    round(dpv.total_value, 2),
                    round(bench_rebased, 2) if isinstance(bench_rebased, float) else "",
                    round(dd_pct, 2),
                ]
            )

        if rows:
            ws.append_rows(rows)
            _format_header_row(ws, len(headers))

    def upload_rolling_returns(self, series: list[DailyPortfolioValue]) -> None:
        """Upload rolling return windows (30d, 90d, 1yr)."""
        headers = ["date", "30d_return", "90d_return", "1yr_return"]
        ws = self._get_or_create_worksheet("Rolling Returns", headers)

        rows: list[list[object]] = []
        for i, dpv in enumerate(series):
            r30 = self._rolling_return(series, i, 30)
            r90 = self._rolling_return(series, i, 90)
            r365 = self._rolling_return(series, i, 365)
            rows.append(
                [
                    dpv.date.isoformat(),
                    round(r30 * 100, 2) if r30 is not None else "",
                    round(r90 * 100, 2) if r90 is not None else "",
                    round(r365 * 100, 2) if r365 is not None else "",
                ]
            )

        if rows:
            ws.append_rows(rows)
            _format_header_row(ws, len(headers))

    @staticmethod
    def _rolling_return(series: list[DailyPortfolioValue], idx: int, window: int) -> float | None:
        """Compute rolling return for a given window size ending at idx."""
        start_idx = idx - window
        if start_idx < 0:
            return None
        start_val = series[start_idx].total_value
        if start_val <= 0:
            return None
        return (series[idx].total_value - start_val) / start_val

    def upload_monthly_returns(self, series: list[DailyPortfolioValue]) -> None:
        """Upload monthly returns in pivot table format (year × month)."""
        headers = [
            "year",
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
            "YTD",
        ]
        ws = self._get_or_create_worksheet("Monthly Returns", headers)

        # Group values by (year, month) → take first and last value
        monthly: dict[tuple[int, int], tuple[float, float]] = {}
        for dpv in series:
            key = (dpv.date.year, dpv.date.month)
            if key not in monthly:
                monthly[key] = (dpv.total_value, dpv.total_value)
            else:
                monthly[key] = (monthly[key][0], dpv.total_value)

        # Group by year
        years: dict[int, dict[int, float]] = defaultdict(dict)
        for (yr, mo), (first_val, last_val) in monthly.items():
            if first_val > 0:
                years[yr][mo] = (last_val - first_val) / first_val * 100

        # Year-start values for YTD
        year_start: dict[int, float] = {}
        for dpv in series:
            if dpv.date.year not in year_start:
                year_start[dpv.date.year] = dpv.total_value

        year_end: dict[int, float] = {}
        for dpv in series:
            year_end[dpv.date.year] = dpv.total_value

        rows: list[list[object]] = [[yr] for yr in sorted(years.keys())]
        for row in rows:
            yr = row[0]
            for mo in range(1, 13):
                row.append(round(years[yr].get(mo, 0.0), 2) if mo in years[yr] else "")
            start = year_start.get(yr, 0)
            end = year_end.get(yr, 0)
            ytd = round((end - start) / start * 100, 2) if start > 0 else ""
            row.append(ytd)

        # Write all at once (overwrite data area)
        if rows:
            ws.update(f"A2:{_col_letter(len(headers))}{1 + len(rows)}", rows)
            _format_header_row(ws, len(headers))

    def upload_allocation(self, holdings: list[Holding]) -> None:
        """Upload current allocation (top 10 + Others)."""
        headers = ["instrument", "weight_pct", "current_value"]
        ws = self._get_or_create_worksheet("Allocation", headers)

        total = sum(h.current_value for h in holdings)
        if total <= 0:
            return

        sorted_h = sorted(holdings, key=lambda h: h.current_value, reverse=True)
        rows: list[list[object]] = []
        others_value = 0.0
        for i, h in enumerate(sorted_h):
            if i < 10:
                rows.append(
                    [
                        h.instrument,
                        round(h.current_value / total * 100, 2),
                        round(h.current_value, 2),
                    ]
                )
            else:
                others_value += h.current_value

        if others_value > 0:
            rows.append(["Others", round(others_value / total * 100, 2), round(others_value, 2)])

        ws.update(f"A2:{_col_letter(len(headers))}{1 + len(rows)}", rows)
        _format_header_row(ws, len(headers))

    def upload_metrics(self, result: AnalysisResult) -> None:
        """Upload a single metrics row."""
        headers = [
            "date",
            "xirr",
            "twr_annualized",
            "benchmark_twr",
            "alpha",
            "beta",
            "sharpe",
            "sortino",
            "max_drawdown",
            "var_95_pct",
            "herfindahl",
            "top_5_concentration",
        ]
        ws = self._get_or_create_worksheet("Metrics", headers)
        row = [
            result.end_date.isoformat(),
            round(result.xirr * 100, 2),
            round(result.twr_annualized * 100, 2),
            round(result.benchmark_twr * 100, 2),
            round(result.alpha * 100, 2),
            round(result.beta, 2),
            round(result.sharpe, 2),
            round(result.sortino, 2),
            round(result.max_drawdown * 100, 2),
            round(result.var_95_pct, 2),
            round(result.herfindahl, 4),
            round(result.top_5_concentration * 100, 2),
        ]
        ws.update(f"A2:{_col_letter(len(headers))}2", [row])
        _format_header_row(ws, len(headers))

    # ------------------------------------------------------------------
    # Charts + Slicer
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

    def create_or_update_charts(
        self,
        daily_values_rows: int,
        rolling_returns_rows: int,
        allocation_rows: int,
    ) -> None:
        """Create or update all analysis charts via Sheets API batchUpdate."""
        dv_id = self._get_sheet_id("Daily Values")
        rr_id = self._get_sheet_id("Rolling Returns")
        al_id = self._get_sheet_id("Allocation")
        if dv_id is None or rr_id is None or al_id is None:
            return

        existing = self._find_existing_charts()
        requests: list[dict] = []

        chart_specs = [
            self._portfolio_vs_benchmark_spec(dv_id, daily_values_rows),
            self._drawdown_spec(dv_id, daily_values_rows),
            self._rolling_returns_spec(rr_id, rolling_returns_rows),
            self._allocation_spec(al_id, allocation_rows),
        ]

        for title, spec, anchor_sheet_id, anchor_offset in chart_specs:
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
                                            "columnIndex": anchor_offset,
                                        }
                                    }
                                },
                            }
                        }
                    }
                )

        if requests:
            self._spreadsheet.batch_update({"requests": requests})

    @staticmethod
    def _portfolio_vs_benchmark_spec(sheet_id: int, num_rows: int) -> tuple[str, dict, int, int]:
        title = "Portfolio vs Benchmark"
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
                                        "endRowIndex": num_rows + 1,
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
                                        "endRowIndex": num_rows + 1,
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
                                        "endRowIndex": num_rows + 1,
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
        return title, spec, sheet_id, 5

    @staticmethod
    def _drawdown_spec(sheet_id: int, num_rows: int) -> tuple[str, dict, int, int]:
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
                                        "endRowIndex": num_rows + 1,
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
                                        "endRowIndex": num_rows + 1,
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
        return title, spec, sheet_id, 5

    @staticmethod
    def _rolling_returns_spec(sheet_id: int, num_rows: int) -> tuple[str, dict, int, int]:
        title = "Rolling Returns"
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
                                        "endRowIndex": num_rows + 1,
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
                                        "endRowIndex": num_rows + 1,
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
                                        "endRowIndex": num_rows + 1,
                                        "startColumnIndex": 2,
                                        "endColumnIndex": 3,
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
                                        "endRowIndex": num_rows + 1,
                                        "startColumnIndex": 3,
                                        "endColumnIndex": 4,
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
        return title, spec, sheet_id, 5

    @staticmethod
    def _allocation_spec(sheet_id: int, num_rows: int) -> tuple[str, dict, int, int]:
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
                                "endRowIndex": num_rows + 1,
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
                                "endRowIndex": num_rows + 1,
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

    def create_date_slicer(self, num_rows: int) -> None:
        """Create a date slicer on the Daily Values sheet."""
        dv_id = self._get_sheet_id("Daily Values")
        if dv_id is None:
            return

        # Check for existing slicers
        metadata = self._spreadsheet.fetch_sheet_metadata()
        for sheet in metadata.get("sheets", []):
            if sheet["properties"]["sheetId"] == dv_id and sheet.get("slicers"):
                return  # Already has a slicer

        self._spreadsheet.batch_update(
            {
                "requests": [
                    {
                        "addSlicer": {
                            "slicer": {
                                "spec": {
                                    "dataRange": {
                                        "sheetId": dv_id,
                                        "startRowIndex": 0,
                                        "endRowIndex": num_rows + 1,
                                        "startColumnIndex": 0,
                                        "endColumnIndex": 1,
                                    },
                                    "columnIndex": 0,
                                    "applyToPivotTables": False,
                                },
                                "position": {
                                    "overlayPosition": {
                                        "anchorCell": {
                                            "sheetId": dv_id,
                                            "rowIndex": 0,
                                            "columnIndex": 5,
                                        }
                                    }
                                },
                            }
                        }
                    }
                ]
            }
        )


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
