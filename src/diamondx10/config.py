"""Doc config.yaml; neu chua co thi dung config.example.yaml / mac dinh."""
from pathlib import Path
import yaml

DEFAULT = {
    "fund": {"name": "DiamondX10", "total_capital_usd": 10000,
             "desks": {"forex": {"manager": "Yuling Pan", "capital_usd": 2500},
                       "us_securities": {"manager": "Kathy", "capital_usd": 2500},
                       "xauusd": {"manager": "Yumi", "capital_usd": 2500},
                       "crypto": {"manager": "Rich", "capital_usd": 2500}}},
    "risk": {"max_risk_per_trade_pct": 1.0, "max_drawdown_pct": 10.0,
             "default_stop_loss_pct": 5.0, "default_take_profit_pct": 5.0,
             "per_symbol_pct": {"EURUSD": 3.0, "XAUUSD": 10.0, "BTCUSD": 8.0}},
    "data": {"provider": "simulated"},
}


def load_config(path=None):
    path = Path(path or "config.yaml")
    if not path.exists():
        path = Path(__file__).resolve().parents[2] / "config.example.yaml"
    if not path.exists():
        return DEFAULT
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    merged = dict(DEFAULT)
    merged.update(data)
    return merged
