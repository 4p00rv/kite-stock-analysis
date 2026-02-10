from stocks_analysis.models import Holding


def make_holding(**overrides: object) -> Holding:
    """Create a sample Holding with sensible defaults. Override any field via kwargs."""
    defaults = {
        "instrument": "RELIANCE",
        "quantity": 10,
        "avg_cost": 2450.50,
        "ltp": 2500.00,
        "current_value": 25000.00,
        "pnl": 495.00,
        "pnl_percent": 2.02,
        "day_change": 15.00,
        "day_change_percent": 0.60,
    }
    defaults.update(overrides)
    return Holding(**defaults)
