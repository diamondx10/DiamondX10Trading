"""Lay bar da khung thoi gian (multi-timeframe) — lop DATA.

Stack v1: trend H1 + entry M15. Timing M5 KHONG dung trong logic
tin hieu v1, nhung duong lay du lieu ho tro san (fetch theo cau hinh
chung, khong cung ma theo tung khung).

Thiet ke:
- Ham nay CHI biet lay bar qua 1 callable get_bars(timeframe, n) ma
  nguoi goi truyen vao; no KHONG import live.py hay MT5Feed. Coordinator
  se adapt MT5Feed/SimulatedFeed thanh callable do sau (vd voi MT5Feed:
  lambda tf, n: feed.bars_range(tf, start, end) hoac feed co timeframe
  doi duoc — tuy coordinator chon).
- Moi khung lay doc lap: 1 khung loi (callable raise) hoac thieu bar
  (tra ve < MIN_BARS bar) thi chi ghi vao "missing", khong raise,
  khong lam hong cac khung khac.
- Neu truyen store (HistoryStore) thi moi khung lay duoc se upsert vao
  kho; loi store khong bao gio raise.

Cau hinh (muc `timeframes:` trong config — do 1 worker khac them vao
config.example.yaml; o day CHI DOC, khong dinh nghia schema):
    timeframes:
      entry: M15
      trend: H1
      timing: M5
      trend_enabled: true
      timing_enabled: false
      htf_adx_min: 20
      trend_bars: 60
Thieu muc nay thi mac dinh M15-only, filter tat (xem DEFAULT_TIMEFRAMES).

Luu y: DEFAULT_TIMEFRAMES o day la BAN SAO nho cua mac dinh ma worker
config se dat trong config.example.yaml / resolver cua ho. Giu 2 cho
dong bo khi doi mac dinh (chi co 7 khoa, khong import resolver cua ho
vi luc viet module nay resolver do chua ton tai).
"""
# So bar toi thieu de 1 khung duoc coi la "lay duoc": it hon thi coi
# nhu thieu du lieu (vd MT5 moi mo, chua du lich su).
MIN_BARS = 10
# So bar mac dinh cho khung entry va khung timing.
ENTRY_BARS = 60
TIMING_BARS = 60

DEFAULT_TIMEFRAMES = {
    "entry": "M15",
    "trend": "H1",
    "timing": "M5",
    "trend_enabled": True,
    "timing_enabled": False,
    "htf_adx_min": 20,
    "trend_bars": 60,
}


def resolve_timeframes_config(cfg):
    """Muc `timeframes:` trong config (dict cfg) gop voi mac dinh.

    Thieu muc / thieu khoa thi lay mac dinh. Khong bao gio raise
    (cfg None hay muc timeframes khong phai dict thi dung mac dinh).
    """
    merged = dict(DEFAULT_TIMEFRAMES)
    tf_cfg = (cfg or {}).get("timeframes") or {}
    if isinstance(tf_cfg, dict):
        merged.update(tf_cfg)
    return merged


def planned_timeframes(cfg):
    """Ke hoach lay bar: list (timeframe, n) theo thu tu entry, trend,
    timing — chi gom khung duoc bat trong config.

    - entry: luon lay, n = ENTRY_BARS (60).
    - trend: chi khi trend_enabled, n = trend_bars (mac dinh 60).
    - timing: chi khi timing_enabled, n = TIMING_BARS (60).
    Khung trung nhau (vd trend == entry) thi chi lay 1 lan, lay n lon
    nhat trong cac vai tro do.
    """
    tf_cfg = resolve_timeframes_config(cfg)
    plan = {}

    def _add(name, n):
        if not name:
            return
        name = str(name).strip().upper()
        if not name:
            return
        plan[name] = max(int(n), plan.get(name, 0))

    _add(tf_cfg.get("entry"), ENTRY_BARS)
    if tf_cfg.get("trend_enabled"):
        _add(tf_cfg.get("trend"), tf_cfg.get("trend_bars") or ENTRY_BARS)
    if tf_cfg.get("timing_enabled"):
        _add(tf_cfg.get("timing"), TIMING_BARS)
    # Giu thu tu entry -> trend -> timing (dict giu thu tu chen).
    return [(tf, n) for tf, n in plan.items()]


def configured_stack(cfg):
    """Ten cac khung trong stack da cau hinh, theo thu tu
    entry -> trend (neu bat) -> timing (neu bat).

    Dung cho CLI `backfill --all-timeframes`. Khong co muc timeframes
    trong config thi tra ["M15", "H1"] (entry + trend mac dinh).
    """
    return [tf for tf, _n in planned_timeframes(cfg)]


def parse_timeframes(value):
    """Parse chuoi CLI --timeframes, vd "M15,H1" -> ["M15", "H1"].

    Chu hoa, cat khoang trang, loai trung (giu thu tu xuat hien dau).
    Gia tri khong nam trong SUPPORTED_TIMEFRAMES thi raise ValueError
    NEU TEN gia tri xau do (de CLI bao loi sach). Chuoi rong thi raise
    ValueError. Ham nay KHONG import __main__ (tranh vong tron):
    tap hop khung ho tro duoc sao chep tu SUPPORTED_TIMEFRAMES trong
    __main__.py — giu dong bo khi them khung moi (H4 hien CHUA ho tro).
    """
    supported = {"M1", "M5", "M15", "H1", "D1"}
    if value is None or not str(value).strip():
        raise ValueError("--timeframes can it nhat 1 khung nen, vd M15,H1")
    out = []
    for raw in str(value).split(","):
        name = raw.strip().upper()
        if not name:
            continue
        if name not in supported:
            raise ValueError(
                f"Khung thoi gian khong ho tro: {name!r} "
                f"(chon trong {sorted(supported)})")
        if name not in out:
            out.append(name)
    if not out:
        raise ValueError("--timeframes can it nhat 1 khung nen, vd M15,H1")
    return out


def fetch_bars_for_timeframes(get_bars, symbol, cfg, *, store=None):
    """Lay bar cho ca stack khung thoi gian cua 1 symbol.

    get_bars(timeframe, n) -> list bar OHLC (dict {time, open, high,
    low, close, volume?}); do nguoi goi adapt tu MT5Feed /
    SimulatedFeed. symbol: ten chuan, vd 'EURUSD'. cfg: dict config
    (doc muc `timeframes:`, thieu thi M15-only). store: HistoryStore
    (tuy chon) — moi khung lay duoc se upsert vao kho.

    Tra {"bars": {tf: [bar, ...]}, "missing": [tf, ...]}:
    - "bars" chi chua khung lay duoc (>= MIN_BARS bar).
    - "missing" gom khung ma get_bars raise hoac tra ve qua it bar.
    - Khong bao gio raise: loi 1 khung khong anh huong khung khac;
      loi store.upsert_bars cung khong raise.
    """
    plan = planned_timeframes(cfg)
    bars_out, missing = {}, []
    for timeframe, n in plan:
        try:
            bars = get_bars(timeframe, n)
        except Exception:  # noqa: BLE001 — khung loi thi ghi missing
            missing.append(timeframe)
            continue
        if bars is None:
            missing.append(timeframe)
            continue
        try:
            bars = list(bars)
        except TypeError:
            missing.append(timeframe)
            continue
        if len(bars) < MIN_BARS:
            missing.append(timeframe)
            continue
        bars_out[timeframe] = bars
        if store is not None:
            try:
                store.upsert_bars(symbol, timeframe, bars)
            except Exception:  # noqa: BLE001 — loi kho khong raise
                pass
    return {"bars": bars_out, "missing": missing}
