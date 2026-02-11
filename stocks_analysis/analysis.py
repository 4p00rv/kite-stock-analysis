from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
from scipy.optimize import brentq

from stocks_analysis.market_data import MarketDataClient, nse_to_yfinance_ticker
from stocks_analysis.models import (
    AnalysisResult,
    DailyPortfolioValue,
    Snapshot,
    SnapshotHolding,
    Transaction,
)


def parse_snapshots_from_rows(rows: list[list[str]]) -> list[Snapshot]:
    """Parse raw Holdings sheet rows into Snapshots grouped and sorted by date."""
    if not rows:
        return []

    by_date: dict[str, list[SnapshotHolding]] = defaultdict(list)
    for row in rows:
        sh = SnapshotHolding.from_sheet_row(row)
        by_date[sh.date.isoformat()].append(sh)

    snapshots = [
        Snapshot(date=holdings[0].date, holdings=holdings) for holdings in by_date.values()
    ]
    snapshots.sort(key=lambda s: s.date)
    return snapshots


def _infer_between_snapshots(prev: Snapshot, curr: Snapshot) -> list[Transaction]:
    """Compare two consecutive snapshots and infer transactions."""
    prev_map = {h.instrument: h for h in prev.holdings}
    curr_map = {h.instrument: h for h in curr.holdings}
    txns: list[Transaction] = []

    # Check for new or changed instruments
    for instrument, curr_h in curr_map.items():
        prev_h = prev_map.get(instrument)
        if prev_h is None:
            # New instrument → BUY at avg_cost
            txns.append(
                Transaction(
                    date=curr.date,
                    instrument=instrument,
                    type="BUY",
                    quantity=curr_h.quantity,
                    price=curr_h.avg_cost,
                    amount=-(curr_h.avg_cost * curr_h.quantity),
                )
            )
        elif curr_h.quantity > prev_h.quantity:
            # Quantity increased → BUY additional
            qty_diff = curr_h.quantity - prev_h.quantity
            estimated_price = (
                curr_h.avg_cost * curr_h.quantity - prev_h.avg_cost * prev_h.quantity
            ) / qty_diff
            if estimated_price <= 0:
                estimated_price = curr_h.avg_cost
            txns.append(
                Transaction(
                    date=curr.date,
                    instrument=instrument,
                    type="BUY",
                    quantity=qty_diff,
                    price=estimated_price,
                    amount=-(estimated_price * qty_diff),
                )
            )
        elif curr_h.quantity < prev_h.quantity:
            # Quantity decreased → SELL at previous LTP
            qty_diff = prev_h.quantity - curr_h.quantity
            txns.append(
                Transaction(
                    date=curr.date,
                    instrument=instrument,
                    type="SELL",
                    quantity=qty_diff,
                    price=prev_h.ltp,
                    amount=prev_h.ltp * qty_diff,
                )
            )
        # else: unchanged, no transaction

    # Check for disappeared instruments → SELL all at previous LTP
    for instrument, prev_h in prev_map.items():
        if instrument not in curr_map:
            txns.append(
                Transaction(
                    date=curr.date,
                    instrument=instrument,
                    type="SELL",
                    quantity=prev_h.quantity,
                    price=prev_h.ltp,
                    amount=prev_h.ltp * prev_h.quantity,
                )
            )

    return txns


def infer_transactions(snapshots: list[Snapshot]) -> list[Transaction]:
    """Infer all transactions from a chronologically-sorted list of snapshots."""
    if not snapshots:
        return []

    txns: list[Transaction] = []

    # First snapshot: BUY everything at avg_cost
    for h in snapshots[0].holdings:
        txns.append(
            Transaction(
                date=snapshots[0].date,
                instrument=h.instrument,
                type="BUY",
                quantity=h.quantity,
                price=h.avg_cost,
                amount=-(h.avg_cost * h.quantity),
            )
        )

    # Subsequent snapshots: diff with previous
    for i in range(1, len(snapshots)):
        txns.extend(_infer_between_snapshots(snapshots[i - 1], snapshots[i]))

    return txns


def build_daily_portfolio_series(
    snapshots: list[Snapshot],
    transactions: list[Transaction],
    prices: dict[str, dict[date, float]],
    start: date,
    end: date,
) -> list[DailyPortfolioValue]:
    """Reconstruct daily portfolio values from snapshots, transactions, and market prices."""
    if not snapshots:
        return []

    # Build a map of instrument → ticker for price lookup
    instrument_tickers: dict[str, str] = {}
    for snap in snapshots:
        for h in snap.holdings:
            if h.instrument not in instrument_tickers:
                instrument_tickers[h.instrument] = nse_to_yfinance_ticker(h.instrument, h.exchange)

    # Build LTP fallback from snapshots (instrument → date → ltp)
    ltp_fallback: dict[str, dict[date, float]] = defaultdict(dict)
    for snap in snapshots:
        for h in snap.holdings:
            ltp_fallback[h.instrument][snap.date] = h.ltp

    # Build daily holdings tracker: apply transactions chronologically
    holdings_state: dict[str, int] = {}
    txn_by_date: dict[date, list[Transaction]] = defaultdict(list)
    for txn in transactions:
        txn_by_date[txn.date].append(txn)

    total_cost = 0.0
    series: list[DailyPortfolioValue] = []
    prev_value: float | None = None
    current = start

    while current <= end:
        # Apply transactions for this date
        for txn in txn_by_date.get(current, []):
            if txn.type == "BUY":
                holdings_state[txn.instrument] = (
                    holdings_state.get(txn.instrument, 0) + txn.quantity
                )
                total_cost += txn.price * txn.quantity
            elif txn.type == "SELL":
                qty_before = holdings_state.get(txn.instrument, 0)
                holdings_state[txn.instrument] = qty_before - txn.quantity
                total_cost = max(0.0, total_cost - txn.price * txn.quantity)
                if holdings_state[txn.instrument] <= 0:
                    del holdings_state[txn.instrument]

        # Compute portfolio value for this day
        total_value = 0.0
        for instrument, qty in holdings_state.items():
            ticker = instrument_tickers.get(instrument, "")
            price = _resolve_price(ticker, instrument, current, prices, ltp_fallback)
            if price is not None:
                total_value += price * qty

        daily_return = 0.0
        if prev_value is not None and prev_value > 0:
            daily_return = (total_value - prev_value) / prev_value

        series.append(
            DailyPortfolioValue(
                date=current,
                total_value=total_value,
                total_cost=total_cost,
                daily_return=daily_return,
            )
        )
        prev_value = total_value
        current += timedelta(days=1)

    return series


def _resolve_price(
    ticker: str,
    instrument: str,
    dt: date,
    prices: dict[str, dict[date, float]],
    ltp_fallback: dict[str, dict[date, float]],
) -> float | None:
    """Resolve price: market data → forward-fill → snapshot LTP fallback."""
    if ticker in prices:
        if dt in prices[ticker]:
            return prices[ticker][dt]
        # Forward-fill from most recent date
        past_dates = [d for d in prices[ticker] if d <= dt]
        if past_dates:
            return prices[ticker][max(past_dates)]
    # LTP fallback
    if instrument in ltp_fallback:
        past_dates = [d for d in ltp_fallback[instrument] if d <= dt]
        if past_dates:
            return ltp_fallback[instrument][max(past_dates)]
    return None


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def compute_concentration(weights: dict[str, float]) -> tuple[float, float]:
    """Compute Herfindahl index and top-5 concentration from position weights.

    Returns (hhi, top5_concentration).
    """
    if not weights:
        return 0.0, 0.0
    values = sorted(weights.values(), reverse=True)
    hhi = sum(w * w for w in values)
    top5 = sum(values[:5])
    return hhi, top5


def compute_max_drawdown(
    series: list[DailyPortfolioValue],
) -> tuple[float, date | None]:
    """Compute maximum drawdown and trough date.

    Returns (max_drawdown_fraction, trough_date).
    """
    if not series:
        return 0.0, None

    running_max = series[0].total_value
    max_dd = 0.0
    trough_date: date | None = None

    for dpv in series:
        if dpv.total_value > running_max:
            running_max = dpv.total_value
        if running_max > 0:
            dd = 1.0 - dpv.total_value / running_max
            if dd > max_dd:
                max_dd = dd
                trough_date = dpv.date

    return max_dd, trough_date


def compute_var_95(daily_returns: list[float], portfolio_value: float) -> float:
    """Compute Value at Risk at 95% confidence (5th percentile of daily returns × value)."""
    if not daily_returns:
        return 0.0
    percentile_5 = float(np.percentile(daily_returns, 5))
    return percentile_5 * portfolio_value


def compute_sharpe_ratio(daily_returns: list[float], risk_free_annual: float = 0.07) -> float:
    """Compute annualized Sharpe ratio."""
    if len(daily_returns) < 2:
        return 0.0
    rf_daily = risk_free_annual / 252
    excess = [r - rf_daily for r in daily_returns]
    std = float(np.std(excess, ddof=1))
    if std == 0:
        return 0.0
    return float(np.mean(excess)) / std * math.sqrt(252)


def compute_sortino_ratio(daily_returns: list[float], risk_free_annual: float = 0.07) -> float:
    """Compute annualized Sortino ratio (downside deviation only)."""
    if len(daily_returns) < 2:
        return 0.0
    rf_daily = risk_free_annual / 252
    excess = [r - rf_daily for r in daily_returns]
    downside = [e for e in excess if e < 0]
    if not downside:
        return 0.0
    downside_std = float(np.std(downside, ddof=1))
    if downside_std == 0:
        return 0.0
    return float(np.mean(excess)) / downside_std * math.sqrt(252)


def compute_beta(portfolio_returns: list[float], benchmark_returns: list[float]) -> float:
    """Compute portfolio beta vs benchmark."""
    n = min(len(portfolio_returns), len(benchmark_returns))
    if n < 2:
        return 0.0
    p = np.array(portfolio_returns[:n])
    b = np.array(benchmark_returns[:n])
    var_b = float(np.var(b, ddof=1))
    if var_b == 0:
        return 0.0
    cov = float(np.cov(p, b, ddof=1)[0, 1])
    return cov / var_b


def compute_twr(series: list[DailyPortfolioValue]) -> float:
    """Compute Time-Weighted Return by chain-linking daily returns."""
    if len(series) < 2:
        return 0.0
    cumulative = 1.0
    for dpv in series[1:]:
        cumulative *= 1.0 + dpv.daily_return
    return cumulative - 1.0


def annualize_return(total_return: float, days: int) -> float:
    """Annualize a total return over a given number of days."""
    if days <= 0:
        return 0.0
    return (1.0 + total_return) ** (365.0 / days) - 1.0


def compute_alpha(
    portfolio_twr: float,
    benchmark_twr: float,
    beta: float,
    risk_free_annual: float = 0.07,
) -> float:
    """Compute Jensen's alpha."""
    return (portfolio_twr - risk_free_annual) - beta * (benchmark_twr - risk_free_annual)


def compute_xirr(
    transactions: list[Transaction],
    current_value: float,
    end_date: date,
) -> float:
    """Compute XIRR from transaction cash flows + terminal value."""
    if not transactions:
        return 0.0

    # Build cash flows: (date, amount) — amounts are investor-perspective
    cashflows: list[tuple[date, float]] = [(t.date, t.amount) for t in transactions]
    # Terminal value (positive: investor receives)
    cashflows.append((end_date, current_value))

    # Reference date = first cash flow
    d0 = cashflows[0][0]

    def npv(rate: float) -> float:
        return sum(amount / (1.0 + rate) ** ((d - d0).days / 365.0) for d, amount in cashflows)

    try:
        return float(brentq(npv, -0.99, 10.0, maxiter=1000))
    except (ValueError, RuntimeError):
        return 0.0


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

_EMPTY_RESULT = AnalysisResult(
    start_date=date.min,
    end_date=date.min,
    xirr=0.0,
    twr_annualized=0.0,
    benchmark_twr=0.0,
    alpha=0.0,
    beta=0.0,
    sharpe=0.0,
    sortino=0.0,
    max_drawdown=0.0,
    max_drawdown_date=None,
    var_95_pct=0.0,
    herfindahl=0.0,
    top_5_concentration=0.0,
    warnings=[],
)


def run_analysis(
    rows: list[list[str]],
    cache_dir: str | None = None,
) -> tuple[AnalysisResult, list[DailyPortfolioValue], list[Transaction]]:
    """Run full portfolio analysis pipeline.

    Returns (AnalysisResult, daily_series, transactions).
    """
    snapshots = parse_snapshots_from_rows(rows)
    if not snapshots:
        return _EMPTY_RESULT, [], []

    transactions = infer_transactions(snapshots)
    start = snapshots[0].date
    end = snapshots[-1].date
    warnings: list[str] = []

    # Collect all unique tickers
    tickers: set[str] = set()
    for snap in snapshots:
        for h in snap.holdings:
            tickers.add(nse_to_yfinance_ticker(h.instrument, h.exchange))

    # Fetch market data
    market = MarketDataClient(cache_dir=cache_dir)
    prices = market.get_multiple_prices(sorted(tickers), start, end)
    benchmark_prices = market.get_benchmark_prices(start, end)

    missing = tickers - set(prices.keys())
    if missing:
        warnings.append(f"Missing price data for: {', '.join(sorted(missing))}")

    # Build daily series
    daily_series = build_daily_portfolio_series(snapshots, transactions, prices, start, end)
    if not daily_series:
        return _EMPTY_RESULT, [], transactions

    # Compute benchmark daily returns
    bench_dates = sorted(benchmark_prices.keys())
    bench_returns: list[float] = []
    for i in range(1, len(bench_dates)):
        prev_val = benchmark_prices[bench_dates[i - 1]]
        curr_val = benchmark_prices[bench_dates[i]]
        if prev_val > 0:
            bench_returns.append((curr_val - prev_val) / prev_val)

    # Portfolio daily returns (skip first day which is 0)
    port_returns = [dpv.daily_return for dpv in daily_series[1:]]

    # Current portfolio value
    current_value = daily_series[-1].total_value
    days = (end - start).days

    # Concentration
    last_snap = snapshots[-1]
    total_val = sum(h.current_value for h in last_snap.holdings)
    weights: dict[str, float] = {}
    if total_val > 0:
        for h in last_snap.holdings:
            weights[h.instrument] = h.current_value / total_val
    hhi, top5 = compute_concentration(weights)

    # Metrics
    max_dd, dd_date = compute_max_drawdown(daily_series)
    var_95 = compute_var_95(port_returns, current_value)
    sharpe = compute_sharpe_ratio(port_returns)
    sortino = compute_sortino_ratio(port_returns)
    beta = compute_beta(port_returns, bench_returns)
    twr = compute_twr(daily_series)
    twr_ann = annualize_return(twr, days) if days > 0 else 0.0

    # Benchmark TWR
    bench_twr = 0.0
    if len(bench_dates) >= 2:
        first_bench = benchmark_prices[bench_dates[0]]
        last_bench = benchmark_prices[bench_dates[-1]]
        if first_bench > 0:
            bench_twr = annualize_return((last_bench - first_bench) / first_bench, days)

    alpha = compute_alpha(twr_ann, bench_twr, beta)
    xirr = compute_xirr(transactions, current_value, end)

    result = AnalysisResult(
        start_date=start,
        end_date=end,
        xirr=xirr,
        twr_annualized=twr_ann,
        benchmark_twr=bench_twr,
        alpha=alpha,
        beta=beta,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_dd,
        max_drawdown_date=dd_date,
        var_95_pct=var_95 / current_value * 100 if current_value > 0 else 0.0,
        herfindahl=hhi,
        top_5_concentration=top5,
        warnings=warnings,
    )

    return result, daily_series, transactions
