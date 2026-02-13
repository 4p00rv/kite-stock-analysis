"""Google Sheets integration package.

Re-exports public API for backward compatibility:
    from stocks_analysis.sheets import SheetsClient, create_sheets_client
"""

from __future__ import annotations

from stocks_analysis.sheets.client import SheetsClient as SheetsClient
from stocks_analysis.sheets.client import create_sheets_client as create_sheets_client
from stocks_analysis.sheets.formatting import DATE_COLOR_A as DATE_COLOR_A
from stocks_analysis.sheets.formatting import DATE_COLOR_B as DATE_COLOR_B
from stocks_analysis.sheets.formatting import HEADER_BG as HEADER_BG
from stocks_analysis.sheets.formatting import HEADER_FG as HEADER_FG
from stocks_analysis.sheets.formatting import (
    _apply_alternating_date_colors as _apply_alternating_date_colors,
)
from stocks_analysis.sheets.formatting import _col_letter as _col_letter
from stocks_analysis.sheets.formatting import _format_header_row as _format_header_row
from stocks_analysis.sheets.formatting import _get_date_groups as _get_date_groups

__all__ = [
    "SheetsClient",
    "create_sheets_client",
    "DATE_COLOR_A",
    "DATE_COLOR_B",
    "HEADER_BG",
    "HEADER_FG",
    "_apply_alternating_date_colors",
    "_col_letter",
    "_format_header_row",
    "_get_date_groups",
]
