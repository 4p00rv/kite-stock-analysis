from __future__ import annotations

from collections import defaultdict

from stocks_analysis.models import (
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
