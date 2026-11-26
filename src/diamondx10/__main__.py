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


def _desk_symbols(cfg, desk, symbol):
    """Tat ca symbol cua desk; --symbol thi chi lay 1 symbol do."""
    if symbol:
        return [symbol]
    symbols = (cfg.get("data", {}).get("symbols", {}) or {}).get(desk) or []
    if not symbols:
        raise ValueError(f"Chua cau hinh symbol cho desk {desk!r} trong config.yaml")
    return list(symbols)


def split_desk_capital(desk_cap, n_symbols):
    """Chia von desk deu cho n symbol; moi symbol chi dung 1 phan von
    de tinh size, tranh dat qua tay khi nhieu symbol cung co tin hieu."""
    if n_symbols <= 0:
        return 0.0
    return desk_cap / n_symbols


def stop_and_target(entry, action, sl_pct, tp_pct):
    """Tinh stop loss va take profit theo % gia vao.
    BUY: SL duoi gia, TP tren gia. SELL: nguoc lai. Tra (sl, tp)."""
    if action == "BUY":
        return entry * (1 - sl_pct), entry * (1 + tp_pct)
    return entry * (1 + sl_pct), entry * (1 - tp_pct)


def risk_pct_for_symbol(cfg, symbol):
    """% rui ro moi lenh cho 1 symbol: lay trong bang per_symbol_pct neu co,
    khong thi dung muc chung max_risk_per_trade_pct. Chi nhung symbol can
    rui ro cao moi dat duoc 0.01 lot (EURUSD 3%, XAUUSD 10%, BTCUSD 8%)
    moi co trong bang; con lai giu muc chung thap."""
    risk_cfg = (cfg or {}).get("risk") or {}
    table = risk_cfg.get("per_symbol_pct") or {}
    if symbol in table:
        return float(table[symbol])
    return float(risk_cfg.get("max_risk_per_trade_pct", 1.0))


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
        symbols = _desk_symbols(cfg, args.desk, args.symbol)
        print(f"DiamondX10 MT5 DEMO [{mode}] — desk {args.desk}, "
              f"symbols {', '.join(symbols)}")
        print("CHI TAI KHOAN DEMO. Khong bao gio dat lenh that.")
        pf = Portfolio.from_config(cfg)
        desk_cap = pf.desks[args.desk].capital_usd
        per_symbol_cap = split_desk_capital(desk_cap, len(symbols))
        print(f"Von desk {desk_cap:.0f} USD chia cho {len(symbols)} symbol: "
              f"{per_symbol_cap:.0f} USD/symbol de tinh size.")
        sl_pct = cfg["risk"]["default_stop_loss_pct"] / 100.0
        tp_pct = cfg["risk"].get("default_take_profit_pct", 5.0) / 100.0
        failed = 0
        for symbol in symbols:
            print(f"--- {symbol} "
                  f"(rui ro {risk_pct_for_symbol(cfg, symbol):g}%/lenh) ---")
            try:
                feed, mt5, account, server = _mt5_context(cfg, args.desk, symbol)
            except (ImportError, ConnectionError, ValueError) as exc:
                print(f"LOI ({symbol}): {exc}")
                failed += 1
                continue
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
                    print("OK: dry-run xong, KHONG dat lenh.")
                    continue
                if sig["action"] == "HOLD":
                    print("Tin hieu HOLD — khong dat lenh.")
                    continue
                entry = feed.latest_price(symbol)
                sl, tp = stop_and_target(entry, sig["action"], sl_pct, tp_pct)
                from .execution import CONTRACT_SIZES

                contract = CONTRACT_SIZES.get(args.desk, 100000)
                risk_pct = risk_pct_for_symbol(cfg, symbol)
                volume = args.volume or position_size_lots(
                    per_symbol_cap, risk_pct, entry, sl, contract_size=contract)
                if volume <= 0:
                    print("Volume tinh duoc = 0 — khong dat lenh "
                          "(kiem tra risk/entry/SL).")
                    continue
                result = place_demo_order(
                    mt5, symbol=symbol, action=sig["action"], volume=volume,
                    price=entry, sl=sl, tp=tp, desk=args.desk,
                    manager=cfg["fund"]["desks"][args.desk]["manager"],
                    cfg=cfg, account_info=account, server=server)
                print(f"OK: lenh DEMO da gui: {result}")
            finally:
                feed.close()
        print(f"Xong {mode} desk {args.desk} ({len(symbols)} symbol). "
              f"Xem decisions/decisions-log.csv")
        if failed:
            print(f"Co {failed}/{len(symbols)} symbol loi.")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
