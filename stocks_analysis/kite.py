import logging
import re

from stocks_analysis.models import Holding

logger = logging.getLogger(__name__)

KITE_LOGIN_URL = "https://kite.zerodha.com/"
KITE_HOLDINGS_URL = "https://kite.zerodha.com/holdings"
_POST_LOGIN_URL_PATTERN = re.compile(r"https://kite\.zerodha\.com/(dashboard|holdings|positions)")

# Placeholder selectors — calibrate against real Kite DOM on first run
_HOLDINGS_ROW_SELECTOR = "table.holdings tbody tr"
_COLUMN_MAP = [
    "instrument",
    "quantity",
    "avg_cost",
    "ltp",
    "current_value",
    "pnl",
    "pnl_percent",
    "day_change",
    "day_change_percent",
]


def _clean_number(text: str) -> float:
    cleaned = text.replace(",", "").replace("%", "").replace("+", "").strip()
    return float(cleaned)


def parse_holding_row(row_data: dict[str, str]) -> Holding:
    return Holding(
        instrument=row_data["instrument"].strip(),
        quantity=int(row_data["quantity"].replace(",", "")),
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

    def wait_for_login(self, timeout_ms: int = 300_000) -> None:
        self.page.wait_for_url(_POST_LOGIN_URL_PATTERN, timeout=timeout_ms)

    def navigate_to_holdings(self) -> None:
        self.page.goto(KITE_HOLDINGS_URL)
        self.page.wait_for_load_state("networkidle")

    def fetch_holdings(self) -> list[Holding]:
        rows = self.page.query_selector_all(_HOLDINGS_ROW_SELECTOR)
        holdings: list[Holding] = []
        for row in rows:
            try:
                cells = row.query_selector_all("td")
                if len(cells) < len(_COLUMN_MAP):
                    continue
                row_data = {key: cells[i].inner_text() for i, key in enumerate(_COLUMN_MAP)}
                holdings.append(parse_holding_row(row_data))
            except (ValueError, KeyError, IndexError):
                logger.warning("Skipping malformed row", exc_info=True)
        return holdings
