"""Quan ly von theo desk: moi desk 2500 USD, tong 10000 USD.
LJ/Kel xay nen tang, khong giao dich trong 10000 USD nay."""
from dataclasses import dataclass, field


@dataclass
class Desk:
    name: str
    manager: str
    capital_usd: float = 2500.0
    positions: dict = field(default_factory=dict)


@dataclass
class Portfolio:
    desks: dict

    @classmethod
    def from_config(cls, cfg):
        desks = {}
        for name, info in cfg["fund"]["desks"].items():
            desks[name] = Desk(name, info["manager"], float(info["capital_usd"]))
        return cls(desks)

    @property
    def total_capital_usd(self):
        return sum(d.capital_usd for d in self.desks.values())

    def summary(self):
        lines = ["Portfolio DiamondX10 (gia dinh):"]
        for d in self.desks.values():
            lines.append(f"  - {d.name}: {d.manager} — {d.capital_usd:.0f} USD")
        lines.append(f"  Tong: {self.total_capital_usd:.0f} USD")
        return "\n".join(lines)
