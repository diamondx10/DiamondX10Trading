"""CLI entry: python3 -m diamondx10 demo | backtest | signals."""
import argparse
from .backtest import run_backtest
from .config import load_config
from .data.feeds import SimulatedFeed
from .decisions import log_decision
from .portfolio import Portfolio
from .signals import generate_signals
from .strategies import STRATEGIES


def main(argv=None):
    p = argparse.ArgumentParser(prog="diamondx10")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="chay demo voi du lieu mo phong")
    b = sub.add_parser("backtest", help="backtest placeholder")
    b.add_argument("--desk", default="forex")
    b.add_argument("--days", type=int, default=30)
    s = sub.add_parser("signals", help="in tin hieu hien tai (mo phong)")
    s.add_argument("--desk", default="forex")
    args = p.parse_args(argv)
    cfg = load_config()
    if args.cmd == "demo":
        print("DiamondX10 demo — du lieu MO PHONG, khong phai gia that")
        for desk, strat in STRATEGIES.items():
            feed = SimulatedFeed(desk)
            bars = feed.bars(30)
            print(f"[{desk}] {strat.name}: {len(bars)} bars, close cuoi={bars[-1]['close']:.2f}")
        pf = Portfolio.from_config(cfg)
        print(pf.summary())
        log_decision("DEMO", "HOLD", "demo run, khong co lenh that")
        print("OK: demo chay xong. Xem decisions/decisions-log.csv")
    elif args.cmd == "backtest":
        print(run_backtest(args.desk, args.days))
    elif args.cmd == "signals":
        feed = SimulatedFeed(args.desk)
        print(generate_signals(args.desk, feed.bars(60)))


if __name__ == "__main__":
    main()
