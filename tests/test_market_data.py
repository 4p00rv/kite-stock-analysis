from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from stocks_analysis.market_data import MarketDataClient, nse_to_yfinance_ticker


class TestNseToYfinanceTicker:
    def test_nse_stock(self) -> None:
        assert nse_to_yfinance_ticker("RELIANCE", "NSE") == "RELIANCE.NS"

    def test_bse_stock(self) -> None:
        assert nse_to_yfinance_ticker("RELIANCE", "BSE") == "RELIANCE.BO"

    def test_default_exchange_is_nse(self) -> None:
        assert nse_to_yfinance_ticker("TCS") == "TCS.NS"

    def test_benchmark_nifty(self) -> None:
        assert nse_to_yfinance_ticker("NIFTY 50") == "^NSEI"

    def test_strips_whitespace(self) -> None:
        assert nse_to_yfinance_ticker(" RELIANCE ") == "RELIANCE.NS"


class TestMarketDataClient:
    def test_get_daily_prices_returns_dict(self) -> None:
        mock_data = pd.DataFrame(
            {"Close": [100.0, 101.0, 102.0]},
            index=pd.to_datetime(["2025-01-15", "2025-01-16", "2025-01-17"]),
        )
        with patch("stocks_analysis.market_data.yf") as mock_yf:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = mock_data
            mock_yf.Ticker.return_value = mock_ticker
            client = MarketDataClient(cache_dir=None)
            prices = client.get_daily_prices("RELIANCE.NS", date(2025, 1, 15), date(2025, 1, 17))

        assert len(prices) == 3
        assert prices[date(2025, 1, 15)] == pytest.approx(100.0)
        assert prices[date(2025, 1, 17)] == pytest.approx(102.0)

    def test_get_daily_prices_empty_on_error(self) -> None:
        with patch("stocks_analysis.market_data.yf") as mock_yf:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = pd.DataFrame()
            mock_yf.Ticker.return_value = mock_ticker
            client = MarketDataClient(cache_dir=None)
            prices = client.get_daily_prices("INVALID.NS", date(2025, 1, 15), date(2025, 1, 17))

        assert prices == {}

    def test_get_multiple_prices(self) -> None:
        rel_data = pd.DataFrame(
            {"Close": [100.0, 101.0]},
            index=pd.to_datetime(["2025-01-15", "2025-01-16"]),
        )
        tcs_data = pd.DataFrame(
            {"Close": [200.0, 201.0]},
            index=pd.to_datetime(["2025-01-15", "2025-01-16"]),
        )

        def fake_history(**kwargs: object) -> pd.DataFrame:
            return fake_history._next.pop(0)

        fake_history._next = [rel_data, tcs_data]

        with patch("stocks_analysis.market_data.yf") as mock_yf:
            mock_ticker = MagicMock()
            mock_ticker.history = fake_history
            mock_yf.Ticker.return_value = mock_ticker
            client = MarketDataClient(cache_dir=None)
            result = client.get_multiple_prices(
                ["RELIANCE.NS", "TCS.NS"], date(2025, 1, 15), date(2025, 1, 16)
            )

        assert "RELIANCE.NS" in result
        assert "TCS.NS" in result
        assert result["RELIANCE.NS"][date(2025, 1, 15)] == pytest.approx(100.0)
        assert result["TCS.NS"][date(2025, 1, 16)] == pytest.approx(201.0)

    def test_get_benchmark_prices(self) -> None:
        mock_data = pd.DataFrame(
            {"Close": [22000.0, 22100.0]},
            index=pd.to_datetime(["2025-01-15", "2025-01-16"]),
        )
        with patch("stocks_analysis.market_data.yf") as mock_yf:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = mock_data
            mock_yf.Ticker.return_value = mock_ticker
            client = MarketDataClient(cache_dir=None)
            prices = client.get_benchmark_prices(date(2025, 1, 15), date(2025, 1, 16))

        assert len(prices) == 2
        assert prices[date(2025, 1, 15)] == pytest.approx(22000.0)

    def test_cache_dir_used_when_provided(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / ".price_cache"
        mock_data = pd.DataFrame(
            {"Close": [100.0]},
            index=pd.to_datetime(["2025-01-15"]),
        )
        with patch("stocks_analysis.market_data.yf") as mock_yf:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = mock_data
            mock_yf.Ticker.return_value = mock_ticker
            client = MarketDataClient(cache_dir=cache_dir)
            # First call - fetches from yfinance and caches
            prices1 = client.get_daily_prices("RELIANCE.NS", date(2025, 1, 15), date(2025, 1, 15))
            assert len(prices1) == 1
            # Cache file should exist
            assert cache_dir.exists()
            cached_files = list(cache_dir.glob("*.csv"))
            assert len(cached_files) == 1

            # Second call - should use cache (reset mock to return empty)
            mock_ticker.history.return_value = pd.DataFrame()
            prices2 = client.get_daily_prices("RELIANCE.NS", date(2025, 1, 15), date(2025, 1, 15))
            assert prices2[date(2025, 1, 15)] == pytest.approx(100.0)
