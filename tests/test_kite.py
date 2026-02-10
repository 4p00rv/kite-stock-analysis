from unittest.mock import MagicMock

from stocks_analysis.kite import (
    KITE_HOLDINGS_URL,
    KITE_LOGIN_URL,
    KiteFetcher,
    _POST_LOGIN_URL_PATTERN,
    parse_holding_row,
)


class TestKiteFetcherInit:
    def test_accepts_page_object(self) -> None:
        page = MagicMock()
        fetcher = KiteFetcher(page)
        assert fetcher.page is page


class TestOpenLoginPage:
    def test_calls_goto_with_login_url(self) -> None:
        page = MagicMock()
        fetcher = KiteFetcher(page)
        fetcher.open_login_page()
        page.goto.assert_called_once_with(KITE_LOGIN_URL)


class TestWaitForLogin:
    def test_calls_wait_for_url_with_default_timeout(self) -> None:
        page = MagicMock()
        fetcher = KiteFetcher(page)
        fetcher.wait_for_login()
        page.wait_for_url.assert_called_once_with(
            _POST_LOGIN_URL_PATTERN, timeout=300_000
        )

    def test_calls_wait_for_url_with_custom_timeout(self) -> None:
        page = MagicMock()
        fetcher = KiteFetcher(page)
        fetcher.wait_for_login(timeout_ms=60_000)
        page.wait_for_url.assert_called_once_with(
            _POST_LOGIN_URL_PATTERN, timeout=60_000
        )


class TestNavigateToHoldings:
    def test_goes_to_holdings_url(self) -> None:
        page = MagicMock()
        fetcher = KiteFetcher(page)
        fetcher.navigate_to_holdings()
        page.goto.assert_called_once_with(KITE_HOLDINGS_URL)

    def test_waits_for_network_idle(self) -> None:
        page = MagicMock()
        fetcher = KiteFetcher(page)
        fetcher.navigate_to_holdings()
        page.wait_for_load_state.assert_called_once_with("networkidle")


class TestParseHoldingRow:
    def test_standard_row_with_commas_and_signs(self) -> None:
        row_data = {
            "instrument": "RELIANCE",
            "quantity": "10",
            "avg_cost": "2,450.50",
            "ltp": "2,500.00",
            "current_value": "25,000.00",
            "pnl": "+495.00",
            "pnl_percent": "+2.02%",
            "day_change": "+15.00",
            "day_change_percent": "+0.60%",
        }
        h = parse_holding_row(row_data)
        assert h.instrument == "RELIANCE"
        assert h.quantity == 10
        assert h.avg_cost == 2450.50
        assert h.ltp == 2500.00
        assert h.current_value == 25000.00
        assert h.pnl == 495.00
        assert h.pnl_percent == 2.02
        assert h.day_change == 15.00
        assert h.day_change_percent == 0.60
        assert h.exchange == "NSE"

    def test_negative_pnl(self) -> None:
        row_data = {
            "instrument": "INFY",
            "quantity": "5",
            "avg_cost": "1,800.00",
            "ltp": "1,750.00",
            "current_value": "8,750.00",
            "pnl": "-250.00",
            "pnl_percent": "-2.78%",
            "day_change": "-30.00",
            "day_change_percent": "-1.69%",
        }
        h = parse_holding_row(row_data)
        assert h.instrument == "INFY"
        assert h.pnl == -250.00
        assert h.pnl_percent == -2.78
        assert h.day_change == -30.00
        assert h.day_change_percent == -1.69

    def test_no_commas_simple_values(self) -> None:
        row_data = {
            "instrument": "ITC",
            "quantity": "100",
            "avg_cost": "450.00",
            "ltp": "460.00",
            "current_value": "46000.00",
            "pnl": "1000.00",
            "pnl_percent": "2.22%",
            "day_change": "5.00",
            "day_change_percent": "1.10%",
        }
        h = parse_holding_row(row_data)
        assert h.instrument == "ITC"
        assert h.quantity == 100
        assert h.avg_cost == 450.00
