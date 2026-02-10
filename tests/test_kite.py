from unittest.mock import MagicMock

from stocks_analysis.kite import (
    KITE_HOLDINGS_URL,
    KITE_LOGIN_URL,
    KiteFetcher,
    _POST_LOGIN_URL_PATTERN,
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
