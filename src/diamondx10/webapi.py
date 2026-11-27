"""API backend FastAPI cho WebUI DiamondX10 (dx10).

Phuc vu build React (src/diamondx10/static) o / va JSON API o /api/*.

BAO MAT — chi local, KHONG co auth (giong dashboard chi doc):
  - Bind mac dinh 127.0.0.1, KHONG BAO GIO 0.0.0.0. Chi mo cong ra
    ngoai khi biet ro minh dang lam gi.
  - Khong co token / mat khau trong code hay response; moi lenh dat
    deu qua dung chan nhu nut Telegram (kill switch, demo-only, ky
    quy, do lech entry — xem listener.place_pending_order).
  - File briefing gui len Muse chi duoc doc trong thu muc briefings/
    (chan path traversal).

Quy tac chung:
  - Chuoi hien thi tieng Viet KHONG dau trong code, log va JSON.
  - Moi endpoint that bai sach (JSON error, khong traceback) khi
    thieu file state hay khong co MT5; MT5 tren Linux luon bao
    mt5_ok=false chu khong raise.
  - Config doc moi lan xu ly request (load_config) nen sua config
    khong can khoi dong lai server.
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
from datetime import datetime, timezone
from pathlib import Path

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    _FASTAPI_ERROR = None
except ImportError as exc:  # noqa: BLE001 — chay thieu fastapi thi bao ro
    FastAPI = None
    HTTPException = None
    FileResponse = None
    JSONResponse = None
    StaticFiles = None
    _FASTAPI_ERROR = exc

from . import killswitch, telegram
from .briefing import DESKS as BRIEFING_DESKS, build_briefing
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
from .data.providers import build_feed
from .listener import place_pending_order
from .models.quant import atr as _atr
from .models.quant import rsi as _rsi
from .pending import PendingOrderStore
from .signals import generate_signals
from .synthesis import (
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

# Registry tien trinh live / listener: {name: {"proc", "started", "mode"}}.
_PROCS = {}
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
    """Chay 1 tien trinh con (diem tiem cho test)."""
    env = os.environ.copy()
    src_dir = str(REPO_ROOT / "src")
    existing = env.get("PYTHONPATH") or ""
    env["PYTHONPATH"] = src_dir + (os.pathsep + existing if existing else "")
    return subprocess.Popen(
        argv, cwd=str(REPO_ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _start_proc(name, argv, mode):
    """Khoi dong tien trinh (neu chua chay). Tra (ok, reason)."""
    entry = _PROCS.get(name)
    if entry is not None and entry["proc"].poll() is None:
        return False, f"{name} da chay"
    try:
        proc = _spawn_proc(argv)
    except Exception as exc:  # noqa: BLE001 — khong chay duoc thi bao ro
        return False, f"khong khoi dong duoc {name}: {exc}"
    _PROCS[name] = {"proc": proc,
                    "started": datetime.now(timezone.utc).isoformat(),
                    "mode": mode}
    time.sleep(0.3)
    if proc.poll() is not None:
        return False, (f"{name} thoat ngay (ma {proc.returncode}) — "
                       "kiem tra config / MT5 / log")
    return True, f"da khoi dong {name}"


def _stop_proc(name):
    """Dung tien trinh (neu chay). Tra True neu da dung / khong chay."""
    entry = _PROCS.get(name)
    if entry is None:
        return True
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

    @app.exception_handler(Exception)
    async def _unhandled(request, exc):  # noqa: ARG001
        # Moi loi bat ngo deu tra JSON sach, khong traceback.
        print(f"LOI webapi: {exc}")
        return JSONResponse(status_code=500,
                            content={"detail": f"loi server: {exc}"})

    @app.get("/")
    def index():
        index_path = static_path / "index.html"
        if index_path.is_file():
            return FileResponse(str(index_path))
        return {"message": "frontend chua duoc build — API van hoat dong",
                "api": "/api/status"}

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
                status_code=400, detail="truong 'on' phai la true/false")
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
        if mode not in ("recommend", "auto"):
            return {"ok": False,
                    "reason": "mode khong hop le (chon recommend | auto)"}
        argv = [sys.executable, "-m", "diamondx10", "live",
                "--desk", desk]
        if mode == "recommend":
            argv.append("--recommend-only")
        ok, reason = _start_proc("live", argv, mode)
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
          "(chi local, khong co auth — dung mo cong ra ngoai)")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
