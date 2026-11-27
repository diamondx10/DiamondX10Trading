"""Briefing PTCB (phan tich truoc phien) cho tung desk DiamondX10.

Moi briefing gom 2 file giong nhau ve noi dung:
- briefings/briefing-<desk>-<YYYYMMDD-HHMM>.md (de analyst doc)
- briefings/briefing-<desk>-<YYYYMMDD-HHMM>.json (du lieu co cau truc)

Noi dung: gia moi nhat + tin hieu TA (SMA/RSI/ATR) cho tung symbol
cua desk, tin thi truong gom theo tier do tin cay, snapshot vi mo
(neu config co muc `macro:`), va mau verdict JSON ma analyst phai
tra ve (direction / confidence / drivers / risks / note).

Quy tac:
- Chuoi hien thi tieng Viet KHONG dau (vd "khong co", "tin hieu").
- Khong goi mang that / MT5 trong test: feed va news_fetcher la
  diem tiem (injection) cho test; khi khong truyen feed thi dung
  chung lua chon feed nhu cac lenh khac (data.providers.build_feed:
  'simulated' mac dinh, 'mt5' tren may co MT5 terminal).
- Tin thi truong lay qua data.news.run_news. Briefing la anh chup
  (snapshot) nen luon hien thi tat ca tin da loc trong `days` ngay
  (include_seen=True) va dung NewsStore tam thoi — khong lam thay
  doi lich su dedup chung o data/news-history.db.
- Tin tier 3 (RO RI) luon kem canh bao CHUA XAC MINH, khong dung
  lam can cu duy nhat cho quyet dinh giao dich.
"""
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .data.news import TRUST_TIERS, NewsStore, run_news
from .data.providers import build_feed
from .models.macro import macro_edge
from .signals import generate_signals

DESKS = ["forex", "xauusd", "crypto", "us_securities"]

DESK_ANALYSTS = {
    "forex": "Yuling Pan",
    "xauusd": "Yumi",
    "crypto": "Rich",
    "us_securities": "Kathy",
}

MISSING_NEWS_MESSAGE = (
    "chua co news: trong config — copy tu config.example.yaml"
)

DEFAULT_BARS = 60
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[2] / "briefings"

VERDICT_DIRECTIONS = ("buy", "sell", "neutral")


# --- Tien ich nho ---

def _close_feed(feed):
    """Dong feed neu co close() (MT5Feed.shutdown); loi dong thi bo qua."""
    close = getattr(feed, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # noqa: BLE001 — dong feed khong duoc thi thoi
            pass


def _jsonable(value):
    """Chuyen 1 gia tri ve dang ghi duoc ra JSON (dict/list/str/so/bool/None).

    Dung cho cac truong do code khac tra ve (vd "patterns" — module
    signals co the them khoa nay sau) ma khong chac da JSON-safe.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def _desk_symbols(cfg, desk):
    """Symbol cua desk trong config (data.symbols)."""
    symbols = ((cfg or {}).get("data", {}).get("symbols", {}) or {}).get(desk) or []
    if not symbols:
        raise ValueError(
            f"Chua cau hinh symbol cho desk {desk!r} trong config.yaml "
            "(data.symbols).")
    return list(symbols)


def _analyst_for_desk(cfg, desk):
    """Ten analyst phu trach desk (bang co dinh; fallback ve manager
    trong config neu desk la)."""
    if desk in DESK_ANALYSTS:
        return DESK_ANALYSTS[desk]
    manager = (((cfg or {}).get("fund") or {}).get("desks") or {}).get(desk) or {}
    if isinstance(manager, dict) and manager.get("manager"):
        return str(manager["manager"])
    return desk


def _open_feed_for_symbol(cfg, desk, symbol, feed):
    """Feed cho 1 symbol. Tra (feed_obj, close_after).

    - feed=None: dung chung lua chon feed nhu cac lenh khac
      (build_feed: provider 'simulated' mac dinh, 'mt5' khi cau hinh).
    - feed la dict {symbol: feed}: lay feed theo symbol.
    - feed la ham (symbol) -> feed: goi de lay feed (dung cho test).
    - feed la object co bars()/latest_price(): dung truc tiep.
    """
    if feed is None:
        return build_feed(cfg, desk, symbol=symbol), True
    if isinstance(feed, dict):
        if symbol not in feed:
            raise ValueError(f"Feed gia khong co symbol {symbol!r}.")
        return feed[symbol], False
    if callable(feed):
        return feed(symbol), True
    return feed, False


def _format_regime(regime):
    """Regime (dict tu signals.detect_regime, hoac str) -> 1 dong doc duoc."""
    if regime is None:
        return "(khong co thong tin regime)"
    if isinstance(regime, str):
        return regime
    if isinstance(regime, dict):
        name = regime.get("regime", "UNKNOWN")
        direction = regime.get("direction", "")
        adx = regime.get("adx")
        vol = regime.get("volatility", "")
        conf = regime.get("confidence")
        parts = [str(name)]
        if direction:
            parts.append(f"huong {direction}")
        if adx is not None:
            parts.append(f"ADX {adx}")
        if vol:
            parts.append(f"bien dong {vol}")
        if conf is not None:
            parts.append(f"do tin cay {conf}")
        return " | ".join(parts)
    return str(regime)


def _format_patterns(patterns):
    """Patterns (list str hoac dict, doc phong thu) -> list dong doc duoc.

    Signals co the tra ve 1 pattern cho MOI bar (vd 60 doji) nen md
    GOM NHOM theo (ten, direction): dem so lan xuat hien, chi ghi
    bar moi nhat — tranh in 60 dong lap lai. File .json van giu
    NGUYEN danh sach patterns day du.
    """
    lines = []
    grouped = {}
    order = []
    for pat in patterns or []:
        if isinstance(pat, str):
            key = (pat, "", "")
            display = pat
            bar_index = None
        elif isinstance(pat, dict):
            name = pat.get("name") or pat.get("pattern") or pat.get("type") or ""
            direction = str(pat.get("direction") or "")
            strength = pat.get("strength")
            extra = f"strength={strength}" if strength is not None else ""
            key = (str(name), direction, extra)
            display = str(name)
            bar_index = pat.get("bar_index")
            if isinstance(bar_index, str) and bar_index.isdigit():
                bar_index = int(bar_index)
        else:
            key = (str(pat), "", "")
            display = str(pat)
            bar_index = None
        if key not in grouped:
            grouped[key] = {"display": display, "count": 0, "last_bar": None}
            order.append(key)
        grouped[key]["count"] += 1
        if isinstance(bar_index, int):
            last = grouped[key]["last_bar"]
            grouped[key]["last_bar"] = (bar_index if last is None
                                        else max(last, bar_index))
    for key in order:
        entry = grouped[key]
        name, direction, extra = key
        parts = [entry["display"]]
        if direction:
            parts.append(f"direction={direction}")
        if extra:
            parts.append(extra)
        if entry["count"] > 1:
            parts.append(f"x{entry['count']} lan")
        if entry["last_bar"] is not None:
            parts.append(f"bar moi nhat {entry['last_bar']}")
        lines.append(" ".join(parts) if len(parts) == 1
                     else f"{parts[0]} ({', '.join(parts[1:])})")
    return lines


def _article_dict(article):
    """NewsArticle -> dict JSON-safe (ghi vao file .json)."""
    pub = getattr(article, "pub_date", None)
    return {
        "title": article.title,
        "link": article.link,
        "source": article.source,
        "summary": article.summary or "",
        "trust_tier": int(getattr(article, "trust_tier", 2)),
        "trust_label": article.trust_label(),
        "is_urgent": bool(getattr(article, "is_urgent", False)),
        "pub_date": pub.isoformat() if pub is not None else None,
        "desks": list(getattr(article, "desk_tags", []) or []),
    }


def _group_news(result):
    """Gom tin theo tier: {"tier_1": [...], "tier_2": [...], "tier_3": [...]}."""
    grouped = {"tier_1": [], "tier_2": [], "tier_3": []}
    for article in result.get("articles") or []:
        tier = int(getattr(article, "trust_tier", 2) or 2)
        if tier not in (1, 2, 3):
            tier = 2
        grouped[f"tier_{tier}"].append(_article_dict(article))
    return grouped


def _build_macro(cfg, symbols):
    """Snapshot vi mo + macro edge tung symbol; None neu khong co muc macro:."""
    macro_cfg = (cfg or {}).get("macro")
    if not macro_cfg:
        return None
    snapshot = {k: macro_cfg.get(k)
                for k in ("dxy", "us10y", "vix", "spx")
                if macro_cfg.get(k) is not None}
    edges = {}
    for symbol in symbols:
        edges[symbol] = _jsonable(macro_edge(
            symbol,
            dxy=macro_cfg.get("dxy"), us10y=macro_cfg.get("us10y"),
            vix=macro_cfg.get("vix"), spx=macro_cfg.get("spx")))
    return {"snapshot": snapshot, "edges": edges}


def _verdict_template(desk, analyst, generated):
    """Mau verdict JSON ma analyst phai tra ve (gia tri vi du hop le)."""
    return {
        "desk": desk,
        "analyst": analyst,
        "direction": "neutral",
        "confidence": 0.0,
        "drivers": [],
        "risks": [],
        "note": "",
        "created_utc": generated.isoformat(),
    }


# --- Render Markdown ---

def _render_md(desk, analyst, symbols_data, news_grouped, news_errors,
               macro, verdict, generated):
    """Noi dung file .md (tieng Viet khong dau)."""
    stamp = generated.strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# BRIEFING PHAN TICH — DESK {desk.upper()}",
        "",
        f"Chao {analyst},",
        "",
        "Briefing nay tong hop gia + tin hieu ky thuat (TA), tin thi truong "
        "va boi canh vi mo de ban dua ra verdict cho desk "
        f"{desk} truoc phien giao dich.",
        "",
        f"- Desk: {desk}",
        f"- Analyst: {analyst}",
        f"- Ngay tao (UTC): {stamp}",
        "- Symbols: " + ", ".join(s['symbol'] for s in symbols_data),
        "",
        "## TONG QUAN KY THUAT (TA)",
        "",
    ]
    for item in symbols_data:
        lines.append(f"### {item['symbol']}")
        lines.append(f"- Gia moi nhat: {item['price']}")
        lines.append(f"- Tin hieu: {item['action']} — {item['reason']}")
        lines.append(f"- Regime: {_format_regime(item['regime'])}")
        pattern_lines = _format_patterns(item.get("patterns") or [])
        if pattern_lines:
            lines.append("- Patterns:")
            for pat in pattern_lines:
                lines.append(f"  - {pat}")
        levels = item.get("levels") or {}
        if levels:
            lines.append(
                "- Levels: entry={entry} SL={sl} TP={tp} ATR={atr}".format(
                    entry=levels.get("entry", "?"),
                    sl=levels.get("sl", "?"),
                    tp=levels.get("tp", "?"),
                    atr=levels.get("atr", "?")))
        lines.append("")
    lines.append("## TIN THI TRUONG")
    lines.append("")
    if news_errors:
        lines.append("Loi lay tin:")
        for err in news_errors:
            lines.append(f"- {err}")
        lines.append("")
    for tier in (1, 2, 3):
        label = TRUST_TIERS.get(tier, "BAO CHI")
        lines.append(f"### Tier {tier} — {label}")
        if tier == 3:
            lines.append(
                "CANH BAO: tin ro ri CHUA XAC MINH — khong dung lam can cu "
                "duy nhat cho quyet dinh giao dich.")
        items = news_grouped.get(f"tier_{tier}") or []
        if not items:
            lines.append("(khong co tin.)")
        for art in items:
            flag = " [KHAN]" if art.get("is_urgent") else ""
            lines.append(
                f"- [{art['trust_label']}]{flag} {art['title']}")
            lines.append(f"  {art['source']} | {art['link']}")
            if art.get("summary"):
                lines.append(f"  {art['summary'][:200]}")
            if tier == 3:
                lines.append(
                    "  CANH BAO: tin ro ri CHUA XAC MINH — khong dung lam "
                    "can cu duy nhat cho quyet dinh giao dich.")
        lines.append("")
    if macro is not None:
        lines.append("## VI MO (MACRO)")
        lines.append("")
        snapshot = macro.get("snapshot") or {}
        for key, label in (("dxy", "DXY"), ("us10y", "US10Y"),
                           ("vix", "VIX"), ("spx", "SPX")):
            if snapshot.get(key) is not None:
                lines.append(f"- {label}: {snapshot[key]}")
        for symbol, edge in (macro.get("edges") or {}).items():
            if isinstance(edge, dict):
                lines.append(
                    f"- {symbol}: macro edge score {edge.get('score')} — "
                    f"{edge.get('summary')}")
        lines.append("")
    lines.append("## KET LUAN CAN TRA VE (VERDICT)")
    lines.append("")
    lines.append(
        f"{analyst} tra ve verdict theo dung mau JSON duoi day (1 object "
        "JSON duy nhat, khong them truong ngoai mau).")
    lines.append(
        'direction chi nhan "buy" | "sell" | "neutral"; '
        "confidence la so 0..1; drivers / risks la danh sach chuoi; "
        "created_utc la thoi gian ISO UTC luc tao verdict.")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(verdict, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


# --- API chinh ---

def build_briefing(cfg, desk, days=3, *, feed=None, news_fetcher=None,
                   out_dir=None):
    """Tao briefing cho 1 desk, ghi file .md + .json, tra dict tom tat.

    Tra {"desk", "analyst", "symbols" (list ten symbol), "generated_utc"
    (ISO), "md_path", "json_path" (str)}.

    Raise ValueError neu config thieu muc `news:` hoac thieu symbol
    cho desk; ImportError/ConnectionError neu khong lay duoc feed
    (vd provider 'mt5' tren may khong co MT5).
    """
    if desk not in DESKS:
        raise ValueError(
            f"Desk khong biet: {desk!r} (chon trong {DESKS}).")
    if int(days) <= 0:
        raise ValueError(f"--days phai > 0 (nhan {days!r}).")
    news_cfg = (cfg or {}).get("news")
    if not news_cfg:
        raise ValueError(f"{MISSING_NEWS_MESSAGE} (desk {desk}).")
    symbols = _desk_symbols(cfg, desk)
    analyst = _analyst_for_desk(cfg, desk)
    generated = datetime.now(timezone.utc)
    stamp = generated.strftime("%Y%m%d-%H%M")

    # 1. Gia + TA tung symbol (feed mac dinh: build_feed theo config).
    symbols_data = []
    for symbol in symbols:
        feed_obj, close_after = _open_feed_for_symbol(cfg, desk, symbol, feed)
        try:
            bars = feed_obj.bars(DEFAULT_BARS)
            if not bars:
                raise ValueError(
                    f"Feed khong tra ve bar nao cho {symbol!r}.")
            try:
                price = float(feed_obj.latest_price(symbol))
            except Exception:  # noqa: BLE001 — fallback ve gia dong bar cuoi
                price = float(bars[-1]["close"])
            sig = generate_signals(desk, bars, symbol=symbol, cfg=cfg)
        finally:
            if close_after:
                _close_feed(feed_obj)
        symbols_data.append({
            "symbol": symbol,
            "price": price,
            "action": sig.get("action"),
            "reason": sig.get("reason", ""),
            "regime": _jsonable(sig.get("regime")),
            "patterns": _jsonable(sig.get("patterns", [])),
            "levels": _jsonable(sig.get("levels") or {}),
            "strategy": sig.get("strategy"),
        })

    # 2. Tin thi truong (snapshot: hien tat ca tin da loc, khong dung
    # lich su dedup chung).
    with tempfile.TemporaryDirectory(prefix="diamondx10-news-") as tmp:
        store = NewsStore(Path(tmp) / "news-history.db")
        try:
            news_result = run_news(news_cfg, desk=desk, max_age_days=days,
                                   fetcher=news_fetcher, store=store,
                                   include_seen=True)
        finally:
            store.close()
    news_grouped = _group_news(news_result)
    news_errors = list(news_result.get("errors") or [])

    # 3. Vi mo (chi khi config co muc macro:).
    macro = _build_macro(cfg, symbols)

    verdict = _verdict_template(desk, analyst, generated)
    data = {
        "desk": desk,
        "analyst": analyst,
        "symbols": symbols_data,
        "generated_utc": generated.isoformat(),
        "news": {
            "tier_1": news_grouped["tier_1"],
            "tier_2": news_grouped["tier_2"],
            "tier_3": news_grouped["tier_3"],
            "fetched": news_result.get("fetched", 0),
            "matched": news_result.get("matched", 0),
            "new": news_result.get("new", 0),
            "errors": news_errors,
        },
        "macro": macro,
        "verdict_template": verdict,
    }

    out = Path(out_dir) if out_dir is not None else DEFAULT_OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"briefing-{desk}-{stamp}.md"
    json_path = out / f"briefing-{desk}-{stamp}.json"
    md_path.write_text(
        _render_md(desk, analyst, symbols_data, news_grouped,
                   news_errors, macro, verdict, generated),
        encoding="utf-8")
    json_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return {
        "desk": desk,
        "analyst": analyst,
        "symbols": symbols,
        "generated_utc": generated.isoformat(),
        "md_path": str(md_path),
        "json_path": str(json_path),
    }


def cmd_briefing(cfg, desk="forex", days=3, all_desks=False, *, feed=None,
                 news_fetcher=None, out_dir=None):
    """Lenh CLI `briefing`: tao briefing 1 desk hoac tat ca 4 desk.

    Tra 0 neu xong, 1 neu that bai (in loi tieng Viet ngan gon, KHONG
    in traceback). Loi thuong gap: thieu muc `news:` trong config,
    provider 'mt5' tren may khong co MT5.
    """
    desks = list(DESKS) if all_desks else [desk]
    try:
        results = [build_briefing(cfg, d, days, feed=feed,
                                  news_fetcher=news_fetcher, out_dir=out_dir)
                   for d in desks]
    except (ValueError, ImportError, ConnectionError, OSError) as exc:
        print(f"LOI: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 — lenh CLI khong bao gio traceback
        print(f"LOI: khong tao duoc briefing ({exc})")
        return 1
    for result in results:
        print(f"OK: briefing {result['desk']} cho {result['analyst']}")
        print(f"  MD: {result['md_path']}")
        print(f"  JSON: {result['json_path']}")
    return 0
