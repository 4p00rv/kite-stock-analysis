import argparse
import csv
import logging
import os
import re
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from dotenv import load_dotenv

from stocks_analysis.analysis import run_analysis
from stocks_analysis.kite import KiteFetcher
from stocks_analysis.models import AnalysisResult, Holding, PortfolioSummary
from stocks_analysis.sheets import create_sheets_client

logger = logging.getLogger(__name__)

_DEFAULT_OUTPUT_DIR = Path("output")


def save_holdings_to_csv(holdings: list[Holding], output_dir: Path | None = None) -> Path:
    output_dir = output_dir or _DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"holdings_{timestamp}.csv"

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(Holding.csv_headers())
        for holding in holdings:
            writer.writerow(holding.to_csv_row())

    return filepath


def load_holdings_from_csv(filepath: Path) -> list[Holding]:
    """Read a CSV file (with header) and return a list of Holdings."""
    with open(filepath, newline="") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        return [Holding.from_csv_row(row) for row in reader]


@contextmanager
def create_kite_fetcher() -> Generator[KiteFetcher]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            yield KiteFetcher(page)
        finally:
            browser.close()


def _upload_to_sheets_if_configured(holdings: list[Holding]) -> None:
    if not os.environ.get("GOOGLE_SHEETS_CREDENTIALS") or not os.environ.get("GOOGLE_SHEET_ID"):
        return

    try:
        client = create_sheets_client()
        summary = PortfolioSummary.from_holdings(holdings)
        count = client.upload_holdings(holdings)
        client.upload_summary(summary)
        print(f"Uploaded {count} holdings and summary to Google Sheets.")
    except Exception:
        logger.warning("Failed to upload to Google Sheets", exc_info=True)


def _extract_date_from_filename(filepath: Path) -> str:
    """Extract the date from a holdings CSV filename (e.g. holdings_20240115_120000.csv).

    Falls back to today's date if the filename doesn't match the expected pattern.
    """
    match = re.match(r"holdings_(\d{4})(\d{2})(\d{2})_\d{6}", filepath.stem)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return date.today().isoformat()


def _upload_csv_to_sheets(filepath: Path) -> None:
    """Load holdings from CSV and upload to Google Sheets."""
    holdings = load_holdings_from_csv(filepath)
    print(f"Loaded {len(holdings)} holdings from {filepath}")
    date_str = _extract_date_from_filename(filepath)
    client = create_sheets_client()
    summary = PortfolioSummary.from_holdings(holdings)
    count = client.upload_holdings(holdings, date_str=date_str)
    client.upload_summary(summary, date_str=date_str)
    print(f"Uploaded {count} holdings and summary to Google Sheets.")


def _scrape() -> None:
    """Kite login → scrape → CSV → optional sheets upload."""
    with create_kite_fetcher() as fetcher:
        print("Opening Kite login page...")
        fetcher.open_login_page()

        user_id = os.environ.get("KITE_USER_ID")
        password = os.environ.get("KITE_PASSWORD")
        if user_id and password:
            print("Auto-filling Kite credentials...")
            fetcher.fill_login_credentials(user_id, password)

        print("Waiting for login (complete 2FA in the browser)...")
        fetcher.wait_for_login()

        print("Navigating to holdings...")
        fetcher.navigate_to_holdings()

        print("Fetching holdings...")
        holdings = fetcher.fetch_holdings()

    print(f"Found {len(holdings)} holdings.")
    filepath = save_holdings_to_csv(holdings)
    print(f"Saved to {filepath}")

    _upload_to_sheets_if_configured(holdings)


def _print_summary(result: AnalysisResult) -> None:
    """Print compact analysis summary to terminal."""
    print(
        f"\nPORTFOLIO ANALYSIS ({result.start_date} \u2192 {result.end_date})\n"
        f"  XIRR: {result.xirr * 100:.2f}%  |  TWR: {result.twr_annualized * 100:.1f}%"
        f"  |  Nifty 50: {result.benchmark_twr * 100:.1f}%  |  Alpha: {result.alpha * 100:.1f}%\n"
        f"  Sharpe: {result.sharpe:.2f}   |  Sortino: {result.sortino:.2f}"
        f"  |  Beta: {result.beta:.2f}\n"
        f"  Max Drawdown: {-result.max_drawdown * 100:.1f}%"
        f"  |  VaR 95%: {result.var_95_pct:.1f}%\n"
        f"  Top 5: {result.top_5_concentration * 100:.1f}%"
        f"  |  HHI: {result.herfindahl:.4f}\n"
    )
    if result.warnings:
        for w in result.warnings:
            print(f"  \u26a0 {w}")


def _analyze() -> None:
    """Read holdings from Sheets, run analysis, upload results."""
    client = create_sheets_client()
    rows = client.read_all_holdings_rows()

    result, daily_series, transactions = run_analysis(rows)

    if not daily_series:
        print("No data to analyze.")
        return

    # Get last snapshot holdings for allocation
    from stocks_analysis.analysis import parse_snapshots_from_rows

    snapshots = parse_snapshots_from_rows(rows)
    last_snap = snapshots[-1] if snapshots else None

    # Fetch benchmark prices for chart data
    from stocks_analysis.market_data import MarketDataClient

    market = MarketDataClient()
    benchmark_prices = market.get_benchmark_prices(result.start_date, result.end_date)

    # Upload computed data
    client.upload_daily_values(daily_series, benchmark_prices)
    client.upload_rolling_returns(daily_series)
    client.upload_monthly_returns(daily_series)
    if last_snap:
        # Convert SnapshotHoldings to Holdings for upload_allocation
        holdings = [
            Holding(
                instrument=h.instrument,
                quantity=h.quantity,
                avg_cost=h.avg_cost,
                ltp=h.ltp,
                current_value=h.current_value,
                pnl=h.pnl,
                pnl_percent=h.pnl_percent,
                day_change=h.day_change,
                day_change_percent=h.day_change_percent,
                exchange=h.exchange,
            )
            for h in last_snap.holdings
        ]
        client.upload_allocation(holdings)
    client.upload_metrics(result)

    # Charts + slicer
    client.create_or_update_charts(
        daily_values_rows=len(daily_series),
        rolling_returns_rows=len(daily_series),
        allocation_rows=len(last_snap.holdings) if last_snap else 0,
    )
    client.create_date_slicer(num_rows=len(daily_series))

    _print_summary(result)
    print("Charts updated in Google Sheets.")


def run() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Stocks analysis")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("scrape", help="Scrape holdings from Kite")
    upload_parser = sub.add_parser("upload", help="Upload existing CSV to Google Sheets")
    upload_parser.add_argument("csv_path", type=Path, help="Path to holdings CSV file")
    sub.add_parser("analyze", help="Run portfolio analysis")

    args = parser.parse_args()

    if args.command == "upload":
        _upload_csv_to_sheets(args.csv_path)
    elif args.command == "analyze":
        _analyze()
    else:
        _scrape()
