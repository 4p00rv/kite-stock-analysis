# 01 — Fetch Kite Holdings & Export to CSV

## Objective

Automate fetching stock holdings from Zerodha Kite's web dashboard using Playwright (headed browser, manual login/2FA) and save them to a timestamped CSV file in `output/`.

## Requirements

- [ ] `Holding` dataclass with fields: instrument, quantity, avg_cost, ltp, current_value, pnl, pnl_percent, day_change, day_change_percent, exchange (default "NSE")
- [ ] `csv_headers()` classmethod and `to_csv_row()` method on `Holding`
- [ ] `save_holdings_to_csv(holdings, output_dir)` writes timestamped CSV to `output/`
- [ ] `KiteFetcher` class accepts a Playwright `page` object (dependency injection)
- [ ] `open_login_page()` navigates to Kite login
- [ ] `wait_for_login(timeout_ms)` waits for user to complete login/2FA (default 5 min)
- [ ] `navigate_to_holdings()` navigates to holdings page and waits for network idle
- [ ] `parse_holding_row(row_data)` pure function converts string dict to `Holding`
- [ ] `_clean_number(text)` strips commas, %, +/- signs from numeric strings
- [ ] `fetch_holdings()` scrapes holdings table rows and returns `list[Holding]`
- [ ] `create_kite_fetcher()` context manager launches headed Chromium, yields fetcher
- [ ] `run()` orchestrates full flow: login → wait → navigate → fetch → CSV
- [ ] `__main__.py` entry point enables `python -m stocks_analysis`

## Acceptance Criteria

- All unit tests pass with mocked Playwright
- Coverage >= 80%
- Ruff lint and format checks pass
- CSV output includes headers and correct row data
- Empty holdings produces header-only CSV
- Malformed rows are skipped gracefully

## Dependencies

- Task 00 (project scaffolding) — complete

## Notes

- CSS selectors are placeholders; calibrate on first real run against Kite DOM
- Manual login/2FA is expected — script waits for user interaction
