from __future__ import annotations

import csv
import logging
from datetime import date, timedelta
from pathlib import Path

import yfinance as yf

logger = logging.getLogger(__name__)

BENCHMARK_TICKER = "^NSEI"

_SPECIAL_TICKERS: dict[str, str] = {
    "NIFTY 50": "^NSEI",
    "NIFTY50": "^NSEI",
}


def nse_to_yfinance_ticker(instrument: str, exchange: str = "NSE") -> str:
    """Convert an NSE/BSE instrument name to a yfinance ticker symbol."""
    instrument = instrument.strip()
    if instrument in _SPECIAL_TICKERS:
        return _SPECIAL_TICKERS[instrument]
    suffix = ".BO" if exchange == "BSE" else ".NS"
    return f"{instrument}{suffix}"


class MarketDataClient:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache_dir = cache_dir

    def _cache_path(self, ticker: str) -> Path | None:
        if self._cache_dir is None:
            return None
        return self._cache_dir / f"{ticker.replace('^', '_').replace('.', '_')}.csv"

    def _read_cache(self, ticker: str) -> dict[date, float]:
        path = self._cache_path(ticker)
        if path is None or not path.exists():
            return {}
        prices: dict[date, float] = {}
        with open(path, newline="") as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if len(row) >= 2:
                    prices[date.fromisoformat(row[0])] = float(row[1])
        return prices

    def _write_cache(self, ticker: str, prices: dict[date, float]) -> None:
        path = self._cache_path(ticker)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "close"])
            for dt in sorted(prices):
                writer.writerow([dt.isoformat(), prices[dt]])

    def get_daily_prices(self, ticker: str, start: date, end: date) -> dict[date, float]:
        """Fetch daily closing prices for a ticker between start and end dates."""
        cached = self._read_cache(ticker)
        # Check if cache covers the requested range
        if cached:
            cached_in_range = {d: p for d, p in cached.items() if start <= d <= end}
            if cached_in_range:
                return cached_in_range

        try:
            t = yf.Ticker(ticker)
            # Add a day buffer to end to ensure we get the end date
            df = t.history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat())
            if df.empty:
                return {}
            prices: dict[date, float] = {}
            for ts, row in df.iterrows():
                dt = ts.date() if hasattr(ts, "date") else ts
                prices[dt] = float(row["Close"])

            # Merge with cache and save
            if self._cache_dir is not None:
                merged = {**cached, **prices}
                self._write_cache(ticker, merged)

            return {d: p for d, p in prices.items() if start <= d <= end}
        except Exception:
            logger.warning("Failed to fetch prices for %s", ticker, exc_info=True)
            return {}

    def get_multiple_prices(
        self, tickers: list[str], start: date, end: date
    ) -> dict[str, dict[date, float]]:
        """Fetch daily prices for multiple tickers."""
        result: dict[str, dict[date, float]] = {}
        for ticker in tickers:
            prices = self.get_daily_prices(ticker, start, end)
            if prices:
                result[ticker] = prices
        return result

    def get_benchmark_prices(self, start: date, end: date) -> dict[date, float]:
        """Fetch Nifty 50 daily prices."""
        return self.get_daily_prices(BENCHMARK_TICKER, start, end)
