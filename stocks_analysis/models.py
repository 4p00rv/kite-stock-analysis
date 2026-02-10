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
