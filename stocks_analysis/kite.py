import re

KITE_LOGIN_URL = "https://kite.zerodha.com/"
KITE_HOLDINGS_URL = "https://kite.zerodha.com/holdings"
_POST_LOGIN_URL_PATTERN = re.compile(r"https://kite\.zerodha\.com/(dashboard|holdings|positions)")


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
