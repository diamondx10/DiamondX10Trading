"""API backend FastAPI cho WebUI DiamondX10 (dx10).

Phuc vu build React (src/diamondx10/static) o / va JSON API o /api/*.

BAO MAT — chi local + dang nhap OTP qua Telegram (xem webauth.py):
  - Bind mac dinh 127.0.0.1, KHONG BAO GIO 0.0.0.0. Chi mo cong ra
    ngoai khi biet ro minh dang lam gi.
  - Moi /api/* (tru /api/auth/request-otp, /api/auth/verify-otp,
    /api/auth/status) doi cookie phien "dx10_session" hop le; OTP
    6 chu so gui qua Telegram, TTL 60 giay, dung 1 lan.
  - Khong co token / mat khau trong code hay response; moi lenh dat
    deu qua dung chan nhu nut Telegram (kill switch, demo-only, ky
    quy, do lech entry — xem listener.place_pending_order).
  - File briefing gui len Muse chi duoc doc trong thu muc briefings/
    (chan path traversal).

Quy tac chung:
  - Chuoi hien thi tieng Viet KHONG dau trong code, log va JSON —
    TRU ly do tra ve cho tab Manager cua WebUI (dich theo ngon ngu
    config qua i18n, tieng Viet co dau day du — xem _start_proc).
  - Moi endpoint that bai sach (JSON error, khong traceback) khi
    thieu file state hay khong co MT5; MT5 tren Linux luon bao
    mt5_ok=false chu khong raise.
  - Config doc moi lan xu ly request (load_config) nen sua config
    khong can khoi dong lai server. Nho vay tab Muse (tao briefing /
    gui briefing) va GET /api/language luon dung ngon ngu hien tai
    trong config.yaml luc goi (quy tac 51).
  - muse_browser.py la hop dong TUY CHON: chi import LAZY trong worker
    gui briefing; neu chua co thi job bao loi "Muse browser chua san
    sang" chu khong crash server.

Chay: python -m diamondx10.webapi [--port 8000] [--host 127.0.0.1]
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    _FASTAPI_ERROR = None
except ImportError as exc:  # noqa: BLE001 — chay thieu fastapi thi bao ro
    FastAPI = None
    HTTPException = None
    Request = None
    FileResponse = None
    JSONResponse = None
    StaticFiles = None
    _FASTAPI_ERROR = exc

from . import killswitch, telegram
from .i18n import proc_display_name, t as _i18n_t
from .webauth import (
    OTP_TTL_SECONDS,
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    OTPManager,
    SessionStore,
)
from .briefing import DESK_ANALYSTS, DESKS as BRIEFING_DESKS
from .briefing import _article_dict, _news_card, build_briefing
from .config import load_config
from .dashboard import (
    _find_backtest_result,
    _max_dd_pct,
    _positions_section,
    _safe_load_state,
    _safe_read_log,
)
from .data.feeds import SimulatedFeed
from .data.history import HistoryStore
from .data.news import DEFAULT_STORE_PATH as NEWS_STORE_PATH
from .data.news import run_news
from .data.providers import build_feed
from .listener import place_pending_order
from .models.quant import atr as _atr
from .models.quant import rsi as _rsi
from .pending import PendingOrderStore
from .posts import PostStore
from .procman import MANAGED_PROCESSES, ProcessManager
from .signals import generate_signals
from .synthesis import (
    cmd_synthesize,
    load_verdict,
    load_verdicts,
    save_verdict,
    synthesize,
    validate_verdict,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
BRIEFINGS_DIR = REPO_ROOT / "briefings"
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"

# Symbol mac dinh moi desk (giong config.example.yaml) — dung khi
# config local chua cau hinh data.symbols.
DEFAULT_SYMBOLS = {
    "forex": ["EURUSD"],
    "us_securities": ["AMD", "CDNS", "SNPS", "INTC", "NVDA"],
    "xauusd": ["XAUUSD"],
    "crypto": ["BTCUSD", "BNBUSD", "ETHUSD"],
}

# Ngon ngu giao dien (quy tac 51): "vi" | "en", mac dinh "vi".
# Doc tu khoa `language:` o cap cao nhat cua config.yaml.
SUPPORTED_LANGUAGES = ("vi", "en")

# Registry tien trinh live / listener: {name: {"proc", "started", "mode"}}.
_PROCS = {}
# Manager bat log cho tien trinh duoc quan ly (live / listener /
# diagnostics): stdout + stderr vao ring buffer trong bo nho.
_MANAGER = ProcessManager()
# Job gui briefing len Muse: {job_id: {"status","verdict","reason"}}.
_MUSE_JOBS = {}
_MUSE_JOBS_LOCK = threading.Lock()


# --- Tien ich nho ---

def _load_cfg():
    """Doc config moi (sua config khong can restart server)."""
    try:
        return load_config(DEFAULT_CONFIG_PATH)
    except Exception:  # noqa: BLE001 — config hong thi dung mac dinh rong
        return {}


def _resolve_language(cfg):
    """Ngon ngu hien tai ("vi" | "en", mac dinh "vi").

    Neu module i18n (cua nhom) da co thi dung `i18n.get_language`
    cua no de 1 cho duy nhat quyet dinh; chua co thi doc truc tiep
    khoa `language:` o cap cao nhat cua config. Gia tri la thi
    ve "vi" — khong bao gio raise.
    """
    try:
        import importlib
        i18n = importlib.import_module("diamondx10.i18n")
        get_language = getattr(i18n, "get_language", None)
        if callable(get_language):
            lang = get_language(cfg)
            if isinstance(lang, str) and lang in SUPPORTED_LANGUAGES:
                return lang
            return "vi"
    except Exception:  # noqa: BLE001 — chua co i18n thi doc truc tiep
        pass
    lang = (cfg or {}).get("language")
    if isinstance(lang, str) and lang.strip() in SUPPORTED_LANGUAGES:
        return lang.strip()
    return "vi"


def _apply_language_to_config_text(text, language):
    """Ap dung `language:` o cap cao nhat vao noi dung config.yaml.

    Kieu quickstart._apply_telegram_to_config_text: thay dong
    `language:` cap cao nhat neu co (khong dung vao dong `language:`
    thut dau trong khoi con), chua co thi them o cuoi file. Cac khoa
    va comment khac giu nguyen.
    """
    lines = text.splitlines()
    out = []
    seen = False
    for line in lines:
        stripped = line.strip()
        if (not line.startswith((" ", "\t")) and stripped
                and stripped.startswith("language:")):
            out.append(f"language: {language}")
            seen = True
            continue
        out.append(line)
    if not seen:
        if out and out[-1].strip():
            out.append("")
        out.append(f"language: {language}")
    return "\n".join(out) + "\n"


def _apply_news_settings_to_config_text(text, settings):
    """Ap dung cac khoa vao muc `news:` cua config.yaml.

    Giong _apply_language_to_config_text (sua theo dong, giu nguyen
    cac khoa/comment khac): doi dong khoa trong khoi `news:` neu co;
    chua co thi chen ngay sau dong `news:` (neu khoi `news:` da co)
    hoac them khoi `news:` moi o cuoi file. `settings`: dict
    key -> gia tri da format san cho YAML (vd "true", "5"). Khong
    bao gio tao file — chi sua text da doc duoc (endpoint kiem tra
    file ton tai truoc).
    """
    lines = text.splitlines()
    # 1. Tim khoi `news:` cap cao nhat (dong khong thut dau).
    news_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (not line.startswith((" ", "\t")) and stripped
                and stripped.startswith("news:")):
            news_idx = i
            break
    if news_idx is None:
        out = list(lines)
        if out and out[-1].strip():
            out.append("")
        out.append("news:")
        for key, value in settings.items():
            out.append(f"  {key}: {value}")
        return "\n".join(out) + "\n"
    # 2. Cuoi khoi news: (dong sau `news:` den khoa cap cao nhat ke
    # tiep) — gioi han pham vi tim/chen khoa.
    end = len(lines)
    for i in range(news_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if (not lines[i].startswith((" ", "\t")) and stripped
                and not stripped.startswith("#")):
            end = i
            break
    pending = dict(settings)
    for i in range(news_idx + 1, end):
        stripped = lines[i].strip()
        for key in list(pending):
            if stripped.startswith(f"{key}:"):
                indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
                lines[i] = f"{indent or '  '}{key}: {pending.pop(key)}"
    # 3. Khoa con thieu: chen ngay sau dong `news:` (neu dong do la
    # khoi rong, khong phai mapping inline nhu `news: {}`).
    if pending:
        news_line = lines[news_idx].strip()
        at = news_idx + 1
        if not (news_line == "news:"
                or news_line.startswith("news: #")):
            at = end
        insert = [f"  {key}: {value}"
                  for key, value in pending.items()]
        lines[at:at] = insert
    return "\n".join(lines) + "\n"


def _apply_test_mode_to_config_text(text, test_mode):
    """Ap dung `test_mode:` vao muc `news:` (xem
    _apply_news_settings_to_config_text)."""
    return _apply_news_settings_to_config_text(
        text, {"test_mode": "true" if test_mode else "false"})


# --- Lay tin + dang the tin (dung chung cho POST /api/news-fetch va
# vong tu dong lay tin) ---

def _fetch_news_once(cfg):
    """1 luot lay tin tat ca desk + dang the tin moi len feed.

    Giong lenh CLI `news --all` (xem __main__._cmd_news): dung
    run_news + kho NewsStore ben vung (dedupe MD5) + NewsCardStore.
    publish_cards (dedupe theo id). Tra {"fetched", "matched",
    "new", "cards_created", "errors"}. Chua cau hinh nguon tin thi
    raise ValueError (endpoint doi thanh 400, vong tu dong chi log
    roi cho luot sau). KHONG gui Telegram — chi lay tin + dang the
    (the moi o trang thai "dang cho phan tich" den khi verdict ve
    qua chu ky briefing/verdict).
    """
    news_cfg = (cfg or {}).get("news") or {}
    if not (news_cfg.get("sources") or []):
        raise ValueError(
            "Chua cau hinh nguon tin (muc 'news' trong config.yaml) — "
            "xem config.example.yaml")
    try:
        days = int(news_cfg.get("max_age_days") or 2)
    except (TypeError, ValueError):
        days = 2
    result = run_news(news_cfg, desk=None, max_age_days=days)
    created = 0
    try:
        from .newsfeed import NewsCardStore
        store = NewsCardStore()
        created_utc = datetime.now(timezone.utc).isoformat()
        cards = []
        for article in result.get("articles") or []:
            tags = list(getattr(article, "desk_tags", []) or [])
            art_desk = tags[0] if tags else "forex"
            analyst = DESK_ANALYSTS.get(art_desk, art_desk)
            cards.append(_news_card(_article_dict(article), art_desk,
                                    analyst, created_utc))
        if cards:
            created, _skipped = store.publish_cards(cards)
    except Exception as exc:  # noqa: BLE001 — dang the loi thi bao, khong hong luot lay tin
        print(f"LOI webapi news-fetch cards: {exc}")
    return {"fetched": int(result.get("fetched") or 0),
            "matched": int(result.get("matched") or 0),
            "new": int(result.get("new") or 0),
            "cards_created": int(created),
            "errors": list(result.get("errors") or [])}


# --- Vong tu dong lay tin (chay nen, khong phu thuoc trinh duyet) ---

_AUTO_FETCH_INTERVAL_DEFAULT = 5
_AUTO_FETCH_INTERVAL_MIN = 1
_AUTO_FETCH_INTERVAL_MAX = 60
_AUTO_FETCH_STATE = {"last_fetch_utc": None, "next_fetch_utc": None}
_AUTO_FETCH_STATE_LOCK = threading.Lock()
_AUTO_FETCH_THREAD = None
_AUTO_FETCH_WAKE = threading.Event()


def _clamp_auto_fetch_interval(value):
    """Khoang thoi gian tu dong lay tin (phut), kep 1–60."""
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        minutes = _AUTO_FETCH_INTERVAL_DEFAULT
    return max(_AUTO_FETCH_INTERVAL_MIN,
               min(_AUTO_FETCH_INTERVAL_MAX, minutes))


def _auto_fetch_config(cfg):
    """(enabled, interval_min) tu config — mac dinh tat / 5 phut."""
    news_cfg = (cfg or {}).get("news") or {}
    return (bool(news_cfg.get("auto_fetch_enabled")),
            _clamp_auto_fetch_interval(
                news_cfg.get("auto_fetch_interval_min")))


def _auto_fetch_state():
    """Trang thai vong tu dong lay tin: enabled/interval tu config
    (nguon that), last/next fetch tu runtime."""
    cfg = _load_cfg()
    enabled, interval = _auto_fetch_config(cfg)
    with _AUTO_FETCH_STATE_LOCK:
        last = _AUTO_FETCH_STATE["last_fetch_utc"]
        nxt = _AUTO_FETCH_STATE["next_fetch_utc"]
    return {"enabled": enabled, "interval_min": interval,
            "last_fetch_utc": last, "next_fetch_utc": nxt}


def _auto_fetch_loop():
    """Vong lap nen: doc config moi luot; bat thi lay tin ngay roi
    cho het khoang thoi gian; tat thi cho 5 giay roi doc lai config
    (POST bat/tat goi _AUTO_FETCH_WAKE de luot hien tai tinh lai
    ngay, khong doi het khoang cho). Luot loi (chua cau hinh /
    mang loi) chi log roi cho luot sau — khong bao gio crash
    server, khong bao gio gui Telegram."""
    while True:
        cfg = _load_cfg()
        enabled, interval = _auto_fetch_config(cfg)
        if not enabled:
            with _AUTO_FETCH_STATE_LOCK:
                _AUTO_FETCH_STATE["next_fetch_utc"] = None
            _AUTO_FETCH_WAKE.wait(timeout=5)
            _AUTO_FETCH_WAKE.clear()
            continue
        try:
            _fetch_news_once(cfg)
            now = datetime.now(timezone.utc)
            with _AUTO_FETCH_STATE_LOCK:
                _AUTO_FETCH_STATE["last_fetch_utc"] = now.isoformat()
                nxt = now + timedelta(minutes=interval)
                _AUTO_FETCH_STATE["next_fetch_utc"] = nxt.isoformat()
        except Exception as exc:  # noqa: BLE001 — luot loi thi log, cho luot sau
            print(f"LOI webapi auto-fetch: {exc}")
            now = datetime.now(timezone.utc)
            with _AUTO_FETCH_STATE_LOCK:
                _AUTO_FETCH_STATE["next_fetch_utc"] = (
                    now + timedelta(minutes=interval)).isoformat()
        _AUTO_FETCH_WAKE.wait(timeout=interval * 60)
        _AUTO_FETCH_WAKE.clear()


def _ensure_auto_fetch_thread():
    """Khoi dong vong tu dong lay tin 1 lan duy nhat (daemon — chet
    cung server). Goi o create_app de cau hinh bat san tu config
    cung chay ma khong can mo trinh duyet."""
    global _AUTO_FETCH_THREAD
    if _AUTO_FETCH_THREAD is not None and _AUTO_FETCH_THREAD.is_alive():
        return
    thread = threading.Thread(target=_auto_fetch_loop, daemon=True,
                              name="dx10-auto-fetch")
    thread.start()
    _AUTO_FETCH_THREAD = thread


def _latest_briefing_by_desk():
    """Briefing moi nhat moi desk: {desk: {"file", "time"}}."""
    latest = {}
    if BRIEFINGS_DIR.is_dir():
        for path in BRIEFINGS_DIR.glob("briefing-*.md"):
            try:
                mtime = datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            parts = path.name.split("-")
            desk = parts[1] if len(parts) > 1 else ""
            if desk not in BRIEFING_DESKS:
                continue
            item = {"file": path.name, "time": mtime.isoformat()}
            if desk not in latest or item["time"] > latest[desk]["time"]:
                latest[desk] = item
    return latest


def _team_news_items(briefings_by_desk):
    """Tin moi nhat moi desk tu kho tin (NewsStore).

    Moi desk toi da 1 bai (bai moi nhat). Kho thieu/hong thi [] —
    khong bao gio raise.
    """
    items = []
    try:
        if not NEWS_STORE_PATH.exists():
            return []
        conn = sqlite3.connect(f"file:{NEWS_STORE_PATH}?mode=ro",
                               uri=True, timeout=5)
        try:
            rows = conn.execute(
                "SELECT article_title, article_url, source, "
                "trust_tier, pub_date, seen_at, desks "
                "FROM seen_articles "
                "ORDER BY seen_at DESC, rowid DESC LIMIT 200").fetchall()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — kho tin loi thi rong
        print(f"LOI webapi team-news: {exc}")
        return []
    seen_desks = set()
    for title, url, source, tier, pub_date, seen_at, desks in rows:
        for desk in (d.strip() for d in (desks or "").split(",")):
            if desk not in BRIEFING_DESKS or desk in seen_desks:
                continue
            seen_desks.add(desk)
            briefing = briefings_by_desk.get(desk)
            items.append({
                "title": title or "",
                "source": source or "",
                "tier": tier if tier in (1, 2, 3) else 2,
                "desk": desk,
                "analyst": DESK_ANALYSTS.get(desk, desk),
                "time": pub_date or seen_at or "",
                "briefing_url": (f"briefings/{briefing['file']}"
                                 if briefing else None),
            })
        if len(seen_desks) >= len(BRIEFING_DESKS):
            break
    return items


def _desk_symbols(cfg, desk):
    symbols = ((cfg or {}).get("data", {}).get("symbols", {}) or {}).get(desk)
    if symbols:
        return list(symbols)
    return list(DEFAULT_SYMBOLS.get(desk) or [])


def _history_path(cfg):
    raw = ((cfg or {}).get("history") or {}).get("db_path") or "data/history.db"
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def _timeframe(cfg):
    return ((cfg or {}).get("history") or {}).get("default_timeframe") or "M15"


def _load_mt5_or_none():
    """Module MetaTrader5 neu cai duoc, None neu khong (Linux)."""
    try:
        from .data.mt5_feed import load_mt5
        return load_mt5()
    except Exception:  # noqa: BLE001 — khong co MT5 thi None, khong raise
        return None


def _mt5_ok(cfg):
    """True neu import duoc MT5 VA terminal khoi dong duoc.

    Tren Linux luon False. Khong bao gio raise, khong treo server.
    """
    try:
        from .data.mt5_feed import load_mt5, resolve_mt5_terminal_path
        mt5 = load_mt5()
        path = resolve_mt5_terminal_path(cfg)
        if path is None:
            return False
        ok = bool(mt5.initialize(path=str(path)))
        try:
            mt5.shutdown()
        except Exception:  # noqa: BLE001 — dong MT5 loi thi thoi
            pass
        return ok
    except Exception:  # noqa: BLE001 — moi loi MT5 deu la "khong ok"
        return False


def _bars_for_symbol(cfg, desk, symbol, n=60):
    """Bar cho 1 symbol: MT5 live (neu provider mt5) -> kho lich su ->
    mo phong. Khong bao gio raise (mo phong luon co)."""
    # 1. Feed theo config (simulated mac dinh; mt5 tren may co MT5).
    try:
        feed = build_feed(cfg, desk, symbol=symbol)
        try:
            bars = feed.bars(n)
        finally:
            close = getattr(feed, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 — dong feed loi thi thoi
                    pass
        if bars:
            return list(bars)
    except Exception:  # noqa: BLE001 — roi xuong kho lich su / mo phong
        pass
    # 2. Kho lich su local.
    try:
        with HistoryStore(str(_history_path(cfg))) as store:
            bars = store.get_bars(symbol, _timeframe(cfg))
        if bars:
            return list(bars[-n:])
    except Exception:  # noqa: BLE001 — roi xuong mo phong
        pass
    # 3. Mo phong (giong lenh CLI `signals`).
    return list(SimulatedFeed(desk).bars(n))


def _pattern_names(patterns):
    """List pattern (dict hoac str) -> list ten (str)."""
    names = []
    for pat in patterns or []:
        if isinstance(pat, str):
            names.append(pat)
        elif isinstance(pat, dict):
            name = pat.get("name") or pat.get("pattern") or pat.get("type")
            if name:
                names.append(str(name))
        else:
            names.append(str(pat))
    return names


def _signal_item(cfg, desk, symbol):
    """1 tin hieu TA cho 1 symbol (dung chung cho /signals va
    /synthesis)."""
    bars = _bars_for_symbol(cfg, desk, symbol)
    sig = generate_signals(desk, bars, symbol=symbol, cfg=cfg)
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    strategy_cfg = (cfg or {}).get("strategy") or {}
    try:
        rsi_val = _rsi(closes, int(strategy_cfg.get("rsi_period", 14)))
    except Exception:  # noqa: BLE001 — khong tinh duoc RSI thi None
        rsi_val = None
    try:
        atr_val = _atr(highs, lows, closes,
                       int(strategy_cfg.get("atr_period", 14)))
    except Exception:  # noqa: BLE001 — khong tinh duoc ATR thi None
        atr_val = None
    levels = sig.get("levels") or {}
    if atr_val is None and levels.get("atr") is not None:
        try:
            atr_val = float(levels["atr"])
        except (TypeError, ValueError):
            atr_val = None
    regime = sig.get("regime")
    if isinstance(regime, dict):
        regime_name = regime.get("regime")
    elif regime is None:
        regime_name = None
    else:
        regime_name = str(regime)
    return {
        "symbol": symbol,
        "action": sig.get("action"),
        "rsi": (round(float(rsi_val), 2) if rsi_val is not None else None),
        "atr": (round(float(atr_val), 6) if atr_val is not None else None),
        "patterns": _pattern_names(sig.get("patterns")),
        "regime": regime_name,
    }


def _desk_signals(cfg, desk):
    """Tin hieu TA cho moi symbol cua desk; symbol loi thi bo qua
    (khong crash ca endpoint)."""
    items = []
    for symbol in _desk_symbols(cfg, desk):
        try:
            items.append(_signal_item(cfg, desk, symbol))
        except Exception as exc:  # noqa: BLE001 — 1 symbol loi thi bo
            print(f"LOI webapi signals {desk}/{symbol}: {exc}")
    return items


def _verdict_age_hours(verdict):
    """Tuoi nhan dinh (gio); None neu khong tinh duoc."""
    if not verdict:
        return None
    try:
        created = datetime.fromisoformat(
            str(verdict.get("created_utc") or "").replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - created).total_seconds()
                     / 3600.0, 2)
    except (ValueError, TypeError):
        return None


def _fund_status(cfg):
    """Von/drawdown/vi the tu equity state (None khi chua co state)."""
    state = _safe_load_state()
    capital = float((cfg.get("fund") or {}).get("total_capital_usd") or 0)
    desks_cfg = (cfg.get("fund") or {}).get("desks") or {}
    if not state or not isinstance(state.get("guard"), dict):
        return {
            "equity": None, "capital": capital, "drawdown_pct": None,
            "desks": [{"desk": d, "equity": None, "open_positions": 0}
                      for d in desks_cfg],
            "positions": [],
        }
    guard = state["guard"]
    fund_curve = guard.get("fund_curve") or []
    equity = float(fund_curve[-1]) if fund_curve else None
    drawdown = _max_dd_pct([float(v) for v in fund_curve]) if fund_curve else None
    positions = state.get("positions") or []
    desks = []
    for desk in desks_cfg:
        curve = (guard.get("desk_curves") or {}).get(desk) or []
        desks.append({
            "desk": desk,
            "equity": float(curve[-1]) if curve else None,
            "open_positions": sum(
                1 for p in positions if p.get("desk") == desk),
        })
    return {"equity": equity, "capital": capital,
            "drawdown_pct": drawdown, "desks": desks,
            "positions": positions}


# --- Quan ly tien trinh live / listener ---

def _spawn_proc(argv):
    """Chay 1 tien trinh con (diem tiem cho test).

    stdout/stderr ve PIPE (text, line-buffered) de _MANAGER bat log
    theo dong; khong dung DEVNULL nua.
    """
    env = os.environ.copy()
    src_dir = str(REPO_ROOT / "src")
    existing = env.get("PYTHONPATH") or ""
    env["PYTHONPATH"] = src_dir + (os.pathsep + existing if existing else "")
    # Log chay thang ra stdout khi tien trinh con dang chay (khong doi
    # day bo dem): LogViewer poll /api/logs moi 2 giay thay dong moi
    # ngay, thay vi chi thay khi tien trinh thoat. Chi anh huong
    # tien trinh con cua web UI (live / listener / diagnostics).
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.Popen(
        argv, cwd=str(REPO_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1)


def _start_proc(name, argv, mode, lang=None):
    """Khoi dong tien trinh (neu chua chay). Tra (ok, reason).

    Ly do (reason) duoc dich theo ngon ngu cua config (mac dinh "vi",
    tieng Viet co dau day du): `lang` truyen vao thang neu co, khong
    thi doc config nhu cac endpoint khac. Ten tien trinh hien thi
    cung duoc dich qua i18n.proc_display_name (khong de lo ten noi
    bo "live" / "listener" / "diagnostics" ra UI); chi tiet ky thuat
    (exception, ma thoat) giu nguyen dang goc.
    """
    if lang is None:
        lang = _resolve_language(_load_cfg())
    display = proc_display_name(name, lang)
    entry = _PROCS.get(name)
    if entry is not None and entry["proc"].poll() is None:
        return False, _i18n_t("mgr.proc_running", lang, proc=display)
    try:
        proc = _spawn_proc(argv)
    except Exception as exc:  # noqa: BLE001 — khong chay duoc thi bao ro
        return False, _i18n_t("mgr.proc_start_failed", lang,
                              proc=display, detail=exc)
    started = datetime.now(timezone.utc).isoformat()
    _PROCS[name] = {"proc": proc, "started": started, "mode": mode}
    # Dang ky vao manager TRUOC khi doi 0.3s de bat ca log thoat som.
    try:
        _MANAGER.register(name, proc, started_utc=started)
    except Exception:  # noqa: BLE001 — bat log loi thi van chay tien trinh
        pass
    time.sleep(0.3)
    if proc.poll() is not None:
        return False, _i18n_t("mgr.proc_exited", lang, proc=display,
                              code=proc.returncode)
    return True, _i18n_t("mgr.proc_started", lang, proc=display)


def _stop_proc(name):
    """Dung tien trinh (neu chay). Tra True neu da dung / khong chay."""
    entry = _PROCS.get(name)
    if entry is None:
        return True
    if _MANAGER.get(name) is not None:
        return _MANAGER.stop(name)
    proc = entry["proc"]
    if proc.poll() is not None:
        return True
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 — kill loi thi thoi
            pass
    except Exception:  # noqa: BLE001 — dung loi thi thoi
        pass
    return True


def _proc_status(name):
    """Trang thai tien trinh: {"running","mode","started"}."""
    entry = _PROCS.get(name)
    if entry is None or entry["proc"].poll() is not None:
        return {"running": False, "mode": None, "started": None}
    return {"running": True, "mode": entry.get("mode"),
            "started": entry.get("started")}


def _proc_lines(name, after=0):
    """Log da bat cua tien trinh `name` sau cursor `after`.

    Tra {"process","running","started_utc","exit_code","lines",
    "total"} — total la tong so dong trong buffer (de frontend poll
    tang dan bang after=total). Chua tung chay thi buffer rong.
    """
    status = _MANAGER.status(name)
    total, lines = _MANAGER.lines(name, after=after)
    return {"process": name, "running": status["running"],
            "started_utc": status["started_utc"],
            "exit_code": status["exit_code"],
            "lines": lines, "total": total}


# --- Job gui briefing len Muse ---

def _set_job(job_id, status, verdict, reason):
    with _MUSE_JOBS_LOCK:
        _MUSE_JOBS[job_id] = {"status": status, "verdict": verdict,
                              "reason": reason or ""}


def _muse_send_worker(job_id, path, cfg):
    """Worker thread: gui briefing -> doi verdict -> luu verdict.

    Import muse_browser LAZY o day; neu module chua co thi job bao loi
    "Muse browser chua san sang" chu khong crash.
    """
    try:
        import importlib
        try:
            muse_browser = importlib.import_module(
                "diamondx10.muse_browser")
        except ImportError:
            _set_job(job_id, "error", None, "Muse browser chua san sang")
            return
        try:
            result = muse_browser.send_briefing(str(path), cfg)
        except Exception as exc:  # noqa: BLE001 — gui loi thi bao ro
            _set_job(job_id, "error", None,
                     f"khong gui duoc briefing: {exc}")
            return
        if not result.get("sent"):
            _set_job(job_id, "error", None,
                     result.get("message") or "khong gui duoc briefing")
            return
        _set_job(job_id, "sent", None,
                 result.get("message") or "da gui briefing")
        wait_min = int(((cfg or {}).get("muse") or {}).get("wait_min") or 10)
        try:
            verdict = muse_browser.wait_for_verdict(cfg,
                                                    timeout_min=wait_min)
        except Exception as exc:  # noqa: BLE001 — doi verdict loi thi bao
            _set_job(job_id, "error", None, f"loi khi doi verdict: {exc}")
            return
        if verdict is None:
            _set_job(job_id, "timeout", None,
                     "het thoi gian cho verdict — copy verdict tu chat "
                     "Muse roi chay: verdict --file <verdict.json>")
        else:
            # wait_for_verdict da luu verdict qua synthesis.save_verdict.
            _set_job(job_id, "verdict_stored", verdict, "da luu verdict")
    except Exception as exc:  # noqa: BLE001 — worker khong bao gio crash
        _set_job(job_id, "error", None, f"loi khong ro: {exc}")


# --- App ---

def create_app(static_dir=None):
    """Tao app FastAPI. static_dir: thu muc build React (mac dinh
    src/diamondx10/static); truyen ro de test duoc ca 2 truong hop
    co / chua co frontend."""
    if FastAPI is None:
        raise RuntimeError(
            "FastAPI chua cai — chay: pip install fastapi uvicorn")
    static_path = Path(static_dir) if static_dir is not None else STATIC_DIR
    app = FastAPI(title="DiamondX10 WebAPI")

    # Vong tu dong lay tin chay nen theo config (quy tac 60): khoi
    # dong 1 lan duy nhat cho ca process — app nao tao sau cung
    # dung chung vong do, khong tao them thread.
    _ensure_auto_fetch_thread()

    @app.exception_handler(Exception)
    async def _unhandled(request, exc):  # noqa: ARG001
        # Moi loi bat ngo deu tra JSON sach, khong traceback.
        print(f"LOI webapi: {exc}")
        return JSONResponse(status_code=500,
                            content={"detail": f"loi server: {exc}"})

    # --- Xac thuc OTP (webauth.py, chi trong bo nho) ---
    # Moi create_app() co OTPManager + SessionStore rieng: app moi thi
    # khong co OTP / phien cu. Test doc OTP qua app.state.otp_manager
    # .peek_otp() (chi trong process, KHONG qua API).
    otp_manager = OTPManager()
    session_store = SessionStore()
    app.state.otp_manager = otp_manager
    app.state.session_store = session_store
    _AUTH_EXEMPT = frozenset({
        "/api/auth/request-otp", "/api/auth/verify-otp",
        "/api/auth/status"})

    @app.middleware("http")
    async def _auth_middleware(request, call_next):
        path = request.url.path
        if path.startswith("/api/") and path not in _AUTH_EXEMPT:
            token = request.cookies.get(SESSION_COOKIE_NAME)
            if not token or not session_store.is_valid(token):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "chua dang nhap — can ma OTP "
                                       "de dang nhap"})
        return await call_next(request)

    @app.post("/api/auth/request-otp")
    def api_auth_request_otp(payload: dict = None):  # noqa: ARG001
        result = otp_manager.request_otp()
        if not result["ok"]:
            return JSONResponse(
                status_code=429,
                content={"detail": "yeu cau ma qua nhanh — cho chut roi "
                                   "thu lai",
                         "retry_after": result["retry_after"]})
        code = result["code"]
        cfg = _load_cfg()
        lang = _resolve_language(cfg)
        sent = False
        reason = ""
        try:
            if telegram.setup_status(cfg).get("ready"):
                sent = bool(telegram.send_message(
                    _i18n_t("auth.otp_message", lang, code=code,
                            seconds=OTP_TTL_SECONDS),
                    cfg=cfg))
                if not sent:
                    reason = "khong gui duoc qua Telegram"
            else:
                reason = "telegram chua cau hinh"
        except Exception as exc:  # noqa: BLE001 — gui loi thi fallback
            sent = False
            reason = f"khong gui duoc qua Telegram: {exc}"
        if sent:
            return {"sent": True}
        # Fallback: in ma ra stdout cua terminal chay server de nguoi
        # dung doc truc tiep. Chi in ra console, KHONG ghi file/log.
        print("DX10 MA DANG NHAP (chi hien tren terminal nay, hieu luc "
              f"60 giay, khong chia se): {code}")
        return {"sent": False, "fallback": "terminal", "reason": reason}

    @app.post("/api/auth/verify-otp")
    def api_auth_verify_otp(payload: dict):
        code = payload.get("code") if isinstance(payload, dict) else None
        if not isinstance(code, str) or not code.strip():
            return JSONResponse(status_code=401,
                                content={"reason": "invalid"})
        ok, reason = otp_manager.verify_otp(code)
        if not ok:
            return JSONResponse(status_code=401,
                                content={"reason": reason})
        token = session_store.create()
        response = JSONResponse(content={"ok": True,
                                         "authenticated": True})
        response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True,
                            samesite="lax", path="/",
                            max_age=SESSION_MAX_AGE_SECONDS)
        return response

    @app.post("/api/auth/sign-out")
    def api_auth_sign_out(request: Request):
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if token:
            session_store.revoke(token)
        response = JSONResponse(content={"ok": True})
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return response

    @app.get("/api/auth/status")
    def api_auth_status(request: Request):
        token = request.cookies.get(SESSION_COOKIE_NAME)
        return {"authenticated": bool(
            token and session_store.is_valid(token))}

    @app.get("/")
    def index():
        index_path = static_path / "index.html"
        if index_path.is_file():
            return FileResponse(str(index_path))
        return {"message": "frontend chua duoc build — API van hoat dong",
                "api": "/api/status"}

    @app.get("/favicon.svg")
    def favicon():
        """Icon web UI (dau kim cuong + X, webui/public/favicon.svg dem
        vao build). SVG la text nen day len GitHub duoc (push snapshot
        chi cho file UTF-8, khong cho file nhi phan nhu PNG). Khong doi
        auth (nhu GET /) de trinh duyet tai duoc khi mo trang."""
        icon_path = static_path / "favicon.svg"
        if icon_path.is_file():
            return FileResponse(str(icon_path), media_type="image/svg+xml")
        raise HTTPException(
            status_code=404,
            detail="chua co favicon — build web UI truoc")

    # --- Trang thai / vi the ---

    @app.get("/api/status")
    def api_status():
        cfg = _load_cfg()
        try:
            fund = _fund_status(cfg)
        except Exception as exc:  # noqa: BLE001 — state hong thi bao rong
            print(f"LOI webapi status: {exc}")
            fund = {"equity": None,
                    "capital": float((cfg.get("fund") or {})
                                     .get("total_capital_usd") or 0),
                    "drawdown_pct": None, "desks": [], "positions": []}
        try:
            tg_ready = bool(telegram.setup_status(cfg).get("ready"))
        except Exception:  # noqa: BLE001 — telegram loi thi coi nhu chua san
            tg_ready = False
        return {
            "equity": fund["equity"],
            "capital": fund["capital"],
            "drawdown_pct": fund["drawdown_pct"],
            "kill_switch_on": killswitch.is_engaged(),
            "mt5_ok": _mt5_ok(cfg),
            "telegram_ready": tg_ready,
            "live_running": _proc_status("live")["running"],
            "listener_running": _proc_status("listener")["running"],
            "desks": fund["desks"],
        }

    @app.get("/api/positions")
    def api_positions():
        cfg = _load_cfg()
        state = _safe_load_state()
        if not state:
            return {"positions": []}
        try:
            rows = _positions_section(state, _history_path(cfg),
                                      _timeframe(cfg))
        except Exception as exc:  # noqa: BLE001 — doc vi the loi thi rong
            print(f"LOI webapi positions: {exc}")
            return {"positions": []}
        return {"positions": [
            {"desk": r.get("desk"), "symbol": r.get("symbol"),
             "direction": r.get("direction"), "entry": r.get("entry"),
             "sl": r.get("sl"), "tp": r.get("tp"),
             "volume": r.get("volume"),
             "opened_date": r.get("opened_date"),
             "latest_price": r.get("latest_price"),
             "unrealized_pnl": r.get("unrealized_pnl")}
            for r in rows]}

    # --- Tin hieu / tong hop ---

    @app.get("/api/signals")
    def api_signals(desk: str = "forex"):
        cfg = _load_cfg()
        return {"desk": desk, "signals": _desk_signals(cfg, desk)}

    @app.get("/api/synthesis")
    def api_synthesis(desk: str = "forex"):
        cfg = _load_cfg()
        try:
            verdict = load_verdict(None, desk)
        except Exception:  # noqa: BLE001 — kho verdict hong thi coi nhu chua co
            verdict = None
        age = _verdict_age_hours(verdict)
        items = []
        for sig in _desk_signals(cfg, desk):
            try:
                syn = synthesize(
                    sig.get("action") or "HOLD",
                    verdict.get("direction") if verdict else None,
                    verdict.get("confidence") if verdict else None,
                    cfg, verdict_age_hours=age)
            except ValueError as exc:
                items.append({
                    "symbol": sig["symbol"], "ta_action": sig.get("action"),
                    "fa_direction": None, "fa_confidence": None,
                    "recommendation": "CHO", "size_factor": 0.0,
                    "verdict_age_hours": age,
                    "rationale": f"khong tong hop duoc: {exc}"})
                continue
            missing = syn.get("fa_status") in ("missing", "stale")
            items.append({
                "symbol": sig["symbol"],
                "ta_action": sig.get("action"),
                "fa_direction": None if missing else (
                    verdict.get("direction") if verdict else None),
                "fa_confidence": None if missing else (
                    verdict.get("confidence") if verdict else None),
                "recommendation": syn.get("recommendation"),
                "size_factor": syn.get("size"),
                "verdict_age_hours": age,
                "rationale": syn.get("rationale") or "",
            })
        return {"desk": desk, "items": items}

    # --- Lenh cho ---

    @app.get("/api/pending")
    def api_pending():
        store = PendingOrderStore()
        try:
            store.prune_expired()
        except Exception:  # noqa: BLE001 — prune loi thi van tra danh sach
            pass
        records = [dict(r) for r in (store._orders or {}).values()]
        records.sort(key=lambda r: r.get("created_utc") or "", reverse=True)
        return {"pending": records}

    @app.post("/api/pending/{order_id}/place")
    def api_pending_place(order_id: str):
        cfg = _load_cfg()
        store = PendingOrderStore()
        if store.get(order_id) is None:
            raise HTTPException(
                status_code=404,
                detail=f"khong tim thay lenh cho {order_id}")
        mt5 = _load_mt5_or_none()
        result = place_pending_order(cfg, mt5, store, order_id)
        return {"ok": bool(result.get("ok")),
                "ticket": result.get("ticket"),
                "reason": result.get("reason") or ""}

    @app.post("/api/pending/{order_id}/ignore")
    def api_pending_ignore(order_id: str):
        store = PendingOrderStore()
        if store.get(order_id) is None:
            raise HTTPException(
                status_code=404,
                detail=f"khong tim thay lenh cho {order_id}")
        ok = bool(store.mark_cancelled(order_id))
        return {"ok": ok}

    # --- Kill switch ---

    @app.post("/api/kill-switch")
    def api_kill_switch(payload: dict):
        on = payload.get("on")
        if not isinstance(on, bool):
            raise HTTPException(
                status_code=400,
                detail=_i18n_t("mgr.kill_switch_bad_field",
                               _resolve_language(_load_cfg())))
        if on:
            killswitch.engage("webui", by="webui")
        else:
            killswitch.disengage(by="webui")
        return {"kill_switch_on": killswitch.is_engaged()}

    # --- Log / briefing / verdict ---

    @app.get("/api/decisions")
    def api_decisions(lines: int = 50):
        rows = _safe_read_log()
        lines = max(1, min(int(lines), 500))
        recent = list(reversed(rows[-lines:])) if rows else []
        return {"rows": [
            {"time": r.get("date", ""), "symbol": r.get("symbol", ""),
             "action": r.get("action", ""), "reason": r.get("reason", ""),
             "desk": r.get("desk", ""), "manager": r.get("manager", "")}
            for r in recent]}

    @app.get("/api/briefings")
    def api_briefings():
        items = []
        if BRIEFINGS_DIR.is_dir():
            for path in BRIEFINGS_DIR.glob("briefing-*.md"):
                try:
                    mtime = datetime.fromtimestamp(
                        path.stat().st_mtime, tz=timezone.utc)
                except OSError:
                    continue
                parts = path.name.split("-")
                desk = parts[1] if len(parts) > 1 else ""
                items.append({"desk": desk, "file": path.name,
                              "name": path.name,
                              "created": mtime.isoformat(),
                              "path": str(path)})
        items.sort(key=lambda i: i["created"], reverse=True)
        return {"briefings": items}

    @app.post("/api/briefing")
    def api_briefing(payload: dict):
        desk = payload.get("desk") or "forex"
        days = payload.get("days") or 3
        if desk not in BRIEFING_DESKS:
            return {"ok": False, "file": None,
                    "reason": f"desk khong hop le: {desk!r}"}
        cfg = _load_cfg()
        try:
            result = build_briefing(cfg, desk, days=int(days))
        except Exception as exc:  # noqa: BLE001 — loi tao briefing thi bao ro
            return {"ok": False, "file": None, "reason": str(exc)}
        return {"ok": True, "file": result.get("md_path"),
                "reason": f"da tao briefing {desk}"}

    @app.post("/api/muse-send")
    def api_muse_send(payload: dict):
        name = payload.get("file") or ""
        if (not isinstance(name, str) or not name or "/" in name
                or "\\" in name or ".." in name):
            raise HTTPException(
                status_code=400,
                detail="file phai la ten file trong thu muc briefings/ "
                       "(khong duong dan, khong '..')")
        path = BRIEFINGS_DIR / name
        if not path.is_file():
            raise HTTPException(
                status_code=400,
                detail=f"khong tim thay file briefing {name}")
        job_id = uuid.uuid4().hex[:12]
        _set_job(job_id, "sending", None, "dang gui briefing len Muse")
        cfg = _load_cfg()
        thread = threading.Thread(
            target=_muse_send_worker, args=(job_id, path, cfg), daemon=True)
        thread.start()
        return {"job_id": job_id, "status": "sending"}

    @app.get("/api/muse-send/{job_id}")
    def api_muse_send_status(job_id: str):
        with _MUSE_JOBS_LOCK:
            job = _MUSE_JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404,
                                detail=f"khong tim thay job {job_id}")
        return {"status": job["status"], "verdict": job["verdict"],
                "reason": job["reason"]}

    @app.get("/api/verdicts")
    def api_verdicts():
        try:
            verdicts = load_verdicts()
        except Exception:  # noqa: BLE001 — kho hong thi tra rong
            verdicts = {}
        items = []
        for verdict in verdicts.values():
            items.append({
                "desk": verdict.get("desk"),
                "analyst": verdict.get("analyst"),
                "direction": verdict.get("direction"),
                "confidence": verdict.get("confidence"),
                "drivers": verdict.get("drivers") or [],
                "risks": verdict.get("risks") or [],
                "note": verdict.get("note") or "",
                "created_utc": verdict.get("created_utc"),
                "age_hours": _verdict_age_hours(verdict),
            })
        items.sort(key=lambda i: i["created_utc"] or "", reverse=True)
        return {"verdicts": items}

    @app.post("/api/verdicts")
    def api_verdicts_post(payload: dict):
        data = payload.get("verdict")
        if not isinstance(data, dict):
            data = payload
        try:
            cleaned = validate_verdict(data)
            save_verdict(cleaned)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True,
                "reason": f"da luu nhan dinh desk {cleaned['desk']}"}

    # --- Ngon ngu giao dien (quy tac 51) ---

    @app.get("/api/language")
    def api_language():
        cfg = _load_cfg()
        return {"language": _resolve_language(cfg)}

    @app.post("/api/language")
    def api_language_post(payload: dict):
        language = payload.get("language") if isinstance(payload, dict) else None
        if language not in SUPPORTED_LANGUAGES:
            raise HTTPException(
                status_code=400,
                detail="language phai la 'vi' hoac 'en'")
        if not DEFAULT_CONFIG_PATH.is_file():
            raise HTTPException(
                status_code=404,
                detail="khong tim thay config.yaml — chay quickstart "
                       "truoc de tao config (khong tu tao config nua "
                       "voi)")
        try:
            text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"khong doc duoc config.yaml: {exc}")
        try:
            DEFAULT_CONFIG_PATH.write_text(
                _apply_language_to_config_text(text, language),
                encoding="utf-8")
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"khong ghi duoc config.yaml: {exc}")
        return {"language": language}

    # --- Che do thu nghiem tin tuc (quy tac 59) ---

    @app.get("/api/news-test-mode")
    def api_news_test_mode():
        cfg = _load_cfg()
        return {"test_mode": bool(
            ((cfg or {}).get("news") or {}).get("test_mode"))}

    @app.post("/api/news-test-mode")
    def api_news_test_mode_post(payload: dict):
        test_mode = payload.get("test_mode") \
            if isinstance(payload, dict) else None
        if not isinstance(test_mode, bool):
            raise HTTPException(
                status_code=400,
                detail="test_mode phai la true hoac false")
        if not DEFAULT_CONFIG_PATH.is_file():
            raise HTTPException(
                status_code=404,
                detail="khong tim thay config.yaml — chay quickstart "
                       "truoc de tao config (khong tu tao config nua "
                       "voi)")
        try:
            text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"khong doc duoc config.yaml: {exc}")
        try:
            DEFAULT_CONFIG_PATH.write_text(
                _apply_test_mode_to_config_text(text, test_mode),
                encoding="utf-8")
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"khong ghi duoc config.yaml: {exc}")
        return {"test_mode": test_mode}

    # --- Tu dong lay tin (quy tac 60) ---

    @app.get("/api/news-auto-fetch")
    def api_news_auto_fetch():
        return _auto_fetch_state()

    @app.post("/api/news-auto-fetch")
    def api_news_auto_fetch_post(payload: dict):
        payload = payload if isinstance(payload, dict) else {}
        cfg = _load_cfg()
        enabled_now, interval_now = _auto_fetch_config(cfg)
        enabled = payload.get("enabled", enabled_now)
        if not isinstance(enabled, bool):
            raise HTTPException(
                status_code=400,
                detail="enabled phai la true hoac false")
        interval = payload.get("interval_min", interval_now)
        if isinstance(interval, bool) or not isinstance(interval, int):
            raise HTTPException(
                status_code=400,
                detail="interval_min phai la so nguyen (phut)")
        interval = _clamp_auto_fetch_interval(interval)
        if not DEFAULT_CONFIG_PATH.is_file():
            raise HTTPException(
                status_code=404,
                detail="khong tim thay config.yaml — chay quickstart "
                       "truoc de tao config (khong tu tao config nua "
                       "voi)")
        try:
            text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"khong doc duoc config.yaml: {exc}")
        try:
            DEFAULT_CONFIG_PATH.write_text(
                _apply_news_settings_to_config_text(text, {
                    "auto_fetch_enabled": "true" if enabled else "false",
                    "auto_fetch_interval_min": str(interval)}),
                encoding="utf-8")
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"khong ghi duoc config.yaml: {exc}")
        # Tinh lai vong lap ngay: bat thi lay tin ngay 1 luot, tat
        # thi dung cho luot tiep theo.
        _AUTO_FETCH_WAKE.set()
        return _auto_fetch_state()

    # --- Tin doi da phan tich (trang chu, quy tac 52) ---

    @app.get("/api/team-news")
    def api_team_news():
        try:
            briefings_by_desk = _latest_briefing_by_desk()
        except Exception as exc:  # noqa: BLE001 — thu muc loi thi rong
            print(f"LOI webapi team-news briefings: {exc}")
            briefings_by_desk = {}
        try:
            verdicts = load_verdicts()
        except Exception as exc:  # noqa: BLE001 — kho hong thi rong
            print(f"LOI webapi team-news verdicts: {exc}")
            verdicts = {}
        verdicts_out = {}
        for desk in BRIEFING_DESKS:
            verdict = verdicts.get(desk)
            if verdict:
                verdicts_out[desk] = {
                    "direction": verdict.get("direction"),
                    "confidence": verdict.get("confidence"),
                }
            else:
                verdicts_out[desk] = None
        briefings = [
            {"desk": desk, "file": info["file"], "time": info["time"]}
            for desk, info in sorted(briefings_by_desk.items())]
        return {
            "items": _team_news_items(briefings_by_desk),
            "verdicts": verdicts_out,
            "briefings": briefings,
        }

    # --- The tin tuc tren feed trang chu (quy tac 58) ---

    @app.get("/api/news-cards")
    def api_news_cards(limit: int = 50, desk: str = None):
        """The tin tuc hien tren feed trang chu, moi nhat len dau.

        ?limit=N (mac dinh 50, kep 1–200) &desk=forex (tuy chon).
        Kho thieu/hong thi tra danh sach rong — khong bao gio raise
        (giong /api/team-news, /api/posts). Moi card co `impact`
        (None neu chua co phan tich tac dong cua Muse) de feed hien
        trang thai "dang cho phan tich".
        """
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 200))
        try:
            from .newsfeed import NewsCardStore
        except Exception as exc:  # noqa: BLE001 — chua co module thi rong
            print(f"LOI webapi news-cards: {exc}")
            return {"cards": []}
        try:
            return {"cards": NewsCardStore().list_cards(
                limit=limit, desk=desk)}
        except Exception as exc:  # noqa: BLE001 — kho hong thi rong
            print(f"LOI webapi news-cards: {exc}")
            return {"cards": []}

    @app.post("/api/news-fetch")
    def api_news_fetch(payload: dict = None):
        """Lay tin ngay (tat ca desk) + dang the tin moi len feed.

        Giong lenh CLI `news --all` (xem __main__._cmd_news): dung
        chung _fetch_news_once voi vong tu dong lay tin. Chua cau
        hinh nguon tin (muc `news:` trong config) thi 400 ro rang,
        khong tra success rong, khong traceback.
        """
        cfg = _load_cfg()
        try:
            return _fetch_news_once(cfg)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:  # noqa: BLE001 — lay tin loi thi 500 sach, khong traceback
            print(f"LOI webapi news-fetch: {exc}")
            raise HTTPException(
                status_code=500, detail=f"khong tai duoc tin: {exc}")

    # --- Bai dang phan tich (feed trang chu) ---

    @app.get("/api/posts")
    def api_posts(limit: int = 20, desk: str = None):
        """Feed bai dang phan tich, moi nhat len dau.

        ?limit=N (mac dinh 20, toi da 200) &desk=forex (tuy chon).
        Kho thieu/hong thi tra danh sach rong — khong bao gio raise.
        """
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 200))
        store = PostStore()
        return {"posts": store.list_posts(limit=limit, desk=desk)}

    @app.post("/api/posts")
    def api_posts_create(payload: dict):
        """Dang 1 bai phan tich thu cong (composer o web UI).

        Body: {desk, symbol, action, summary, confidence?, entry?,
        sl?, tp?, drivers?, risks?}. Thieu truong bat buoc hoac
        action la thi 400. Bai BUY/SELL thi gui tom tat qua Telegram
        (chi khi telegram.enabled = true); NEUTRAL khong gui.
        """
        cfg = _load_cfg()
        payload = payload or {}
        desk = payload.get("desk")
        symbol = payload.get("symbol")
        action = payload.get("action")
        summary = payload.get("summary")
        for field, value in (("desk", desk), ("symbol", symbol),
                             ("action", action), ("summary", summary)):
            if not isinstance(value, str) or not value.strip():
                raise HTTPException(
                    status_code=400, detail=f"thieu truong '{field}'")
        if (not isinstance(action, str)
                or action.strip().upper() not in ("BUY", "SELL", "NEUTRAL")):
            raise HTTPException(
                status_code=400,
                detail="action phai la BUY | SELL | NEUTRAL")
        drivers = payload.get("drivers")
        risks = payload.get("risks")
        for field, value in (("drivers", drivers), ("risks", risks)):
            if value is not None and not isinstance(value, list):
                raise HTTPException(
                    status_code=400,
                    detail=f"truong '{field}' phai la list cac chuoi")
        try:
            post, _created = PostStore().publish_post(
                desk=desk.strip(), symbol=symbol, action=action,
                summary=summary, confidence=payload.get("confidence", 0.0),
                drivers=drivers, risks=risks, entry=payload.get("entry"),
                sl=payload.get("sl"), tp=payload.get("tp"),
                source="manual", cfg=cfg)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return JSONResponse(status_code=201, content={"post": post})

    @app.post("/api/publish")
    def api_publish(payload: dict = None):
        """Chay tong hop Yuling + dang bai phan tich cho 1 desk/symbol.

        Body: {desk?, symbol?} (mac dinh desk=forex, tat ca symbol cua
        desk). Tra {"posts": [...bai MOI tao...]} — bai da co do
        dedupe thi khong nam trong danh sach. Tong hop loi thi 500.
        """
        cfg = _load_cfg()
        payload = payload or {}
        desk = payload.get("desk") or "forex"
        symbol = payload.get("symbol")
        if desk not in BRIEFING_DESKS:
            raise HTTPException(
                status_code=400, detail=f"desk khong hop le: {desk!r}")
        store = PostStore()
        before = {post["id"]
                  for post in store.list_posts(limit=1000)}
        rc = cmd_synthesize(cfg, desk, symbol, publish=True,
                            post_store=store)
        if rc != 0:
            raise HTTPException(
                status_code=500,
                detail="khong tong hop/dang bai duoc — xem log server")
        after = store.list_posts(limit=1000)
        created = [post for post in after if post["id"] not in before]
        return {"posts": created}

    # --- Tin / backtest / bar ---

    @app.get("/api/news")
    def api_news(desk: str = "forex"):
        cfg = _load_cfg()
        news_cfg = (cfg or {}).get("news") or {}
        if not (news_cfg.get("sources") or []):
            return {"desk": desk, "articles": [],
                    "note": "chua cau hinh news trong config — copy muc "
                            "news: tu config.example.yaml"}
        articles = []
        note = ""
        try:
            if NEWS_STORE_PATH.exists():
                conn = sqlite3.connect(f"file:{NEWS_STORE_PATH}?mode=ro",
                                       uri=True, timeout=5)
                try:
                    rows = conn.execute(
                        "SELECT article_title, article_url, source, "
                        "trust_tier, pub_date FROM seen_articles "
                        "WHERE desks LIKE ? ORDER BY seen_at DESC LIMIT 50",
                        (f"%{desk}%",)).fetchall()
                finally:
                    conn.close()
                articles = [{"title": r[0], "url": r[1], "source": r[2],
                             "tier": r[3], "published": r[4]} for r in rows]
        except Exception as exc:  # noqa: BLE001 — doc kho tin loi thi rong
            print(f"LOI webapi news: {exc}")
            articles = []
        if not articles:
            note = "chua co tin trong kho — chay lenh `news` truoc"
        return {"desk": desk, "articles": articles, "note": note}

    @app.get("/api/backtest")
    def api_backtest():
        path = _find_backtest_result()
        if path is None:
            return {"backtest": None}
        try:
            with open(path, encoding="utf-8") as f:
                return {"backtest": json.load(f)}
        except (ValueError, OSError) as exc:
            print(f"LOI webapi backtest: {exc}")
            return {"backtest": None}

    @app.get("/api/bars")
    def api_bars(symbol: str = "EURUSD", n: int = 60):
        cfg = _load_cfg()
        n = max(1, min(int(n), 500))
        bars = []
        try:
            with HistoryStore(str(_history_path(cfg))) as store:
                bars = store.get_bars(symbol, _timeframe(cfg))
        except Exception as exc:  # noqa: BLE001 — kho loi thi mo phong
            print(f"LOI webapi bars: {exc}")
            bars = []
        if not bars:
            desk = next((d for d, syms in DEFAULT_SYMBOLS.items()
                         if symbol in syms), "forex")
            bars = list(SimulatedFeed(desk).bars(n))
        else:
            bars = list(bars[-n:])
        return {"symbol": symbol,
                "bars": [{"time": b.get("time"),
                          "open": float(b["open"]),
                          "high": float(b["high"]),
                          "low": float(b["low"]),
                          "close": float(b["close"])} for b in bars]}

    # --- Live / listener ---

    @app.get("/api/live")
    def api_live():
        return _proc_status("live")

    @app.post("/api/live/start")
    def api_live_start(payload: dict):
        mode = payload.get("mode") or "recommend"
        desk = payload.get("desk") or "forex"
        lang = _resolve_language(_load_cfg())
        if mode not in ("recommend", "auto"):
            return {"ok": False,
                    "reason": _i18n_t("mgr.live_bad_mode", lang)}
        argv = [sys.executable, "-m", "diamondx10", "live",
                "--desk", desk]
        if mode == "recommend":
            argv.append("--recommend-only")
        ok, reason = _start_proc("live", argv, mode, lang=lang)
        return {"ok": ok, "reason": reason}

    @app.post("/api/live/stop")
    def api_live_stop():
        _stop_proc("live")
        return {"ok": True}

    @app.get("/api/listener")
    def api_listener():
        status = _proc_status("listener")
        return {"running": status["running"]}

    @app.post("/api/listener/start")
    def api_listener_start():
        argv = [sys.executable, "-m", "diamondx10", "telegram-listen"]
        ok, reason = _start_proc("listener", argv, "listen")
        return {"ok": ok, "reason": reason}

    @app.post("/api/listener/stop")
    def api_listener_stop():
        _stop_proc("listener")
        return {"ok": True}

    @app.post("/api/start-all")
    def api_start_all():
        """Khoi dong ca Live (che do recommend) va Telegram listener.

        Moi thanh phan khoi dong doc lap qua cung helper _start_proc
        nhu nut rieng: 1 cai loi thi cai kia van thu, ca hai ket qua
        deu duoc tra ve. Thanh phan da chay thi ok:true (khong phai
        loi) — ly do (reason) lay nguyen tu helper.
        """
        live_argv = [sys.executable, "-m", "diamondx10", "live",
                     "--desk", "forex", "--recommend-only"]
        live_ok, live_reason = _start_proc("live", live_argv, "recommend")
        if not live_ok and _proc_status("live")["running"]:
            live_ok = True  # da chay: idempotent, khong phai loi
        listener_argv = [sys.executable, "-m", "diamondx10",
                         "telegram-listen"]
        listener_ok, listener_reason = _start_proc(
            "listener", listener_argv, "listen")
        if not listener_ok and _proc_status("listener")["running"]:
            listener_ok = True  # da chay: idempotent, khong phai loi
        return {"live": {"ok": live_ok, "reason": live_reason},
                "listener": {"ok": listener_ok,
                             "reason": listener_reason}}

    # --- Manager console: log tien trinh / diagnostics / telegram-test ---

    @app.get("/api/logs")
    def api_logs(process: str = "live", after: int = 0):
        """Log da bat cua 1 tien trinh duoc quan ly.

        ?process=live|listener|diagnostics &after=N (cursor: so dong
        da doc; tra chi cac dong moi hon + total de poll tang dan).
        Ten tien trinh la thi 400.
        """
        if process not in MANAGED_PROCESSES:
            raise HTTPException(
                status_code=400,
                detail=_i18n_t(
                    "mgr.logs_bad_process",
                    _resolve_language(_load_cfg()), process=process))
        return _proc_lines(process, after=after)

    @app.post("/api/diagnostics")
    def api_diagnostics_start():
        """Chay test_run.py o che do an toan mac dinh (khong dat lenh)
        nhu tien trinh "diagnostics" duoc quan ly; log xem o /api/logs
        ?process=diagnostics. Da chay thi ok:false.
        """
        argv = [sys.executable, "test_run.py"]
        ok, reason = _start_proc("diagnostics", argv, "diagnostics")
        return {"ok": ok, "reason": reason}

    @app.post("/api/telegram-test")
    def api_telegram_test():
        """Gui 1 tin nhan thu qua Telegram (dung lai logic CLI
        telegram-test: kiem tra setup truoc, roi gui 1 tin).
        """
        from .__main__ import cmd_telegram_test

        cfg = _load_cfg()
        lang = _resolve_language(cfg)
        status = telegram.setup_status(cfg)
        if not status.get("ready"):
            # Dich tung muc thieu theo co (enabled / token / chat_id)
            # thay vi dung lai chuoi khong dau cua setup_status (chuoi
            # do phuc vu CLI, giu nguyen).
            missing = []
            if not status.get("enabled"):
                missing.append(_i18n_t("mgr.tg_missing_enabled", lang))
            if not status.get("has_token"):
                missing.append(_i18n_t("mgr.tg_missing_token", lang))
            if not status.get("has_chat_id"):
                missing.append(_i18n_t("mgr.tg_missing_chat_id", lang))
            if not missing:
                missing = [str(m) for m in
                           (status.get("missing") or ["?"])]
            return {"ok": False,
                    "reason": _i18n_t("mgr.telegram_not_ready", lang,
                                      missing="; ".join(missing))}
        rc = cmd_telegram_test(cfg)
        if rc == 0:
            return {"ok": True,
                    "reason": _i18n_t("mgr.telegram_test_sent", lang)}
        return {"ok": False,
                "reason": _i18n_t("mgr.telegram_test_failed", lang)}

    # Static assets cua build React (/assets/*) — mount SAU cac route
    # /api/* de API luon thang.
    assets_dir = static_path / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)),
                  name="assets")
    elif static_path.is_dir():
        app.mount("/assets", StaticFiles(directory=str(static_path)),
                  name="assets")

    return app


try:
    app = create_app() if FastAPI is not None else None
except RuntimeError:
    app = None


def main(argv=None):
    """Entry: python -m diamondx10.webapi [--port 8000]
    [--host 127.0.0.1]."""
    parser = argparse.ArgumentParser(
        description="DiamondX10 WebAPI (FastAPI) — phuc vu WebUI + API.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="dia chi bind (mac dinh 127.0.0.1 — chi local)")
    parser.add_argument("--port", type=int, default=8000,
                        help="cong (mac dinh 8000)")
    args = parser.parse_args(argv)
    if FastAPI is None or app is None:
        print("LOI: FastAPI chua cai — chay: pip install fastapi uvicorn")
        return 1
    try:
        import uvicorn
    except ImportError:
        print("LOI: uvicorn chua cai — chay: pip install fastapi uvicorn")
        return 1
    print(f"DiamondX10 WebAPI: http://{args.host}:{args.port}/ "
          "(chi local, dang nhap bang ma OTP qua Telegram — "
          "dung mo cong ra ngoai)")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
