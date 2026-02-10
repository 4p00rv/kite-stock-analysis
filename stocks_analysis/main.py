import csv
from datetime import datetime, timezone
from pathlib import Path

from stocks_analysis.models import Holding

_DEFAULT_OUTPUT_DIR = Path("output")


def save_holdings_to_csv(
    holdings: list[Holding], output_dir: Path | None = None
) -> Path:
    output_dir = output_dir or _DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"holdings_{timestamp}.csv"

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(Holding.csv_headers())
        for holding in holdings:
            writer.writerow(holding.to_csv_row())

    return filepath
