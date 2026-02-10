# 02 — Google Sheets Integration

## Objective

Push scraped holdings data into Google Sheets so it accumulates daily for analysis. Store holdings rows and a portfolio summary in separate worksheet tabs.

## Requirements

- [ ] `PortfolioSummary` dataclass in `models.py` with `from_holdings()` classmethod
- [ ] `SheetsClient` class in `sheets.py` with:
  - [ ] `_get_or_create_worksheet(title, headers)` — creates tab if missing
  - [ ] `_ensure_headers(worksheet, headers)` — writes/overwrites header row
  - [ ] `_delete_rows_for_date(worksheet, date_str)` — dedup: remove stale rows
  - [ ] `upload_holdings(holdings, date_str)` — write holdings to "Holdings" tab
  - [ ] `upload_summary(summary, date_str)` — write summary to "Summary" tab
- [ ] `create_sheets_client()` factory reading env vars
- [ ] `_upload_to_sheets_if_configured()` in `main.py` — called after CSV save
- [ ] Graceful failure: sheets errors logged as warnings, never crash CSV flow
- [ ] All gspread calls mocked in unit tests

## Acceptance Criteria

- Running with env vars set uploads holdings + summary to Google Sheets
- Running without env vars silently skips upload
- Multiple runs on same day replace (not duplicate) data
- Holdings added/removed between runs are handled correctly
- Coverage ≥ 80%

## Dependencies

- Task 01 (Kite holdings fetch) complete

## Notes

- **Row format:** `date | <Holding.csv_headers()>`
- **Summary columns:** `date | total_investment | current_value | total_pnl | total_pnl_percent | day_pnl | day_pnl_percent | num_holdings`
- **Date format:** `YYYY-MM-DD` (ISO 8601)
- **Dedup strategy:** delete all rows matching today's date, then append fresh (last run wins)
- Env vars: `GOOGLE_SHEETS_CREDENTIALS` (service account JSON path), `GOOGLE_SHEET_ID`
