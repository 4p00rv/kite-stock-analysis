from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stocks_analysis.sheets.client import SheetsClient


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
                            "startColumnIndex": 3,  # D = weight_pct
                            "endColumnIndex": 4,
                        }
                    ]
                }
            },
            "pieHole": 0.4,
        },
    }
    return title, spec, sheet_id, 7


def _stock_performance_spec(sheet_id: int) -> tuple[str, dict, int, int]:
    title = "Stock Performance"
    spec = {
        "title": title,
        "basicChart": {
            "chartType": "BAR",
            "legendPosition": "NO_LEGEND",
            "domains": [
                {
                    "domain": {
                        "sourceRange": {
                            "sources": [
                                {
                                    "sheetId": sheet_id,
                                    "startRowIndex": 0,
                                    "endRowIndex": 1000,
                                    "startColumnIndex": 0,  # A = instrument
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
                                    "startColumnIndex": 5,  # F = return_pct
                                    "endColumnIndex": 6,
                                }
                            ]
                        }
                    },
                    "targetAxis": "BOTTOM_AXIS",
                }
            ],
            "headerCount": 1,
        },
    }
    return title, spec, sheet_id, 7


def setup_charts(client: SheetsClient) -> None:
    """Create or update formula-based charts via Sheets API batchUpdate."""
    ph_id = client._get_sheet_id("Portfolio History")
    al_id = client._get_sheet_id("Allocation")
    dash_id = client._get_sheet_id("Dashboard")
    if ph_id is None or al_id is None or dash_id is None:
        return

    existing = client._find_existing_charts()
    requests: list[dict] = []

    chart_specs = [
        _portfolio_value_vs_cost_spec(ph_id),
        _drawdown_formula_spec(ph_id),
        _pnl_over_time_spec(ph_id),
        _allocation_formula_spec(al_id),
        _stock_performance_spec(al_id),
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
        client._spreadsheet.batch_update({"requests": requests})
    print("Charts configured.")
