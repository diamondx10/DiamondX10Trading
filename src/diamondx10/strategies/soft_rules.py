"""Quy tac cung (hard rules) + quy tac mem (soft rules) cho TA dx10.

QUY TAC CUNG — KHONG BAO GIO ghi de duoc tu muc `strategy:` trong YAML:
cac khoa trong HARD_RULE_KEYS (rui ro / von / drawdown / kill switch /
demo-only / gioi han lenh / no-trade window / PTCB / lenh cho Telegram)
song o ngoai muc strategy (risk:, synthesis:, telegram:, mt5:,
no_trade_events: ...) va chi doi duoc o do, co Phu duyet. Neu bat ky
khoa nao xuat hien o bat ky cho nao duoi `strategy:` thi
check_hard_rule_keys() raise ValueError neu ro khoa do — khong bao gio
lang le bo qua hay lang le ap dung.

QUY TAC MEM — danh sach `soft_rules:` duoi `strategy:` (xem
validate_soft_rules / resolve_soft_rules). Mot quy tac mem chi duoc:
  * block   — dieu kien dung thi BUY/SELL -> HOLD;
  * require — dieu kien SAI thi BUY/SELL -> HOLD;
  * scale   — dieu kien dung thi nhan size voi factor trong (0, 1]
              (CHI GIAM, khong bao gio tang size / risk).
Quy tac mem khong bao gio tang size vuot size cung da tinh, khong doi
risk %, khong bo qua bat ky gate cung nao. Quy tac bi go sai phai bao
loi LOUD o luc load config (ValueError), khong bao gio lang le khong
lam gi.

Dieu kien v1 (chi nhung thu tinh duoc tu chi bao trong duong signal):
  rsi_range  {low, high}        RSI(14) trong [low, high]
  sma_cross  {direction}        "bullish": SMAfast > SMA slow;
                                "bearish": SMAfast < SMA slow
  adx_min    {value}            ADX(14) >= value
  adx_max    {value}            ADX(14) <= value
  atr_pct_min {value}           ATR(14)/gia >= value
  atr_pct_max {value}           ATR(14)/gia <= value
  pattern    {name}             mau hinh `name` xuat hien trong bars
                                (xem diamondx10.patterns.detect_patterns)
KHONG co dieu kien cua so thoi gian / phien giao dich o v1: bar `time`
o du lieu mo phong chi la chi so 0..N (khong phai epoch), con o MT5 la
epoch UTC — khong co moc thoi gian dang tin cay chung de danh gia phien
London/New York trong duong signal. Phien / earnings blackout van dung
co che cung san co: no_trade_events (xem config.example.yaml).

Danh gia o 1 diem duy nhat: Strategy.signal() (strategies/base.py)
qua Strategy._apply_soft_rules(); DonchianBreakout.signal() dung
chung helper do. Moi duong (live, backtest, compare/sweep, signals)
deu di qua build_strategy/build_strategy_for_symbol nen deu thay
quy tac mem. Size sau scale duoc mang trong levels["size_scale"]
(1.0 = khong doi); live.py va backtest.py nhan size_scale do de
nhan volume/units (lam tron xuong buoc 0.01 lot o live).
"""
import copy

# --- Quy tac cung -------------------------------------------------------
# Ten khoa (o bat ky cap nao duoi strategy:) bi cam tuyet doi. Danh
# sach nay lay theo ten khoa THAT trong config.example.yaml / code:
#   risk.per_symbol_pct / max_risk_per_trade_pct / max_drawdown_pct /
#   desk_warning_pct / fund_daily_loss_pct / max_open_positions_* /
#   default_stop_loss_pct / default_take_profit_pct (risk:)
#   mt5.demo_only, kill switch (decisions/kill-switch.json, khong co
#   khoa config — cam ca ten goi), gioi han 1 lenh/symbol/ngay
#   (count_trades_today, cung trong code, khong co khoa config),
#   no_trade_events, synthesis.require_fa / verdict_max_age_hours /
#   fa_high_confidence, telegram.pending_order_ttl_min /
#   max_entry_deviation_pct, trading.require_confirmation.
# Them ten cac muc cap cao (risk/fund/live/mt5/synthesis/telegram/...)
# de 1 muc lac cho duoi strategy: cung bi chan voi thong bao quy tac
# cung thay vi bao "tham so khong biet".
HARD_RULE_KEYS = {
    # Rui ro / von / drawdown (risk:)
    "risk", "risk_per_symbol_pct", "per_symbol_pct",
    "max_risk_per_trade_pct", "max_drawdown_pct", "desk_warning_pct",
    "fund_daily_loss_pct", "max_open_positions_fund",
    "max_open_positions_desk", "default_stop_loss_pct",
    "default_take_profit_pct",
    # Kill switch / demo-only / gioi han lenh
    "kill_switch", "kill-switch", "demo_only", "demo-only",
    "max_daily_trades", "daily_trade_limit", "max_trades_per_day",
    "max_trades_per_symbol_per_day",
    # Cua so cam giao dich
    "no_trade_events",
    # PTCB / tong hop Yuling (synthesis:)
    "synthesis", "require_fa", "verdict_max_age_hours",
    "fa_high_confidence",
    # Lenh cho Telegram (telegram: / trading:)
    "telegram", "pending_order_ttl_min", "max_entry_deviation_pct",
    "require_confirmation", "chat_id", "bot_token_env",
    # Cac muc cap cao khac — khong bao gio la tham so strategy
    "fund", "live", "mt5", "news", "backtest", "history", "muse",
    "data",
}

_HARD_MSG = ("la quy tac cung (hard rule) — khong the ghi de tu YAML "
             "(muc strategy:); doi o muc goc cua no (risk:/synthesis:/"
             "telegram:/mt5:/no_trade_events:...) va chi khi Phu duyet")


def check_hard_rule_keys(obj, _path="strategy"):
    """Quet de quy 1 muc strategy: (dict/list) — gap bat ky khoa nao
    trong HARD_RULE_KEYS thi raise ValueError neu ro khoa do.

    Goi o dau resolve (resolve_strategy_params / resolve_soft_rules),
    build_strategies, get_strategy va load_config — moi duong nap
    config deu bi chan, khong co duong vong.
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in HARD_RULE_KEYS:
                raise ValueError(
                    f"Khoa {key!r} trong {_path} {_HARD_MSG}")
            check_hard_rule_keys(value, f"{_path}.{key}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            check_hard_rule_keys(item, f"{_path}[{i}]")


# --- Quy tac mem --------------------------------------------------------
KNOWN_DESKS = ("forex", "xauusd", "crypto", "us_securities")
KNOWN_SYMBOLS = ("EURUSD", "XAUUSD", "BTCUSD", "ETHUSD", "BNBUSD",
                 "AMD", "CDNS", "SNPS", "INTC", "NVDA")

CONDITION_TYPES = ("rsi_range", "sma_cross", "adx_min", "adx_max",
                   "atr_pct_min", "atr_pct_max", "pattern")

# Ten mau hinh detect_patterns() co the tra (diamondx10.patterns).
KNOWN_PATTERN_NAMES = ("doji", "bullish_engulfing", "bearish_engulfing",
                       "hammer", "shooting_star", "morning_star",
                       "evening_star", "resistance", "support",
                       "double_top", "double_bottom", "breakout_up",
                       "breakout_down")

_RULE_KEYS = {"name", "scope", "condition", "effect"}
_SCOPE_KEYS = {"desk", "symbol"}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_range(value, lo, hi, what):
    if not _is_number(value):
        raise ValueError(f"{what} phai la so, nhan {value!r}")
    if not lo <= value <= hi:
        raise ValueError(f"{what} = {value} vuot khoang hop ly [{lo}, {hi}]")


def validate_condition(condition, rule_name):
    """Kiem tra 1 dict condition: type biet, dung khoa, gia tri trong
    khoang. Raise ValueError neu ro ten rule + khoa loi."""
    if not isinstance(condition, dict):
        raise ValueError(
            f"Soft rule {rule_name!r}: condition phai la dict, "
            f"nhan {type(condition).__name__}")
    ctype = condition.get("type")
    if ctype not in CONDITION_TYPES:
        raise ValueError(
            f"Soft rule {rule_name!r}: loai condition khong biet: "
            f"{ctype!r} (co: {', '.join(CONDITION_TYPES)})")
    allowed = {"type"}
    if ctype == "rsi_range":
        allowed |= {"low", "high"}
        for k in ("low", "high"):
            if k not in condition:
                raise ValueError(
                    f"Soft rule {rule_name!r}: condition rsi_range "
                    f"thieu {k!r}")
            _check_range(condition[k], 0, 100,
                         f"Soft rule {rule_name!r}: rsi_range {k}")
        if condition["low"] >= condition["high"]:
            raise ValueError(
                f"Soft rule {rule_name!r}: rsi_range low "
                f"({condition['low']}) phai nho hon high "
                f"({condition['high']})")
    elif ctype == "sma_cross":
        allowed |= {"direction"}
        if condition.get("direction") not in ("bullish", "bearish"):
            raise ValueError(
                f"Soft rule {rule_name!r}: sma_cross direction phai la "
                f"'bullish' hoac 'bearish', nhan "
                f"{condition.get('direction')!r}")
    elif ctype in ("adx_min", "adx_max"):
        allowed |= {"value"}
        if "value" not in condition:
            raise ValueError(
                f"Soft rule {rule_name!r}: condition {ctype} thieu 'value'")
        _check_range(condition["value"], 0, 100,
                     f"Soft rule {rule_name!r}: {ctype} value")
    elif ctype in ("atr_pct_min", "atr_pct_max"):
        allowed |= {"value"}
        if "value" not in condition:
            raise ValueError(
                f"Soft rule {rule_name!r}: condition {ctype} thieu 'value'")
        _check_range(condition["value"], 0, 0.05,
                     f"Soft rule {rule_name!r}: {ctype} value")
        if condition["value"] <= 0:
            raise ValueError(
                f"Soft rule {rule_name!r}: {ctype} value phai > 0, "
                f"nhan {condition['value']!r}")
    elif ctype == "pattern":
        allowed |= {"name"}
        if condition.get("name") not in KNOWN_PATTERN_NAMES:
            raise ValueError(
                f"Soft rule {rule_name!r}: pattern khong biet: "
                f"{condition.get('name')!r} "
                f"(co: {', '.join(KNOWN_PATTERN_NAMES)})")
    extra = set(condition) - allowed
    if extra:
        raise ValueError(
            f"Soft rule {rule_name!r}: khoa khong biet trong condition "
            f"{ctype}: {', '.join(sorted(extra))}")


def _validate_effect(effect, rule_name):
    """Chuan hoa effect ve dang: 'block' | 'require' |
    {'type': 'scale', 'factor': float}. Raise ValueError neu sai."""
    if isinstance(effect, str):
        if effect in ("block", "require"):
            return effect
        raise ValueError(
            f"Soft rule {rule_name!r}: effect khong biet: {effect!r} "
            f"(co: 'block', 'require', {{'type': 'scale', 'factor': x}}); "
            f"'scale' can factor nen phai viet dang dict")
    if isinstance(effect, dict):
        if set(effect) - {"type", "factor"}:
            raise ValueError(
                f"Soft rule {rule_name!r}: khoa khong biet trong effect: "
                f"{', '.join(sorted(set(effect) - {'type', 'factor'}))}")
        if effect.get("type") != "scale":
            raise ValueError(
                f"Soft rule {rule_name!r}: effect dang dict chi ho tro "
                f"type 'scale', nhan {effect.get('type')!r}")
        factor = effect.get("factor")
        if not _is_number(factor) or not 0 < factor <= 1:
            raise ValueError(
                f"Soft rule {rule_name!r}: scale factor phai trong "
                f"(0, 1], nhan {factor!r} (scale chi duoc GIAM size, "
                f"khong bao gio tang)")
        return {"type": "scale", "factor": float(factor)}
    raise ValueError(
        f"Soft rule {rule_name!r}: effect phai la 'block' / 'require' / "
        f"{{'type': 'scale', 'factor': x}}, nhan {effect!r}")


def validate_soft_rules(rules, known_symbols=None):
    """Kiem tra + chuan hoa danh sach soft rule (fail LOUD).

    known_symbols: symbol hop le trong scope (lay tu config
    data.symbols neu co; mac dinh 10 symbol cua dx10). Tra ve ban
    sao da chuan hoa (effect scale ve dict, cac dict con duoc copy)
    — sua ket qua khong anh huong config goc.
    Raise ValueError neu: khong phai list, rule khong phai dict,
    khoa khong biet, thieu name/condition/effect, trung ten, scope
    sai (ca desk + symbol, desk/symbol khong biet), condition /
    effect sai (xem validate_condition / _validate_effect).
    """
    if rules is None:
        return []
    if not isinstance(rules, list):
        raise ValueError(
            f"Soft rules phai la list, nhan {type(rules).__name__}")
    symbols = set(known_symbols) if known_symbols else set(KNOWN_SYMBOLS)
    seen = set()
    out = []
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(
                f"Soft rule thu {i}: phai la dict, "
                f"nhan {type(rule).__name__}")
        extra = set(rule) - _RULE_KEYS
        if extra:
            raise ValueError(
                f"Soft rule thu {i}: khoa khong biet: "
                f"{', '.join(sorted(extra))} "
                f"(chi co: {', '.join(sorted(_RULE_KEYS))})")
        name = rule.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"Soft rule thu {i}: thieu 'name' (ten duy nhat, bat buoc)")
        if name in seen:
            raise ValueError(
                f"Soft rule trung ten: {name!r} (ten rule phai duy nhat)")
        seen.add(name)
        scope = rule.get("scope")
        norm_scope = None
        if scope is not None:
            if not isinstance(scope, dict):
                raise ValueError(
                    f"Soft rule {name!r}: scope phai la dict "
                    f"{{desk: ...}} hoac {{symbol: ...}}, "
                    f"nhan {type(scope).__name__}")
            if set(scope) - _SCOPE_KEYS:
                raise ValueError(
                    f"Soft rule {name!r}: scope chi co 'desk' hoac "
                    f"'symbol', nhan {', '.join(sorted(scope))}")
            if len(scope) != 1:
                raise ValueError(
                    f"Soft rule {name!r}: scope chi duoc 1 trong 2: "
                    f"desk hoac symbol, nhan {scope!r}")
            if "desk" in scope:
                if scope["desk"] not in KNOWN_DESKS:
                    raise ValueError(
                        f"Soft rule {name!r}: desk khong biet trong scope: "
                        f"{scope['desk']!r} "
                        f"(co: {', '.join(KNOWN_DESKS)})")
                norm_scope = {"desk": scope["desk"]}
            else:
                if scope["symbol"] not in symbols:
                    raise ValueError(
                        f"Soft rule {name!r}: symbol khong biet trong "
                        f"scope: {scope['symbol']!r} "
                        f"(co: {', '.join(sorted(symbols))})")
                norm_scope = {"symbol": scope["symbol"]}
        if "condition" not in rule:
            raise ValueError(f"Soft rule {name!r}: thieu 'condition'")
        validate_condition(rule["condition"], name)
        if "effect" not in rule:
            raise ValueError(f"Soft rule {name!r}: thieu 'effect'")
        effect = _validate_effect(rule["effect"], name)
        norm = {"name": name,
                "condition": copy.deepcopy(rule["condition"]),
                "effect": effect}
        if norm_scope is not None:
            norm["scope"] = norm_scope
        out.append(norm)
    return out


def resolve_soft_rules(cfg, desk, symbol=None):
    """Lay soft rule ap dung cho 1 (desk, symbol) tu config day du
    (hoac muc 'strategy' rieng). Tra ve list rule da validate +
    chuan hoa, da loc theo scope (khong scope = moi symbol; scope
    desk phai khop desk; scope symbol phai khop symbol — khong co
    symbol thi rule scope-symbol bi loai). Cung kiem tra quy tac cung
    trong muc strategy: truoc khi validate.
    """
    cfg = cfg or {}
    section = cfg.get("strategy")
    if not isinstance(section, dict):
        if any(k in ("soft_rules", "desks", "per_symbol") for k in cfg):
            section = cfg
        else:
            section = {}
    check_hard_rule_keys(section)
    raw = section.get("soft_rules") or []
    symbols_cfg = (cfg.get("data") or {}).get("symbols") or {}
    known = []
    if isinstance(symbols_cfg, dict):
        for desk_symbols in symbols_cfg.values():
            known.extend(desk_symbols or [])
    validated = validate_soft_rules(raw, known_symbols=known or None)
    out = []
    for rule in validated:
        scope = rule.get("scope")
        if scope is None:
            out.append(rule)
        elif "desk" in scope:
            if scope["desk"] == desk:
                out.append(rule)
        elif "symbol" in scope:
            if symbol is not None and scope["symbol"] == symbol:
                out.append(rule)
    return out


def evaluate_condition(condition, ctx):
    """Danh gia 1 condition tren context chi bao (ctx). Tra True/False.

    ctx: dict {rsi, sma_fast, sma_slow, adx, atr_pct, patterns}
    (gia tri None = khong tinh duoc -> condition ve chi bao do = False,
    khong bao gio doan mo). patterns: list dict tu detect_patterns()
    (hoac None — chi tinh khi condition pattern can, keo lazy o
    Strategy._soft_context).
    """
    ctype = condition["type"]
    if ctype == "rsi_range":
        v = ctx.get("rsi")
        return v is not None and condition["low"] <= v <= condition["high"]
    if ctype == "sma_cross":
        fast, slow = ctx.get("sma_fast"), ctx.get("sma_slow")
        if fast is None or slow is None:
            return False
        if condition["direction"] == "bullish":
            return fast > slow
        return fast < slow
    if ctype == "adx_min":
        v = ctx.get("adx")
        return v is not None and v >= condition["value"]
    if ctype == "adx_max":
        v = ctx.get("adx")
        return v is not None and v <= condition["value"]
    if ctype == "atr_pct_min":
        v = ctx.get("atr_pct")
        return v is not None and v >= condition["value"]
    if ctype == "atr_pct_max":
        v = ctx.get("atr_pct")
        return v is not None and v <= condition["value"]
    if ctype == "pattern":
        patterns = ctx.get("patterns") or []
        return any(p.get("name") == condition["name"] for p in patterns)
    raise ValueError(f"Loai condition khong biet: {ctype!r}")


def apply_soft_rules(rules, action, ctx):
    """Ap dung cac soft rule (da loc scope) len 1 tin hieu BUY/SELL.

    Tra (action, size_scale, applied, block_reason):
      * block + condition dung, hoac require + condition sai
        -> (HOLD, 1.0, [ten rule], ly do) — rule DAU TIEN chan se
        thang, cac rule sau khong danh gia nua.
      * scale + condition dung -> size_scale nhan factor (tich luy
        nhieu rule scale, van <= 1.0), applied ghi ten rule.
      * khong rule nao tac dong -> (action, 1.0, [], None).
    HOLD truyen vao thi tra nguyen (soft rule chi anh huong lenh moi).
    """
    if action not in ("BUY", "SELL"):
        return action, 1.0, [], None
    size_scale = 1.0
    applied = []
    for rule in rules or []:
        name = rule["name"]
        cond = evaluate_condition(rule["condition"], ctx)
        effect = rule["effect"]
        if effect == "block":
            if cond:
                return ("HOLD", 1.0, [name],
                        f"soft rule '{name}': block — dieu kien "
                        f"{rule['condition']['type']} thoa, khong mo lenh "
                        f"{action}")
        elif effect == "require":
            if not cond:
                return ("HOLD", 1.0, [name],
                        f"soft rule '{name}': require — dieu kien "
                        f"{rule['condition']['type']} khong thoa, khong mo "
                        f"lenh {action}")
        else:  # scale
            if cond:
                size_scale *= effect["factor"]
                applied.append(name)
    return action, size_scale, applied, None


__all__ = [
    "HARD_RULE_KEYS",
    "KNOWN_DESKS",
    "KNOWN_SYMBOLS",
    "CONDITION_TYPES",
    "KNOWN_PATTERN_NAMES",
    "check_hard_rule_keys",
    "validate_condition",
    "validate_soft_rules",
    "resolve_soft_rules",
    "evaluate_condition",
    "apply_soft_rules",
]
