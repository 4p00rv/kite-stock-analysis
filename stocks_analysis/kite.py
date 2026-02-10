import re

from stocks_analysis.models import Holding

KITE_LOGIN_URL = "https://kite.zerodha.com/"
KITE_HOLDINGS_URL = "https://kite.zerodha.com/holdings"
_POST_LOGIN_URL_PATTERN = re.compile(
    r"https://kite\.zerodha\.com/(dashboard|holdings|positions)"
)


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
