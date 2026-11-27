"""Dataset giam sat cho mo hinh TA offline cua dx10 (MODEL-AGNOSTIC).

Dau ra chi la list thuan (stdlib, KHONG phu thuoc torch / numpy /
pandas): X = list[list[float]] (moi hang dai len(FEATURE_NAMES)),
y = list[int] (ma lop), meta = list[dict] (1 dict / mau). Agent train
mo hinh nao cung an duoc X/y truc tiep.

NHAN (label) — 2 che do, mac dinh TP/SL-first:
  * "tp_sl" (mac dinh, khop cach evaluator.py cham diem): tai moi bar
    t, gia vao = close[t], SL/TP theo ATR cua symbol (atr_sl_mult va
    tp_mult tu tham so da resolve — xem strategies/registry.py).
    Quet cac bar SAU t, toi da outcome_window_bars bar (mac dinh lay
    tu config learning.outcome_window_bars, fallback 20 — giong
    evaluator.DEFAULT_WINDOW_BARS):
      - TP cham truoc  -> lop 2 "tp_first"   (thang)
      - SL cham truoc  -> lop 0 "sl_first"   (thua)
      - khong cham cai nao trong cua so -> lop 1 "timeout"
    Ca TP va SL cham trong CUNG 1 bar (khong biet thu tu trong bar)
    thi tinh la thua — cach tinh bao thu, giong het evaluator.
    BUY: TP khi high >= tp, SL khi low <= sl. SELL: nguoc lai.
  * "direction" (tuy chon): so sanh close sau `horizon` bar (mac dinh
    = outcome_window_bars) voi close[t]: ret > threshold -> lop 2
    "up", ret < -threshold -> lop 0 "down", con lai lop 1 "flat".
    threshold mac dinh 0.002 (0.2%).

  KHAC BIET 1 BAR SO VOI evaluator.score_signal — CO CHU Y: evaluator
  cham tin hieu tu bar tin hieu tro di (bar do co high/low bao ca
  khoang truoc luc phat tin hieu). O day bar t NAM TRONG cua so
  feature (high/low cua no da la feature) nen nhan CHI quet cac bar
  > t: neu quet ca bar t thi nhan se dung lai thong tin da co trong
  feature — vi pham no-lookahead. Dinh nghia thang/thua/timeout va
  cach xu "ca 2 cham cung bar -> thua" thi giong het evaluator.

KHONG LOOKAHEAD (bao dam): feature cua mau t chi dung bar <= t
(features.build_features); nhan chi dung bar > t. Mau t cuoi cung
duoc xay la t = n - outcome_window - 1 (con du bar tuong lai de
cham diem). Test test_no_lookahead_* chung minh: chen 1 spike vao
tuong lai sau t thi doi nhan nhung khong doi feature.

DATASET THEO SYMBOL (khong tron symbol): build_dataset(cfg, symbol)
chi dung bar cua 1 symbol — model vang khong phai model forex.
Tham so TA (SMA/RSI/ATR, atr_sl_mult, tp_mult) lay theo symbol do
qua resolve_strategy_params; desk suy tu config data.symbols, fallback
bang KNOWN_DESKS cho 10 symbol dx10.

DATASET THEO TIMEFRAME (M15 o v1, san sang cho multi-timeframe sau
nay): moi dataset dict deu co khoa "timeframe" (vd "M15") va moi
cot feature deu la feature CUA TIMEFRAME DO — khi multi-timeframe
duoc build (build rieng, chua co o v1), cot khung cao hon se duoc
namespaced theo timeframe (vd "h1_log_ret_1", "h1_adx_scaled")
va FEATURE_VERSION tang, thay vi tron lan voi cot M15. Vong live
hien tai chi dung M15; khong co code nao o day doc 2 timeframe
cung luc.

SO BAR CAN: can it nhat FEATURE_WINDOW + outcome_window
+ min_samples - 1 bar (mac dinh min_samples = 10, tuc 50 + 20 + 9
= 79 bar M15 cho 10 mau). Thieu hon thi raise InsufficientHistoryError
ghi ro can bao nhieu / co bao nhieu — khong bao gio tra dataset rac
lang le. Lich su trong thi bao "chay backfill truoc".

NGUON NHAN THU 2 (tuy chon, mac dinh TAT): log outcome
(decisions/signal-outcomes.jsonl, xem outcomes.py) qua
samples_from_outcomes() / build_dataset(..., include_outcomes=True).
Mapping, 1 ban ghi da danh gia -> 1 mau:
  - ban ghi chua co truong `outcome` (chua duoc evaluate-signals
    cham) -> bo qua, dem vao skipped_unevaluated;
  - outcome "win" -> tp_first (2), "loss" -> sl_first (0),
    "timeout" -> timeout (1); KHONG cham lai — tin ket qua cua
    evaluator.py;
  - huong = record["action"], entry/sl/tp lay tu ban ghi;
  - feature xay tu FEATURE_WINDOW bar ket thuc o thoi diem tin hieu
    (lay tu HistoryStore hoac bars_by_symbol); thieu bar -> bo qua,
    dem vao skipped_no_bars;
  - meta them source="outcomes-log", outcome_id, rule_status.
  Mau tu log trung (symbol, time, direction) voi mau tu bar thi bi
  bo qua (dedupe) — tranh nhan doi cung 1 tin hieu.
  Day la mau "tin hieu rule-based thang/thua that", khac mau tu bar
  (moi bar t deu sinh mau, 2 huong). Hai nguon co the dung chung
  trong 1 dataset nho meta["source"].
"""
from pathlib import Path

from .features import (FEATURE_NAMES, FEATURE_VERSION, FEATURE_WINDOW,
                       build_features)
from ..data.history import HistoryStore
from ..evaluator import _parse_time, _signal_time
from ..outcomes import DEFAULT_STORE as DEFAULT_OUTCOMES_PATH
from ..outcomes import load as load_outcomes
from ..strategies.registry import resolve_strategy_params

TIMEFRAME = "M15"
DEFAULT_OUTCOME_WINDOW_BARS = 20
DEFAULT_MIN_SAMPLES = 10
DEFAULT_DIRECTION_THRESHOLD = 0.002

LABEL_NAMES_TP_SL = ("sl_first", "timeout", "tp_first")
LABEL_NAMES_DIRECTION = ("down", "flat", "up")
# Ma lop: 0 = bat loi / giam, 1 = trung lap / timeout, 2 = co loi / tang.
LABEL_TP_SL = {"sl_first": 0, "timeout": 1, "tp_first": 2}
LABEL_DIRECTION = {"down": 0, "flat": 1, "up": 2}
_OUTCOME_TO_TP_SL = {"win": LABEL_TP_SL["tp_first"],
                     "loss": LABEL_TP_SL["sl_first"],
                     "timeout": LABEL_TP_SL["timeout"]}

# Desk mac dinh cho 10 symbol dx10 (fallback khi config khong khai
# bao data.symbols; config van la nguon chinh).
KNOWN_DESKS = {"EURUSD": "forex", "XAUUSD": "xauusd",
               "BTCUSD": "crypto", "ETHUSD": "crypto",
               "BNBUSD": "crypto", "AMD": "us_securities",
               "CDNS": "us_securities", "SNPS": "us_securities",
               "INTC": "us_securities", "NVDA": "us_securities"}


class InsufficientHistoryError(ValueError):
    """Lich su thieu / qua ngan de xay dataset — thong bao ghi ro
    can bao nhieu bar, co bao nhieu bar, va phai lam gi (backfill)."""


def _positive_number(value):
    """So thuc > 0, hoac None (bool / chuoi / None deu khong hop le)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _learning_window(cfg, outcome_window):
    """Cua so cham diem: --window > config learning.outcome_window_bars
    > 20 (giong evaluator._learning_window)."""
    if outcome_window is not None:
        try:
            return max(1, int(outcome_window))
        except (TypeError, ValueError):
            pass
    learning = (cfg or {}).get("learning") or {}
    try:
        return max(1, int(learning.get("outcome_window_bars")
                           or DEFAULT_OUTCOME_WINDOW_BARS))
    except (TypeError, ValueError):
        return DEFAULT_OUTCOME_WINDOW_BARS


def _desk_for_symbol(cfg, symbol):
    """Desk chua symbol: config data.symbols truoc, KNOWN_DESKS sau.
    Raise ValueError neu khong biet symbol."""
    for desk, syms in ((cfg or {}).get("data", {}).get("symbols", {})
                       or {}).items():
        if symbol in (syms or []):
            return desk
    if symbol in KNOWN_DESKS:
        return KNOWN_DESKS[symbol]
    raise ValueError(
        "Khong biet desk cua symbol %r (config data.symbols khong co, "
        "khong nam trong 10 symbol dx10: %s)"
        % (symbol, ", ".join(sorted(KNOWN_DESKS))))


def levels_for(direction, entry, atr_value, atr_sl_mult, tp_mult):
    """SL/TP theo ATR — giong Strategy.levels_for_entry (BUY: SL duoi
    gia, TP tren gia; SELL: nguoc lai). Tra (sl, tp). Raise
    ValueError neu ATR khong tinh duoc (<= 0 / None)."""
    if direction not in ("BUY", "SELL"):
        raise ValueError("levels_for: direction phai la 'BUY'/'SELL', "
                         "nhan %r" % (direction,))
    if atr_value is None or atr_value <= 0:
        raise ValueError("levels_for: khong tinh duoc ATR (> 0) tai "
                         "bar vao lenh — khong the dat SL/TP")
    sl_dist = float(atr_sl_mult) * float(atr_value)
    if direction == "BUY":
        return entry - sl_dist, entry + float(tp_mult) * sl_dist
    return entry + sl_dist, entry - float(tp_mult) * sl_dist


def label_tp_sl(direction, entry, sl, tp, future_bars):
    """Nhan TP/SL-first cho 1 lenh gia dinh.

    future_bars: cac bar SAU bar vao lenh (khong bao gom bar vao —
    xem khac biet 1 bar voi evaluator o docstring module). Quet
    theo thu tu thoi gian; bar nao cham TP truoc thi thang, cham
    SL truoc thi thua; ca 2 cung bar -> thua; het list ma chua
    cham -> timeout. Tra (ma_lop, bars_held). Raise ValueError
    neu khong co bar tuong lai nao.
    """
    if direction not in ("BUY", "SELL"):
        raise ValueError("label_tp_sl: direction phai la 'BUY'/'SELL', "
                         "nhan %r" % (direction,))
    if not future_bars:
        raise ValueError("label_tp_sl: khong co bar tuong lai de "
                         "cham diem (can it nhat 1 bar sau bar vao)")
    is_buy = direction == "BUY"
    for idx, bar in enumerate(future_bars):
        high, low = float(bar["high"]), float(bar["low"])
        if is_buy:
            hit_tp, hit_sl = high >= tp, low <= sl
        else:
            hit_tp, hit_sl = low <= tp, high >= sl
        if hit_tp or hit_sl:
            # Ca 2 cham cung bar -> thua (bao thu, giong evaluator).
            won = hit_tp and not hit_sl
            code = (LABEL_TP_SL["tp_first"] if won
                    else LABEL_TP_SL["sl_first"])
            return code, idx + 1
    return LABEL_TP_SL["timeout"], len(future_bars)


def label_direction(entry_close, future_bars, horizon, threshold):
    """Nhan huong gia: close cua bar tuong lai thu `horizon` so voi
    close vao lenh. ret > threshold -> "up" (2), ret < -threshold ->
    "down" (0), con lai "flat" (1). Neu khong du `horizon` bar thi
    dung bar cuoi co san (giong tinh than timeout cua evaluator).
    Tra (ma_lop, bars_held). Raise ValueError neu khong co bar nao.
    """
    if not future_bars:
        raise ValueError("label_direction: khong co bar tuong lai de "
                         "cham diem")
    horizon = max(1, int(horizon))
    if threshold is None or float(threshold) < 0:
        raise ValueError("label_direction: threshold phai >= 0, nhan %r"
                         % (threshold,))
    use = future_bars[:horizon]
    last_close = float(use[-1]["close"])
    ret = (last_close - float(entry_close)) / float(entry_close)
    if ret > float(threshold):
        return LABEL_DIRECTION["up"], len(use)
    if ret < -float(threshold):
        return LABEL_DIRECTION["down"], len(use)
    return LABEL_DIRECTION["flat"], len(use)


def class_counts(y, label_names):
    """Dem mau theo lop: {ten_lop: so_mau} (gom ca lop 0 mau)."""
    counts = {name: 0 for name in label_names}
    for code in y or []:
        counts[label_names[int(code)]] += 1
    return counts


def build_samples(bars, *, symbol, params, outcome_window=20,
                  label_mode="tp_sl", directions=("BUY", "SELL"),
                  direction_threshold=DEFAULT_DIRECTION_THRESHOLD,
                  horizon=None):
    """Xay mau giam sat tu list bar cua 1 symbol (pure function).

    bars: list dict {time, open, high, low, close, volume?} theo
        thu tu thoi gian (se sap xep theo time neu chua sap).
    symbol: ten symbol (ghi vao meta). params: tham so TA da resolve
        (sma_fast/slow, rsi/atr period, atr_sl_mult, tp_mult).
    outcome_window: so bar tuong lai toi da quet nhan TP/SL.
    label_mode: "tp_sl" (mac dinh) hoac "direction".
    directions: tuple cac huong sinh mau moi bar t — mac dinh ca
        BUY va SELL (2 mau / bar t; cot direction_long phan biet).
        Truyen ("BUY",) hoac ("SELL",) de chi lay 1 huong.
    horizon: so bar cho nhan direction (mac dinh = outcome_window).

    Tra (X, y, meta): X list[list[float]] (moi hang dai
    len(FEATURE_NAMES)), y list[int], meta list[dict] {symbol, time,
    direction, entry, sl, tp, atr, bars_held, label_name, source,
    feature_version}. Mau t chay tu FEATURE_WINDOW - 1 den
    n - forward_window - 1 (du bar truoc de tinh feature, du bar
    sau de cham nhan). Raise ValueError neu tham so sai / ATR
    khong tinh duoc; KHONG raise vi thieu bar — truong hop do la
    viec cua build_dataset (InsufficientHistoryError).
    """
    if label_mode not in ("tp_sl", "direction"):
        raise ValueError("label_mode phai la 'tp_sl' hoac 'direction', "
                         "nhan %r" % (label_mode,))
    dirs = tuple(directions or ())
    if not dirs or any(d not in ("BUY", "SELL") for d in dirs):
        raise ValueError("directions phai la tuple con cua "
                         "('BUY', 'SELL'), nhan %r" % (directions,))
    window_bars = max(1, int(outcome_window))
    forward = window_bars if label_mode == "tp_sl" else max(
        1, int(horizon if horizon is not None else outcome_window))
    label_names = (LABEL_NAMES_TP_SL if label_mode == "tp_sl"
                   else LABEL_NAMES_DIRECTION)
    ordered = sorted(bars or [], key=lambda b: b.get("time", 0))
    atr_p = int((params or {}).get("atr_period", 14))
    atr_sl_mult = float((params or {}).get("atr_sl_mult", 1.5))
    tp_mult = float((params or {}).get("tp_mult", 2.0))

    from ..models.quant import atr as _atr
    X, y, meta = [], [], []
    last_t = len(ordered) - forward - 1
    for t in range(FEATURE_WINDOW - 1, last_t + 1):
        window = ordered[t - FEATURE_WINDOW + 1:t + 1]
        closes = [float(b["close"]) for b in window]
        highs = [float(b["high"]) for b in window]
        lows = [float(b["low"]) for b in window]
        atr_val = _atr(highs, lows, closes, atr_p)
        if atr_val is None or atr_val <= 0:
            raise ValueError(
                "build_samples: khong tinh duoc ATR tai bar t=%s "
                "(symbol %s) — khong the dat SL/TP"
                % (window[-1].get("time"), symbol))
        entry = closes[-1]
        future = ordered[t + 1:t + 1 + forward]
        for direction in dirs:
            sl, tp = levels_for(direction, entry, atr_val,
                                atr_sl_mult, tp_mult)
            if label_mode == "tp_sl":
                code, held = label_tp_sl(direction, entry, sl, tp,
                                         future[:window_bars])
            else:
                code, held = label_direction(entry, future, forward,
                                             direction_threshold)
            X.append(build_features(window, params=params,
                                    direction=direction))
            y.append(code)
            meta.append({
                "symbol": symbol,
                "time": window[-1].get("time"),
                "direction": direction,
                "entry": float(entry),
                "sl": float(sl),
                "tp": float(tp),
                "atr": float(atr_val),
                "bars_held": int(held),
                "label_name": label_names[code],
                "source": "bars",
                "feature_version": FEATURE_VERSION,
            })
    return X, y, meta


def samples_from_outcomes(records=None, *, cfg=None, store=None,
                          bars_by_symbol=None, outcomes_path=None,
                          params_by_symbol=None, timeframe=TIMEFRAME):
    """Mau tu log outcome da danh gia (xem mapping o docstring module).

    records: list ban ghi (doc tu outcomes.load) hoac None (doc tu
        outcomes_path / mac dinh decisions/signal-outcomes.jsonl).
    store: HistoryStore de lay bar truoc thoi diem tin hieu; neu
        truyen bars_by_symbol {symbol: [bar, ...]} thi dung no thay
        store. params_by_symbol: {symbol: params da resolve}; neu
        thieu symbol va co cfg thi resolve tu cfg.
    Tra (X, y, meta, stats): stats {included, skipped_unevaluated,
        skipped_bad, skipped_no_bars, skipped_no_params}.
    Khong bao gio raise vi 1 ban ghi hong — dem vao stats va bo qua.
    """
    if records is None:
        records = load_outcomes(outcomes_path or DEFAULT_OUTCOMES_PATH)
    stats = {"included": 0, "skipped_unevaluated": 0, "skipped_bad": 0,
             "skipped_no_bars": 0, "skipped_no_params": 0}
    X, y, meta = [], [], []
    for record in records or []:
        if not isinstance(record, dict):
            stats["skipped_bad"] += 1
            continue
        outcome = record.get("outcome")
        if outcome not in _OUTCOME_TO_TP_SL:
            stats["skipped_unevaluated"] += 1
            continue
        action = (record.get("action") or "").strip().upper()
        entry = _positive_number(record.get("entry"))
        sl = _positive_number(record.get("sl"))
        tp = _positive_number(record.get("tp"))
        symbol = record.get("symbol")
        signal_epoch = _signal_time(record)
        if (action not in ("BUY", "SELL") or entry is None
                or sl is None or tp is None or not symbol
                or signal_epoch is None):
            stats["skipped_bad"] += 1
            continue
        if bars_by_symbol is not None:
            bars = [b for b in (bars_by_symbol.get(symbol) or [])
                    if _parse_time(b.get("time")) is not None
                    and _parse_time(b.get("time")) <= signal_epoch]
        elif store is not None:
            try:
                bars = store.get_bars(symbol, timeframe,
                                      end=signal_epoch)
            except Exception:  # noqa: BLE001 — kho loi thi dem thieu bar
                bars = []
        else:
            bars = []
        bars = sorted(bars, key=lambda b: b.get("time", 0))
        if len(bars) < FEATURE_WINDOW:
            stats["skipped_no_bars"] += 1
            continue
        params = (params_by_symbol or {}).get(symbol)
        if params is None and cfg is not None:
            try:
                desk = _desk_for_symbol(cfg, symbol)
                params = resolve_strategy_params(cfg, desk, symbol)
            except Exception:  # noqa: BLE001 — resolve loi thi dem
                params = None
        if params is None:
            stats["skipped_no_params"] += 1
            continue
        window = bars[-FEATURE_WINDOW:]
        try:
            row = build_features(window, params=params, direction=action)
        except ValueError:
            stats["skipped_bad"] += 1
            continue
        code = _OUTCOME_TO_TP_SL[outcome]
        X.append(row)
        y.append(code)
        meta.append({
            "symbol": symbol,
            "time": window[-1].get("time"),
            "direction": action,
            "entry": float(entry),
            "sl": float(sl),
            "tp": float(tp),
            "atr": None,
            "bars_held": None,
            "label_name": LABEL_NAMES_TP_SL[code],
            "source": "outcomes-log",
            "feature_version": FEATURE_VERSION,
            "outcome_id": record.get("id"),
            "rule_status": record.get("status"),
        })
        stats["included"] += 1
    return X, y, meta, stats


def build_dataset(cfg, symbol, bars=None, *, timeframe=TIMEFRAME,
                  outcome_window=None, label_mode="tp_sl",
                  directions=("BUY", "SELL"),
                  direction_threshold=DEFAULT_DIRECTION_THRESHOLD,
                  horizon=None, min_samples=DEFAULT_MIN_SAMPLES,
                  store=None, include_outcomes=False,
                  outcomes_path=None, outcomes_records=None):
    """Xay dataset giam sat cho 1 symbol.

    cfg: config day du (strategy + data.symbols + learning tuy chon).
    symbol: vd "EURUSD". bars: list bar neu co san; None thi doc tu
        HistoryStore theo config history.db_path (mac dinh
        data/history.db) — can chay `backfill` truoc.
    outcome_window / label_mode / directions / direction_threshold /
        horizon: nhu build_samples. min_samples: so mau toi thieu
        (mac dinh 10); can FEATURE_WINDOW + forward_window +
        min_samples - 1 bar.
    store: HistoryStore co san (test / caller da mo); None thi tu mo
        theo config (chi khi bars is None).
    include_outcomes: True thi them mau tu log outcome (xem
        samples_from_outcomes); outcomes_records truyen truc tiep
        list ban ghi de test hoac dung outcomes_path.

    Tra dict {symbol, desk, timeframe, feature_version,
    feature_names, label_mode, label_names, outcome_window_bars,
    min_samples, n_samples, class_counts, params, X, y, meta
    (+ outcomes_stats khi include_outcomes)}.
    Raise InsufficientHistoryError khi khong co / qua it lich su
    (ghi ro can / co bao nhieu bar); ValueError khi symbol / tham
    so sai (tu resolve_strategy_params).
    """
    if not symbol or not isinstance(symbol, str):
        raise ValueError("build_dataset can symbol, vd 'EURUSD'")
    desk = _desk_for_symbol(cfg, symbol)
    params = resolve_strategy_params(cfg, desk, symbol)
    window = _learning_window(cfg, outcome_window)
    forward = window if label_mode == "tp_sl" else max(
        1, int(horizon if horizon is not None else window))
    label_names = (LABEL_NAMES_TP_SL if label_mode == "tp_sl"
                   else LABEL_NAMES_DIRECTION)
    bars_from_store = False
    own_store = False
    if bars is None:
        bars_from_store = True
        history_cfg = (cfg or {}).get("history") or {}
        db_path = history_cfg.get("db_path") or "data/history.db"
        own_store = store is None
        store = store or HistoryStore(db_path)
        try:
            bars = store.get_bars(symbol, timeframe)
        finally:
            # Chi dong ngay neu khong can store nua (khong co
            # include_outcomes); con khong thi dong o cuoi ham.
            if own_store and not include_outcomes:
                store.close()
                own_store = False
    bars = sorted(bars or [], key=lambda b: b.get("time", 0))
    needed = FEATURE_WINDOW + forward + max(1, int(min_samples)) - 1
    if len(bars) < needed:
        if not bars:
            raise InsufficientHistoryError(
                "Khong co lich su M15 cho symbol %s (kho %s rong) — "
                "chay `backfill` truoc roi xay dataset lai. Can it "
                "nhat %d bar (cua so feature %d + cua so nhan %d + "
                "%d mau toi thieu - 1), hien co 0 bar."
                % (symbol, timeframe, needed, FEATURE_WINDOW, forward,
                   max(1, int(min_samples))))
        raise InsufficientHistoryError(
            "Lich su M15 cho symbol %s qua ngan: can it nhat %d bar "
            "(cua so feature %d + cua so nhan %d + %d mau toi thieu "
            "- 1), hien chi co %d bar — chay `backfill` them (can "
            "them %d bar) roi xay dataset lai."
            % (symbol, needed, FEATURE_WINDOW, forward,
               max(1, int(min_samples)), len(bars),
               needed - len(bars)))
    X, y, meta = build_samples(
        bars, symbol=symbol, params=params, outcome_window=window,
        label_mode=label_mode, directions=directions,
        direction_threshold=direction_threshold, horizon=horizon)
    dataset = {
        "symbol": symbol,
        "desk": desk,
        "timeframe": timeframe,
        "feature_version": FEATURE_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "label_mode": label_mode,
        "label_names": list(label_names),
        "outcome_window_bars": window,
        "min_samples": max(1, int(min_samples)),
        "n_samples": len(y),
        "class_counts": class_counts(y, label_names),
        "params": dict(params),
        "X": X,
        "y": y,
        "meta": meta,
    }
    if include_outcomes:
        if outcomes_records is not None:
            records = outcomes_records
        else:
            records = load_outcomes(
                outcomes_path or DEFAULT_OUTCOMES_PATH)
        seen = {(m["symbol"], m.get("time"), m["direction"])
                for m in meta}
        oX, oy, ometa, stats = samples_from_outcomes(
            records, cfg=cfg, store=store
            if bars_from_store else None,
            bars_by_symbol={symbol: bars}
            if not bars_from_store else None,
            params_by_symbol={symbol: params})
        # Dedupe: mau log trung (symbol, time, direction) voi mau bar
        # thi bo qua (da co trong dataset tu bar).
        kept = [(x, c, m) for x, c, m in zip(oX, oy, ometa)
                if (m["symbol"], m.get("time"), m["direction"])
                not in seen]
        stats["skipped_duplicate"] = len(oX) - len(kept)
        for x, c, m in kept:
            X.append(x)
            y.append(c)
            meta.append(m)
        dataset["n_samples"] = len(y)
        dataset["class_counts"] = class_counts(y, label_names)
        dataset["outcomes_stats"] = stats
    if own_store and store is not None:
        store.close()
    return dataset


__all__ = ["TIMEFRAME", "DEFAULT_OUTCOME_WINDOW_BARS",
           "DEFAULT_MIN_SAMPLES", "DEFAULT_DIRECTION_THRESHOLD",
           "LABEL_NAMES_TP_SL", "LABEL_NAMES_DIRECTION",
           "LABEL_TP_SL", "LABEL_DIRECTION", "KNOWN_DESKS",
           "InsufficientHistoryError", "levels_for", "label_tp_sl",
           "label_direction", "class_counts", "build_samples",
           "samples_from_outcomes", "build_dataset"]
