import csv
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from stocks_analysis.kite import KiteFetcher
from stocks_analysis.models import Holding

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


def run() -> None:
    with create_kite_fetcher() as fetcher:
        print("Opening Kite login page...")
        fetcher.open_login_page()

        print("Waiting for login (complete 2FA in the browser)...")
        fetcher.wait_for_login()

        print("Navigating to holdings...")
        fetcher.navigate_to_holdings()

        print("Fetching holdings...")
        holdings = fetcher.fetch_holdings()

        print(f"Found {len(holdings)} holdings.")
        filepath = save_holdings_to_csv(holdings)
        print(f"Saved to {filepath}")
