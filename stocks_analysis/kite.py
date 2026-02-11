import logging
import re

from stocks_analysis.models import Holding

logger = logging.getLogger(__name__)

KITE_LOGIN_URL = "https://kite.zerodha.com/"
KITE_HOLDINGS_URL = "https://kite.zerodha.com/holdings"
_POST_LOGIN_URL_PATTERN = re.compile(r"https://kite\.zerodha\.com/(dashboard|holdings|positions)")

# Calibrated against Kite's holdings page DOM
_HOLDINGS_ROW_SELECTOR = ".holdings-table tbody tr"
_DATA_LABELS: dict[str, str] = {
    "Instrument": "instrument",
    "Qty.": "quantity",
    "Avg. cost": "avg_cost",
    "LTP": "ltp",
    "Cur. val": "current_value",
    "P&L": "pnl",
    "Net chg.": "pnl_percent",
    "Day chg.": "day_change_percent",
}


def _parse_quantity(text: str) -> int:
    """Parse quantity text that may contain T1/T2 settlement annotations.

    Kite shows settlement info in the Qty cell, e.g. "T1: 3 3" where
    3 shares are awaiting T1 delivery and 3 are settled. Total = 6.
    """
    # Strip T-day labels (T1:, T2:, etc.), then sum all remaining numbers
    cleaned = re.sub(r"T\d+:", "", text)
    numbers = re.findall(r"[\d,]+", cleaned)
    return sum(int(n.replace(",", "")) for n in numbers)


def _clean_number(text: str) -> float:
    cleaned = text.replace(",", "").replace("%", "").replace("+", "").strip()
    return float(cleaned)


def _parse_tooltip_value(tooltip: str) -> str:
    """Extract absolute value from tooltip like '-22.72 (-0.13%)'."""
    return tooltip.split("(")[0].strip() if tooltip else "0"


def _extract_row_data(row: object) -> dict[str, str]:
    """Extract holding data from a table row element using data-label selectors."""
    data: dict[str, str] = {}
    for label, field in _DATA_LABELS.items():
        cell = row.query_selector(f'td[data-label="{label}"]')
        if cell is None:
            raise ValueError(f"Missing cell: {label}")
        if label == "Instrument":
            name_el = cell.query_selector("a span:first-child")
            data[field] = (name_el or cell).inner_text().strip()
        else:
            data[field] = cell.inner_text().strip()

    # day_change absolute value from Day chg. tooltip
    tooltip_el = row.query_selector('td[data-label="Day chg."] span[data-tooltip-content]')
    if tooltip_el:
        tooltip = tooltip_el.get_attribute("data-tooltip-content") or ""
        data["day_change"] = _parse_tooltip_value(tooltip)
    else:
        data["day_change"] = "0"

    return data


def parse_holding_row(row_data: dict[str, str]) -> Holding:
    return Holding(
        instrument=row_data["instrument"].strip(),
        quantity=_parse_quantity(row_data["quantity"]),
        avg_cost=_clean_number(row_data["avg_cost"]),
        ltp=_clean_number(row_data["ltp"]),
        current_value=_clean_number(row_data["current_value"]),
        pnl=_clean_number(row_data["pnl"]),
        pnl_percent=_clean_number(row_data["pnl_percent"]),
        day_change=_clean_number(row_data["day_change"]),
        day_change_percent=_clean_number(row_data["day_change_percent"]),
    )


class KiteFetcher:
    def __init__(self, page: object) -> None:
        self.page = page

    def open_login_page(self) -> None:
        self.page.goto(KITE_LOGIN_URL)

    def fill_login_credentials(self, user_id: str, password: str) -> None:
        """Auto-fill Kite login form (user ID + password). 2FA remains manual."""
        self.page.fill('input[type="text"]#userid', user_id)
        self.page.click('button[type="submit"]')
        self.page.wait_for_selector('input[type="password"]', timeout=10_000)
        self.page.fill('input[type="password"]', password)
        self.page.click('button[type="submit"]')

    def wait_for_login(self, timeout_ms: int = 300_000) -> None:
        self.page.wait_for_url(_POST_LOGIN_URL_PATTERN, timeout=timeout_ms)

    def navigate_to_holdings(self) -> None:
        self.page.goto(KITE_HOLDINGS_URL)
        self.page.wait_for_load_state("domcontentloaded")
        self.page.wait_for_selector(".holdings", timeout=30_000)
        self.page.wait_for_selector(".holdings .su-loader", state="hidden", timeout=60_000)

    def fetch_holdings(self) -> list[Holding]:
        rows = self.page.query_selector_all(_HOLDINGS_ROW_SELECTOR)
        holdings: list[Holding] = []
        for row in rows:
            try:
                row_data = _extract_row_data(row)
                holdings.append(parse_holding_row(row_data))
            except (ValueError, KeyError, IndexError):
                logger.warning("Skipping malformed row", exc_info=True)
        return holdings
