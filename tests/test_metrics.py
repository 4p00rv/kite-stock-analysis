from datetime import date

import pytest

from stocks_analysis.analysis import (
    annualize_return,
    compute_alpha,
    compute_beta,
    compute_concentration,
    compute_max_drawdown,
    compute_sharpe_ratio,
    compute_sortino_ratio,
    compute_twr,
    compute_var_95,
    compute_xirr,
)
from stocks_analysis.models import DailyPortfolioValue, Transaction


class TestComputeConcentration:
    def test_single_holding(self) -> None:
        weights = {"RELIANCE": 1.0}
        hhi, top5 = compute_concentration(weights)
        assert hhi == pytest.approx(1.0)
        assert top5 == pytest.approx(1.0)

    def test_equal_weights(self) -> None:
        weights = {f"STOCK{i}": 0.1 for i in range(10)}
        hhi, top5 = compute_concentration(weights)
        assert hhi == pytest.approx(0.1)  # 10 * 0.01
        assert top5 == pytest.approx(0.5)

    def test_concentrated_portfolio(self) -> None:
        weights = {"A": 0.5, "B": 0.2, "C": 0.15, "D": 0.1, "E": 0.05}
        hhi, top5 = compute_concentration(weights)
        # 0.25 + 0.04 + 0.0225 + 0.01 + 0.0025 = 0.325
        assert hhi == pytest.approx(0.325)
        assert top5 == pytest.approx(1.0)

    def test_empty_weights(self) -> None:
        hhi, top5 = compute_concentration({})
        assert hhi == 0.0
        assert top5 == 0.0


class TestComputeMaxDrawdown:
    def test_no_drawdown(self) -> None:
        series = [
            DailyPortfolioValue(date(2025, 1, d), 100.0 + d, 100.0, 0.01) for d in range(1, 6)
        ]
        dd, trough = compute_max_drawdown(series)
        assert dd == pytest.approx(0.0)

    def test_simple_drawdown(self) -> None:
        series = [
            DailyPortfolioValue(date(2025, 1, 1), 100.0, 90.0, 0.0),
            DailyPortfolioValue(date(2025, 1, 2), 110.0, 90.0, 0.1),
            DailyPortfolioValue(date(2025, 1, 3), 90.0, 90.0, -0.18),
            DailyPortfolioValue(date(2025, 1, 4), 95.0, 90.0, 0.056),
            DailyPortfolioValue(date(2025, 1, 5), 120.0, 90.0, 0.26),
        ]
        dd, trough = compute_max_drawdown(series)
        # Peak was 110, trough was 90 → 20/110 = 0.1818...
        assert dd == pytest.approx(20.0 / 110.0, rel=1e-3)
        assert trough == date(2025, 1, 3)

    def test_empty_series(self) -> None:
        dd, trough = compute_max_drawdown([])
        assert dd == 0.0
        assert trough is None


class TestComputeVar95:
    def test_known_returns(self) -> None:
        # 20 daily returns, sorted: the 5th percentile is the 1st value
        returns = [float(i) for i in range(-10, 10)]
        var = compute_var_95(returns, 100000.0)
        # 5th percentile of [-10..9] ≈ -9.05
        assert var < 0  # VaR is a loss

    def test_empty_returns(self) -> None:
        var = compute_var_95([], 100000.0)
        assert var == 0.0


class TestComputeSharpeRatio:
    def test_positive_sharpe(self) -> None:
        # Steady positive returns
        returns = [0.001] * 252
        sharpe = compute_sharpe_ratio(returns, risk_free_annual=0.07)
        assert sharpe > 0

    def test_zero_std_returns_zero(self) -> None:
        # All same returns → std=0 → sharpe=0
        returns = [0.0003] * 10
        sharpe = compute_sharpe_ratio(returns, risk_free_annual=0.07)
        assert sharpe == 0.0

    def test_empty_returns(self) -> None:
        sharpe = compute_sharpe_ratio([], risk_free_annual=0.07)
        assert sharpe == 0.0


class TestComputeSortinoRatio:
    def test_positive_sortino(self) -> None:
        # Mix of positive and negative returns so there IS downside
        returns = [0.005, -0.002, 0.003, -0.001, 0.004] * 50
        sortino = compute_sortino_ratio(returns, risk_free_annual=0.07)
        assert sortino > 0

    def test_no_downside_returns_zero(self) -> None:
        # All positive excess returns → no downside deviation → 0
        returns = [0.01] * 10
        sortino = compute_sortino_ratio(returns, risk_free_annual=0.0)
        assert sortino == 0.0

    def test_empty_returns(self) -> None:
        sortino = compute_sortino_ratio([], risk_free_annual=0.07)
        assert sortino == 0.0


class TestComputeBeta:
    def test_perfect_correlation(self) -> None:
        port_returns = [0.01, -0.02, 0.015, -0.005, 0.02]
        bench_returns = [0.01, -0.02, 0.015, -0.005, 0.02]
        beta = compute_beta(port_returns, bench_returns)
        assert beta == pytest.approx(1.0)

    def test_inverse_correlation(self) -> None:
        port_returns = [0.01, -0.02, 0.015, -0.005, 0.02]
        bench_returns = [-0.01, 0.02, -0.015, 0.005, -0.02]
        beta = compute_beta(port_returns, bench_returns)
        assert beta == pytest.approx(-1.0)

    def test_empty_returns(self) -> None:
        beta = compute_beta([], [])
        assert beta == 0.0

    def test_mismatched_lengths_uses_minimum(self) -> None:
        port_returns = [0.01, -0.02, 0.015]
        bench_returns = [0.01, -0.02]
        beta = compute_beta(port_returns, bench_returns)
        assert isinstance(beta, float)


class TestComputeTwr:
    def test_simple_growth(self) -> None:
        series = [
            DailyPortfolioValue(date(2025, 1, 1), 100.0, 100.0, 0.0),
            DailyPortfolioValue(date(2025, 1, 2), 110.0, 100.0, 0.1),
            DailyPortfolioValue(date(2025, 1, 3), 121.0, 100.0, 0.1),
        ]
        twr = compute_twr(series)
        assert twr == pytest.approx(0.21, rel=1e-3)

    def test_empty_series(self) -> None:
        twr = compute_twr([])
        assert twr == 0.0


class TestAnnualizeReturn:
    def test_one_year(self) -> None:
        result = annualize_return(0.10, 365)
        assert result == pytest.approx(0.10, rel=1e-3)

    def test_two_years(self) -> None:
        # 21% over 2 years → ~10% annualized
        result = annualize_return(0.21, 730)
        assert result == pytest.approx(0.10, rel=1e-2)

    def test_zero_days(self) -> None:
        result = annualize_return(0.10, 0)
        assert result == 0.0


class TestComputeAlpha:
    def test_outperformance(self) -> None:
        alpha = compute_alpha(
            portfolio_twr=0.20, benchmark_twr=0.12, beta=0.9, risk_free_annual=0.07
        )
        # alpha = (0.20 - 0.07) - 0.9*(0.12 - 0.07) = 0.13 - 0.045 = 0.085
        assert alpha == pytest.approx(0.085)


class TestComputeXirr:
    def test_simple_investment(self) -> None:
        txns = [
            Transaction(date(2024, 1, 15), "RELIANCE", "BUY", 10, 2000.0, -20000.0),
        ]
        current_value = 22000.0
        end_date = date(2025, 1, 15)
        xirr = compute_xirr(txns, current_value, end_date)
        # Invested 20000, now worth 22000 after 1 year → ~10%
        assert xirr == pytest.approx(0.10, rel=1e-2)

    def test_multiple_investments(self) -> None:
        txns = [
            Transaction(date(2024, 1, 1), "A", "BUY", 10, 100.0, -1000.0),
            Transaction(date(2024, 7, 1), "B", "BUY", 5, 200.0, -1000.0),
        ]
        current_value = 2200.0
        end_date = date(2025, 1, 1)
        xirr = compute_xirr(txns, current_value, end_date)
        assert xirr > 0  # Should be positive

    def test_empty_transactions(self) -> None:
        xirr = compute_xirr([], 0.0, date(2025, 1, 1))
        assert xirr == 0.0

    def test_includes_sell_cashflows(self) -> None:
        txns = [
            Transaction(date(2024, 1, 1), "A", "BUY", 10, 100.0, -1000.0),
            Transaction(date(2024, 6, 1), "A", "SELL", 5, 120.0, 600.0),
        ]
        current_value = 650.0
        end_date = date(2025, 1, 1)
        xirr = compute_xirr(txns, current_value, end_date)
        assert isinstance(xirr, float)
