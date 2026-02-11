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

from stocks_analysis.kite import KiteFetcher
from stocks_analysis.models import Holding, PortfolioSummary
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


def run() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Stocks analysis")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("scrape", help="Scrape holdings from Kite")
    upload_parser = sub.add_parser("upload", help="Upload existing CSV to Google Sheets")
    upload_parser.add_argument("csv_path", type=Path, help="Path to holdings CSV file")

    args = parser.parse_args()

    if args.command == "upload":
        _upload_csv_to_sheets(args.csv_path)
    else:
        _scrape()
