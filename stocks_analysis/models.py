from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass
class Holding:
    instrument: str
    quantity: int
    avg_cost: float
    ltp: float
    current_value: float
    pnl: float
    pnl_percent: float
    day_change: float
    day_change_percent: float
    exchange: str = "NSE"

    @classmethod
    def csv_headers(cls) -> list[str]:
        return [f.name for f in fields(cls)]

    def to_csv_row(self) -> list[object]:
        return [getattr(self, f.name) for f in fields(self)]

    @classmethod
    def from_csv_row(cls, row: list[str]) -> Holding:
        """Parse a CSV row (list of strings) into a Holding."""
        return cls(
            instrument=row[0],
            quantity=int(row[1]),
            avg_cost=float(row[2]),
            ltp=float(row[3]),
            current_value=float(row[4]),
            pnl=float(row[5]),
            pnl_percent=float(row[6]),
            day_change=float(row[7]),
            day_change_percent=float(row[8]),
            exchange=row[9] if len(row) > 9 else "NSE",
        )


@dataclass
class PortfolioSummary:
    total_investment: float
    current_value: float
    total_pnl: float
    total_pnl_percent: float
    day_pnl: float
    day_pnl_percent: float
    num_holdings: int

    @classmethod
    def from_holdings(cls, holdings: list[Holding]) -> PortfolioSummary:
        """Compute portfolio summary from a list of holdings."""
        if not holdings:
            return cls(
                total_investment=0.0,
                current_value=0.0,
                total_pnl=0.0,
                total_pnl_percent=0.0,
                day_pnl=0.0,
                day_pnl_percent=0.0,
                num_holdings=0,
            )

        current_value = sum(h.current_value for h in holdings)
        total_pnl = sum(h.pnl for h in holdings)
        total_investment = current_value - total_pnl
        day_pnl = sum(h.day_change * h.quantity for h in holdings)

        return cls(
            total_investment=total_investment,
            current_value=current_value,
            total_pnl=total_pnl,
            total_pnl_percent=(total_pnl / total_investment * 100) if total_investment else 0.0,
            day_pnl=day_pnl,
            day_pnl_percent=(day_pnl / current_value * 100) if current_value else 0.0,
            num_holdings=len(holdings),
        )

    @classmethod
    def csv_headers(cls) -> list[str]:
        return [f.name for f in fields(cls)]

    def to_csv_row(self) -> list[object]:
        return [getattr(self, f.name) for f in fields(self)]
