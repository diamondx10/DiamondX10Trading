"""Backtest engine that (Phase 3): chay chien luoc tren du lieu MO PHONG
va tinh P&L that theo tung lenh (thay cho placeholder chi in tin hieu
cuoi o Phase 0-2).

Gia dinh (assumptions) — doc ky truoc khi doc ket qua:
- Du lieu MO PHONG (`SimulatedFeed`, theo desk): ket qua KHONG phai
  hieu suat that, khong dung de ra quyet dinh giao dich that.
- SimulatedFeed la theo DESK (1 chuoi gia cho ca desk), khong theo
  symbol. Backtest per-symbol chay CUNG chuoi gia do voi von/risk/
  contract size rieng cua tung symbol — chi de kiem tra logic
  sizing va chien luoc, khong phai so sanh symbol that.
- Warm-up: bo qua tin hieu cho den khi co it nhat 20 bar lich su
  (du cho SMA20/RSI(14)/ATR(14)). Chien luoc tu than cung tra HOLD
  khi chua du du lieu.
- Vao lenh o gia dong cua cua bar co tin hieu BUY/SELL (khi chua co
  vi the mo). Quan ly vi the mo o moi bar sau do, theo thu tu:
  1. cap nhat trailing SL theo gia dong cua (`strategy.trailing_stop`);
  2. cham SL (low <= SL neu BUY, high >= SL neu SELL) hoac TP
     (high >= TP neu BUY, low <= TP neu SELL) — trong CUNG 1 bar ma
     ca SL va TP deu cham thi uu tien SL (huong bao thu);
  3. tin hieu dao chieu day du (`strategy.reversal_exit`) -> dong
     o gia dong cua.
  Vi the van mo o bar cuoi cung duoc dong ep o gia dong cua cuoi
  (ly do "end_of_data") de moi lenh deu duoc hach toan.
- Sizing: `risk.position_size` voi von chia deu cua symbol, % risk
  cua symbol (doc tu bang `risk.per_symbol_pct` trong config, giong
  `__main__.risk_pct_for_symbol`) va contract size theo desk tu
  `execution.CONTRACT_SIZES`. Lot MT5 = units / contract size, chi
  de tham khao: lenh duoi 0,01 lot VAN DUOC MO trong backtest (de
  du lieu mo phong van cho ra ket qua) nhung duoc danh dau
  `below_min_lot=True` — lenh do KHONG dat duoc tren MT5 that.
- Phi: `fee_pct` % tren notional (units x gia vao), tru 1 lan moi
  lenh tron (round trip). Truot gia: `slippage_pct` % tren gia vao,
  ap dung bat loi ca 2 chan (vao + ra): BUY vao cao hon, ra thap hon;
  SELL nguoc lai. Chi phi truot gia = 2 x units x gia vao x slippage%.
  Mac dinh (config muc "backtest"): fee 0,02%, slippage 0,01% —
  muc bao thu, co the doi trong config.
- Sharpe: tinh tu loi nhuan tren duong equity theo tung bar (co
  tinh P&L chua thuc hien cua vi the mo, mark-to-market o gia dong
  cua), annualize bang sqrt(24192) — 252 ngay giao dich/nam x 96
  bar M15/ngay. Du lieu mo phong khong co lich that nen Sharpe nay
  CHI MINH HOA.
- In-sample / out-of-sample: `train_fraction` (mac dinh 0,7) cat
  bars thanh 2 doan; engine chay RIENG tren tung doan (von khoi
  dau lai tu dau, warm-up lai tu dau) va bao cao ca 2 doan + toan bo.

Phase C (du lieu that — xem docs/real-data-backtest.md): them
`run_backtest_from_history` / `run_walk_forward_from_history` doc
bars tu kho SQLite (`HistoryStore`) thay cho `SimulatedFeed`.
Moi symbol dung CHUOI BAR RIENG cua no (khac du lieu mo phong theo
desk — moi symbol chay cung chuoi gia): `run_backtest` /
`run_walk_forward` nhan them `bars_by_symbol={symbol: [bars]}` va
duong equity cap desk duoc noi theo TRUC THOI GIAN (hop nhat cac
moc thoi gian cua moi symbol, forward-fill) thay cho gop theo chi
so bar. Khi khong truyen `bars_by_symbol` thi duong cu giu nguyen
y het (ket qua cu khong doi).
"""
import copy
import itertools
import math
from datetime import datetime, timezone

from .config import load_config
from .data.feeds import SimulatedFeed
from .data.history import HistoryStore
from .execution import CONTRACT_SIZES, DEFAULT_CONTRACT_SIZE
from .models.quant import atr as _atr
from .risk import expected_shortfall, position_size, value_at_risk
from .strategies import STRATEGIES, build_strategies
from .strategies.registry import (
    STRATEGY_REGISTRY,
    build_strategy_for_symbol,
    get_strategy,
    validate_strategy_params,
)

WARMUP_BARS = 20
DEFAULT_FEE_PCT = 0.02
DEFAULT_SLIPPAGE_PCT = 0.01
# So bar toi thieu de backtest tu kho lich su (Phase C): moi doan
# train/test can it nhat 1 luot warm-up (20 bar) moi cho ra tin hieu
# co nghia — it hon thi bao loi ro rang thay vi tra bao cao rong.
MIN_HISTORY_BARS = 2 * WARMUP_BARS
# Duong dan kho mac dinh khi config khong co muc `history.db_path`
# (trung voi HistoryStore mac dinh: data/history.db theo goc repo).
DEFAULT_HISTORY_DB_PATH = "data/history.db"
# 252 ngay giao dich/nam x 96 bar M15/ngay. Chi de annualize Sharpe;
# du lieu mo phong khong co lich that nen con so nay chi minh hoa.
SHARPE_BARS_PER_YEAR = 24192
MIN_LOT = 0.01


def _risk_pct_for_symbol(cfg, symbol):
    """% rui ro moi lenh cua 1 symbol, doc tu bang `risk.per_symbol_pct`
    trong config, khong co thi dung muc chung `max_risk_per_trade_pct`.
    Cung logic nhu `__main__.risk_pct_for_symbol`; viet lai o day (chi
    doc bang trong config, KHONG sao chep bang) de tranh import vong
    giua backtest <-> __main__ (bang so lieu duy nhat nam o config)."""
    risk_cfg = (cfg or {}).get("risk") or {}
    table = risk_cfg.get("per_symbol_pct") or {}
    if symbol in table:
        return float(table[symbol])
    return float(risk_cfg.get("max_risk_per_trade_pct", 1.0))


def _split_capital(desk_cap, n_symbols):
    """Von desk chia deu cho n symbol (giong `__main__.split_desk_capital`)."""
    if n_symbols <= 0:
        return 0.0
    return desk_cap / n_symbols


def _merge_equity_curves(series, per_symbol_cap, desk_cap):
    """Noi duong equity cua cac symbol thanh duong equity cap desk
    theo TRUC THOI GIAN (Phase C — moi symbol co chuoi bar rieng).

    series: list (times, equity_curve) moi symbol — equity_curve[i]
    la von symbol tai bar times[i] (bat dau = per_symbol_cap).
    Tra (timeline, desk_curve): timeline la hop nhat cac moc thoi
    gian (tang dan); tai moi moc, von cua symbol nao chua co bar
    thi giu gia tri gan nhat truoc do (forward-fill), truoc bar dau
    tien thi = per_symbol_cap. desk_curve bat dau = desk_cap.
    Khi moi symbol cung moc thoi gian thi ket qua y het gop theo
    chi so bar nhu duong cu.
    """
    timeline = sorted({t for times, _ in series for t in times})
    desk_curve = []
    for t in timeline:
        total = desk_cap
        for times, curve in series:
            value = per_symbol_cap
            for bar_time, equity in zip(times, curve):
                if bar_time <= t:
                    value = equity
                else:
                    break
            total += value - per_symbol_cap
        desk_curve.append(total)
    return timeline, desk_curve


def compute_metrics(trades, equity_curve, start_capital):
    """Chi so tu danh sach lenh da dong + duong equity theo tung bar.

    Tra ve dict: total_return_pct, n_trades, wins, losses, win_rate,
    profit_factor (None neu khong co lenh thua — khong xac dinh,
    hien "n/a" trong bao cao), sharpe (None neu khong du bien dong),
    max_drawdown_pct, total_pnl, gross_profit, gross_loss,
    final_equity, avg_win, avg_loss.
    """
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    total_pnl = sum(pnls)
    if equity_curve:
        final_equity = equity_curve[-1]
    else:
        final_equity = start_capital
    total_return_pct = ((final_equity - start_capital) / start_capital * 100
                        if start_capital else 0.0)
    max_dd = 0.0
    peak = equity_curve[0] if equity_curve else start_capital
    for v in equity_curve:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak * 100)
    sharpe = None
    returns = []
    for prev, cur in zip(equity_curve, equity_curve[1:]):
        if prev:
            returns.append((cur - prev) / prev)
    if len(returns) >= 2:
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / len(returns)
        std = math.sqrt(var)
        if std > 0:
            sharpe = mean / std * math.sqrt(SHARPE_BARS_PER_YEAR)
    profit_factor = None
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    # VaR/CVaR lich su 95% tren loi nhuan tung bar (repo DiamondX10 cu,
    # PortfolioRiskEngine._calc_var/_calc_cvar). Can it nhat 20 ky nhu
    # ban goc; it hon thi None (hien "n/a"). Chi so bao cao, khong
    # phai gioi han chan lenh.
    var_95 = cvar_95 = None
    if len(returns) >= 20:
        var_95 = value_at_risk(returns, 0.95)
        cvar_95 = expected_shortfall(returns, 0.95)
    return {
        "total_return_pct": total_return_pct,
        "n_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(trades) * 100) if trades else 0.0,
        "profit_factor": profit_factor,
        "sharpe": sharpe,
        "max_drawdown_pct": max_dd,
        "var_95_pct": (var_95 * 100) if var_95 is not None else None,
        "cvar_95_pct": (cvar_95 * 100) if cvar_95 is not None else None,
        "total_pnl": total_pnl,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "final_equity": final_equity,
        "avg_win": (gross_profit / len(wins)) if wins else 0.0,
        "avg_loss": (gross_loss / len(losses)) if losses else 0.0,
    }


def _close_position(position, exit_price, exit_reason, exit_index,
                    exit_time, fee_pct, slippage_pct):
    """Dong vi the mo thanh 1 trade da hach toan day du phi/truot gia."""
    direction = position["direction"]
    entry = position["entry"]
    units = position["units"]
    sign = 1 if direction == "BUY" else -1
    slip = entry * slippage_pct / 100.0
    if direction == "BUY":
        eff_entry, eff_exit = entry + slip, exit_price - slip
    else:
        eff_entry, eff_exit = entry - slip, exit_price + slip
    gross = sign * (eff_exit - eff_entry) * units
    fee = units * entry * fee_pct / 100.0
    slippage_cost = 2 * units * slip
    pnl = gross - fee
    return {
        "symbol": position["symbol"],
        "direction": direction,
        "entry": entry,
        "exit": exit_price,
        "entry_index": position["entry_index"],
        "exit_index": exit_index,
        "entry_time": position["entry_time"],
        "exit_time": exit_time,
        "exit_reason": exit_reason,
        "entry_reason": position["entry_reason"],
        "units": units,
        "lots": position["lots"],
        "below_min_lot": position["lots"] < MIN_LOT,
        "sl_initial": position["sl_initial"],
        "sl": position["sl"],
        "tp": position["tp"],
        "atr": position["atr"],
        "gross_pnl": gross,
        "fee": fee,
        "slippage_cost": slippage_cost,
        "pnl": pnl,
    }


def _run_segment(strategy, bars, *, symbol, capital, risk_pct,
                 contract_size, fee_pct, slippage_pct):
    """Chay engine tren 1 doan bars lien tuc. Tra ve dict trades,
    equity_curve (do dai = so bar, bat dau = capital) va so tin hieu
    bi bo qua vi size tinh ra bang 0."""
    trades = []
    equity_curve = []
    position = None
    realized = 0.0
    skipped_zero_size = 0
    atr_period = strategy.params.get("atr_period", 14)
    for i, bar in enumerate(bars):
        history = bars[:i + 1]
        if position is not None and i > position["entry_index"]:
            # 1. Trailing SL theo gia dong cua (ATR cua lich su den bar nay).
            atr_val = _atr([b["high"] for b in history],
                           [b["low"] for b in history],
                           [b["close"] for b in history], atr_period)
            if atr_val:
                position["sl"] = strategy.trailing_stop(
                    position["entry"], position["sl"],
                    position["direction"], bar["close"], atr_val)
            # 2. SL truoc, TP sau (cung bar cham ca hai -> uu tien SL).
            exit_price = None
            exit_reason = None
            if position["direction"] == "BUY":
                if bar["low"] <= position["sl"]:
                    exit_price, exit_reason = position["sl"], "SL"
                elif bar["high"] >= position["tp"]:
                    exit_price, exit_reason = position["tp"], "TP"
            else:
                if bar["high"] >= position["sl"]:
                    exit_price, exit_reason = position["sl"], "SL"
                elif bar["low"] <= position["tp"]:
                    exit_price, exit_reason = position["tp"], "TP"
            # 3. Dao chieu day du -> dong o gia dong cua.
            if exit_price is None and strategy.reversal_exit(
                    position["direction"], history):
                exit_price, exit_reason = bar["close"], "reversal"
            if exit_price is not None:
                trade = _close_position(position, exit_price, exit_reason,
                                        i, bar["time"], fee_pct, slippage_pct)
                trades.append(trade)
                realized += trade["pnl"]
                position = None
        if position is None and len(history) >= WARMUP_BARS:
            action, sig_reason, levels = strategy.signal(history)
            if action in ("BUY", "SELL") and levels:
                entry = levels["entry"]
                units = position_size(capital, risk_pct, entry, levels["sl"])
                if units <= 0:
                    skipped_zero_size += 1
                else:
                    position = {
                        "symbol": symbol,
                        "direction": action,
                        "entry": entry,
                        "entry_index": i,
                        "entry_time": bar["time"],
                        "entry_reason": sig_reason,
                        "units": units,
                        "lots": units / contract_size if contract_size else 0.0,
                        "sl_initial": levels["sl"],
                        "sl": levels["sl"],
                        "tp": levels["tp"],
                        "atr": levels["atr"],
                    }
        unrealized = 0.0
        if position is not None:
            sign = 1 if position["direction"] == "BUY" else -1
            unrealized = sign * (bar["close"] - position["entry"]) * position["units"]
        equity_curve.append(capital + realized + unrealized)
    if position is not None:
        # Dong ep o gia dong cua bar cuoi de hach toan moi lenh da mo.
        trade = _close_position(position, bars[-1]["close"], "end_of_data",
                                len(bars) - 1, bars[-1]["time"],
                                fee_pct, slippage_pct)
        trades.append(trade)
        realized += trade["pnl"]
        equity_curve[-1] = capital + realized
    return {"trades": trades, "equity_curve": equity_curve,
            "skipped_zero_size": skipped_zero_size}


def _run_symbol(strategy, bars, *, symbol, capital, risk_pct,
                contract_size, fee_pct, slippage_pct, train_fraction):
    """Chay full + 2 doan train/test cho 1 symbol."""
    full = _run_segment(strategy, bars, symbol=symbol, capital=capital,
                        risk_pct=risk_pct, contract_size=contract_size,
                        fee_pct=fee_pct, slippage_pct=slippage_pct)
    split_idx = int(len(bars) * train_fraction)
    train = _run_segment(strategy, bars[:split_idx], symbol=symbol,
                         capital=capital, risk_pct=risk_pct,
                         contract_size=contract_size, fee_pct=fee_pct,
                         slippage_pct=slippage_pct)
    test = _run_segment(strategy, bars[split_idx:], symbol=symbol,
                        capital=capital, risk_pct=risk_pct,
                        contract_size=contract_size, fee_pct=fee_pct,
                        slippage_pct=slippage_pct)
    return {
        "capital_usd": capital,
        "risk_pct": risk_pct,
        "contract_size": contract_size,
        "trades": full["trades"],
        "equity_curve": full["equity_curve"],
        "skipped_zero_size": full["skipped_zero_size"],
        "metrics": compute_metrics(full["trades"], full["equity_curve"], capital),
        "segments": {
            "train": {"n_bars": len(bars[:split_idx]),
                      "trades": train["trades"],
                      "equity_curve": train["equity_curve"],
                      "metrics": compute_metrics(
                          train["trades"], train["equity_curve"], capital)},
            "test": {"n_bars": len(bars[split_idx:]),
                     "trades": test["trades"],
                     "equity_curve": test["equity_curve"],
                     "metrics": compute_metrics(
                         test["trades"], test["equity_curve"], capital)},
        },
    }


def run_backtest(desk, days=30, *, cfg=None, symbols=None,
                 train_fraction=0.7, bars=None, fee_pct=None,
                 slippage_pct=None, strategy_name=None,
                 bars_by_symbol=None):
    """Backtest 1 desk tren du lieu mo phong. Tra ve dict ket qua
    (trades, metrics theo desk/symbol/doan, assumptions) — xem
    `format_backtest_report` de in thanh van ban.

    Giu tuong thich cu: `run_backtest(desk, days)` van chay duoc.
    `bars`: truyen bars san co (dung cho test); khong truyen thi lay
    tu SimulatedFeed (days + 20 bar warm-up).
    `bars_by_symbol` (Phase C): dict {symbol: [bars]} — moi symbol
    chay chuoi bar RIENG cua no (du lieu that tu kho, moi symbol
    1 chuoi gia). Chi truyen 1 trong 2: `bars` hoac `bars_by_symbol`.
    Duong equity cap desk khi do noi theo truc thoi gian
    (`_merge_equity_curves`); khi moi symbol cung moc thoi gian thi
    ket qua y het duong `bars` chung.
    `strategy_name`: None/"default" = quy tac chung da chot;
    "donchian" = chien luoc breakout Donchian (CHI DE SO SANH
    TRONG BACKTEST, khong dung cho duong live).
    """
    if desk not in STRATEGIES:
        raise ValueError(f"Desk khong biet: {desk!r} "
                         f"(co: {', '.join(sorted(STRATEGIES))})")
    if not 0 < train_fraction < 1:
        raise ValueError(f"train_fraction phai trong (0, 1), nhan {train_fraction}")
    cfg = cfg if cfg is not None else load_config()
    if symbols is None:
        symbols = (cfg.get("data", {}).get("symbols", {}) or {}).get(desk) or []
    symbols = list(symbols)
    if not symbols:
        raise ValueError(f"Chua cau hinh symbol cho desk {desk!r} trong config.yaml")
    # Moi symbol chay dung tham so cua no (mac dinh < chung < desk <
    # symbol — xem strategies/registry.py). Khong co override thi
    # giong he thong cu: 1 chien luoc/desk cho moi symbol.
    strategies = {s: _pick_strategy(desk, cfg, strategy_name, symbol=s)
                  for s in symbols}
    strat = strategies[symbols[0]]
    try:
        desk_cap = float(cfg["fund"]["desks"][desk]["capital_usd"])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"Chua cau hinh von cho desk {desk!r} trong config")
    bt_cfg = (cfg or {}).get("backtest") or {}
    if fee_pct is None:
        fee = float(bt_cfg.get("fee_pct", DEFAULT_FEE_PCT))
    else:
        fee = float(fee_pct)
    if slippage_pct is None:
        slip = float(bt_cfg.get("slippage_pct", DEFAULT_SLIPPAGE_PCT))
    else:
        slip = float(slippage_pct)
    if bars is not None and bars_by_symbol is not None:
        raise ValueError("Chi truyen 1 trong 2: bars hoac bars_by_symbol")
    if bars_by_symbol is not None:
        # Phase C: moi symbol 1 chuoi bar rieng (du lieu that tu kho).
        bars_map = {}
        for symbol in symbols:
            if symbol not in bars_by_symbol:
                raise ValueError(
                    f"Thieu bars cho symbol {symbol!r} trong bars_by_symbol "
                    f"(co: {', '.join(sorted(bars_by_symbol)) or '(rong)'})")
            symbol_bars = list(bars_by_symbol[symbol])
            if not symbol_bars:
                raise ValueError(
                    f"Symbol {symbol!r} khong co bar nao trong bars_by_symbol")
            bars_map[symbol] = symbol_bars
        n_bars = max(len(b) for b in bars_map.values())
        # Doan train/test o cap desk lay theo symbol dai nhat (moi
        # symbol cat rieng theo ti le train_fraction ben trong
        # _run_symbol; so bar doan cua tung symbol nam o per_symbol).
        split_idx = max(int(len(b) * train_fraction)
                        for b in bars_map.values())
        desk_curve = desk_train_curve = desk_test_curve = None
    else:
        if bars is None:
            bars = SimulatedFeed(desk).bars(days + WARMUP_BARS)
        bars = list(bars)
        bars_map = {s: bars for s in symbols}
        n_bars = len(bars)
        split_idx = int(len(bars) * train_fraction)
        desk_curve = [desk_cap] * len(bars)
        desk_train_curve = [desk_cap] * split_idx
        desk_test_curve = [desk_cap] * (len(bars) - split_idx)
    contract_size = CONTRACT_SIZES.get(desk, DEFAULT_CONTRACT_SIZE)
    per_symbol_cap = _split_capital(desk_cap, len(symbols))
    per_symbol = {}
    all_trades = []
    # Moc thoi gian moi symbol (de noi duong equity theo truc thoi
    # gian khi moi symbol 1 chuoi bar rieng).
    symbol_times = {}
    for symbol in symbols:
        risk_pct = _risk_pct_for_symbol(cfg, symbol)
        res = _run_symbol(strategies[symbol], bars_map[symbol], symbol=symbol, capital=per_symbol_cap,
                          risk_pct=risk_pct, contract_size=contract_size,
                          fee_pct=fee, slippage_pct=slip,
                          train_fraction=train_fraction)
        per_symbol[symbol] = res
        all_trades.extend(res["trades"])
        symbol_times[symbol] = [b["time"] for b in bars_map[symbol]]
        if bars_by_symbol is None:
            for i, v in enumerate(res["equity_curve"]):
                desk_curve[i] += v - per_symbol_cap
            for i, v in enumerate(res["segments"]["train"]["equity_curve"]):
                desk_train_curve[i] += v - per_symbol_cap
            for i, v in enumerate(res["segments"]["test"]["equity_curve"]):
                desk_test_curve[i] += v - per_symbol_cap
    if bars_by_symbol is not None:
        # Noi duong equity cap desk theo truc thoi gian (forward-fill
        # symbol nao chua co bar tai moc do). So bar doan train cua
        # moi symbol lay tu chinh ket qua _run_symbol cua no.
        _, desk_curve = _merge_equity_curves(
            [(symbol_times[s], per_symbol[s]["equity_curve"])
             for s in symbols], per_symbol_cap, desk_cap)
        _, desk_train_curve = _merge_equity_curves(
            [(symbol_times[s][:per_symbol[s]["segments"]["train"]["n_bars"]],
              per_symbol[s]["segments"]["train"]["equity_curve"])
             for s in symbols], per_symbol_cap, desk_cap)
        _, desk_test_curve = _merge_equity_curves(
            [(symbol_times[s][per_symbol[s]["segments"]["train"]["n_bars"]:],
              per_symbol[s]["segments"]["test"]["equity_curve"])
             for s in symbols], per_symbol_cap, desk_cap)
    desk_metrics = compute_metrics(all_trades, desk_curve, desk_cap)
    # Metrics doan o cap desk: gop trades cua doan tu moi symbol.
    # (Doan chay lai rieng nen trades doan khong phai cat lat cua full.)
    train_trades = [t for res in per_symbol.values()
                    for t in res["segments"]["train"]["trades"]]
    test_trades = [t for res in per_symbol.values()
                   for t in res["segments"]["test"]["trades"]]
    assumptions = {
        "fee_pct": fee,
        "slippage_pct": slip,
        "warmup_bars": WARMUP_BARS,
        "sharpe_bars_per_year": SHARPE_BARS_PER_YEAR,
        "contract_size": contract_size,
        "simulated": True,
        "sizing": ("units = risk.position_size(von symbol, risk% symbol, "
                   "entry, SL); lots = units / contract size (tham khao); "
                   "lenh duoi 0,01 lot van mo trong backtest, danh dau "
                   "below_min_lot — khong dat duoc tren MT5 that"),
        "exit_priority": "trong 1 bar: trailing SL -> SL truoc TP -> dao chieu",
        "forced_close": "vi the mo o bar cuoi dong ep o gia dong cua (end_of_data)",
    }
    return {
        "desk": desk,
        "strategy": strat.name,
        "strategy_name": strategy_name or "default",
        "strategy_params": {s: dict(strategies[s].params)
                            for s in symbols},
        "days": days,
        "n_bars": n_bars,
        "n_bars_by_symbol": ({s: len(bars_map[s]) for s in symbols}
                             if bars_by_symbol is not None else None),
        "capital_usd": desk_cap,
        "symbols": symbols,
        "train_fraction": train_fraction,
        "simulated": True,
        "assumptions": assumptions,
        "metrics": desk_metrics,
        "segments": {
            "train": {"n_bars": split_idx,
                      "metrics": compute_metrics(train_trades, desk_train_curve,
                                                 desk_cap)},
            "test": {"n_bars": n_bars - split_idx,
                     "metrics": compute_metrics(test_trades, desk_test_curve,
                                                desk_cap)},
        },
        "per_symbol": per_symbol,
        "trades": sorted(all_trades, key=lambda t: t["exit_index"]),
    }


def _pick_strategy(desk, cfg, strategy_name=None, symbol=None):
    """Chon chien luoc cho 1 desk (va 1 symbol neu co).

    Mac dinh ("default"/None): quy tac chung da chot (SMA + RSI + ATR,
    build_strategies). "donchian": breakout Donchian — CHI DUNG CHO
    BACKTEST SO SANH, khong dung cho duong live (xem
    strategies/breakout.py). Ten la -> ValueError (tu registry).
    Co symbol thi tham so resolve rieng cho symbol do (mac dinh <
    chung < desk < symbol); khong co symbol thi dung tham so desk.
    """
    name = strategy_name or "default"
    if symbol is not None:
        return build_strategy_for_symbol(cfg, desk, symbol, name)
    cfg_s = (cfg or {}).get("strategy") or {}
    shared = {k: v for k, v in cfg_s.items()
              if k not in ("desks", "per_symbol")}
    desk_params = (cfg_s.get("desks") or {}).get(desk) or {}
    return get_strategy(name, desk=desk, params=shared,
                        desk_params=desk_params)


def run_walk_forward(desk, days=90, *, cfg=None, symbols=None,
                     train_bars=60, test_bars=20, step_bars=20,
                     fee_pct=None, slippage_pct=None, bars=None,
                     strategy_name=None, bars_by_symbol=None):
    """Walk-forward validation (y tuong tu repo DiamondX10 cu,
    backtest/walk_forward.py — nhung chay bang engine cua chinh tool
    nay, khong copy ban loi cua repo cu: lot co dinh 0,01, SL tinh
    tu (high-low) cua bar thay vi ATR, P&L nhan 100000 cho ca vang).

    Cat bars thanh cac cua so lan luot: train_bars bar de danh gia
    in-sample, test_bars bar tiep theo de danh gia out-of-sample,
    roi truot step_bars bar va lap lai. Moi cua so chay lai tu dau
    (von khoi dau lai, warm-up lai). Tra ve dict: windows (moi cua so
    gom train/test metrics + so lenh), aggregated (metrics gop cua
    tat ca doan out-of-sample, duong equity noi cac doan test lai
    voi nhau), all_oos_trades.

    bars: truyen bars san co (dung cho test); khong truyen thi lay tu
    SimulatedFeed (days + 20 bar warm-up). Can it nhat
    train_bars + test_bars bar, neu khong du thi ValueError.
    `bars_by_symbol` (Phase C): nhu `run_backtest` — moi symbol
    1 chuoi bar rieng; so cua so lay theo symbol NGAN nhat (moi cua
    so phai du bar cho moi symbol), duong equity cua so noi theo
    truc thoi gian.
    """
    if desk not in STRATEGIES:
        raise ValueError(f"Desk khong biet: {desk!r} "
                         f"(co: {', '.join(sorted(STRATEGIES))})")
    if train_bars <= 0 or test_bars <= 0 or step_bars <= 0:
        raise ValueError("train_bars/test_bars/step_bars phai > 0")
    cfg = cfg if cfg is not None else load_config()
    if symbols is None:
        symbols = (cfg.get("data", {}).get("symbols", {}) or {}).get(desk) or []
    symbols = list(symbols)
    if not symbols:
        raise ValueError(f"Chua cau hinh symbol cho desk {desk!r} trong config.yaml")
    # Moi symbol chay dung tham so cua no (xem run_backtest).
    strategies = {s: _pick_strategy(desk, cfg, strategy_name, symbol=s)
                  for s in symbols}
    strat = strategies[symbols[0]]
    try:
        desk_cap = float(cfg["fund"]["desks"][desk]["capital_usd"])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"Chua cau hinh von cho desk {desk!r} trong config")
    bt_cfg = (cfg or {}).get("backtest") or {}
    fee = float(bt_cfg.get("fee_pct", DEFAULT_FEE_PCT)) \
        if fee_pct is None else float(fee_pct)
    slip = float(bt_cfg.get("slippage_pct", DEFAULT_SLIPPAGE_PCT)) \
        if slippage_pct is None else float(slippage_pct)
    if bars is not None and bars_by_symbol is not None:
        raise ValueError("Chi truyen 1 trong 2: bars hoac bars_by_symbol")
    if bars_by_symbol is not None:
        # Phase C: moi symbol 1 chuoi bar rieng (du lieu that tu kho).
        bars_map = {}
        for symbol in symbols:
            if symbol not in bars_by_symbol:
                raise ValueError(
                    f"Thieu bars cho symbol {symbol!r} trong bars_by_symbol "
                    f"(co: {', '.join(sorted(bars_by_symbol)) or '(rong)'})")
            symbol_bars = list(bars_by_symbol[symbol])
            if not symbol_bars:
                raise ValueError(
                    f"Symbol {symbol!r} khong co bar nao trong bars_by_symbol")
            if len(symbol_bars) < train_bars + test_bars:
                raise ValueError(
                    f"Khong du bars cho walk-forward ({symbol}): can toi "
                    f"thieu {train_bars + test_bars}, chi co "
                    f"{len(symbol_bars)}")
            bars_map[symbol] = symbol_bars
        n_bars = max(len(b) for b in bars_map.values())
        # So cua so lay theo symbol ngan nhat.
        max_start = min(len(b) for b in bars_map.values())
    else:
        if bars is None:
            bars = SimulatedFeed(desk).bars(days + WARMUP_BARS)
        bars = list(bars)
        bars_map = {s: bars for s in symbols}
        n_bars = len(bars)
        max_start = len(bars)
        if len(bars) < train_bars + test_bars:
            raise ValueError(
                f"Khong du bars cho walk-forward: can toi thieu "
                f"{train_bars + test_bars}, chi co {len(bars)}")
    contract_size = CONTRACT_SIZES.get(desk, DEFAULT_CONTRACT_SIZE)
    per_symbol_cap = _split_capital(desk_cap, len(symbols))
    windows = []
    oos_trades = []
    oos_curve = [desk_cap]
    # Gop ca doan train (chi de so sanh train vs test khi sweep /
    # kiem tra overfitting — ket qua chinh van chi la OOS).
    # Luu y: cac cua so train CHONG LAP nhau (truot step_bars) nen
    # train gop khong phai mau doc lap, chi de tham khao.
    train_trades = []
    train_curve = [desk_cap]
    start = 0
    while start + train_bars + test_bars <= max_start:
        win = {"index": len(windows), "start_bar": start,
               "train_bars": train_bars, "test_bars": test_bars,
               "per_symbol": {}}
        win_trades = []
        win_train_trades = []
        win_test_series = []
        win_train_series = []
        for symbol in symbols:
            symbol_bars = bars_map[symbol]
            train_seg = symbol_bars[start:start + train_bars]
            test_seg = symbol_bars[start + train_bars:
                                   start + train_bars + test_bars]
            risk_pct = _risk_pct_for_symbol(cfg, symbol)
            strat_sym = strategies[symbol]
            # Danh gia TRUC TIEP tren tung doan (khong cat train/test
            # ben trong nua — doan train/test da duoc cat o vong ngoai).
            train_seg_res = _run_segment(
                strat_sym, train_seg, symbol=symbol, capital=per_symbol_cap,
                risk_pct=risk_pct, contract_size=contract_size,
                fee_pct=fee, slippage_pct=slip)
            test_seg_res = _run_segment(
                strat_sym, test_seg, symbol=symbol, capital=per_symbol_cap,
                risk_pct=risk_pct, contract_size=contract_size,
                fee_pct=fee, slippage_pct=slip)
            win["per_symbol"][symbol] = {
                "train": compute_metrics(
                    train_seg_res["trades"], train_seg_res["equity_curve"],
                    per_symbol_cap),
                "test": compute_metrics(
                    test_seg_res["trades"], test_seg_res["equity_curve"],
                    per_symbol_cap),
                "test_trades": len(test_seg_res["trades"]),
            }
            win_trades.extend(test_seg_res["trades"])
            win_train_trades.extend(train_seg_res["trades"])
            win_test_series.append(
                ([b["time"] for b in test_seg],
                 test_seg_res["equity_curve"]))
            win_train_series.append(
                ([b["time"] for b in train_seg],
                 train_seg_res["equity_curve"]))
        # Duong equity cua so: gop theo chi so bar khi chung 1 chuoi
        # gia, theo truc thoi gian khi moi symbol 1 chuoi rieng
        # (_merge_equity_curves tra cung ket qua khi moc thoi gian
        # giong nhau).
        _, win_curve = _merge_equity_curves(win_test_series,
                                            per_symbol_cap, desk_cap)
        _, win_train_curve = _merge_equity_curves(win_train_series,
                                                  per_symbol_cap, desk_cap)
        win["test_metrics"] = compute_metrics(win_trades, win_curve, desk_cap)
        win["test_trades"] = len(win_trades)
        win["train_metrics"] = compute_metrics(win_train_trades,
                                               win_train_curve, desk_cap)
        win["train_trades"] = len(win_train_trades)
        windows.append(win)
        oos_trades.extend(win_trades)
        train_trades.extend(win_train_trades)
        # Noi duong equity out-of-sample: cong don bien dong tung cua so.
        for v in win_curve[1:]:
            oos_curve.append(oos_curve[-1] + (v - win_curve[0]))
        for v in win_train_curve[1:]:
            train_curve.append(train_curve[-1] + (v - win_train_curve[0]))
        start += step_bars
    aggregated = compute_metrics(oos_trades, oos_curve, desk_cap)
    aggregated_train = compute_metrics(train_trades, train_curve, desk_cap)
    return {
        "desk": desk,
        "strategy": strat.name,
        "strategy_name": strategy_name or "default",
        "strategy_params": {s: dict(strategies[s].params)
                            for s in symbols},
        "days": days,
        "n_bars": n_bars,
        "n_bars_by_symbol": ({s: len(bars_map[s]) for s in symbols}
                             if bars_by_symbol is not None else None),
        "capital_usd": desk_cap,
        "symbols": symbols,
        "train_bars": train_bars,
        "test_bars": test_bars,
        "step_bars": step_bars,
        "n_windows": len(windows),
        "windows": windows,
        "aggregated": aggregated,
        "aggregated_train": aggregated_train,
        "oos_trades": sorted(oos_trades, key=lambda t: t["exit_index"]),
        "oos_equity_curve": oos_curve,
    }


# --- Phase C: backtest / walk-forward tren du lieu that tu kho ---

def _open_history_store(cfg, store):
    """Mo kho lich su theo config neu caller khong truyen store san.

    Tra (store, tu_mo): caller chi dong kho khi tu_mo=True. Duong dan
    kho lay tu muc `history.db_path` trong config, mac dinh
    `data/history.db` (tuong doi theo goc repo — xem HistoryStore).
    """
    if store is not None:
        return store, False
    hist_cfg = (cfg or {}).get("history") or {}
    db_path = hist_cfg.get("db_path") or DEFAULT_HISTORY_DB_PATH
    return HistoryStore(db_path), True


def _resolve_history_symbols(desk, cfg, symbols):
    """Symbol cho backtest tu kho: truyen ro thi dung, khong thi lay
    tu config (data.symbols[desk]). Desk la / khong co symbol thi
    ValueError ro rang (giong run_backtest)."""
    if desk not in STRATEGIES:
        raise ValueError(f"Desk khong biet: {desk!r} "
                         f"(co: {', '.join(sorted(STRATEGIES))})")
    if symbols is None:
        symbols = (cfg.get("data", {}).get("symbols", {}) or {}).get(desk) or []
    symbols = list(symbols)
    if not symbols:
        raise ValueError(f"Chua cau hinh symbol cho desk {desk!r} trong config.yaml")
    return symbols


def _load_history_bars(store, symbols, timeframe, start=None, end=None):
    """Doc bar tu kho cho moi symbol; tra {symbol: [bars]}.

    Kho trong hoac symbol it bar thi ValueError neu ro so bar hien co
    va so toi thieu can (MIN_HISTORY_BARS) — khong tra bao cao rong
    de nguoi doc tuong la chien luoc khong co lenh.
    """
    bars_map = {}
    for symbol in symbols:
        bars = store.get_bars(symbol, timeframe, start=start, end=end)
        if not bars:
            raise ValueError(
                f"Kho lich su chua co bar nao cho {symbol} ({timeframe})"
                + (f" trong khoang da chon" if start is not None or end is not None else "")
                + " — chay backfill / export-bars tren may Windows "
                  "(MT5 demo) truoc, roi import CSV vao kho "
                  "(xem docs/real-data-backtest.md)")
        if len(bars) < MIN_HISTORY_BARS:
            raise ValueError(
                f"Symbol {symbol} ({timeframe}) chi co {len(bars)} bar "
                f"trong kho, can toi thieu {MIN_HISTORY_BARS} bar de "
                f"backtest (warm-up {WARMUP_BARS} bar + chia train/test) "
                "— backfill them (90 ngay M15 ~ 8640 bar) roi chay lai")
        bars_map[symbol] = bars
    return bars_map


def _history_span_days(bars_map):
    """So ngay (float) tu bar dau den bar cuoi cua toan bo symbol."""
    starts = [b[0]["time"] for b in bars_map.values() if b]
    ends = [b[-1]["time"] for b in bars_map.values() if b]
    if not starts:
        return None
    return round((max(ends) - min(starts)) / 86400, 2)


def _mark_history_result(result, timeframe, bars_map):
    """Danh dau ket qua la tu du lieu that (thay cho mo phong)."""
    result["simulated"] = False
    result["source"] = "history"
    result["timeframe"] = timeframe
    result["start"] = min(b[0]["time"] for b in bars_map.values())
    result["end"] = max(b[-1]["time"] for b in bars_map.values())
    result["days"] = _history_span_days(bars_map)
    assumptions = result.get("assumptions")
    if isinstance(assumptions, dict):
        assumptions["simulated"] = False
        assumptions["source"] = ("history — nen that MT5 demo, kho SQLite; "
                                 "moi symbol 1 chuoi bar rieng")
        assumptions["timeframe"] = timeframe
    return result


def run_backtest_from_history(desk, cfg, *, symbols=None,
                              timeframe="M15", start=None, end=None,
                              train_fraction=0.7, strategy_name="default",
                              store=None, fee_pct=None, slippage_pct=None):
    """Backtest 1 desk tren NEN THAT tu kho lich su (Phase C).

    Doc bars cua moi symbol tu `HistoryStore` (mac dinh mo theo
    `history.db_path` trong cfg; truyen `store` san neu da mo), roi
    chay lai DUNG engine `run_backtest` (khong viet engine thu hai)
    voi `bars_by_symbol` — moi symbol 1 chuoi bar rieng.
    start/end: epoch int hoac datetime (loc time >= start, <= end).
    Kho trong / symbol thieu bar -> ValueError neu so bar hien co
    va so toi thieu can. Ket qua giong `run_backtest` nhung
    `simulated=False`, `source="history"`, them `timeframe` /
    `start` / `end` (epoch UTC) / `n_bars_by_symbol`.
    CLI `--source history` se goi ham nay o buoc tich hop sau.
    """
    if not 0 < train_fraction < 1:
        raise ValueError(f"train_fraction phai trong (0, 1), nhan {train_fraction}")
    symbols = _resolve_history_symbols(desk, cfg, symbols)
    store, own_store = _open_history_store(cfg, store)
    try:
        bars_map = _load_history_bars(store, symbols, timeframe,
                                      start=start, end=end)
    finally:
        if own_store:
            store.close()
    result = run_backtest(
        desk, _history_span_days(bars_map), cfg=cfg, symbols=symbols,
        train_fraction=train_fraction, bars_by_symbol=bars_map,
        strategy_name=strategy_name, fee_pct=fee_pct,
        slippage_pct=slippage_pct)
    return _mark_history_result(result, timeframe, bars_map)


def run_walk_forward_from_history(desk, cfg, *, symbols=None,
                                  timeframe="M15", start=None, end=None,
                                  train_bars=60, test_bars=20, step_bars=20,
                                  strategy_name="default", store=None,
                                  fee_pct=None, slippage_pct=None):
    """Walk-forward tren NEN THAT tu kho lich su (Phase C).

    Nhu `run_backtest_from_history` nhung goi `run_walk_forward`:
    nhieu cua so train/test truot, chi doan test (OOS) gop vao ket
    qua tong hop. Moi symbol can it nhat train_bars + test_bars bar
    (thieu thi ValueError neu ten symbol + so bar hien co).
    Ket qua giong `run_walk_forward` nhung `simulated=False`,
    `source="history"`, them `timeframe` / `start` / `end`.
    CLI `--source history` se goi ham nay o buoc tich hop sau.
    """
    if train_bars <= 0 or test_bars <= 0 or step_bars <= 0:
        raise ValueError("train_bars/test_bars/step_bars phai > 0")
    symbols = _resolve_history_symbols(desk, cfg, symbols)
    store, own_store = _open_history_store(cfg, store)
    try:
        bars_map = _load_history_bars(store, symbols, timeframe,
                                      start=start, end=end)
    finally:
        if own_store:
            store.close()
    result = run_walk_forward(
        desk, _history_span_days(bars_map), cfg=cfg, symbols=symbols,
        train_bars=train_bars, test_bars=test_bars, step_bars=step_bars,
        bars_by_symbol=bars_map, strategy_name=strategy_name,
        fee_pct=fee_pct, slippage_pct=slippage_pct)
    return _mark_history_result(result, timeframe, bars_map)


def format_walk_forward_report(result):
    """In ket qua run_walk_forward() thanh van ban (tieng Viet)."""
    simulated = result.get("simulated", True)
    header = ("DiamondX10 WALK-FORWARD (MO PHONG) — KHONG PHAI HIEU SUAT THAT"
              if simulated else
              "DiamondX10 WALK-FORWARD (DU LIEU THAT — MT5 DEMO)")
    lines = [
        header,
        f"Desk: {result['desk']} ({result['strategy']}) | "
        f"von desk: {result['capital_usd']:.0f} USD | "
        f"bars: {result['n_bars']} | cua so: train {result['train_bars']} "
        f"bar / test {result['test_bars']} bar / buoc {result['step_bars']} "
        f"bar | so cua so: {result['n_windows']}",
        f"Symbols: {', '.join(result['symbols'])}",
        "",
        "== TONG HOP OUT-OF-SAMPLE (gop moi cua so test) ==",
    ]
    lines += _metrics_block("OOS gop", result["aggregated"])
    lines.append("")
    lines.append("== TUNG CUA SO (test = out-of-sample) ==")
    for w in result["windows"]:
        m = w["test_metrics"]
        lines.append(
            f"  Cua so {w['index']} (bar {w['start_bar']}-"
            f"{w['start_bar'] + w['train_bars'] + w['test_bars'] - 1}): "
            f"lenh OOS {w['test_trades']} | return "
            f"{_fmt_num(m['total_return_pct'], '%')} | win rate "
            f"{_fmt_num(m['win_rate'], '%')} | Sharpe "
            f"{_fmt_num(m['sharpe'])} | max DD "
            f"{_fmt_num(m['max_drawdown_pct'], '%')} | P&L "
            f"{_fmt_num(m['total_pnl'], ' USD')}")
    lines.append("")
    if simulated:
        lines.append("Ghi chu: moi cua so chay lai tu dau (von khoi dau lai, "
                     "warm-up lai); chi doan test duoc gop vao ket qua tong "
                     "hop. Ket qua tren du lieu mo phong, chi dung de kiem "
                     "tra do on dinh cua chien luoc qua cac doan thoi gian.")
    else:
        lines.append("Ghi chu: moi cua so chay lai tu dau (von khoi dau lai, "
                     "warm-up lai); chi doan test duoc gop vao ket qua tong "
                     "hop. Ket qua tren nen that MT5 demo — van KHONG phai "
                     "bao dam loi nhuan tuong lai, chi dung de kiem tra do "
                     "on dinh cua chien luoc qua cac doan thoi gian.")
    return "\n".join(lines)


def _metrics_summary(metrics):
    """Rut gon 1 dict metrics ve cac chi so dung de so sanh/xep hang."""
    return {
        "total_return_pct": metrics["total_return_pct"],
        "win_rate": metrics["win_rate"],
        "max_drawdown_pct": metrics["max_drawdown_pct"],
        "n_trades": metrics["n_trades"],
        "sharpe": metrics["sharpe"],
        "profit_factor": metrics["profit_factor"],
        "total_pnl": metrics["total_pnl"],
    }


def compare_strategies(desk, strategy_names, days=90, *, cfg=None,
                       symbols=None, train_bars=60, test_bars=20,
                       step_bars=20, fee_pct=None, slippage_pct=None,
                       bars=None, bars_by_symbol=None):
    """Chay walk-forward cho nhieu chien luoc tren CUNG du lieu va tra
    bang so sanh CHI TREN ket qua out-of-sample (doan test).

    strategy_names: list ten trong registry (vd ["default",
    "donchian"]). Ten la -> ValueError tu registry. Moi chien luoc
    1 dong: tong return OOS, win rate OOS, max drawdown OOS, so
    lenh OOS (+ Sharpe / profit factor / P&L OOS de tham khao).
    "rows" sap theo return OOS giam dan (tot nhat len dau) — thu tu
    nay chi de doc, khong phai ket luan chien luoc tot nhat (xem
    docs/strategy-engine.md: can them so cua so + du lieu that).
    "walk_forward" giu ket qua day du tung chien luoc de doc sau.
    `bars_by_symbol` (Phase C): nhu `run_backtest` — moi symbol
    1 chuoi bar rieng (du lieu that tu kho).
    """
    if not strategy_names:
        raise ValueError("compare_strategies can it nhat 1 chien luoc")
    for name in strategy_names:
        if name not in STRATEGY_REGISTRY:
            raise ValueError(
                f"Chien luoc khong biet: {name!r} "
                f"(co: {', '.join(sorted(STRATEGY_REGISTRY))})")
    if symbols is None:
        cfg_eff = cfg if cfg is not None else load_config()
        symbols = (cfg_eff.get("data", {}).get("symbols", {}) or {}).get(desk) or []
    rows = []
    walk_forward = {}
    for name in strategy_names:
        result = run_walk_forward(
            desk, days, cfg=cfg, symbols=list(symbols),
            train_bars=train_bars, test_bars=test_bars,
            step_bars=step_bars, fee_pct=fee_pct,
            slippage_pct=slippage_pct, bars=bars,
            bars_by_symbol=bars_by_symbol, strategy_name=name)
        walk_forward[name] = result
        meta = STRATEGY_REGISTRY[name]
        row = {"strategy": result["strategy"],
               "strategy_name": name,
               "backtest_only": meta["backtest_only"],
               "n_windows": result["n_windows"],
               "oos_return_pct": result["aggregated"]["total_return_pct"],
               "oos_win_rate": result["aggregated"]["win_rate"],
               "oos_max_drawdown_pct":
                   result["aggregated"]["max_drawdown_pct"],
               "oos_n_trades": result["aggregated"]["n_trades"],
               "oos_sharpe": result["aggregated"]["sharpe"],
               "oos_profit_factor": result["aggregated"]["profit_factor"],
               "oos_total_pnl": result["aggregated"]["total_pnl"]}
        rows.append(row)
    rows.sort(key=lambda r: r["oos_return_pct"], reverse=True)
    return {
        "desk": desk,
        "symbols": list(symbols),
        "strategy_names": list(strategy_names),
        "train_bars": train_bars,
        "test_bars": test_bars,
        "step_bars": step_bars,
        "n_windows": rows[0]["n_windows"] if rows else 0,
        "simulated": bars_by_symbol is None,
        "rows": rows,
        "walk_forward": walk_forward,
    }


def format_strategy_comparison(comparison):
    """In bang so sanh cua compare_strategies() thanh van ban."""
    simulated = comparison.get("simulated", True)
    header = ("DiamondX10 SO SANH CHIEN LUOC — CHI TREN OUT-OF-SAMPLE "
              "(MO PHONG)" if simulated else
              "DiamondX10 SO SANH CHIEN LUOC — CHI TREN OUT-OF-SAMPLE "
              "(DU LIEU THAT — MT5 DEMO)")
    lines = [
        header,
        f"Desk: {comparison['desk']} | symbols: "
        f"{', '.join(comparison['symbols'])} | cua so: train "
        f"{comparison['train_bars']} / test {comparison['test_bars']} / "
        f"buoc {comparison['step_bars']} bar | so cua so: "
        f"{comparison['n_windows']}",
        "",
        "Chien luoc | Return OOS | Win rate OOS | Max DD OOS | Lenh OOS | "
        "Sharpe OOS | P&L OOS",
    ]
    for r in comparison["rows"]:
        flag = " [CHI BACKTEST]" if r["backtest_only"] else ""
        lines.append(
            f"{r['strategy_name']} ({r['strategy']}){flag} | "
            f"{_fmt_num(r['oos_return_pct'], '%')} | "
            f"{_fmt_num(r['oos_win_rate'], '%')} | "
            f"{_fmt_num(r['oos_max_drawdown_pct'], '%')} | "
            f"{r['oos_n_trades']} | "
            f"{_fmt_num(r['oos_sharpe'])} | "
            f"{_fmt_num(r['oos_total_pnl'], ' USD')}")
    lines.append("")
    if simulated:
        lines.append("Ghi chu: bang chi dung ket qua out-of-sample (doan test "
                     "cua walk-forward) — doan train khong tinh vao bang nay. "
                     "Ket qua tren du lieu mo phong, chi dung de so sanh logic "
                     "chien luoc, khong phai bang chung hieu suat that.")
    else:
        lines.append("Ghi chu: bang chi dung ket qua out-of-sample (doan test "
                     "cua walk-forward) — doan train khong tinh vao bang nay. "
                     "Ket qua tren nen that MT5 demo, chi dung de so sanh logic "
                     "chien luoc, khong phai bang chung hieu suat tuong lai.")
    return "\n".join(lines)


# Luoi mac dinh cho sweep: NHO de chay nhanh (9 to hop). Chi quet
# tham so anh huong truc tiep den vao lenh / stop; khong quet loai
# chien luoc hay quy tac (khong doi quy tac bang sweep).
DEFAULT_SWEEP_GRID = {
    "atr_sl_mult": [1.0, 1.5, 2.0],
    "rsi_buy_low": [45, 50, 55],
}

# Chenh lech train - test (diem %) vuot muc nay thi danh dau nghi
# overfitting trong bao cao sweep.
SWEEP_OVERFIT_GAP_PCT = 5.0


def sweep_params(desk, bars, strategy_name="default", param_grid=None, *,
                 cfg=None, symbols=None, train_bars=30, test_bars=10,
                 step_bars=10, fee_pct=None, slippage_pct=None,
                 max_combinations=27, top_n=3, bars_by_symbol=None):
    """Quet luoi tham so (nghien cuu — CHONG OVERFITTING o muc nhe).

    Moi bo tham so chay walk-forward day du; XEP HANG CHI THEO ket
    qua out-of-sample (doan test). Bao cao kem ca train va test de
    lo overfitting: bo nao train cao ma test thap (chenh > 5 diem %)
    thi bi danh dau, khong duoc chon chi vi train tot.
    param_grid: dict {ten tham so: [gia tri, ...]}; mac dinh
    DEFAULT_SWEEP_GRID (9 to hop). Tong so to hop vuot
    max_combinations -> ValueError (tranh quet luoi lon chay lau
    roi tu cho la "tim duoc" tham so tot tren mau nho).
    Ham nay KHONG tu dong ap tham so thang vao config — nguoi doc
    bao cao tu quyet co doi config khong (xem docs/strategy-engine.md).
    `bars_by_symbol` (Phase C): nhu `run_backtest` — moi symbol
    1 chuoi bar rieng (du lieu that tu kho); khi do `bars` co the
    la None.
    """
    grid = dict(param_grid) if param_grid is not None else dict(DEFAULT_SWEEP_GRID)
    if not grid:
        raise ValueError("param_grid rong: can it nhat 1 tham so de quet")
    for key, values in grid.items():
        if not isinstance(values, (list, tuple)) or not values:
            raise ValueError(
                f"Luoi quet cho {key!r} phai la list gia tri khong rong")
        for value in values:
            validate_strategy_params({key: value}, strategy_name)
    keys = sorted(grid)
    combos = [dict(zip(keys, combo))
              for combo in itertools.product(*(grid[k] for k in keys))]
    if len(combos) > max_combinations:
        raise ValueError(
            f"Luoi quet co {len(combos)} to hop, vuot gioi han "
            f"{max_combinations} — thu nho luoi (it tham so / it gia tri "
            "hon) de tranh overfitting tren mau nho va chay lau")
    base_cfg = cfg if cfg is not None else load_config()
    results = []
    for combo in combos:
        cfg_try = copy.deepcopy(base_cfg)
        strat_cfg = dict(cfg_try.get("strategy") or {})
        strat_cfg.update(combo)
        cfg_try["strategy"] = strat_cfg
        wf = run_walk_forward(
            desk, 0, cfg=cfg_try, symbols=symbols,
            train_bars=train_bars, test_bars=test_bars,
            step_bars=step_bars, fee_pct=fee_pct,
            slippage_pct=slippage_pct, bars=bars,
            bars_by_symbol=bars_by_symbol,
            strategy_name=strategy_name)
        entry = {
            "params": dict(combo),
            "train": _metrics_summary(wf["aggregated_train"]),
            "test": _metrics_summary(wf["aggregated"]),
            "n_windows": wf["n_windows"],
        }
        entry["overfit_gap_pct"] = (
            entry["train"]["total_return_pct"]
            - entry["test"]["total_return_pct"])
        results.append(entry)
    results.sort(key=lambda e: e["test"]["total_return_pct"], reverse=True)
    return {
        "desk": desk,
        "strategy_name": strategy_name,
        "param_grid": {k: list(v) for k, v in grid.items()},
        "n_combinations": len(results),
        "train_bars": train_bars,
        "test_bars": test_bars,
        "step_bars": step_bars,
        "simulated": bars_by_symbol is None,
        "results": results,
        "top": results[:top_n],
    }


def format_sweep_report(sweep):
    """In ket qua sweep_params() thanh van ban (top-N + canh bao)."""
    lines = [
        "DiamondX10 PARAMETER SWEEP — CHI XEP HANG THEO OUT-OF-SAMPLE "
        "(MO PHONG)",
        f"Desk: {sweep['desk']} | chien luoc: {sweep['strategy_name']} | "
        f"luoi: {sweep['param_grid']} | to hop: "
        f"{sweep['n_combinations']} | cua so: train {sweep['train_bars']} "
        f"/ test {sweep['test_bars']} / buoc {sweep['step_bars']} bar",
        "",
        "== TOP (xep theo return OOS — doan test) ==",
    ]
    for i, entry in enumerate(sweep["top"], 1):
        params_txt = ", ".join(f"{k}={v}" for k, v in
                               sorted(entry["params"].items()))
        flag = ""
        if entry["overfit_gap_pct"] > SWEEP_OVERFIT_GAP_PCT:
            flag = (f" [NGHI OVERFITTING: train hon test "
                    f"{entry['overfit_gap_pct']:.2f} diem %]")
        lines.append(
            f"  {i}. {params_txt} | train return "
            f"{_fmt_num(entry['train']['total_return_pct'], '%')} "
            f"(lenh {entry['train']['n_trades']}) | test return "
            f"{_fmt_num(entry['test']['total_return_pct'], '%')} "
            f"(lenh {entry['test']['n_trades']}, win rate "
            f"{_fmt_num(entry['test']['win_rate'], '%')}, max DD "
            f"{_fmt_num(entry['test']['max_drawdown_pct'], '%')}){flag}")
    lines.append("")
    lines.append("CANH BAO OVERFITTING: xep hang chi theo OOS, nhung luoi "
                 "cang lon / mau cang nho thi bo thang OOS cang co the la "
                 "ngau nhien. Khong tu dong ap tham so thang vao config; "
                 "chi doi config sau khi kiem chung lai tren du lieu that "
                 "(MT5) va duoc Phu/Yuling duyet. Ket qua tren du lieu mo "
                 "phong, khong phai hieu suat that.")
    return "\n".join(lines)


def _fmt_num(value, suffix=""):
    if value is None:
        return "n/a"
    return f"{value:.2f}{suffix}"


def _metrics_block(label, metrics):
    lines = [
        f"  {label}: return {_fmt_num(metrics['total_return_pct'], '%')} "
        f"| lenh: {metrics['n_trades']} "
        f"(thang {metrics['wins']}/thua {metrics['losses']}) "
        f"| win rate {_fmt_num(metrics['win_rate'], '%')} "
        f"| profit factor {_fmt_num(metrics['profit_factor'])} "
        f"| Sharpe {_fmt_num(metrics['sharpe'])} "
        f"| max DD {_fmt_num(metrics['max_drawdown_pct'], '%')} "
        f"| VaR95 {_fmt_num(metrics.get('var_95_pct'), '%')} "
        f"| CVaR95 {_fmt_num(metrics.get('cvar_95_pct'), '%')} "
        f"| P&L {_fmt_num(metrics['total_pnl'], ' USD')}",
    ]
    return lines


def format_backtest_report(result):
    """In ket qua run_backtest() thanh van ban (tieng Viet)."""
    simulated = result.get("simulated", True)
    if simulated:
        header = "DiamondX10 BACKTEST (MO PHONG) — KHONG PHAI HIEU SUAT THAT"
        warn = ("Ket qua tren du lieu mo phong khong du doan duoc ket qua giao "
                "dich that. Chi dung de kiem tra logic chien luoc / sizing.")
    else:
        header = "DiamondX10 BACKTEST (DU LIEU THAT — MT5 DEMO)"
        warn = ("Ket qua tren nen that tu kho lich su (MT5 demo). Van KHONG "
                "phai bao dam loi nhuan tuong lai — chi dung de kiem dinh "
                "chien luoc / sizing tren gia that.")
    lines = [
        header,
        warn,
        f"Desk: {result['desk']} ({result['strategy']}) | "
        f"von desk: {result['capital_usd']:.0f} USD | "
        f"bars: {result['n_bars']} (gom {result['assumptions']['warmup_bars']} "
        f"bar warm-up) | train/test: "
        f"{result['train_fraction']:.0%} / {1 - result['train_fraction']:.0%}",
        f"Symbols: {', '.join(result['symbols'])}",
        "",
        "== TONG DESK (gop moi symbol) ==",
    ]
    lines += _metrics_block("Full", result["metrics"])
    lines += _metrics_block(
        f"Train ({result['segments']['train']['n_bars']} bars)",
        result["segments"]["train"]["metrics"])
    lines += _metrics_block(
        f"Test ({result['segments']['test']['n_bars']} bars)",
        result["segments"]["test"]["metrics"])
    lines.append("")
    if simulated:
        lines.append("== THEO SYMBOL (von chia deu, cung chuoi gia mo phong "
                     "cua desk) ==")
    else:
        lines.append("== THEO SYMBOL (von chia deu, moi symbol 1 chuoi bar "
                     "rieng tu kho) ==")
    for symbol, res in result["per_symbol"].items():
        lines.append(
            f"-- {symbol}: von {res['capital_usd']:.0f} USD, "
            f"risk {res['risk_pct']:g}%/lenh, contract size "
            f"{res['contract_size']:g}, bo qua {res['skipped_zero_size']} "
            f"tin hieu vi size = 0")
        lines += _metrics_block("Full", res["metrics"])
        lines += _metrics_block(
            f"Train ({res['segments']['train']['n_bars']} bars)",
            res["segments"]["train"]["metrics"])
        lines += _metrics_block(
            f"Test ({res['segments']['test']['n_bars']} bars)",
            res["segments"]["test"]["metrics"])
    lines.append("")
    lines.append("== LENH DA DONG ==")
    if not result["trades"]:
        lines.append("  Khong co lenh nao (toan HOLD, hoac size tinh ra = 0).")
    for t in result["trades"]:
        flag = " [DUOI 0,01 LOT — khong dat duoc tren MT5]" \
            if t["below_min_lot"] else ""
        lines.append(
            f"  {t['symbol']} {t['direction']} vao {t['entry']:.4f} -> "
            f"ra {t['exit']:.4f} ({t['exit_reason']}) | "
            f"units {t['units']:.2f} ({t['lots']:.4f} lot) | "
            f"P&L {t['pnl']:.2f} USD (phi {t['fee']:.2f}, "
            f"truot gia {t['slippage_cost']:.2f}){flag}")
    lines.append("")
    a = result["assumptions"]
    lines.append("== GIA DINH ==")
    lines.append(f"  Phi: {a['fee_pct']}% notional/lenh tron; "
                 f"truot gia: {a['slippage_pct']}% gia vao, ca 2 chan.")
    lines.append(f"  Warm-up: {a['warmup_bars']} bar. {a['sizing']}.")
    lines.append(f"  {a['exit_priority']}. {a['forced_close']}.")
    lines.append(
        f"  Sharpe annualize sqrt({a['sharpe_bars_per_year']}) "
        "(252 ngay x 96 bar M15/ngay) — chi minh hoa, du lieu mo phong "
        "khong co lich that." if simulated else
        f"  Sharpe annualize sqrt({a['sharpe_bars_per_year']}) "
        "(252 ngay x 96 bar M15/ngay) — gia dinh lich giao dich deu, "
        "chung khoan chi co bar trong phien My.")
    if simulated:
        lines.append(
            "  GIOI HAN: SimulatedFeed la theo DESK — moi symbol cua desk "
            "chay CUNG chuoi gia mo phong, chi khac von/risk/contract size. "
            "Ket qua per-symbol khong phai so sanh that giua cac symbol.")
    else:
        start = datetime.fromtimestamp(result["start"], tz=timezone.utc)
        end = datetime.fromtimestamp(result["end"], tz=timezone.utc)
        lines.append(
            f"  NGUON: kho lich su, {result['timeframe']}, "
            f"{start:%Y-%m-%d %H:%M}..{end:%Y-%m-%d %H:%M} UTC; "
            f"so bar/symbol: {result['n_bars_by_symbol']}. Moi symbol "
            "chay chuoi bar RIENG cua no. Chung khoan chi co bar trong "
            "phien My (nghi cuoi tuan/le) — duong equity cap desk noi "
            "theo truc thoi gian, forward-fill symbol chua co bar.")
    return "\n".join(lines)
