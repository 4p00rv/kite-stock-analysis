from unittest.mock import MagicMock

from stocks_analysis.kite import (
    _POST_LOGIN_URL_PATTERN,
    KITE_HOLDINGS_URL,
    KITE_LOGIN_URL,
    KiteFetcher,
    _extract_row_data,
    _parse_quantity,
    _parse_tooltip_value,
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
        page.wait_for_url.assert_called_once_with(_POST_LOGIN_URL_PATTERN, timeout=300_000)

    def test_calls_wait_for_url_with_custom_timeout(self) -> None:
        page = MagicMock()
        fetcher = KiteFetcher(page)
        fetcher.wait_for_login(timeout_ms=60_000)
        page.wait_for_url.assert_called_once_with(_POST_LOGIN_URL_PATTERN, timeout=60_000)


class TestNavigateToHoldings:
    def test_goes_to_holdings_url(self) -> None:
        page = MagicMock()
        fetcher = KiteFetcher(page)
        fetcher.navigate_to_holdings()
        page.goto.assert_called_once_with(KITE_HOLDINGS_URL)

    def test_waits_for_holdings_content(self) -> None:
        page = MagicMock()
        fetcher = KiteFetcher(page)
        fetcher.navigate_to_holdings()
        page.wait_for_load_state.assert_called_once_with("domcontentloaded")
        assert page.wait_for_selector.call_count == 2
        page.wait_for_selector.assert_any_call(".holdings", timeout=30_000)
        page.wait_for_selector.assert_any_call(
            ".holdings .su-loader", state="hidden", timeout=60_000
        )


class TestParseTooltipValue:
    def test_positive_value(self) -> None:
        assert _parse_tooltip_value("99.63 (+53.27%") == "99.63"

    def test_negative_value(self) -> None:
        assert _parse_tooltip_value("-22.72 (-0.13%)") == "-22.72"

    def test_zero_value(self) -> None:
        assert _parse_tooltip_value("0.00 (0.00%)") == "0.00"

    def test_empty_string(self) -> None:
        assert _parse_tooltip_value("") == "0"

    def test_comma_value(self) -> None:
        assert _parse_tooltip_value("1,234.56 (+10.00%)") == "1,234.56"


class TestParseQuantity:
    def test_simple_integer(self) -> None:
        assert _parse_quantity("10") == 10

    def test_with_commas(self) -> None:
        assert _parse_quantity("1,234") == 1234

    def test_t1_annotation_with_settled(self) -> None:
        """T1: 13 awaiting delivery + 20 settled = 33 total."""
        assert _parse_quantity("T1: 13 20") == 33

    def test_t1_annotation_newline_separated(self) -> None:
        assert _parse_quantity("T1: 13\n20") == 33

    def test_t2_annotation(self) -> None:
        assert _parse_quantity("T2: 5 100") == 105

    def test_multiple_t_day_annotations(self) -> None:
        assert _parse_quantity("T2: 5 T1: 3 100") == 108

    def test_only_t1_annotation(self) -> None:
        """When only T1 quantity exists (no settled shares yet)."""
        assert _parse_quantity("T1: 13") == 13

    def test_quantity_with_commas_and_t1(self) -> None:
        assert _parse_quantity("T1: 1,300 20,500") == 21800

    def test_whitespace_padding(self) -> None:
        assert _parse_quantity("  20  ") == 20


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

    def test_t1_settlement_quantity(self) -> None:
        row_data = {
            "instrument": "HDFCBANK",
            "quantity": "T1: 13 20",
            "avg_cost": "1,600.00",
            "ltp": "1,650.00",
            "current_value": "33,000.00",
            "pnl": "+1,000.00",
            "pnl_percent": "+3.13%",
            "day_change": "+10.00",
            "day_change_percent": "+0.61%",
        }
        h = parse_holding_row(row_data)
        assert h.instrument == "HDFCBANK"
        assert h.quantity == 33

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


def _make_mock_row(
    instrument: str = "RELIANCE",
    qty: str = "10",
    avg_cost: str = "2,450.50",
    ltp: str = "2,500.00",
    cur_val: str = "25,000.00",
    pnl: str = "495.00",
    net_chg: str = "+2.02%",
    day_chg: str = "+0.60%",
    day_chg_tooltip: str = "15.00 (+0.60%)",
) -> MagicMock:
    """Create a mock row element matching Kite's holdings DOM structure."""
    label_map = {
        "Instrument": instrument,
        "Qty.": qty,
        "Avg. cost": avg_cost,
        "LTP": ltp,
        "Cur. val": cur_val,
        "P&L": pnl,
        "Net chg.": net_chg,
        "Day chg.": day_chg,
    }

    def mock_query_selector(selector: str) -> MagicMock | None:
        # Day chg. tooltip span
        if "Day chg." in selector and "data-tooltip-content" in selector:
            span = MagicMock()
            span.get_attribute.return_value = day_chg_tooltip
            return span

        # Regular data-label cells
        for label, text in label_map.items():
            if f'data-label="{label}"' in selector:
                cell = MagicMock()
                cell.inner_text.return_value = text
                if label == "Instrument":
                    name_span = MagicMock()
                    name_span.inner_text.return_value = text
                    cell.query_selector.return_value = name_span
                return cell

        return None

    row = MagicMock()
    row.query_selector = MagicMock(side_effect=mock_query_selector)
    return row


class TestExtractRowData:
    def test_extracts_all_fields(self) -> None:
        row = _make_mock_row()
        data = _extract_row_data(row)
        assert data["instrument"] == "RELIANCE"
        assert data["quantity"] == "10"
        assert data["avg_cost"] == "2,450.50"
        assert data["ltp"] == "2,500.00"
        assert data["current_value"] == "25,000.00"
        assert data["pnl"] == "495.00"
        assert data["pnl_percent"] == "+2.02%"
        assert data["day_change"] == "15.00"
        assert data["day_change_percent"] == "+0.60%"

    def test_missing_cell_raises(self) -> None:
        import pytest

        row = MagicMock()
        row.query_selector.return_value = None
        with pytest.raises(ValueError):
            _extract_row_data(row)

    def test_day_change_defaults_to_zero_without_tooltip(self) -> None:
        def mock_qs(selector: str) -> MagicMock | None:
            if "data-tooltip-content" in selector:
                return None
            for label in [
                "Instrument",
                "Qty.",
                "Avg. cost",
                "LTP",
                "Cur. val",
                "P&L",
                "Net chg.",
                "Day chg.",
            ]:
                if f'data-label="{label}"' in selector:
                    cell = MagicMock()
                    cell.inner_text.return_value = "0"
                    if label == "Instrument":
                        name_span = MagicMock()
                        name_span.inner_text.return_value = "TEST"
                        cell.query_selector.return_value = name_span
                    return cell
            return None

        row = MagicMock()
        row.query_selector = MagicMock(side_effect=mock_qs)
        data = _extract_row_data(row)
        assert data["day_change"] == "0"


class TestFetchHoldings:
    def test_single_holding(self) -> None:
        page = MagicMock()
        row = _make_mock_row()
        page.query_selector_all.return_value = [row]
        fetcher = KiteFetcher(page)
        holdings = fetcher.fetch_holdings()
        assert len(holdings) == 1
        assert holdings[0].instrument == "RELIANCE"
        assert holdings[0].quantity == 10

    def test_empty_holdings(self) -> None:
        page = MagicMock()
        page.query_selector_all.return_value = []
        fetcher = KiteFetcher(page)
        holdings = fetcher.fetch_holdings()
        assert holdings == []

    def test_multiple_holdings(self) -> None:
        page = MagicMock()
        row1 = _make_mock_row(instrument="RELIANCE")
        row2 = _make_mock_row(
            instrument="TCS",
            qty="5",
            avg_cost="3,200.00",
            ltp="3,300.00",
            cur_val="16,500.00",
            pnl="500.00",
            net_chg="+3.13%",
            day_chg="+1.54%",
            day_chg_tooltip="50.00 (+1.54%)",
        )
        page.query_selector_all.return_value = [row1, row2]
        fetcher = KiteFetcher(page)
        holdings = fetcher.fetch_holdings()
        assert len(holdings) == 2
        assert holdings[0].instrument == "RELIANCE"
        assert holdings[1].instrument == "TCS"

    def test_skips_malformed_row(self) -> None:
        page = MagicMock()
        good_row = _make_mock_row()
        bad_row = MagicMock()
        bad_row.query_selector.return_value = None  # missing cells
        page.query_selector_all.return_value = [good_row, bad_row]
        fetcher = KiteFetcher(page)
        holdings = fetcher.fetch_holdings()
        assert len(holdings) == 1
        assert holdings[0].instrument == "RELIANCE"
