# Stocks Analysis

Fetches holdings from Zerodha Kite via Playwright (manual login/2FA), stores them in Google Sheets, and analyzes the portfolio — computing XIRR, Sharpe ratio, trends, and generating graphs.

**Tech stack:** Python 3.13+, uv, Playwright, gspread, pandas, pytest, ruff

## Commands

All commands use `uv run` — never manually activate venvs.

```bash
uv sync                                                                    # install dependencies
uv run pytest                                                              # run tests
uv run pytest --cov=stocks_analysis --cov-report=term-missing --cov-fail-under=80  # tests with coverage
uv run ruff check .                                                        # lint
uv run ruff check . --fix                                                  # lint auto-fix
uv run ruff format .                                                       # format
uv run ruff format --check .                                               # format check
```

## Development Workflow (TDD)

Strict Red-Green-Refactor cycle:

1. **RED** — Write a failing test first. Confirm it fails.
2. **GREEN** — Write minimum code to pass. Confirm it passes.
3. **REFACTOR** — Clean up without changing behavior. Run full suite.

Rules:

- Never write implementation without a failing test first
- Each test file mirrors source: `stocks_analysis/kite.py` → `tests/test_kite.py`
- External services (Kite, Google Sheets) must be mocked in unit tests
- Integration tests in `tests/integration/`, marked with `@pytest.mark.integration`
- Shared fixtures in `tests/conftest.py`
- Coverage minimum: 80%

## Project Structure

```
stocks-analysis/
├── CLAUDE.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
├── stocks_analysis/          # source package
│   ├── __init__.py
│   ├── main.py
│   ├── kite.py               # Playwright-based Kite fetcher
│   ├── sheets.py             # Google Sheets integration
│   ├── analysis.py           # XIRR, Sharpe ratio, metrics
│   ├── graphs.py             # Visualization
│   └── models.py             # Data classes
├── tests/
│   ├── conftest.py
│   ├── test_*.py             # mirrors source modules
│   └── integration/
├── tasks/                    # project roadmap (requirements only)
│   ├── README.md
│   └── NN-short-name.md
└── output/                   # generated graphs/reports (gitignored)
```

## Code Style

- Linter + formatter: ruff
- Line length: 100
- Target: Python 3.13
- Rule sets: E, F, I, UP, B, SIM
- Double quotes
- Type hints on all function signatures
- Use dataclasses for structured data (in `models.py`)
- Dependency injection for external services

## Tasks Folder Convention

- Each task is a numbered markdown file: `NN-short-name.md`
- Sub-tasks use dot notation: `01.1-setup-playwright.md`
- Files contain **only requirements** (objective, requirements checklist, acceptance criteria, dependencies, notes)
- NO implementation plans or code in task files
- `tasks/README.md` holds the roadmap table

## Architecture Decisions

- **Kite:** Playwright in headed mode, user completes login/2FA manually, script waits then scrapes holdings
- **Google Sheets:** gspread + service account, credentials path from env var
- **Analysis:** scipy for XIRR, pandas for returns/Sharpe, matplotlib for graphs
- **Data flow:** Kite → Python dataclasses → Google Sheets → pandas DataFrame → Analysis/Graphs

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `GOOGLE_SHEETS_CREDENTIALS` | Path to service account JSON | Phase 2+ |
| `GOOGLE_SHEET_ID` | Target sheet ID | Phase 2+ |

## Git Conventions

- Branches: `feat/`, `fix/`, `refactor/`
- Commits: conventional commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `chore:`)
- Reference tasks: `feat: fetch holdings from Kite (task-01)`
- Commit: `uv.lock`, `pyproject.toml`, `.python-version`
- Never commit: `.env`, credentials, `output/`, `__pycache__/`, `.venv/`
- Always use `--no-gpg-sign` when committing (GPG signing is enforced globally but Claude does not have access to the GPG key)

## Instructions for Claude

- Read the relevant task file in `tasks/` before implementing
- Always follow TDD — tests first
- Run full suite + lint after changes
- Mock external services in tests
- Bug fixes start with a reproducing test
- Commit frequently — after each passing test, completed feature, or meaningful change
