"""Vong lap live (Phase D): 1 chu ky M15 -> xu ly tung symbol -> canh bao Telegram.

Luan chay:
  run_live_cycle() — 1 chu ky: voi moi symbol, mo MT5Feed (60 nen M15),
  goi process_symbol() (dung trinh tu gate nhu lenh mt5-trade), luu state
  sau moi symbol, gui canh bao Telegram khi co tin hieu / lenh / bi chan.
  run_live_loop() — lap chu ky, ngu toi bien nen M15 tiep theo.

Quy tac giu nguyen (khong doi): demo-only tuyet doi (moi duong dat lenh
qua place_demo_order co chan demo-only + margin check), toi da 1 lenh
moi/symbol/ngay, drawdown quy 10% + canh bao desk 5%, no-trade windows,
crypto cap USD, MT5 cho tat ca (khong Binance). Loi 1 symbol khong crash
ca chu ky; loi lay feed thi ghi log + bo qua symbol/chu ky do.
"""
import math
import time
from datetime import datetime, timezone

from . import audit as audit_mod
from . import outcomes as outcomes_mod
from . import telegram as telegram_mod
from .data.providers import build_feed
from .decisions import (
    count_trades_today,
    load_equity_state,
    log_decision,
    save_equity_state,
)
from .execution import (
    CONTRACT_SIZES,
    account_is_demo,
    check_margin,
    place_demo_order,
    position_size_lots,
)
from .killswitch import is_engaged, status as kill_switch_status
from .multitimeframe import compute_htf_trend, resolve_timeframes
from .portfolio import Portfolio
from .positions import new_position, realize_deals, reconcile_positions
from .risk import (
    DrawdownGuard,
    check_fund_limits,
    in_no_trade_window,
    today_pnl_from_log,
)
from .signals import generate_signals
from .strategies import build_strategy, build_strategies
from .synthesis import _verdict_age_hours, load_verdict, synthesize

# Khung nen ho tro (giong __main__.SUPPORTED_TIMEFRAMES).
SUPPORTED_TIMEFRAMES = {"M1", "M5", "M15", "H1", "D1"}
DEFAULT_LIVE = {"timeframe": "M15", "interval_min": 15}
DEFAULT_BARS = 60


def _recommend_mode(cfg, recommend_only=False):
    """True khi che do khuyen nghi (cho xac nhan) dang bat.

    Bat khi config trading.require_confirmation = true HOAC khi lan chay
    truyen recommend_only=True (co `live --recommend-only` /
    `mt5-trade --recommend-only`). recommend_only=False khong tat che
    do da bat trong config — no chi ep BAT khi True.
    """
    if recommend_only:
        return True
    return bool(((cfg or {}).get("trading") or {}).get(
        "require_confirmation", False))


def _log_outcome(result, sig, cfg, desk, symbol, outcome_store=None):
    """Ghi 1 ban ghi outcome cho tin hieu TRADED/RECOMMENDED.

    Goi TRUOC khi tra ket qua ve cho run_live_cycle (noi gui canh bao
    Telegram sau) — log-first. KHONG BAO GIO raise: loi ghi log chi
    canh bao trong outcomes, vong live chay tiep.
    outcome_store: duong dan file JSONL (de test); None thi dung
    decisions/signal-outcomes.jsonl mac dinh.
    """
    try:
        record = outcomes_mod.build_record(result, sig, cfg, desk, symbol)
        outcomes_mod.log_signal(outcome_store, record)
    except Exception as exc:  # noqa: BLE001 — ghi log khong duoc crash live
        print(f"Canh bao outcomes: khong ghi duoc ban ghi {symbol} ({exc})")


def _pending_store(pending_store=None):
    """PendingOrderStore dung cho che do khuyen nghi.

    pending_store truyen vao (de test) duoc dung luon; khong truyen thi
    tao PendingOrderStore() theo duong dan mac dinh
    (decisions/pending-orders.json).
    """
    if pending_store is not None:
        return pending_store
    from .pending import PendingOrderStore
    return PendingOrderStore()


def _pending_ttl_min(cfg):
    """TTL lenh cho (phut) tu config telegram.pending_order_ttl_min."""
    try:
        return float(((cfg or {}).get("telegram") or {}).get(
            "pending_order_ttl_min") or 15)
    except (TypeError, ValueError):
        return 15.0


def split_desk_capital(desk_cap, n_symbols):
    """Chia von desk deu cho n symbol; moi symbol chi dung 1 phan von
    de tinh size, tranh dat qua tay khi nhieu symbol cung co tin hieu."""
    if n_symbols <= 0:
        return 0.0
    return desk_cap / n_symbols


def risk_pct_for_symbol(cfg, symbol):
    """% rui ro moi lenh cho 1 symbol: lay trong bang per_symbol_pct neu co,
    khong thi dung muc chung max_risk_per_trade_pct."""
    risk_cfg = (cfg or {}).get("risk") or {}
    table = risk_cfg.get("per_symbol_pct") or {}
    if symbol in table:
        return float(table[symbol])
    return float(risk_cfg.get("max_risk_per_trade_pct", 1.0))


def _live_cfg(cfg):
    """Muc `live:` trong config, gop voi mac dinh Phase D."""
    merged = dict(DEFAULT_LIVE)
    merged.update((cfg or {}).get("live") or {})
    return merged


# So phut moi nen theo khung (dung de uoc luong so ngay can lay khi
# doc nen khung trend qua MT5Feed.bars_for_days).
_TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "D1": 1440}


def _fetch_trend_bars(feed, trend_tf, n):
    """Lay n nen khung trend tu feed (MTF v1 — muc 64).

    Tra list bar (co the ngan); tra None khi feed KHONG ho tro lay nen
    khung khac (vd SimulatedFeed / feed gia chi co bars(n)) — luc do
    loc HTF tat lang le, chay M15-only nhu cu. Loi lay nen thi tra []
    (thieu du lieu — loc khong ap dung, chi ghi chu trong reason).
    """
    if getattr(feed, "timeframe", None) == trend_tf:
        try:
            return list(feed.bars(n))
        except Exception:  # noqa: BLE001 — thieu du lieu, khong crash
            return []
    fn = getattr(feed, "bars_for_days", None)
    if not callable(fn):
        return None
    minutes = _TF_MINUTES.get(trend_tf, 60)
    days = max(1, math.ceil(n * minutes / 1440) + 2)
    try:
        bars = list(fn(timeframe=trend_tf, days=days))
    except Exception:  # noqa: BLE001 — thieu du lieu, khong crash
        return []
    return bars[-n:] if len(bars) > n else bars


def _desk_symbols(cfg, desk, symbol=None):
    """Tat ca symbol cua desk; --symbol thi chi lay 1 symbol do."""
    if symbol:
        return [symbol]
    symbols = (cfg.get("data", {}).get("symbols", {}) or {}).get(desk) or []
    if not symbols:
        raise ValueError(f"Chua cau hinh symbol cho desk {desk!r} trong config.yaml")
    return list(symbols)


def load_guard_and_positions(cfg):
    """Doc trang thai von/vi the tu decisions/equity-state.json; neu chua
    co thi tao guard moi tu von trong config. Gioi han drawdown luon lay
    theo config hien tai (nguon that)."""
    state = load_equity_state()
    fund_cfg = cfg.get("fund") or {}
    total = float(fund_cfg.get("total_capital_usd", 10000))
    desks_cfg = fund_cfg.get("desks") or {}
    desk_caps = {d: float(v.get("capital_usd", 0))
                 for d, v in desks_cfg.items()}
    risk_cfg = cfg.get("risk") or {}
    max_dd = float(risk_cfg.get("max_drawdown_pct", 10.0))
    warn = float(risk_cfg.get("desk_warning_pct", 5.0))
    if state and state.get("guard"):
        guard = DrawdownGuard.from_state(state["guard"])
        guard.max_drawdown_pct = max_dd
        guard.desk_warning_pct = warn
        positions = list(state.get("positions") or [])
    else:
        guard = DrawdownGuard(total, desk_caps, max_dd, warn)
        positions = []
    return guard, positions


def save_guard_and_positions(guard, positions):
    """Ghi trang thai von/vi the xuong decisions/equity-state.json."""
    save_equity_state({"guard": guard.to_state(), "positions": positions})


def reconcile_symbol_positions(cfg, desk, symbol, bars, strat, guard,
                               positions, mt5, manager):
    """Doi chieu vi the mo cua (desk, symbol) truoc tin hieu moi.

    O che do MT5 that: thu history_deals_get truoc de thuc hien cac deal
    MT5 da dong; vi the nao khong khop deal (hoac khong lay duoc deal)
    thi doi chieu theo nen (SL/TP/trailing/dao chieu). Loi o buoc deal
    khong lam hong buoc nen — luon co fallback.
    """
    fee_pct = float((cfg.get("backtest") or {}).get("fee_pct", 0) or 0)
    if mt5 is not None and hasattr(mt5, "history_deals_get"):
        try:
            deals = mt5.history_deals_get(0, int(time.time()))
        except Exception as exc:  # noqa: BLE001 — fallback sang doi chieu nen
            print(f"Luu y: khong doc duoc MT5 history_deals_get ({exc}) — "
                  "doi chieu vi the theo nen.")
            deals = None
        if deals:
            closed, _rest = realize_deals(guard, positions, deals,
                                          manager=manager)
            for item in closed:
                print(f"Vi the {item['position']['symbol']} dong theo MT5 deal: "
                      f"P&L {item['pnl']:.2f} USD.")
    closed, _open = reconcile_positions(guard, positions, desk, symbol, bars,
                                        strat, fee_pct, manager)
    for item in closed:
        print(f"Vi the {item['position']['symbol']} dong ({item['cause']}): "
              f"P&L {item['pnl']:.2f} USD.")


def _apply_fa_gate(cfg, desk, ta_action, verdict_store=None):
    """Doc nhan dinh PTCB moi nhat cua desk va tong hop voi PTKT.

    Tra (synthesis_dict, fa_note). synthesis_dict la ket qua cua
    synthesize(); fa_note la chuoi ngan ghi vao ket qua/log:
    "FA: buy 0.8", "FA: chua co", "FA: cu". Kho nhan dinh loi hoac
    khong doc duoc thi coi nhu chua co PTCB — khong bao gio crash
    vong live vi loi PTCB.
    """
    try:
        verdict = load_verdict(verdict_store, desk)
    except (ValueError, OSError) as exc:
        print(f"CANH BAO PTCB ({desk}): khong doc duoc kho nhan dinh "
              f"({exc}) — chay tiep chi theo PTKT.")
        verdict = None
    if verdict is None:
        return synthesize(ta_action, None, None, cfg), "FA: chua co"
    age = _verdict_age_hours(verdict)
    synth = synthesize(ta_action, verdict.get("direction"),
                       verdict.get("confidence"), cfg,
                       verdict_age_hours=age)
    if synth.get("fa_status") == "stale":
        note = "FA: cu"
    else:
        note = (f"FA: {verdict.get('direction')} "
                f"{verdict.get('confidence')}")
    return synth, note


def process_symbol(cfg, desk, symbol, *, feed, mt5, account, server,
                   manager, guard, positions, volume=None,
                   per_symbol_cap=None, strategies=None, bars=None,
                   now=None, verdict_store=None, recommend_only=False,
                   pending_store=None, outcome_store=None,
                   htf_bars=None):
    """Xu ly 1 symbol: dung trinh tu gate nhu lenh mt5-trade.

    (1) doi chieu vi the mo, (2) chan drawdown, (2b) kill switch,
    (2c) gioi han quy Phase F (lo ngay + so vi the mo), (3) chan
    no-trade window, (4) chan daily limit, (5) tin hieu (HOLD thi
    dung), (6) tinh levels/SL/TP theo ATR + sizing (volume 0 thi
    dung), (6b) hop nhat PTCB: nhan dinh co ban moi nhat cua desk
    tong hop voi PTKT (chan khi mau thuan manh — BLOCKED-FA-CONFLICT),
    (7) place_demo_order (demo-only + margin check nam trong do) —
    TRU KHI che do khuyen nghi bat (config trading.require_confirmation
    hoac recommend_only=True): luc do KHONG dat lenh ma tao lenh cho
    xac nhan trong PendingOrderStore, ghi log RECOMMENDED roi tra
    status RECOMMENDED (action van la BUY/SELL — huong tin hieu).
    Tra dict {symbol, action, status, reason, volume?, price?, sl?, tp?}
    voi status TRADED | RECOMMENDED | HELD | BLOCKED-<ly do> | ERROR.
    Len nao dat duoc thi ghi vi the moi vao `positions` (nguoi goi luu
    state sau do); lenh RECOMMENDED thi KHONG ghi vi the (chua dat
    lenh). Loi o 1 symbol chi tra ERROR, khong raise — khong crash
    chu ky.
    verdict_store: duong dan kho nhan dinh PTCB (de test); khong truyen
    thi dung decisions/fundamental-verdicts.json.
    recommend_only: True thi ep che do khuyen nghi cho lan chay nay
    (co `live --recommend-only` / `mt5-trade --recommend-only`).
    pending_store: PendingOrderStore truyen vao (de test); khong truyen
    thi tao moi theo duong dan mac dinh.
    outcome_store: duong dan file JSONL ghi outcome (de test); None
    thi dung decisions/signal-outcomes.jsonl mac dinh.
    htf_bars: nen khung trend (vd H1) truyen vao (de test); khong truyen
    thi tu lay tu feed khi `timeframes.trend_enabled` bat (chi MT5Feed
    ho tro lay nen khung khac; feed khong ho tro thi loc tat lang le).
    """
    strat = build_strategy(desk, symbol=symbol, cfg=cfg)
    if bars is None:
        try:
            bars = feed.bars(DEFAULT_BARS)
        except (ConnectionError, ValueError) as exc:
            print(f"LOI lay nen ({symbol}): {exc}")
            return {"symbol": symbol, "action": "ERROR", "status": "ERROR",
                    "reason": f"khong lay duoc nen: {exc}"}
    # (1) Doi chieu vi the mo TRUOC khi xu ly tin hieu moi.
    try:
        reconcile_symbol_positions(cfg, desk, symbol, bars, strat, guard,
                                   positions, mt5, manager)
    except Exception as exc:  # noqa: BLE001 — giu vong lap chay
        print(f"LOI doi chieu vi the ({symbol}): {exc} — bo qua symbol nay.")
        return {"symbol": symbol, "action": "ERROR", "status": "ERROR",
                "reason": f"doi chieu vi the loi: {exc}"}
    # (5) Loc xu huong khung cao (MTF v1 — muc 64): xu huong H1 dat
    # huong cho phep, M15 cho diem vao. htf_bars truyen vao thi dung
    # truc tiep; khong thi lay tu feed khi trend_enabled bat. Feed
    # khong ho tro lay nen khung khac (mo phong / gia) thi loc tat
    # lang le (htf_trend None) — chay M15-only nhu cu. Lay duoc it
    # nen thi compute_htf_trend tra "unknown" — loc khong ap dung,
    # chi ghi chu trong reason (kem 1 dong canh bao o day).
    tf_cfg = resolve_timeframes(cfg)
    htf_trend = None
    if htf_bars is not None:
        htf_trend = compute_htf_trend(
            htf_bars, cfg, timeframe=tf_cfg["trend"], desk=desk,
            symbol=symbol)
    elif tf_cfg["trend_enabled"]:
        trend_bars = _fetch_trend_bars(
            feed, tf_cfg["trend"], tf_cfg["trend_bars"])
        if trend_bars is not None:
            htf_trend = compute_htf_trend(
                trend_bars, cfg, timeframe=tf_cfg["trend"], desk=desk,
                symbol=symbol)
    if htf_trend is not None and htf_trend["direction"] == "unknown":
        print(f"Canh bao MTF: thieu nen {tf_cfg['trend']} cho {symbol} "
              "— chay M15-only (khong ap dung loc HTF).")
    try:
        sig = generate_signals(desk, bars, symbol=symbol, cfg=cfg,
                               strategies=strategies,
                               htf_trend=htf_trend)
        entry = feed.latest_price(symbol)
    except Exception as exc:  # noqa: BLE001 — tin hieu/gia loi thi bo symbol
        print(f"LOI tinh tin hieu ({symbol}): {exc}")
        return {"symbol": symbol, "action": "ERROR", "status": "ERROR",
                "reason": f"khong tinh duoc tin hieu/gia: {exc}"}
    print(f"Gia moi nhat {symbol}: {entry}")
    print(f"Tin hieu: {sig}")
    # Ten tren broker (vd 'EURUSDm' tren server Trial): feed MT5Feed
    # giai quyet qua broker_symbol(); feed gia khong co ham do thi
    # dung ten chuan. Ten noi bo / log van giu ten chuan.
    broker_symbol = symbol
    _broker_fn = getattr(feed, "broker_symbol", None)
    if callable(_broker_fn):
        try:
            _resolved = _broker_fn(symbol)
        except Exception:  # noqa: BLE001 — roi xuong ten chuan
            _resolved = None
        if _resolved:
            broker_symbol = _resolved
    if sig.get("levels"):
        lv = sig["levels"]
        print(f"Levels: entry={lv['entry']:.4f} SL={lv['sl']:.4f} "
              f"TP={lv['tp']:.4f} ATR={lv['atr']:.4f}")
    # (2) Chan drawdown — quy truoc, desk sau.
    ok, reason = guard.can_open(desk)
    if not ok:
        action = reason.split(":", 1)[0]  # BLOCKED-DRAWDOWN-FUND/DESK
        log_decision(symbol, action, reason, desk=desk, manager=manager)
        print(f"CHAN: {reason} — khong mo lenh moi cho {symbol}.")
        return {"symbol": symbol, "action": action, "status": action,
                "reason": reason}
    # (2b) Kill switch (Phase F) — lop phong thu thu hai: vi the mo da
    # duoc doi chieu o buoc (1), nhung khong mo lenh moi nao nua.
    if is_engaged():
        reason = "Kill switch dang bat — khong mo lenh moi"
        log_decision(symbol, "BLOCKED-KILL-SWITCH", reason,
                     desk=desk, manager=manager)
        print(f"CHAN: {reason} ({symbol}).")
        return {"symbol": symbol, "action": "BLOCKED-KILL-SWITCH",
                "status": "BLOCKED-KILL-SWITCH", "reason": reason}
    # (2c) Gioi han quy (Phase F): lo trong ngay + so vi the mo.
    ok, reason = check_fund_limits(guard, positions, cfg,
                                   today_pnl_from_log(), desk=desk)
    if not ok:
        action = reason.split(":", 1)[0]  # BLOCKED-DAILY-LOSS-FUND /
        # BLOCKED-MAX-POSITIONS-FUND / BLOCKED-MAX-POSITIONS-DESK
        log_decision(symbol, action, reason, desk=desk, manager=manager)
        try:
            audit_mod.log_event(
                "FUND_LIMIT_BLOCKED",
                {"desk": desk, "symbol": symbol, "action": action,
                 "reason": reason})
        except OSError:  # noqa: BLE001 — audit loi khong crash chu ky
            pass
        print(f"CHAN: {reason} — khong mo lenh moi cho {symbol}.")
        return {"symbol": symbol, "action": action, "status": action,
                "reason": reason}
    # (3) Cua so cam giao dich (tin tuc/earnings).
    in_window, event_name = in_no_trade_window(
        now or datetime.now(), cfg.get("no_trade_events") or [], symbol)
    if in_window:
        reason = (f"Trong cua so cam giao dich: {event_name} — "
                  "khong mo lenh moi")
        log_decision(symbol, "BLOCKED-NO-TRADE-WINDOW", reason,
                     desk=desk, manager=manager)
        print(f"CHAN: trong cua so cam giao dich ({event_name}) — "
              "khong mo lenh moi.")
        return {"symbol": symbol, "action": "BLOCKED-NO-TRADE-WINDOW",
                "status": "BLOCKED-NO-TRADE-WINDOW", "reason": reason}
    # (4) Toi da 1 lenh moi / symbol / ngay (Q4).
    if count_trades_today(symbol) >= 1:
        reason = (f"Da dat 1 lenh moi cho {symbol} hom nay — "
                  "gioi han 1 lenh/symbol/ngay")
        log_decision(symbol, "BLOCKED-DAILY-LIMIT", reason,
                     desk=desk, manager=manager)
        print(f"CHAN: da dat lenh cho {symbol} hom nay "
              "(gioi han 1 lenh/ngay).")
        return {"symbol": symbol, "action": "BLOCKED-DAILY-LIMIT",
                "status": "BLOCKED-DAILY-LIMIT", "reason": reason}
    # (5) Tin hieu.
    if sig["action"] == "HOLD":
        print("Tin hieu HOLD — khong dat lenh.")
        return {"symbol": symbol, "action": "HOLD", "status": "HELD",
                "reason": sig["reason"]}
    # (6) SL/TP theo ATR, tinh lai tu gia vao live.
    if not sig.get("levels"):
        print("Khong co levels tu chien luoc — khong dat lenh.")
        return {"symbol": symbol, "action": sig["action"],
                "status": "BLOCKED-NO-LEVELS",
                "reason": "khong co levels tu chien luoc"}
    levels = strat.levels_for_entry(sig["action"], entry,
                                    sig["levels"]["atr"])
    if not levels:
        print("Khong tinh duoc SL/TP theo ATR — khong dat lenh.")
        return {"symbol": symbol, "action": sig["action"],
                "status": "BLOCKED-NO-LEVELS",
                "reason": "khong tinh duoc SL/TP theo ATR"}
    sl, tp = levels["sl"], levels["tp"]
    if per_symbol_cap is None:
        # Nguoi goi khong chia von: dung ca von desk (truong hop 1 symbol).
        per_symbol_cap = Portfolio.from_config(cfg).desks[desk].capital_usd
    contract = CONTRACT_SIZES.get(desk, 100000)
    risk_pct = risk_pct_for_symbol(cfg, symbol)
    vol = volume or position_size_lots(
        per_symbol_cap, risk_pct, entry, sl, contract_size=contract)
    # Soft rule scale: size_scale trong tin hieu (<= 1.0) chi GIAM
    # volume — lam tron XUONG buoc 0.01 lot nhu position_size_lots.
    # volume truyen tay (tham so volume) KHONG bi scale: no la ghi de
    # thu cong cua nguoi chay, khong phai size cung da tinh.
    size_scale = float((sig.get("levels") or {}).get("size_scale", 1.0)
                       or 1.0)
    if volume is None and size_scale < 1.0:
        vol = int(vol * size_scale * 100) / 100.0
    if vol <= 0:
        print("Volume tinh duoc = 0 — khong dat lenh "
              "(kiem tra risk/entry/SL).")
        return {"symbol": symbol, "action": sig["action"],
                "status": "BLOCKED-VOLUME-ZERO",
                "reason": "volume tinh duoc = 0 (kiem tra risk/entry/SL)",
                "price": entry, "sl": sl, "tp": tp}
    # (6b) Hop nhat PTCB (Yuling): nhan dinh co ban moi nhat cua desk.
    # Chan khi tong hop bao KHONG MUA (size 0); thieu/cu thi van chay
    # nhung ghi ro vao ket qua de log thay.
    synth, fa_note = _apply_fa_gate(cfg, desk, sig["action"],
                                    verdict_store=verdict_store)
    if synth.get("blocked"):
        reason = synth.get("rationale") or "PTCB mau thuan voi PTKT"
        log_decision(symbol, "BLOCKED-FA-CONFLICT", reason,
                     desk=desk, manager=manager)
        print(f"CHAN: {reason} ({symbol}).")
        return {"symbol": symbol, "action": "BLOCKED-FA-CONFLICT",
                "status": "BLOCKED-FA-CONFLICT", "reason": reason,
                "price": entry, "sl": sl, "tp": tp, "volume": vol,
                "fa_note": fa_note}
    # (7) Dat lenh DEMO: chan demo-only + margin check nam TRONG
    # place_demo_order (sau chan demo-only, truoc order_send).
    # Che do khuyen nghi: moi gate tren da vuot qua giong het duong dat
    # lenh, nhung KHONG goi place_demo_order — tao lenh cho xac nhan.
    risk_usd = round(per_symbol_cap * risk_pct / 100.0, 2)
    if size_scale < 1.0:
        risk_usd = round(risk_usd * size_scale, 2)
    when = now or datetime.now(timezone.utc)
    if _recommend_mode(cfg, recommend_only):
        # Gate ky quy (nam trong place_demo_order o duong dat lenh):
        # kiem tra o day de khuyen nghi khong dua ra lenh khong dat
        # duoc; thieu ky quy thi BLOCKED-MARGIN nhu duong dat lenh.
        margin_ok, margin_msg = check_margin(mt5, symbol, vol, entry,
                                             account,
                                             broker_symbol=broker_symbol)
        if not margin_ok:
            reason = (f"Khong du ky quy de dat lenh demo {symbol} "
                      f"{sig['action']} {vol} lot @ {entry}: {margin_msg}")
            log_decision(symbol, "BLOCKED-MARGIN", reason,
                         desk=desk, manager=manager)
            print(f"CHAN: {reason}")
            return {"symbol": symbol, "action": "BLOCKED-MARGIN",
                    "status": "BLOCKED-MARGIN", "reason": reason,
                    "price": entry, "sl": sl, "tp": tp, "volume": vol}
        store = _pending_store(pending_store)
        pending_id = store.create(
            {"desk": desk, "manager": manager, "symbol": symbol,
             "action": sig["action"], "entry": entry, "sl": sl, "tp": tp,
             "volume": vol, "risk_usd": risk_usd},
            ttl_min=_pending_ttl_min(cfg))
        log_decision(
            symbol, "RECOMMENDED",
            f"RECOMMENDED {sig['action']} {symbol} {vol} lot @ {entry} "
            f"(SL {sl}, TP {tp}) [cho xac nhan, pending {pending_id}]",
            desk=desk, manager=manager)
        print(f"KHUYEN NGHI: {sig['action']} {symbol} {vol} lot @ "
              f"{entry} (SL {sl}, TP {tp}) — cho xac nhan "
              f"(pending {pending_id}).")
        result = {"symbol": symbol, "action": sig["action"],
                  "status": "RECOMMENDED", "reason": sig["reason"],
                  "volume": vol, "price": entry, "sl": sl, "tp": tp,
                  "risk_usd": risk_usd, "manager": manager,
                  "time": when.isoformat(), "fa_note": fa_note,
                  "size_scale": size_scale,
                  "pending_id": pending_id}
        _log_outcome(result, sig, cfg, desk, symbol, outcome_store)
        return result
    try:
        result = place_demo_order(
            mt5, symbol=symbol, action=sig["action"], volume=vol,
            price=entry, sl=sl, tp=tp, desk=desk, manager=manager,
            cfg=cfg, account_info=account, server=server,
            broker_symbol=broker_symbol)
    except RuntimeError as exc:
        if "ky quy" in str(exc):
            log_decision(symbol, "BLOCKED-MARGIN", str(exc),
                         desk=desk, manager=manager)
            print(f"CHAN: {exc}")
            return {"symbol": symbol, "action": "BLOCKED-MARGIN",
                    "status": "BLOCKED-MARGIN", "reason": str(exc),
                    "price": entry, "sl": sl, "tp": tp, "volume": vol}
        print(f"LOI dat lenh ({symbol}): {exc}")
        return {"symbol": symbol, "action": "ERROR", "status": "ERROR",
                "reason": f"dat lenh that bai: {exc}",
                "price": entry, "sl": sl, "tp": tp, "volume": vol}
    # Ghi vi the moi mo vao state de lan chay sau doi chieu.
    positions.append(new_position(
        desk, symbol, sig["action"], entry, sl, tp, vol,
        contract, sig["levels"]["atr"]))
    print(f"OK: lenh DEMO da gui: {result}")
    outcome = {"symbol": symbol, "action": sig["action"], "status": "TRADED",
               "reason": sig["reason"], "volume": vol, "price": entry,
               "sl": sl, "tp": tp, "order": result.get("order"),
               "risk_usd": risk_usd, "manager": manager,
               "time": when.isoformat(), "fa_note": fa_note,
               "size_scale": size_scale}
    _log_outcome(outcome, sig, cfg, desk, symbol, outcome_store)
    return outcome


def _close_feed(feed):
    """Dong feed neu co close() (MT5Feed.shutdown); loi dong thi bo qua."""
    close = getattr(feed, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # noqa: BLE001 — dong feed khong duoc thi thoi
            pass


def _open_mt5_feed(cfg, desk, symbol, timeframe, mt5_module, feed_factory):
    """Mo feed MT5 cho 1 symbol, tra (feed, mt5, account, server).

    feed_factory: ham (symbol) -> feed (chi dung cho test — truyen feed
    gia); khong truyen thi dung MT5Feed that (provider ep thanh 'mt5',
    khung nen theo `timeframe`). Tren may khong co goi MetaTrader5 thi
    ImportError voi huong dan ro rang (khong traceback) — giong lenh
    mt5-symbols.
    """
    if feed_factory is not None:
        opened = feed_factory(symbol)
        if isinstance(opened, tuple):
            feed, mt5, account, server = opened
            return feed, mt5, account, server
        feed = opened
        mt5 = getattr(feed, "mt5", None) or mt5_module
        account = (feed.account_info()
                   if hasattr(feed, "account_info") else None)
        server = (cfg.get("mt5") or {}).get("server") or ""
        return feed, mt5, account, server
    from .data.mt5_feed import load_mt5

    mt5 = load_mt5(mt5_module)
    cfg_mt5 = dict(cfg or {})
    data_cfg = dict((cfg or {}).get("data") or {})
    data_cfg["provider"] = "mt5"  # vong live luon lay gia that tu MT5
    cfg_mt5["data"] = data_cfg
    mt5_cfg = dict((cfg or {}).get("mt5") or {})
    mt5_cfg["timeframe"] = timeframe
    cfg_mt5["mt5"] = mt5_cfg
    feed = build_feed(cfg_mt5, desk, symbol=symbol, mt5_module=mt5_module)
    account = feed.account_info()
    return feed, mt5, account, mt5_cfg.get("server") or ""


def _maybe_send_alert(cfg, desk, result, telegram):
    """Gui canh bao Telegram cho 1 ket qua (neu user bat telegram.enabled).

    - TRADED (tin hieu BUY/SELL + lenh da dat): format_signal_alert,
      thong bao thuong, KHONG kem ban phim.
    - RECOMMENDED (tin hieu BUY/SELL + lenh cho xac nhan): gui khuyen
      nghi KEM ban phim inline Dat lenh / Bo qua
      (format_signal_alert(..., recommended=True, pending_id=...),
      send_message(..., reply_markup=order_keyboard(...))).
    - BLOCKED-*: format_blocked_alert.
    - HELD / ERROR: khong gui (HOLD la binh thuong; loi da ghi vao
      errors[] cua chu ky).
    telegram: ham gui tuy chon (text) -> bool, chi dung cho test; o
    che do khuyen nghi no nhan them reply_markup (telegram(text,
    reply_markup=...)) — ham chi nhan 1 doi so thi goi lai dang cu.
    Khong truyen thi dung telegram.send_message(text, cfg=cfg). Loi gui
    khong bao gio raise (send_message da tu xu ly).
    """
    if not telegram_mod.telegram_enabled(cfg):
        return False
    from .i18n import get_language
    lang = get_language(cfg)
    status = result.get("status", "")
    manager = ((cfg or {}).get("fund") or {}).get("desks", {}).get(desk, {})
    manager = manager.get("manager") if isinstance(manager, dict) else None
    if status == "RECOMMENDED":
        pending_id = result.get("pending_id")
        text = telegram_mod.format_signal_alert(
            result, desk, manager=manager, recommended=True,
            pending_id=pending_id, lang=lang)
        keyboard = telegram_mod.order_keyboard(
            pending_id, result.get("action"), result.get("symbol"),
            result.get("volume"), lang=lang)
        if telegram is not None:
            try:
                return bool(telegram(text, reply_markup=keyboard))
            except TypeError:
                try:
                    return bool(telegram(text))
                except Exception as exc:  # noqa: BLE001
                    print(f"CANH BAO Telegram: khong gui duoc canh bao ({exc}).")
                    return False
        return telegram_mod.send_message(text, cfg=cfg,
                                         reply_markup=keyboard)
    if status == "TRADED":
        text = telegram_mod.format_signal_alert(result, desk,
                                                manager=manager, lang=lang)
    elif status.startswith("BLOCKED-"):
        text = telegram_mod.format_blocked_alert(result, desk,
                                                 manager=manager, lang=lang)
    else:
        return False
    if telegram is not None:
        try:
            return bool(telegram(text))
        except Exception as exc:  # noqa: BLE001 — Telegram loi khong crash chu ky
            print(f"CANH BAO Telegram: khong gui duoc canh bao ({exc}).")
            return False
    return telegram_mod.send_message(text, cfg=cfg)


def run_live_cycle(cfg, desk, *, symbols=None, timeframe="M15",
                   mt5_module=None, telegram=None, feed_factory=None,
                   volume=None, now=None, verdict_store=None,
                   recommend_only=False, pending_store=None):
    """Chay 1 chu ky live: moi symbol cua desk, 60 nen M15.

    Tra tong ket {desk, timeframe, started_at, results[], n_traded,
    n_recommended, n_blocked, errors[]}. Loi 1 symbol (mo feed, lay nen,
    dat lenh) chi ghi vao errors[] + in log, khong crash chu ky. Tren may
    khong co MT5, moi symbol deu loi ImportError va chu ky tra ve errors
    (nguoi goi in loi sach, khong traceback).
    recommend_only: True thi ep che do khuyen nghi cho ca chu ky (co
    `live --recommend-only`); pending_store: PendingOrderStore truyen
    vao (de test).
    """
    timeframe = timeframe or _live_cfg(cfg).get("timeframe", "M15")
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"Khung thoi gian khong ho tro: {timeframe!r} "
            f"(chon trong {sorted(SUPPORTED_TIMEFRAMES)})")
    symbols = _desk_symbols(cfg, desk) if symbols is None else list(symbols)
    if not symbols:
        raise ValueError(f"Chua cau hinh symbol cho desk {desk!r} trong config.yaml")
    started_at = datetime.now(timezone.utc).isoformat()
    guard, positions = load_guard_and_positions(cfg)
    desk_cap = Portfolio.from_config(cfg).desks[desk].capital_usd
    per_symbol_cap = split_desk_capital(desk_cap, len(symbols))
    strategies = build_strategies(cfg.get("strategy"))
    manager = cfg["fund"]["desks"][desk]["manager"]
    # Kill switch (Phase F): kiem tra DAU chu ky. Neu bat thi chu ky van
    # chay — moi symbol van duoc doi chieu vi the mo (process_symbol
    # buoc 1) — nhung khong mo lenh moi nao (gate 2b trong
    # process_symbol). Ghi log + audit de truy vet.
    ks_engaged = is_engaged()
    if ks_engaged:
        ks = kill_switch_status()
        print("CANH BAO: kill switch dang BAT "
              f"(ly do: {ks['reason'] or '(khong ghi ly do)'}, "
              f"boi {ks['by'] or '(khong ro)'}, luc {ks['engaged_at']}) — "
              "chu ky nay chi doi chieu vi the mo, KHONG mo lenh moi.")
        log_decision("LIVE", "KILL-SWITCH-ENGAGED",
                     f"Kill switch bat (ly do: {ks['reason'] or '?'}) — "
                     "chu ky chi doi chieu vi the mo, khong mo lenh moi",
                     desk=desk, manager=manager)
    try:
        audit_mod.log_event(
            "LIVE_CYCLE_STARTED",
            {"desk": desk, "timeframe": timeframe,
             "kill_switch_engaged": ks_engaged})
    except OSError:  # noqa: BLE001 — audit loi khong crash chu ky
        pass
    results, errors = [], []
    for symbol in symbols:
        print(f"--- {symbol} "
              f"(rui ro {risk_pct_for_symbol(cfg, symbol):g}%/lenh) ---")
        try:
            feed, mt5, account, server = _open_mt5_feed(
                cfg, desk, symbol, timeframe, mt5_module, feed_factory)
        except (ImportError, ConnectionError, ValueError) as exc:
            print(f"LOI ({symbol}): {exc}")
            errors.append({"symbol": symbol, "error": str(exc)})
            continue
        try:
            if account is not None and not account_is_demo(mt5, account, server):
                reason = ("TU CHOI: tai khoan MT5 dang dang nhap KHONG phai demo "
                          f"(server={server!r}). Chi chay demo.")
                print(f"LOI ({symbol}): {reason}")
                errors.append({"symbol": symbol, "error": reason})
                continue
            result = process_symbol(
                cfg, desk, symbol, feed=feed, mt5=mt5, account=account,
                server=server, manager=manager, guard=guard,
                positions=positions, volume=volume,
                per_symbol_cap=per_symbol_cap, strategies=strategies,
                now=now, verdict_store=verdict_store,
                recommend_only=recommend_only,
                pending_store=pending_store)
            results.append(result)
            try:
                save_guard_and_positions(guard, positions)
            except Exception as exc:  # noqa: BLE001 — khong crash chu ky vi ghi state
                print(f"CANH BAO: khong ghi duoc state sau {symbol}: {exc}")
            _maybe_send_alert(cfg, desk, result, telegram)
        except Exception as exc:  # noqa: BLE001 — 1 symbol loi khong crash chu ky
            print(f"LOI ({symbol}): {exc} — bo qua symbol nay.")
            errors.append({"symbol": symbol, "error": str(exc)})
        finally:
            _close_feed(feed)
    n_traded = sum(1 for r in results if r["status"] == "TRADED")
    n_recommended = sum(1 for r in results if r["status"] == "RECOMMENDED")
    n_blocked = sum(1 for r in results
                    if str(r["status"]).startswith("BLOCKED-"))
    # Audit ket thuc chu ky — chi ghi khi chu ky co giao dich, co khuyen
    # nghi cho xac nhan, co lenh bi chan, hoac kill switch dang bat
    # (tranh spam chu ky HOLD).
    if n_traded or n_recommended or n_blocked or ks_engaged:
        try:
            audit_mod.log_event(
                "LIVE_CYCLE_STOPPED",
                {"desk": desk, "timeframe": timeframe,
                 "n_traded": n_traded, "n_recommended": n_recommended,
                 "n_blocked": n_blocked,
                 "n_errors": len(errors),
                 "kill_switch_engaged": ks_engaged})
        except OSError:  # noqa: BLE001 — audit loi khong crash chu ky
            pass
    summary = {"desk": desk, "timeframe": timeframe,
               "started_at": started_at, "results": results,
               "n_traded": n_traded, "n_recommended": n_recommended,
               "n_blocked": n_blocked,
               "errors": errors, "kill_switch_engaged": ks_engaged}
    print(f"Chu ky {desk} {timeframe}: {n_traded} lenh DEMO, "
          f"{n_recommended} khuyen nghi cho xac nhan, "
          f"{n_blocked} bi chan, {len(errors)} loi.")
    return summary


def _seconds_until_next_boundary(interval_min, now=None):
    """So giay toi bien nen tiep theo (moc :00/:15/:30/:45 voi M15).

    Tinh theo dong ho: neu dang dung dung bien thi cho tron 1 khoang,
    tranh chay 2 chu ky lien nhau.
    """
    now = now or datetime.now()
    step = int(interval_min) * 60
    elapsed = now.timestamp() % step
    return step - elapsed if elapsed else step


def run_live_loop(cfg, desk, *, symbols=None, timeframe="M15",
                  interval_min=15, max_cycles=None, mt5_module=None,
                  telegram=None, feed_factory=None, volume=None,
                  sleep_fn=None, recommend_only=False, pending_store=None):
    """Lap chu ky live toi bien nen tiep theo, cho toi khi dung.

    interval_min: so phut giua 2 chu ky (mac dinh 15 — bien nen M15).
    max_cycles: so chu ky toi da (de test/dung; None = chay mai toi khi
    user Ctrl+C — KeyboardInterrupt lan ra ngoai cho lenh `live` bat).
    Loi lay feed o 1 chu ky thi bo chu ky do, khong crash vong lap.
    recommend_only / pending_store: chuyen thang xuong run_live_cycle
    (xem docstring o do).
    Tra list tong ket cac chu ky da chay.
    """
    if interval_min is None:
        interval_min = _live_cfg(cfg).get("interval_min", 15)
    interval_min = int(interval_min)
    if interval_min <= 0:
        raise ValueError(f"--interval-min phai > 0 (nhan {interval_min!r})")
    if max_cycles is not None and int(max_cycles) <= 0:
        raise ValueError(f"--max-cycles phai > 0 (nhan {max_cycles!r})")
    sleep = sleep_fn or time.sleep
    summaries = []
    cycle_no = 0
    while max_cycles is None or cycle_no < int(max_cycles):
        cycle_no += 1
        print(f"=== Chu ky live {cycle_no} — desk {desk} ===")
        try:
            summary = run_live_cycle(
                cfg, desk, symbols=symbols, timeframe=timeframe,
                mt5_module=mt5_module, telegram=telegram,
                feed_factory=feed_factory, volume=volume,
                recommend_only=recommend_only,
                pending_store=pending_store)
        except Exception as exc:  # noqa: BLE001 — chu ky loi thi bo, chay chu ky sau
            print(f"LOI chu ky {cycle_no} ({desk}): {exc} — bo qua chu ky nay.")
            summary = {"desk": desk, "timeframe": timeframe,
                       "started_at": datetime.now(timezone.utc).isoformat(),
                       "results": [], "n_traded": 0, "n_recommended": 0,
                       "n_blocked": 0,
                       "errors": [{"symbol": None, "error": str(exc)}]}
        summaries.append(summary)
        if max_cycles is not None and cycle_no >= int(max_cycles):
            break
        wait = _seconds_until_next_boundary(interval_min)
        print(f"Cho {wait:.0f}s toi bien nen {timeframe} tiep theo...")
        sleep(wait)
    return summaries
