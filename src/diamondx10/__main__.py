"""CLI entry: python3 -m diamondx10 demo | backtest | signals | compare
| sweep | import-bars | mt5-dry-run | mt5-trade | mt5-symbols
| backfill | export-bars | live | telegram-listen | telegram-test
| briefing | verdict | synthesize | muse-setup | muse-send | muse-auto.
| live.

Lenh mt5-* va live CHI dung voi tai khoan DEMO (Exness demo + MT5 terminal).
Xem docs/mt5-demo.md va docs/live-loop.md truoc khi chay.
Lenh backfill / export-bars lay nen OHLC tu MT5 vao kho SQLite local
(xem docs/history-store.md); tren may khong co MT5 thi bao loi sach.
"""
import argparse
import csv
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .backtest import (
    compare_strategies,
    format_backtest_report,
    format_strategy_comparison,
    format_sweep_report,
    format_walk_forward_report,
    run_backtest,
    run_backtest_from_history,
    run_walk_forward,
    run_walk_forward_from_history,
    sweep_params,
)
from . import audit as audit_mod
from .briefing import DESKS as BRIEFING_DESKS
from .briefing import build_briefing, cmd_briefing
from . import killswitch
from . import telegram as telegram_mod
from .data.csv_import import import_csv_bars
from .config import load_config
from .data.feeds import SimulatedFeed
from .data.history import HistoryStore
from .data.news import format_news_report, run_news
from .data.providers import build_feed
from .decisions import log_decision
from .execution import account_is_demo, check_symbols_available
from .muse_browser import (
    DEFAULT_WAIT_MIN,
    MuseBrowserError,
    send_briefing,
    wait_for_verdict,
)
from .muse_auto import cmd_muse_auto
from .live import (
    _maybe_send_alert,
    load_guard_and_positions,
    process_symbol,
    reconcile_symbol_positions,
    risk_pct_for_symbol,
    run_live_cycle,
    run_live_loop,
    save_guard_and_positions,
    split_desk_capital,
)
from .portfolio import Portfolio
from .report import build_report, format_report
from .signals import generate_signals
from .strategies import STRATEGIES, build_strategies, build_strategy
from .synthesis import cmd_synthesize, cmd_verdict


def _mt5_context(cfg, desk, symbol=None, mt5_module=None):
    """Tao MT5Feed + thong tin tai khoan; tra (feed, account_info, server)."""
    from .data.mt5_feed import load_mt5

    mt5 = load_mt5(mt5_module)
    feed = build_feed(cfg, desk, symbol=symbol, mt5_module=mt5_module)
    account = feed.account_info()
    server = (cfg.get("mt5") or {}).get("server") or ""
    return feed, mt5, account, server


def cmd_telegram_test(cfg):
    """Gui 1 tin nhan thu qua Telegram. Tra 0 neu gui duoc, 1 neu khong.

    Kiem tra tung muc truoc khi gui de bao ro thieu cai gi (chua bat
    enabled / thieu token / thieu chat_id) thay vi bao loi chung chung.
    """
    status = telegram_mod.setup_status(cfg)
    if not status["ready"]:
        print("Telegram CHUA SAN SANG — thieu:")
        for item in status["missing"]:
            print(f"  - {item}")
        print("Huong dan: docs/live-loop.md §4 (dat token vao bien moi "
              "truong DIAMONDX10_TELEGRAM_TOKEN, dien chat_id vao "
              "config.yaml local, bat telegram.enabled: true).")
        return 1
    ok = telegram_mod.send_message(
        telegram_mod.format_test_message(cfg=cfg), cfg=cfg)
    if ok:
        print("OK: tin nhan thu da gui toi Telegram — kiem tra chat nhan "
              "khuyen nghi.")
        return 0
    print("LOI: khong gui duoc tin thu (xem CANH BAO Telegram o tren) — "
          "kiem tra token/chat_id va mang.")
    return 1


def cmd_muse_setup():
    """Cai Playwright + Chromium cho lenh muse-send. Tra 0 neu xong,
    1 neu cai that (in huong dan, khong traceback).

    OPT-IN: khong goi tu quickstart — user tu chay khi muon dung
    trinh duyet Muse.
    """
    print("Cai Playwright + Chromium cho Muse browser ...")
    try:
        pip = subprocess.run(
            [sys.executable, "-m", "pip", "install", "playwright"])
    except OSError as exc:
        print(f"LOI: khong chay duoc pip: {exc}")
        print("Huong dan: cai Python 3.10+ roi chay lai "
              "python -m diamondx10 muse-setup")
        return 1
    if pip.returncode != 0:
        print("LOI: pip install playwright that bai (xem loi pip o tren).")
        print("Huong dan: kiem tra mang / quyen ghi, roi chay lai "
              "python -m diamondx10 muse-setup")
        return 1
    try:
        browser = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"])
    except OSError as exc:
        print(f"LOI: khong chay duoc playwright: {exc}")
        return 1
    if browser.returncode != 0:
        print("LOI: playwright install chromium that bai (xem loi o tren).")
        print("Huong dan: kiem tra mang roi chay lai "
              "python -m diamondx10 muse-setup")
        return 1
    print("OK: da cai Playwright + Chromium.")
    print("Buoc tiep theo:")
    print("  1. Chay headed 1 lan de dang nhap (khong --headless):")
    print("       python -m diamondx10 muse-send --file "
          "briefings/briefing-forex-<ngay>.md --no-wait")
    print("  2. Dang nhap vao muse.ai TAY trong cua so trinh duyet mo ra")
    print("     (khong nhap mat khau vao tool), mo chat chinh cua Muse.")
    print("  3. Chay lai muse-send (khong --no-wait) de gui briefing va "
          "doi verdict.")
    return 0


def cmd_muse_send(cfg, file, prompt=None, headless=None, wait_min=None,
                  no_wait=False, *, driver=None):
    """Gui briefing len chat Muse, mac dinh doi verdict roi luu.

    Tra 0 chi khi verdict da luu, hoac --no-wait ma gui thanh cong;
    tra 1 neu gui that / het thoi gian cho verdict (in ly do +
    huong dan fallback tay). driver: diem tiem trinh duyet cho test.
    """
    path = Path(file)
    if not path.exists():
        print(f"LOI: khong tim thay file {file}")
        return 1
    try:
        result = send_briefing(str(path), cfg, prompt=prompt,
                               headless=headless, driver=driver)
    except MuseBrowserError as exc:
        print(f"LOI: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 — lenh CLI khong traceback
        print(f"LOI: khong gui duoc briefing ({exc})")
        return 1
    if not result.get("sent"):
        print(f"LOI: {result.get('message') or 'khong gui duoc briefing.'}")
        return 1
    print(f"OK: {result.get('message')} ({result.get('url') or ''})")
    if no_wait:
        print("Khong cho verdict (--no-wait).")
        return 0
    muse_cfg = (cfg or {}).get("muse") or {}
    wait = (int(wait_min) if wait_min is not None
            else int(muse_cfg.get("wait_min") or DEFAULT_WAIT_MIN))
    print(f"Cho verdict toi da {wait} phut ...")
    verdict = wait_for_verdict(cfg, timeout_min=wait, driver=driver)
    if verdict is None:
        print("Chua luu duoc verdict — xem huong dan fallback tay o tren.")
        return 1
    print(f"OK: verdict da luu — desk {verdict['desk']} — "
          f"direction {verdict['direction']} "
          f"(tin cay {verdict['confidence']:g})")
    return 0


def _cmd_briefing_send(cfg, desk="forex", days=3, all_desks=False, *,
                       driver=None):
    """`briefing --send`: tao briefing nhu binh thuong roi gui tung
    file len chat Muse. File briefing da ghi xong truoc khi gui; neu
    gui that thi in ly do, noi ro file da ghi, tra 1."""
    desks = list(BRIEFING_DESKS) if all_desks else [desk]
    try:
        results = [build_briefing(cfg, d, days) for d in desks]
    except (ValueError, ImportError, ConnectionError, OSError) as exc:
        print(f"LOI: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 — lenh CLI khong traceback
        print(f"LOI: khong tao duoc briefing ({exc})")
        return 1
    for result in results:
        print(f"OK: briefing {result['desk']} cho {result['analyst']}")
        print(f"  MD: {result['md_path']}")
        print(f"  JSON: {result['json_path']}")
    for result in results:
        try:
            sent = send_briefing(result["md_path"], cfg, driver=driver)
        except MuseBrowserError as exc:
            print(f"LOI: khong gui duoc briefing {result['desk']}: {exc}")
            print("Briefing da ghi ra file (xem duong dan o tren) — gui "
                  "tay hoac chay: python -m diamondx10 muse-send --file "
                  f"{result['md_path']}")
            return 1
        except Exception as exc:  # noqa: BLE001 — lenh CLI khong traceback
            print(f"LOI: khong gui duoc briefing {result['desk']}: {exc}")
            print("Briefing da ghi ra file (xem duong dan o tren).")
            return 1
        if not sent.get("sent"):
            print(f"LOI: khong gui duoc briefing {result['desk']}: "
                  f"{sent.get('message')}")
            print("Briefing da ghi ra file (xem duong dan o tren) — gui "
                  "tay hoac chay: python -m diamondx10 muse-send --file "
                  f"{result['md_path']}")
            return 1
        print(f"OK: da gui briefing {result['desk']} toi Muse "
              f"({sent.get('url') or ''})")
    return 0


def _desk_symbols(cfg, desk, symbol):
    """Tat ca symbol cua desk; --symbol thi chi lay 1 symbol do."""
    if symbol:
        return [symbol]
    symbols = (cfg.get("data", {}).get("symbols", {}) or {}).get(desk) or []
    if not symbols:
        raise ValueError(f"Chua cau hinh symbol cho desk {desk!r} trong config.yaml")
    return list(symbols)


# --- Phase A: kho nen OHLC local (SQLite) + backfill/export ---

# Khung nen backfill/export ho tro (it nhat M15, H1, D1 — Phase A).
SUPPORTED_TIMEFRAMES = {"M1", "M5", "M15", "H1", "D1"}
TIMEFRAME_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "D1": 1440}
DEFAULT_HISTORY = {"db_path": "data/history.db",
                   "default_timeframe": "M15", "backfill_days": 90}
# Thu muc xuat CSV mac dinh (goc repo, da gitignore).
DEFAULT_EXPORT_DIR = Path(__file__).resolve().parents[2] / "data" / "exports"


def _history_cfg(cfg):
    """Muc `history:` trong config, gop voi mac dinh Phase A."""
    merged = dict(DEFAULT_HISTORY)
    merged.update((cfg or {}).get("history") or {})
    return merged


def _history_store(cfg):
    """Mo kho nen theo config (history.db_path, mac dinh data/history.db)."""
    return HistoryStore(_history_cfg(cfg).get("db_path")
                        or DEFAULT_HISTORY["db_path"])


def _load_bars_by_symbol(cfg, desk, symbols, timeframe):
    """Doc bar that cua cac symbol tu kho lich su (cho --source history)."""
    symbols = symbols or _desk_symbols(cfg, desk, None)
    out = {}
    with _history_store(cfg) as store:
        for symbol in symbols:
            bars = store.get_bars(symbol, timeframe)
            if not bars:
                raise ValueError(
                    f"Kho lich su chua co bar nao cho {symbol} ({timeframe}) — "
                    "chay backfill / import-bars truoc.")
            out[symbol] = bars
    return out


def _all_symbols(cfg):
    """Tat ca symbol cua ca 4 desk, theo thu tu trong config."""
    symbols = []
    for desk_syms in ((cfg or {}).get("data", {}).get("symbols", {})
                      or {}).values():
        for s in desk_syms or []:
            if s not in symbols:
                symbols.append(s)
    return symbols


def _resolve_history_symbols(cfg, desk, symbol):
    """Symbol cho backfill/export: --symbol > --desk > tat ca desk."""
    if symbol:
        return [symbol]
    if desk:
        return _desk_symbols(cfg, desk, None)
    symbols = _all_symbols(cfg)
    if not symbols:
        raise ValueError("Chua cau hinh symbol nao trong config.yaml "
                         "(data.symbols)")
    return symbols


def _desk_for_symbol(cfg, symbol):
    """Desk chua symbol do (de lay SimulatedFeed theo desk); None neu khong co."""
    for desk, syms in ((cfg or {}).get("data", {}).get("symbols", {})
                       or {}).items():
        if symbol in (syms or []):
            return desk
    return None


def _iso_utc(epoch):
    """Epoch UTC -> ISO UTC, vd 2026-11-27T00:00:00Z (cot time cua CSV)."""
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _mt5_feed_for_symbol(cfg, symbol, mt5_module=None):
    """Tao MT5Feed cho 1 symbol, EP provider thanh 'mt5' (backfill /
    export luon lay tu MT5 that, khong phu thuoc provider trong config).

    Tren may khong co goi MetaTrader5 thi ImportError voi huong dan ro
    rang (khong traceback) — giong lenh mt5-symbols.
    """
    cfg_mt5 = dict(cfg or {})
    data_cfg = dict((cfg or {}).get("data") or {})
    data_cfg["provider"] = "mt5"
    cfg_mt5["data"] = data_cfg
    return build_feed(cfg_mt5, "forex", symbol=symbol,
                      mt5_module=mt5_module)


def _close_feed(feed):
    """Dong feed neu co close() (MT5Feed.shutdown); loi dong thi bo qua."""
    close = getattr(feed, "close", None)
    if callable(close):
        try:
            close()
        except Exception:  # noqa: BLE001 — dong feed khong duoc thi thoi
            pass


def run_backfill(cfg, symbols, timeframe, days, store=None,
                 feed_factory=None, mt5_module=None, now=None):
    """Backfill nen MT5 vao kho lich su.

    symbols: list symbol; timeframe: 'M15'/'H1'/'D1'...; days: so ngay
    gan nhat tinh den `now` (mac dinh: bay gio, UTC).
    feed_factory: ham (symbol) -> feed co bars_range(timeframe, start,
    end) — chi dung cho test (truyen feed gia); khong truyen thi dung
    MT5Feed that. Tra {"results": [...], "total_bars": int,
    "failed": int}. Loi MT5 chua cai (ImportError) thi raise de main()
    bao loi sach 1 lan; loi rieng 1 symbol (mat ket noi, symbol khong
    co) thi in LOI va chay tiep symbol khac.
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"Khung thoi gian khong ho tro: {timeframe!r} "
            f"(chon trong {sorted(SUPPORTED_TIMEFRAMES)})")
    if int(days) <= 0:
        raise ValueError(f"--days phai > 0 (nhan {days!r})")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start = now - timedelta(days=int(days))
    own_store = store is None
    store = store or _history_store(cfg)
    results, failed, total = [], 0, 0
    try:
        for symbol in symbols:
            try:
                feed = (feed_factory(symbol) if feed_factory is not None
                        else _mt5_feed_for_symbol(cfg, symbol, mt5_module))
            except ImportError:
                raise
            except (ConnectionError, ValueError) as exc:
                print(f"LOI ({symbol}): {exc}")
                failed += 1
                continue
            try:
                bars = feed.bars_range(timeframe, start, now)
            except (ConnectionError, ValueError) as exc:
                print(f"LOI ({symbol}): {exc}")
                failed += 1
                continue
            finally:
                _close_feed(feed)
            saved = store.upsert_bars(symbol, timeframe, bars)
            total += saved
            results.append({"symbol": symbol, "fetched": len(bars),
                            "saved": saved,
                            "start": bars[0]["time"] if bars else None,
                            "end": bars[-1]["time"] if bars else None})
            print(f"{symbol}: lay {len(bars)} bar {timeframe} "
                  f"({_iso_utc(start.timestamp())}..{_iso_utc(now.timestamp())}), "
                  f"luu {saved} bar vao kho ({store.path})")
    finally:
        if own_store:
            store.close()
    return {"results": results, "total_bars": total, "failed": failed}


def _retime_simulated_bars(bars, timeframe, end):
    """Gan lai moc thoi gian cho bar mo phong (SimulatedFeed dung
    time 0..499 khong phai epoch): bar cuoi o `end`, cac bar truoc
    cach nhau 1 khung nen. Chi dung cho export --from simulated."""
    step = TIMEFRAME_MINUTES[timeframe] * 60
    end_epoch = int(end.timestamp())
    out = []
    for i, bar in enumerate(bars):
        new_bar = dict(bar)
        new_bar["time"] = end_epoch - (len(bars) - 1 - i) * step
        new_bar.setdefault("volume", 0.0)
        out.append(new_bar)
    return out


def _write_bars_csv(path, bars):
    """Ghi 1 file CSV: cot time,open,high,low,close,volume;
    time la ISO UTC (vd 2026-11-27T00:00:00Z)."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "open", "high", "low", "close", "volume"])
        for bar in bars:
            writer.writerow([_iso_utc(bar["time"]), bar["open"],
                             bar["high"], bar["low"], bar["close"],
                             bar.get("volume") or 0.0])


def run_export_bars(cfg, symbols, timeframe, days, out_dir, source,
                    store=None, feed_factory=None, mt5_module=None,
                    now=None):
    """Xuat nen ra CSV, 1 file / symbol: {SYMBOL}_{TIMEFRAME}.csv.

    source: 'store' (mac dinh — lay tu kho; symbol nao chua co bar
    trong kho thi thu keo tu MT5 live roi luu vao kho), 'mt5' (luon
    keo tu MT5 live roi luu vao kho), 'simulated' (du lieu mo phong —
    chi khi user truyen ro, de demo/test). Tra {"results": [...],
    "failed": int}; moi ket qua ghi ro nguon du lieu (store / mt5 /
    mt5 (fallback) / simulated). ImportError (MT5 chua cai) thi raise
    khi source='mt5'; o che do store thi chi canh bao tung symbol.
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"Khung thoi gian khong ho tro: {timeframe!r} "
            f"(chon trong {sorted(SUPPORTED_TIMEFRAMES)})")
    if source not in ("store", "mt5", "simulated"):
        raise ValueError(f"--from khong hop le: {source!r} "
                         "(chon store | mt5 | simulated)")
    if int(days) <= 0:
        raise ValueError(f"--days phai > 0 (nhan {days!r})")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start = now - timedelta(days=int(days))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # Chi mo kho khi can (store/mt5); --from simulated khong dong
    # den file data/history.db.
    own_store = False
    if source in ("store", "mt5") and store is None:
        store = _history_store(cfg)
        own_store = True
    results, failed = [], 0
    try:
        for symbol in symbols:
            bars, actual_source = [], source
            if source == "simulated":
                desk = _desk_for_symbol(cfg, symbol) or "forex"
                raw = SimulatedFeed(desk).bars(500)
                bars = _retime_simulated_bars(raw, timeframe, now)
            else:
                if source == "store":
                    bars = store.get_bars(symbol, timeframe, start=start,
                                          end=now)
                if source == "mt5" or not bars:
                    # 'mt5': luon keo live. 'store': kho trong thi
                    # fallback keo MT5 live 1 lan roi luu vao kho.
                    try:
                        feed = (feed_factory(symbol)
                                if feed_factory is not None
                                else _mt5_feed_for_symbol(cfg, symbol,
                                                          mt5_module))
                    except ImportError:
                        if source == "mt5":
                            raise
                        print(f"CANH BAO ({symbol}): kho chua co bar ma "
                              "MT5 chua cai — bo qua symbol nay.")
                        failed += 1
                        continue
                    except (ConnectionError, ValueError) as exc:
                        print(f"CANH BAO ({symbol}): {exc} — bo qua "
                              "symbol nay.")
                        failed += 1
                        continue
                    try:
                        bars = feed.bars_range(timeframe, start, now)
                    except (ConnectionError, ValueError) as exc:
                        print(f"CANH BAO ({symbol}): {exc} — bo qua "
                              "symbol nay.")
                        failed += 1
                        continue
                    finally:
                        _close_feed(feed)
                    store.upsert_bars(symbol, timeframe, bars)
                    actual_source = ("mt5" if source == "mt5"
                                     else "mt5 (fallback)")
            if not bars:
                print(f"CANH BAO ({symbol}): khong co bar nao — bo qua.")
                failed += 1
                continue
            path = out / f"{symbol}_{timeframe}.csv"
            _write_bars_csv(path, bars)
            results.append({"symbol": symbol, "bars": len(bars),
                            "start": bars[0]["time"], "end": bars[-1]["time"],
                            "source": actual_source, "path": str(path)})
            print(f"{symbol}: {len(bars)} bar {timeframe}, "
                  f"{_iso_utc(bars[0]['time'])}..{_iso_utc(bars[-1]['time'])}, "
                  f"nguon: {actual_source} -> {path}")
    finally:
        if own_store:
            store.close()
    return {"results": results, "failed": failed}


def stop_and_target(entry, action, sl_pct, tp_pct):
    """Tinh stop loss va take profit theo % gia vao.
    BUY: SL duoi gia, TP tren gia. SELL: nguoc lai. Tra (sl, tp)."""
    if action == "BUY":
        return entry * (1 - sl_pct), entry * (1 + tp_pct)
    return entry * (1 + sl_pct), entry * (1 - tp_pct)


# --- Phase 4: risk enforcement (drawdown, margin, daily limit, no-trade) ---
# Cai dat that nam o live.py (de ca lenh mt5-trade va vong lap live dung
# chung 1 duong xu ly); day chi la ten goi cu giu cho code cu.
# split_desk_capital / risk_pct_for_symbol cung import tu live.py o tren.


def _load_guard_and_positions(cfg):
    """Doc trang thai von/vi the (xem live.load_guard_and_positions)."""
    return load_guard_and_positions(cfg)


def _save_guard_and_positions(guard, positions):
    save_guard_and_positions(guard, positions)


def _reconcile_for_symbol(cfg, desk, symbol, bars, strat, guard, positions,
                          mt5, manager):
    """Doi chieu vi the mo (xem live.reconcile_symbol_positions)."""
    return reconcile_symbol_positions(cfg, desk, symbol, bars, strat, guard,
                                      positions, mt5, manager)


def main(argv=None):
    p = argparse.ArgumentParser(prog="diamondx10")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="chay demo voi du lieu mo phong")
    b = sub.add_parser("backtest", help="backtest co P&L that (mo phong)")
    b.add_argument("--desk", default="forex")
    b.add_argument("--days", type=int, default=30)
    b.add_argument("--split", type=float, default=0.7,
                   help="ty le train cho tach in-sample/out-of-sample (mac dinh 0.7)")
    b.add_argument("--symbol", default=None,
                   help="chi backtest 1 symbol cua desk (mac dinh: tat ca)")
    b.add_argument("--strategy", default="default",
                   help="chien luoc: default (quy tac chung da chot) | "
                        "donchian (breakout Donchian, CHI DE SO SANH)")
    b.add_argument("--walk-forward", action="store_true",
                   help="kiem dinh walk-forward: nhieu cua so train/test "
                        "lan luot thay cho 1 lan tach train/test")
    b.add_argument("--train-bars", type=int, default=30,
                   help="so bar train moi cua so walk-forward (mac dinh 30 "
                        "cho demo; kiem dinh that: --days 120 "
                        "--train-bars 60 --test-bars 20)")
    b.add_argument("--test-bars", type=int, default=10,
                   help="so bar test moi cua so walk-forward (mac dinh 10)")
    b.add_argument("--step-bars", type=int, default=10,
                   help="buoc truot giua cac cua so (mac dinh 10)")
    b.add_argument("--source", default="simulated",
                   choices=["simulated", "history"],
                   help="nguon bar: simulated (mac dinh) | history "
                        "(nen that tu kho lich su Phase A/C)")
    b.add_argument("--timeframe", default="M15",
                   help="khung nen khi --source history (mac dinh M15)")
    c = sub.add_parser("compare",
                       help="so sanh chien luoc bang walk-forward, "
                            "chi tinh OOS (mo phong)")
    c.add_argument("--desk", default="forex")
    c.add_argument("--strategies", nargs="+", default=["default", "donchian"],
                   help="ten chien luoc trong registry (mac dinh: "
                        "default donchian)")
    c.add_argument("--days", type=int, default=120)
    c.add_argument("--symbol", default=None)
    c.add_argument("--train-bars", type=int, default=60)
    c.add_argument("--test-bars", type=int, default=20)
    c.add_argument("--step-bars", type=int, default=20)
    c.add_argument("--source", default="simulated",
                   choices=["simulated", "history"],
                   help="nguon bar: simulated (mac dinh) | history "
                        "(nen that tu kho lich su)")
    c.add_argument("--timeframe", default="M15",
                   help="khung nen khi --source history (mac dinh M15)")
    w = sub.add_parser("sweep",
                       help="quet luoi tham so, xep hang CHI theo OOS "
                            "(nghien cuu, mo phong)")
    w.add_argument("--desk", default="forex")
    w.add_argument("--strategy", default="default",
                   help="chien luoc trong registry (mac dinh: default)")
    w.add_argument("--days", type=int, default=120)
    w.add_argument("--symbol", default=None)
    w.add_argument("--train-bars", type=int, default=60)
    w.add_argument("--test-bars", type=int, default=20)
    w.add_argument("--step-bars", type=int, default=20)
    w.add_argument("--source", default="simulated",
                   choices=["simulated", "history"],
                   help="nguon bar: simulated (mac dinh) | history "
                        "(nen that tu kho lich su)")
    w.add_argument("--timeframe", default="M15",
                   help="khung nen khi --source history (mac dinh M15)")
    ib = sub.add_parser("import-bars",
                        help="nhap file CSV do export-bars xuat vao kho "
                             "lich su (de backtest tren du lieu that)")
    ib.add_argument("--file", required=True,
                    help="duong dan file CSV (dinh dang export-bars)")
    ib.add_argument("--symbol", required=True,
                    help="symbol cua file CSV (vd EURUSD)")
    ib.add_argument("--timeframe", default="M15")
    n = sub.add_parser("news",
                       help="lay tin thi truong theo desk (RSS, chi doc, "
                            "khong dat lenh)")
    n.add_argument("--desk", default=None,
                   help="chi lay tin desk nay (mac dinh: tat ca)")
    n.add_argument("--days", type=int, default=2,
                   help="chi lay tin trong N ngay gan nhat (mac dinh 2)")
    n.add_argument("--all", action="store_true",
                   help="hien ca tin da xem truoc do (khong loc dedup)")
    s = sub.add_parser("signals", help="in tin hieu hien tai (mo phong)")
    s.add_argument("--desk", default="forex")
    rep = sub.add_parser("report",
                         help="bao cao hang ngay: von, drawdown, vi the mo, "
                              "lenh hom nay, cac lan bi chan (doc decisions log)")
    rep.add_argument("--save", default=None, metavar="PATH",
                     help="ghi bao cao ra file thay vi in stdout; tao thu "
                          "muc cha neu can (xem docs/fund-risk-ops.md)")
    k = sub.add_parser("kill-switch",
                       help="nut dung khan cap: on (bat) | off (tat) | "
                            "status (xem trang thai) — xem docs/fund-risk-ops.md")
    k.add_argument("action", choices=["on", "off", "status"],
                   help="on: bat (khong mo lenh moi nua); off: tat; "
                        "status: chi in trang thai")
    k.add_argument("--reason", default="",
                   help="ly do bat kill switch (chi dung voi on)")
    k.add_argument("--by", default="operator",
                   help="ai bat/tat (mac dinh: operator)")
    a = sub.add_parser("audit",
                       help="in N dong audit gan nhat (moi nhat len dau)")
    a.add_argument("--lines", type=int, default=10,
                   help="so dong gan nhat (mac dinh 10)")
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
    t.add_argument("--recommend-only", action="store_true",
                   help="chi gui khuyen nghi Telegram kem nut Dat lenh, "
                        "KHONG tu dat lenh (xem docs/live-loop.md §6)")
    v = sub.add_parser("live",
                       help="DEMO: vong lap live M15 — tin hieu + lenh DEMO "
                            "+ canh bao Telegram (xem docs/live-loop.md)")
    v.add_argument("--desk", default="forex")
    v.add_argument("--symbol", default=None,
                   help="chi chay 1 symbol cua desk (mac dinh: tat ca)")
    v.add_argument("--timeframe", default=None,
                   help="khung nen: M15, H1, D1... (mac dinh: muc live.timeframe "
                        "trong config, neu khong co thi M15)")
    v.add_argument("--once", action="store_true",
                   help="chi chay 1 chu ky roi thoat (dung cho Task Scheduler / "
                        "cron + test)")
    v.add_argument("--interval-min", type=int, default=None,
                   help="so phut giua 2 chu ky o che do lap (mac dinh: muc "
                        "live.interval_min trong config, neu khong co thi 15)")
    v.add_argument("--max-cycles", type=int, default=None,
                   help="so chu ky toi da o che do lap (de test/dung; "
                        "khong truyen thi chay mai toi khi Ctrl+C)")
    v.add_argument("--recommend-only", action="store_true",
                   help="chi gui khuyen nghi Telegram kem nut Dat lenh, "
                        "KHONG tu dat lenh (xem docs/live-loop.md §6)")
    tt = sub.add_parser("telegram-test",
                        help="Gui 1 tin nhan thu qua Telegram de kiem tra "
                             "ket noi bot (xem docs/live-loop.md §4)")
    tl = sub.add_parser("telegram-listen",
                        help="Nhan nut bam Dat lenh / Bo qua tren Telegram "
                             "va dat lenh DEMO theo lenh cho (xem "
                             "docs/live-loop.md §6)")
    tl.add_argument("--interval-sec", type=int, default=5,
                    help="so giay cho giua 2 dot long-poll (mac dinh 5)")
    tl.add_argument("--once", action="store_true",
                    help="chi xu ly 1 dot getUpdates roi thoat")
    br = sub.add_parser("briefing",
                        help="tao briefing phan tich truoc phien (md + json) "
                             "cho 1 desk hoac tat ca 4 desk")
    br.add_argument("--desk", default="forex",
                    help="desk: forex | xauusd | crypto | us_securities "
                         "(mac dinh: forex)")
    br.add_argument("--days", type=int, default=3,
                    help="chi lay tin trong N ngay gan nhat (mac dinh 3)")
    br.add_argument("--all", action="store_true",
                    help="tao briefing cho tat ca 4 desk")
    br.add_argument("--send", action="store_true",
                    help="sau khi tao briefing thi gui tung file len chat "
                         "Muse (can Playwright — chay muse-setup truoc)")
    ms = sub.add_parser("muse-setup",
                        help="cai Playwright + Chromium de gui briefing "
                             "len chat Muse (chay 1 lan)")
    md = sub.add_parser("muse-send",
                        help="gui file briefing len chat Muse va doi "
                             "verdict JSON (can Playwright — chay muse-setup "
                             "truoc)")
    md.add_argument("--file", required=True,
                    help="duong dan file briefing .md can gui")
    md.add_argument("--prompt", default=None,
                    help="prompt gui kem file (mac dinh: nho Muse phan "
                         "tich nhu analyst va tra verdict JSON theo mau "
                         "trong briefing)")
    md.add_argument("--headless", action="store_true", default=None,
                    help="chay trinh duyet an (mac dinh: mo cua so de "
                         "user nhin thay / dang nhap)")
    md.add_argument("--wait-min", type=int, default=None,
                    help="so phut doi verdict toi da (mac dinh: muc "
                         "muse.wait_min trong config, neu khong co thi 10)")
    md.add_argument("--no-wait", action="store_true",
                    help="chi gui, khong doi verdict")
    ma = sub.add_parser("muse-auto",
                        help="chu ky PTCB tu dong: tao briefing -> gui "
                             "Muse -> doi verdict cho 1 desk hoac tat ca "
                             "(chay dinh ky bang Task Scheduler, xem "
                             "docs/muse-browser.md §8)")
    ma.add_argument("--desk", default=None,
                    help="desk: forex | xauusd | crypto | us_securities "
                         "(mac dinh: tat ca, nhu --all)")
    ma.add_argument("--all", action="store_true",
                    help="chay cho tat ca 4 desk (mac dinh khi khong "
                         "truyen --desk)")
    ma.add_argument("--wait-min", type=int, default=None,
                    help="so phut doi verdict toi da moi desk (mac dinh: "
                         "muc muse.wait_min trong config, neu khong co "
                         "thi 10)")
    ma.add_argument("--headless", action="store_true", default=True,
                    help="chay trinh duyet an (mac dinh cho chay dinh ky "
                         "— Task Scheduler khong co desktop tuong tac)")
    ma.add_argument("--headed", dest="headless", action="store_false",
                    help="mo cua so trinh duyet that (dung khi dang nhap "
                         "lan dau hoac muon nhin thay)")
    vd = sub.add_parser("verdict",
                        help="luu nhan dinh co ban (PTCB) cua 1 desk tu file JSON")
    vd.add_argument("--file", required=True,
                    help="duong dan file JSON chua 1 nhan dinh hoac "
                         '{"verdicts": [...]}')
    sy = sub.add_parser("synthesize",
                        help="tong hop Yuling: PTKT + PTCB moi nhat -> khuyen nghi")
    sy.add_argument("--desk", default="forex")
    sy.add_argument("--symbol", default=None,
                    help="chi tong hop 1 symbol cua desk (mac dinh: tat ca)")
    y = sub.add_parser("mt5-symbols",
                       help="DEMO: kiem tra symbol nao co tren server MT5 demo")
    y.add_argument("--desk", default=None)
    bf = sub.add_parser("backfill",
                        help="DEMO: keo nen OHLC tu MT5 demo vao kho SQLite "
                             "local (data/history.db)")
    bf.add_argument("--desk", default=None,
                    help="chi backfill desk nay (mac dinh: tat ca desk)")
    bf.add_argument("--symbol", default=None,
                    help="chi backfill 1 symbol")
    bf.add_argument("--timeframe", default=None,
                    help="khung nen: M15, H1, D1 (mac dinh: "
                         "history.default_timeframe trong config)")
    bf.add_argument("--days", type=int, default=None,
                    help="so ngay gan nhat (mac dinh: history.backfill_days)")
    e = sub.add_parser("export-bars",
                       help="xuat nen OHLC ra CSV (1 file / symbol) de "
                            "backtest / gui cho Muse")
    e.add_argument("--desk", default=None)
    e.add_argument("--symbol", default=None)
    e.add_argument("--timeframe", default=None,
                   help="khung nen: M15, H1, D1 (mac dinh: "
                        "history.default_timeframe trong config)")
    e.add_argument("--days", type=int, default=None,
                   help="so ngay gan nhat (mac dinh: history.backfill_days)")
    e.add_argument("--out", default=None,
                   help="thu muc xuat CSV (mac dinh data/exports/)")
    e.add_argument("--from", dest="source",
                   choices=["store", "mt5", "simulated"], default="store",
                   help="nguon du lieu: store (mac dinh — tu kho, thieu "
                        "thi keo MT5), mt5 (luon keo live), simulated "
                        "(mo phong, chi de demo/test)")
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
        try:
            if args.source == "history":
                with _history_store(cfg) as store:
                    if args.walk_forward:
                        result = run_walk_forward_from_history(
                            args.desk, cfg,
                            symbols=[args.symbol] if args.symbol else None,
                            timeframe=args.timeframe,
                            train_bars=args.train_bars,
                            test_bars=args.test_bars,
                            step_bars=args.step_bars,
                            strategy_name=args.strategy, store=store)
                        print(format_walk_forward_report(result))
                    else:
                        result = run_backtest_from_history(
                            args.desk, cfg,
                            symbols=[args.symbol] if args.symbol else None,
                            timeframe=args.timeframe,
                            train_fraction=args.split,
                            strategy_name=args.strategy, store=store)
                        print(format_backtest_report(result))
            elif args.walk_forward:
                result = run_walk_forward(
                    args.desk, args.days, cfg=cfg,
                    symbols=[args.symbol] if args.symbol else None,
                    train_bars=args.train_bars, test_bars=args.test_bars,
                    step_bars=args.step_bars,
                    strategy_name=args.strategy)
                print(format_walk_forward_report(result))
            else:
                result = run_backtest(
                    args.desk, args.days, cfg=cfg,
                    symbols=[args.symbol] if args.symbol else None,
                    train_fraction=args.split,
                    strategy_name=args.strategy)
                print(format_backtest_report(result))
        except ValueError as exc:
            print(f"LOI: {exc}")
            return 1
    elif args.cmd == "compare":
        try:
            bars_by_symbol = None
            if args.source == "history":
                bars_by_symbol = _load_bars_by_symbol(
                    cfg, args.desk,
                    [args.symbol] if args.symbol else None, args.timeframe)
            comp = compare_strategies(
                args.desk, args.strategies, days=args.days, cfg=cfg,
                symbols=[args.symbol] if args.symbol else None,
                train_bars=args.train_bars, test_bars=args.test_bars,
                step_bars=args.step_bars, bars_by_symbol=bars_by_symbol)
            print(format_strategy_comparison(comp))
        except ValueError as exc:
            print(f"LOI: {exc}")
            return 1
    elif args.cmd == "sweep":
        try:
            if args.source == "history":
                bars_by_symbol = _load_bars_by_symbol(
                    cfg, args.desk,
                    [args.symbol] if args.symbol else None, args.timeframe)
                sw = sweep_params(
                    args.desk, None, args.strategy, cfg=cfg,
                    symbols=[args.symbol] if args.symbol else None,
                    train_bars=args.train_bars, test_bars=args.test_bars,
                    step_bars=args.step_bars,
                    bars_by_symbol=bars_by_symbol)
            else:
                bars = SimulatedFeed(args.desk).bars(args.days)
                sw = sweep_params(
                    args.desk, bars, args.strategy, cfg=cfg,
                    symbols=[args.symbol] if args.symbol else None,
                    train_bars=args.train_bars, test_bars=args.test_bars,
                    step_bars=args.step_bars)
            print(format_sweep_report(sw))
        except ValueError as exc:
            print(f"LOI: {exc}")
            return 1
    elif args.cmd == "import-bars":
        try:
            with _history_store(cfg) as store:
                result = import_csv_bars(store, args.file, args.symbol,
                                         args.timeframe)
            print(f"OK: nhap {result['imported']}/{result['total_rows']} bar "
                  f"({result['skipped']} trung bo qua) cho {args.symbol} "
                  f"({args.timeframe}) tu {args.file}.")
            print(f"Khoang thoi gian: {result['start']} -> {result['end']}.")
        except (ValueError, FileNotFoundError, OSError) as exc:
            print(f"LOI: {exc}")
            return 1
    elif args.cmd == "news":
        news_cfg = cfg.get("news") or {}
        if not (news_cfg.get("sources") or []):
            print("Chua cau hinh nguon tin (muc 'news' trong "
                  "config.yaml). Xem config.example.yaml va "
                  "docs/market-news.md.")
            return 1
        result = run_news(news_cfg, desk=args.desk,
                          max_age_days=args.days, include_seen=args.all)
        print(format_news_report(result, desk=args.desk))
    elif args.cmd == "signals":
        feed = SimulatedFeed(args.desk)
        print(generate_signals(args.desk, feed.bars(60)))
    elif args.cmd == "report":
        rep = build_report(cfg)
        text = format_report(rep)
        if args.save:
            path = Path(args.save)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text + "\n", encoding="utf-8")
            audit_mod.log_event(
                "REPORT_GENERATED",
                {"path": str(path), "date": rep["date"]})
            print(f"Da ghi bao cao ra {path}")
        else:
            print(text)
    elif args.cmd == "kill-switch":
        if args.action == "on":
            st = killswitch.engage(
                args.reason or "kill switch bat bang tay", by=args.by)
            print(f"Kill switch: BAT — ly do: {st['reason']} "
                  f"(boi {st['by']}, luc {st['engaged_at']}). "
                  "Khong mo lenh moi nua; vi the mo van duoc doi chieu "
                  "va dong theo SL/TP.")
        elif args.action == "off":
            killswitch.disengage(by=args.by)
            print("Kill switch: TAT — giao dich tro lai binh thuong.")
        else:
            st = killswitch.status()
            if st["engaged"]:
                print(f"Kill switch: BAT — ly do: {st['reason']} "
                      f"(boi {st['by']}, luc {st['engaged_at']}).")
            else:
                print("Kill switch: TAT.")
    elif args.cmd == "audit":
        events = audit_mod.read_events(limit=args.lines)
        if not events:
            print("(chua co su kien audit nao)")
        for ev in events:
            print(f"{ev.get('ts')} {ev.get('actor')} {ev.get('event')}: "
                  f"{ev.get('details')}")
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
    elif args.cmd == "backfill":
        try:
            symbols = _resolve_history_symbols(cfg, args.desk, args.symbol)
        except ValueError as exc:
            print(f"LOI: {exc}")
            return 1
        hist = _history_cfg(cfg)
        timeframe = args.timeframe or hist.get("default_timeframe", "M15")
        days = (args.days if args.days is not None
                else int(hist.get("backfill_days", 90)))
        print(f"DiamondX10 — backfill MT5 DEMO: {', '.join(symbols)}, "
              f"{timeframe}, {days} ngay gan nhat")
        try:
            result = run_backfill(cfg, symbols, timeframe, days)
        except (ImportError, ValueError) as exc:
            print(f"LOI: {exc}")
            return 1
        print(f"Xong backfill: {result['total_bars']} bar da luu, "
              f"{len(result['results'])}/{len(symbols)} symbol OK.")
        if result["failed"]:
            print(f"Co {result['failed']}/{len(symbols)} symbol loi.")
            return 1
    elif args.cmd == "export-bars":
        try:
            symbols = _resolve_history_symbols(cfg, args.desk, args.symbol)
        except ValueError as exc:
            print(f"LOI: {exc}")
            return 1
        hist = _history_cfg(cfg)
        timeframe = args.timeframe or hist.get("default_timeframe", "M15")
        days = (args.days if args.days is not None
                else int(hist.get("backfill_days", 90)))
        out_dir = args.out or DEFAULT_EXPORT_DIR
        print(f"DiamondX10 — xuat bar: {', '.join(symbols)}, {timeframe}, "
              f"{days} ngay, nguon: {args.source}, ra {out_dir}")
        try:
            result = run_export_bars(cfg, symbols, timeframe, days,
                                     out_dir, args.source)
        except (ImportError, ValueError) as exc:
            print(f"LOI: {exc}")
            return 1
        print(f"Xong xuat bar: {len(result['results'])}/{len(symbols)} "
              f"file CSV trong {out_dir}.")
        if result["failed"]:
            print(f"Co {result['failed']}/{len(symbols)} symbol loi.")
            return 1
    elif args.cmd == "live":
        # Vong lap live (Phase D): 1 chu ky (--once) hoac lap toi bien nen
        # tiep theo toi khi Ctrl+C. CHI TAI KHOAN DEMO; tren may khong co
        # MT5 thi bao loi sach (khong traceback).
        try:
            live_cfg = cfg.get("live") or {}
            timeframe = args.timeframe or live_cfg.get("timeframe", "M15")
            interval_min = (args.interval_min
                            if args.interval_min is not None
                            else int(live_cfg.get("interval_min", 15)))
            symbols = _desk_symbols(cfg, args.desk, args.symbol)
        except ValueError as exc:
            print(f"LOI: {exc}")
            return 1
        print(f"DiamondX10 LIVE [{args.desk}] — {timeframe}, "
              f"symbols {', '.join(symbols)}")
        print("CHI TAI KHOAN DEMO. Khong bao gio dat lenh that.")
        try:
            if args.once:
                summary = run_live_cycle(cfg, args.desk, symbols=symbols,
                                         timeframe=timeframe,
                                         recommend_only=args.recommend_only)
                if summary["errors"] and not summary["results"]:
                    print("LOI: khong chay duoc chu ky live (xem loi tren).")
                    return 1
                return 0
            summaries = run_live_loop(
                cfg, args.desk, symbols=symbols, timeframe=timeframe,
                interval_min=interval_min, max_cycles=args.max_cycles,
                recommend_only=args.recommend_only)
            print(f"Xong vong lap live: {len(summaries)} chu ky.")
            return 0
        except KeyboardInterrupt:
            print("\nDung vong lap live (Ctrl+C) — khong dat lenh moi nua.")
            return 0
        except (ImportError, ValueError) as exc:
            print(f"LOI: {exc}")
            return 1
    elif args.cmd == "telegram-test":
        return cmd_telegram_test(cfg)
    elif args.cmd == "telegram-listen":
        # Nhan nut bam Dat lenh / Bo qua tren Telegram (che do khuyen
        # nghi, xem docs/live-loop.md §6). Phai chay tren CUNG may
        # Windows co MT5 terminal. Long-poll getUpdates toi khi Ctrl+C.
        from .listener import run_listener
        return run_listener(cfg, once=args.once,
                            interval_sec=args.interval_sec)
    elif args.cmd == "briefing":
        if args.send:
            return _cmd_briefing_send(cfg, desk=args.desk, days=args.days,
                                      all_desks=args.all)
        return cmd_briefing(cfg, desk=args.desk, days=args.days,
                            all_desks=args.all)
    elif args.cmd == "muse-setup":
        return cmd_muse_setup()
    elif args.cmd == "muse-send":
        return cmd_muse_send(cfg, args.file, prompt=args.prompt,
                             headless=args.headless,
                             wait_min=args.wait_min, no_wait=args.no_wait)
    elif args.cmd == "muse-auto":
        return cmd_muse_auto(cfg, desk=args.desk, all_desks=args.all,
                             wait_min=args.wait_min,
                             headless=args.headless)
    elif args.cmd == "verdict":
        return cmd_verdict(cfg, args.file)
    elif args.cmd == "synthesize":
        return cmd_synthesize(cfg, args.desk, args.symbol)
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
        # Chien luoc lay tham so tu config (muc "strategy"); mac dinh
        # dung gia tri da chot Phase 2 neu config khong co muc do.
        # Tham so RIENG theo symbol (Phase B) duoc build trong vong lap
        # theo tung symbol (build_strategy), khong dung chung 1 instance
        # cho ca desk nua.
        strategies = build_strategies(cfg.get("strategy"))
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
                manager = cfg["fund"]["desks"][args.desk]["manager"]
                if args.cmd == "mt5-trade":
                    # Duong dat lenh dung chung live.process_symbol:
                    # doi chieu -> drawdown -> no-trade -> daily limit ->
                    # tin hieu -> levels ATR/size -> place_demo_order
                    # (demo-only + margin check trong do). State luu sau
                    # moi symbol (ca khi bi chan — vi the dong luc doi
                    # chieu cung phai luu).
                    guard, positions = _load_guard_and_positions(cfg)
                    result = process_symbol(
                        cfg, args.desk, symbol, feed=feed, mt5=mt5,
                        account=account, server=server, manager=manager,
                        guard=guard, positions=positions,
                        volume=args.volume,
                        per_symbol_cap=per_symbol_cap,
                        strategies=strategies,
                        recommend_only=args.recommend_only)
                    try:
                        _save_guard_and_positions(guard, positions)
                    except Exception as exc:  # noqa: BLE001
                        print(f"CANH BAO: khong ghi duoc vi the moi vao state: {exc}")
                    # mt5-trade cung gui khuyen nghi Telegram nhu vong live
                    # (chi khi co lenh DEMO da dat hoac lenh bi chan; HOLD
                    # thi khong gui). Dry-run o nhanh duoi KHONG gui.
                    _maybe_send_alert(cfg, args.desk, result, telegram=None)
                    if result["status"] in ("ERROR", "BLOCKED-MARGIN"):
                        failed += 1
                    continue
                # mt5-dry-run: chi doi chieu + in tin hieu, KHONG dat lenh.
                bars = feed.bars(60)
                # Phase B: chien luoc RIENG theo symbol (tham so resolve
                # mac dinh < chung < desk < symbol); dung cho ca doi chieu
                # vi the va tin hieu.
                strat = build_strategy(args.desk, symbol=symbol, cfg=cfg)
                # Phase 4 (1): doi chieu vi the mo TRUOC khi xu ly tin hieu
                # moi. State loi thi bo qua symbol nay thay vi giao dich
                # mu — khong bao gio crash ca lenh.
                try:
                    guard, positions = _load_guard_and_positions(cfg)
                    _reconcile_for_symbol(cfg, args.desk, symbol, bars, strat,
                                          guard, positions, mt5, manager)
                    _save_guard_and_positions(guard, positions)
                except Exception as exc:  # noqa: BLE001 — giu vong lap chay
                    print(f"LOI doi chieu vi the ({symbol}): {exc} — "
                          "bo qua symbol nay.")
                    failed += 1
                    continue
                sig = generate_signals(args.desk, bars, symbol=symbol,
                                       cfg=cfg, strategies=strategies)
                print(f"Gia moi nhat {symbol}: {feed.latest_price(symbol)}")
                print(f"Tin hieu: {sig}")
                if sig.get("levels"):
                    lv = sig["levels"]
                    print(f"Levels: entry={lv['entry']:.4f} SL={lv['sl']:.4f} "
                          f"TP={lv['tp']:.4f} ATR={lv['atr']:.4f}")
                log_decision(symbol, f"DRY-RUN-{sig['action']}",
                             f"MT5 demo dry-run: {sig['reason']} [khong gui lenh]",
                             desk=args.desk,
                             manager=manager)
                print("OK: dry-run xong, KHONG dat lenh.")
                continue
            finally:
                feed.close()
        print(f"Xong {mode} desk {args.desk} ({len(symbols)} symbol). "
              f"Xem decisions/decisions-log.csv")
        if failed:
            print(f"Co {failed}/{len(symbols)} symbol loi.")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
