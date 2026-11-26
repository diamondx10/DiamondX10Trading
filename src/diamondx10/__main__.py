"""CLI entry: python3 -m diamondx10 demo | backtest | signals
| mt5-dry-run | mt5-trade | mt5-symbols.

Lenh mt5-* CHI dung voi tai khoan DEMO (Exness demo + MT5 terminal).
Xem docs/mt5-demo.md truoc khi chay.
"""
import argparse
import os

from .backtest import run_backtest
from .config import load_config
from .data.feeds import SimulatedFeed
from .data.providers import build_feed
from .decisions import log_decision
from .execution import (
    account_is_demo,
    check_symbols_available,
    place_demo_order,
    position_size_lots,
)
from .portfolio import Portfolio
from .signals import generate_signals
from .strategies import STRATEGIES


def _mt5_context(cfg, desk, symbol=None, mt5_module=None):
    """Tao MT5Feed + thong tin tai khoan; tra (feed, account_info, server)."""
    from .data.mt5_feed import load_mt5

    mt5 = load_mt5(mt5_module)
    feed = build_feed(cfg, desk, symbol=symbol, mt5_module=mt5_module)
    account = feed.account_info()
    server = (cfg.get("mt5") or {}).get("server") or ""
    return feed, mt5, account, server


def _desk_symbol(cfg, desk, symbol):
    if symbol:
        return symbol
    symbols = (cfg.get("data", {}).get("symbols", {}) or {}).get(desk) or []
    if not symbols:
        raise ValueError(f"Chua cau hinh symbol cho desk {desk!r} trong config.yaml")
    return symbols[0]


def main(argv=None):
    p = argparse.ArgumentParser(prog="diamondx10")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="chay demo voi du lieu mo phong")
    b = sub.add_parser("backtest", help="backtest placeholder")
    b.add_argument("--desk", default="forex")
    b.add_argument("--days", type=int, default=30)
    s = sub.add_parser("signals", help="in tin hieu hien tai (mo phong)")
    s.add_argument("--desk", default="forex")
    d = sub.add_parser("mt5-dry-run",
                       help="DEMO: lay gia that tu MT5 demo, chi in tin hieu, KHONG dat lenh")
    d.add_argument("--desk", default="forex")
    d.add_argument("--symbol", default=None)
    t = sub.add_parser("mt5-trade",
                       help="DEMO: dat lenh DEMO qua MT5 (chi tai khoan demo, co chan an toan)")
    t.add_argument("--desk", default="forex")
    t.add_argument("--symbol", default=None)
    t.add_argument("--volume", type=float, default=None,
                   help="lot MT5; neu khong truyen thi tinh theo risk config")
    y = sub.add_parser("mt5-symbols",
                       help="DEMO: kiem tra symbol nao co tren server MT5 demo")
    y.add_argument("--desk", default=None)
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
    elif args.cmd == "mt5-symbols":
        print("DiamondX10 — kiem tra symbol tren MT5 DEMO (khong dat lenh)")
        desks = [args.desk] if args.desk else list(STRATEGIES)
        all_symbols = []
        for desk in desks:
            all_symbols += (cfg.get("data", {}).get("symbols", {}) or {}).get(desk) or []
        try:
            feed, mt5, account, server = _mt5_context(cfg, desks[0], all_symbols[0])
        except (ImportError, ConnectionError, ValueError) as exc:
            print(f"LOI: {exc}")
            return 1
        try:
            have, missing = check_symbols_available(mt5, all_symbols)
            print(f"Server: {server or '(lay tu tai khoan dang dang nhap)'}")
            print(f"Co tren server demo: {', '.join(have) if have else '(khong co symbol nao)'}")
            if missing:
                print(f"CANH BAO — khong co tren server demo: {', '.join(missing)}")
                print("  Vi du CDNS co the khong co tren Exness MT5 demo — "
                      "doi symbol cho desk do hoac dung nguon du lieu khac.")
        finally:
            feed.close()
    elif args.cmd in ("mt5-dry-run", "mt5-trade"):
        mode = "DRY-RUN" if args.cmd == "mt5-dry-run" else "TRADE"
        symbol = _desk_symbol(cfg, args.desk, args.symbol)
        print(f"DiamondX10 MT5 DEMO [{mode}] — desk {args.desk}, symbol {symbol}")
        print("CHI TAI KHOAN DEMO. Khong bao gio dat lenh that.")
        try:
            feed, mt5, account, server = _mt5_context(cfg, args.desk, symbol)
        except (ImportError, ConnectionError, ValueError) as exc:
            print(f"LOI: {exc}")
            return 1
        try:
            if not account_is_demo(mt5, account, server):
                raise SystemExit(
                    "TU CHOI: tai khoan MT5 dang dang nhap KHONG phai demo "
                    f"(server={server!r}). Chi chay demo."
                )
            bars = feed.bars(60)
            sig = generate_signals(args.desk, bars)
            print(f"Gia moi nhat {symbol}: {feed.latest_price(symbol)}")
            print(f"Tin hieu: {sig}")
            if args.cmd == "mt5-dry-run":
                log_decision(symbol, f"DRY-RUN-{sig['action']}",
                             f"MT5 demo dry-run: {sig['reason']} [khong gui lenh]",
                             desk=args.desk,
                             manager=cfg["fund"]["desks"][args.desk]["manager"])
                print("OK: dry-run xong, KHONG dat lenh. Xem decisions/decisions-log.csv")
                return
            if sig["action"] == "HOLD":
                print("Tin hieu HOLD — khong dat lenh.")
                return
            pf = Portfolio.from_config(cfg)
            desk_cap = pf.desks[args.desk].capital_usd
            risk_pct = cfg["risk"]["max_risk_per_trade_pct"]
            entry = feed.latest_price(symbol)
            sl_pct = cfg["risk"]["default_stop_loss_pct"] / 100.0
            sl = entry * (1 - sl_pct) if sig["action"] == "BUY" else entry * (1 + sl_pct)
            from .execution import CONTRACT_SIZES

            contract = CONTRACT_SIZES.get(args.desk, 100000)
            volume = args.volume or position_size_lots(
                desk_cap, risk_pct, entry, sl, contract_size=contract)
            if volume <= 0:
                print("Volume tinh duoc = 0 — khong dat lenh (kiem tra risk/entry/SL).")
                return
            result = place_demo_order(
                mt5, symbol=symbol, action=sig["action"], volume=volume,
                price=entry, sl=sl, desk=args.desk,
                manager=cfg["fund"]["desks"][args.desk]["manager"],
                cfg=cfg, account_info=account, server=server)
            print(f"OK: lenh DEMO da gui: {result}")
        finally:
            feed.close()


if __name__ == "__main__":
    raise SystemExit(main())
