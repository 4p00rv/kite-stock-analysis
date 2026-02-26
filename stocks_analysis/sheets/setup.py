from __future__ import annotations

from typing import TYPE_CHECKING

import gspread

from stocks_analysis.sheets.formatting import _format_header_row

if TYPE_CHECKING:
    from stocks_analysis.sheets.client import SheetsClient


def _get_or_create_plain_worksheet(
    client: SheetsClient, title: str, rows: int = 1000, cols: int = 20
) -> gspread.Worksheet:
    """Get or create a worksheet without writing headers."""
    try:
        return client._spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return client._spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def setup_capital_flows_sheet(client: SheetsClient) -> None:
    """Create Capital Flows sheet with headers for manual deposit/withdrawal tracking."""
    ws = _get_or_create_plain_worksheet(client, "Capital Flows")
    headers = ["date", "type", "amount", "notes"]
    existing = ws.row_values(1)
    if existing != headers:
        ws.update([headers], range_name="A1:D1")
    _format_header_row(ws, len(headers))
    ws.freeze(rows=1)
    print("Capital Flows sheet configured.")


def setup_prices_sheet(client: SheetsClient) -> None:
    """Create Prices sheet with pivot formulas (date x instrument -> LTP)."""
    # Delete and recreate to ensure clean slate (copyPaste fails on stale sheets)
    try:
        old_ws = client._spreadsheet.worksheet("Prices")
        client._spreadsheet.del_worksheet(old_ws)
    except gspread.WorksheetNotFound:
        pass
    ws = client._spreadsheet.add_worksheet(title="Prices", rows=1000, cols=104)
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
    client._spreadsheet.batch_update(
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


def setup_portfolio_history_sheet(client: SheetsClient) -> None:
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
    ws = _get_or_create_plain_worksheet(client, "Portfolio History")
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
    client._spreadsheet.batch_update(
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


def setup_allocation_sheet(client: SheetsClient) -> None:
    """Create Allocation sheet with latest-snapshot weight and performance formulas."""
    headers = ["instrument", "current_value", "cost", "weight_pct", "pnl", "return_pct"]
    ws = _get_or_create_plain_worksheet(client, "Allocation")

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


def setup_dashboard_sheet(client: SheetsClient) -> None:
    """Create Dashboard sheet with key metrics formulas."""
    ws = _get_or_create_plain_worksheet(client, "Dashboard")

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
        ["Capital Deployed"],
        ["True P&L"],
        ["True Return %"],
    ]
    ws.update(labels[:17], range_name="A1:A17")

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
        [
            "=SUMPRODUCT(('Capital Flows'!B2:B=\"DEPOSIT\")*'Capital Flows'!C2:C)"
            " - SUMPRODUCT(('Capital Flows'!B2:B=\"WITHDRAWAL\")*'Capital Flows'!C2:C)"
        ],
        ['=IF(B2="", "", B2-B15)'],
        ['=IFERROR(B16/B15*100, "")'],
    ]
    ws.update(formulas[:17], range_name="B1:B17", raw=False)

    _format_header_row(ws, 2)
    ws.freeze(rows=1)
    print("Dashboard sheet configured.")


def setup_all(client: SheetsClient) -> None:
    """Run all setup methods to create formula-based sheets and charts."""
    from stocks_analysis.sheets.charts import setup_charts

    setup_prices_sheet(client)
    setup_portfolio_history_sheet(client)
    setup_allocation_sheet(client)
    setup_capital_flows_sheet(client)
    setup_dashboard_sheet(client)
    setup_charts(client)
    print("All formula sheets and charts configured.")
