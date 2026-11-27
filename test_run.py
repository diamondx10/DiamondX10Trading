#!/usr/bin/env python3
"""DiamondX10 test_run.py — chay kiem tra toan bo tool tren may that
(Windows + MT5 demo) va dump log de gui ve debug.

Mac dinh CHI DOC + KIEM TRA, KHONG dat lenh:
  0. Moi truong (Python, goi pip)
  1. Cau hinh (config.yaml, Telegram, kill switch, gioi han quy)
  2. Ket noi MT5 (terminal, tai khoan DEMO, so du)
  3. Symbol (10 symbol co tren server demo khong)
  4. Nen + tin hieu (60 nen M15/symbol, tin hieu SMA/RSI/ATR — chi
     tinh, khong dat lenh)
  5. Kho lich su (so nen da co trong data/history.db)
  6. Telegram (trang thai cau hinh; neu du thi gui 1 tin thu)
  7. Bao cao ngay (lenh report, chi doc)

Tuy chon:
  --live-once   chay them 1 chu ky live M15 cho ca 4 desk (CO THE dat
                lenh DEMO — phai go ro "chay live" moi chay)
  --with-tests  chay them pytest (can pytest, mat vai giay)
  --out DIR     thu muc ghi log (mac dinh logs/ trong goc repo)

Log ghi ra logs/test-run-YYYYMMDD-HHMMSS.log (da gitignore qua *.log).
Log KHONG BAO GIO chua token Telegram hay mat khau MT5 (tu dong che
truoc khi ghi). Gui file log nay cho Muse de debug.

Chay:  python test_run.py
       python test_run.py --live-once
       python test_run.py --with-tests
       python test_run.py --live-once --with-tests

       quickstart.py tu chay bo test nay o buoc 7 (sau khi setup xong,
       truoc khi dat lenh/chay live); dung --skip-tests de bo qua.
"""

import argparse
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

DESKS = ["forex", "xauusd", "crypto", "us_securities"]
TOKEN_ENV = "DIAMONDX10_TELEGRAM_TOKEN"


# ------------------------------------------------------------------ log
class DiagLogger:
    """Ghi log ra ca man hinh va file; moi dong deu qua redact()."""

    def __init__(self, path):
        self.path = path
        self._f = open(path, "w", encoding="utf-8")
        self.results = []  # (ten, trang thai, chi tiet ngan)

    def _redact(self, text):
        for name in (TOKEN_ENV, "MT5_PASSWORD"):
            secret = os.environ.get(name) or ""
            if len(secret) >= 4:
                text = text.replace(secret, "***")
        return text

    def log(self, msg=""):
        line = self._redact(str(msg))
        print(line, flush=True)
        self._f.write(line + "\n")
        self._f.flush()

    def section(self, title):
        self.log("")
        self.log("=" * 68)
        self.log(title)
        self.log("=" * 68)

    def check(self, name, fn):
        """Chay 1 buoc kiem tra; loi thi ghi FAIL + traceback, khong dung."""
        self.log(f"[CHECK] {name} ...")
        try:
            detail = fn() or ""
        except Exception:  # noqa: BLE001 — muc dich la ghi loi vao log
            tb = traceback.format_exc(limit=5)
            last = tb.strip().splitlines()[-1]
            self.results.append((name, "FAIL", last))
            self.log(f"  FAIL: {last}")
            self.log("  Chi tiet loi:")
            for line in tb.strip().splitlines():
                self.log(f"    {line}")
            return False
        self.results.append((name, "PASS", str(detail)))
        self.log(f"  PASS: {detail}" if detail else "  PASS")
        return True

    def skip(self, name, reason):
        self.log(f"[CHECK] {name} ...")
        self.log(f"  SKIP: {reason}")
        self.results.append((name, "SKIP", reason))

    def close(self):
        self._f.close()


def _subprocess_env():
    """Env cho tien trinh con: them src/ vao PYTHONPATH de
    `python -m diamondx10` tim duoc package (khong phu thuoc vao
    PYTHONPATH san cua may). Dat PYTHONUNBUFFERED=1 de stdout cua
    tien trinh con khong bi block-buffer khi ghi ra pipe (~8KB) —
    log chay thang ra man hinh / log viewer trong luc tien trinh con
    van dang chay, thay vi don den khi ket thuc."""
    env = dict(os.environ)
    src = str(ROOT / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")
    env["PYTHONUNBUFFERED"] = "1"
    return env


def redact_for_test(text):
    """Ham thuan de test: che token/mat khau neu xuat hien trong text."""
    for name in (TOKEN_ENV, "MT5_PASSWORD"):
        secret = os.environ.get(name) or ""
        if len(secret) >= 4:
            text = text.replace(secret, "***")
    return text


def _mt5_symbol_suffix(cfg):
    """Hau to symbol MT5 truyen cho MT5Feed / build_symbol_map.

    Doc tu cfg mt5.symbol_suffix (mac dinh "auto"): "auto" (hoac
    thieu) -> None, de ham ben mt5_feed tu nhan theo ten server
    (Trial -> "m", Real -> ""); "m" hoac "" thi ep buoc theo gia tri
    do. Ten symbol chuan trong config KHONG doi.
    """
    raw = ((cfg or {}).get("mt5") or {}).get("symbol_suffix", "auto")
    if raw is None:
        return None
    value = str(raw).strip()
    if value.lower() == "auto":
        return None
    return value


def check_demo_symbol_map(mt5_mod, symbols_cfg, server, suffix=None, log=None):
    """Map ten symbol chuan -> ten broker tren server MT5.

    Dung build_symbol_map trong mt5_feed (khong tu doan hau to o day):
    Trial chi co *m, Real chi co ten goc. Tra (mapping, missing):
    mapping {ten chuan: ten broker | None}, missing [(ten chuan, desk,
    [ten da thu]), ...]. Ghi 1 dong log moi symbol neu co log, vd
    "EURUSD -> EURUSDm (desk forex)".
    """
    from diamondx10.data.mt5_feed import build_symbol_map, resolve_mt5_symbol
    all_symbols = [(desk, sym)
                   for desk in DESKS
                   for sym in (symbols_cfg or {}).get(desk) or []]
    mapping = build_symbol_map(mt5_mod, [s for _, s in all_symbols],
                               server, suffix)
    missing = []
    for desk, sym in all_symbols:
        broker = mapping.get(sym)
        if broker is None:
            suffixed = resolve_mt5_symbol(sym, server, suffix)
            tried = [suffixed] if suffixed == sym else [suffixed, sym]
            missing.append((sym, desk, tried))
            if log is not None:
                log.log(f"  {sym} -> THIEU (desk {desk}, da thu "
                        f"{', '.join(tried)} tren server {server!r})")
        elif log is not None:
            log.log(f"  {sym} -> {broker} (desk {desk})")
    return mapping, missing


def _missing_symbols_detail(missing, server):
    """Chuoi mo ta symbol thieu: ten + desk + ca 2 ten da thu + server."""
    return "; ".join(
        f"{sym} (desk {desk}, da thu {', '.join(tried)} "
        f"tren server {server!r})"
        for sym, desk, tried in missing)


def _mt5_feed_for_symbol(sym, cfg, terminal_path):
    """Tao MT5Feed cho 1 symbol, truyen symbol_suffix tu cfg.

    symbol_suffix "auto" (mac dinh) -> None, de MT5Feed tu nhan theo
    ten server (Trial -> "m", Real -> ""); "m"/"" thi ep buoc.
    """
    from diamondx10.data.mt5_feed import MT5Feed
    mt5_cfg = (cfg or {}).get("mt5") or {}
    return MT5Feed(sym, login=mt5_cfg.get("login"),
                   server=mt5_cfg.get("server"), path=terminal_path,
                   symbol_suffix=_mt5_symbol_suffix(cfg))


# ------------------------------------------------------------------ main
def main(argv=None):
    p = argparse.ArgumentParser(description="DiamondX10 test run (MT5 DEMO)")
    p.add_argument("--live-once", action="store_true",
                   help="chay them 1 chu ky live M15 cho ca 4 desk "
                        "(co the dat lenh DEMO — can go ro 'chay live')")
    p.add_argument("--with-tests", action="store_true",
                   help="chay them pytest")
    p.add_argument("--out", default=None,
                   help="thu muc ghi log (mac dinh logs/ trong goc repo)")
    args = p.parse_args(argv)

    out_dir = Path(args.out) if args.out else ROOT / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = out_dir / f"test-run-{stamp}.log"
    log = DiagLogger(log_path)
    ctx = {}  # cfg, mt5, account, server — dung chung giua cac buoc

    try:
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        log.log("DiamondX10 test run — kiem tra tren may that (MT5 DEMO)")
        log.log(f"Thoi gian: {now_utc}")
        log.log(f"Log ghi vao: {log_path}")
        log.log("Che do mac dinh: CHI KIEM TRA, KHONG dat lenh.")
        if args.live_once:
            log.log("Co --live-once: se hoi xac nhan truoc khi chay chu ky live.")

        # --- 0. Moi truong -------------------------------------------
        log.section("[0] Moi truong")

        def _python():
            v = sys.version_info
            if (v.major, v.minor) < (3, 10):
                raise RuntimeError(f"Python {v.major}.{v.minor} < 3.10")
            return f"Python {v.major}.{v.minor}.{v.micro} tren {sys.platform}"

        log.check("Python >= 3.10", _python)

        def _packages():
            import importlib.util
            missing = [m for m in ("yaml", "MetaTrader5")
                       if importlib.util.find_spec(m) is None]
            if missing:
                raise RuntimeError("thieu goi: " + ", ".join(missing)
                                   + " — chay quickstart.py de cai")
            return "yaml + MetaTrader5 deu co"

        log.check("Goi pip can thiet", _packages)

        # --- 1. Cau hinh ----------------------------------------------
        log.section("[1] Cau hinh")

        def _config():
            from diamondx10.config import load_config
            cfg = load_config()
            ctx["cfg"] = cfg
            desks = cfg.get("fund", {}).get("desks", {})
            symbols = cfg.get("data", {}).get("symbols", {})
            total = sum(len(v or []) for v in symbols.values())
            return (f"provider={cfg.get('data', {}).get('provider')}, "
                    f"von={cfg.get('fund', {}).get('total_capital_usd')} USD, "
                    f"{len(desks)} desk, {total} symbol")

        log.check("Doc config.yaml", _config)

        def _telegram_status():
            from diamondx10 import telegram as tg
            cfg = ctx.get("cfg") or {}
            st = tg.setup_status(cfg)
            if st["ready"]:
                return "Telegram SAN SANG (enabled + token + chat_id)"
            raise RuntimeError("Telegram chua san sang — thieu: "
                               + "; ".join(st["missing"]))

        log.check("Cau hinh Telegram", _telegram_status)

        def _kill_switch():
            from diamondx10.killswitch import is_engaged
            if is_engaged():
                raise RuntimeError("kill switch DANG BAT — vong live se "
                                   "khong mo lenh moi")
            return "kill switch TAT"

        log.check("Kill switch", _kill_switch)

        def _fund_limits():
            cfg = ctx.get("cfg") or {}
            risk = cfg.get("risk", {})
            return (f"lo ngay toi da {risk.get('fund_daily_loss_pct')}% von "
                    f"quy, toi da {risk.get('max_open_positions_fund')} vi the "
                    f"mo toan quy / {risk.get('max_open_positions_desk')}/desk")

        log.check("Gioi han quy (Phase F)", _fund_limits)

        # --- 2. Ket noi MT5 --------------------------------------------
        log.section("[2] Ket noi MT5")

        def _terminal():
            from diamondx10.data.mt5_feed import (
                load_mt5, resolve_mt5_terminal_path)
            mt5_mod = load_mt5()
            ctx["mt5"] = mt5_mod
            cfg = ctx.get("cfg") or {}
            terminal = resolve_mt5_terminal_path(cfg=cfg)
            ctx["terminal_path"] = terminal
            if terminal is not None:
                log.log(f"  Tim thay terminal: {terminal}")
                ok = mt5_mod.initialize(path=str(terminal))
            else:
                log.log("  Khong tim thay file terminal64.exe o vi tri "
                        "mac dinh — thu noi mac dinh.")
                ok = mt5_mod.initialize()
            if not ok:
                raise ConnectionError(
                    "khong noi duoc MT5 terminal — mo MT5 terminal len, "
                    "dang nhap tai khoan DEMO truoc, roi chay lai. "
                    f"Loi MT5: {mt5_mod.last_error()}")
            info = mt5_mod.terminal_info()
            detail = ""
            if info is not None:
                detail = (f"terminal {getattr(info, 'name', '')} "
                          f"{getattr(info, 'version', '')} "
                          f"build {getattr(info, 'build', '')}")
            return "noi duoc MT5 terminal" + (f" ({detail})" if detail else "")

        mt5_ok = log.check("MT5 terminal", _terminal)

        def _account():
            from diamondx10.execution import account_is_demo
            mt5_mod = ctx["mt5"]
            account = mt5_mod.account_info()
            ctx["account"] = account
            server = getattr(account, "server", "") if account else ""
            ctx["server"] = server
            if account is None:
                raise RuntimeError("khong doc duoc thong tin tai khoan — "
                                   "terminal chua dang nhap?")
            demo = account_is_demo(mt5_mod, account, server)
            if not demo:
                raise RuntimeError(
                    f"tai khoan KHONG phai demo (login="
                    f"{getattr(account, 'login', '?')}, server={server!r}) "
                    "— tool CHI chay demo, dung lai.")
            return (f"tai khoan DEMO login={getattr(account, 'login', '?')} "
                    f"server={server!r} so du="
                    f"{getattr(account, 'balance', '?')} "
                    f"{getattr(account, 'currency', '')}")

        if mt5_ok:
            log.check("Tai khoan MT5 (phai la DEMO)", _account)
        else:
            log.skip("Tai khoan MT5 (phai la DEMO)", "khong noi duoc terminal")

        if mt5_ok and not os.environ.get("MT5_PASSWORD"):
            log.log("  LUU Y: bien MT5_PASSWORD chua dat. Neu MT5 terminal "
                    "chua dang nhap san tai khoan demo thi buoc mo feed "
                    "o duoi co the loi dang nhap.")

        # --- 3. Symbol ---------------------------------------------
        log.section("[3] Symbol tren server demo")

        def _symbols():
            cfg = ctx["cfg"]
            mt5_mod = ctx["mt5"]
            server = (ctx.get("server")
                      or (cfg.get("mt5") or {}).get("server") or "")
            suffix = _mt5_symbol_suffix(cfg)
            mapping, missing = check_demo_symbol_map(
                mt5_mod, cfg.get("data", {}).get("symbols", {}), server,
                suffix, log=log)
            if missing:
                raise RuntimeError(
                    "symbol THIEU tren server demo: "
                    + _missing_symbols_detail(missing, server))
            total = len(mapping)
            return f"ca {total} symbol deu co tren server demo"

        if mt5_ok:
            log.check("10 symbol (EURUSD/XAUUSD/BTC/ETH/BNB/AMD/CDNS/SNPS/INTC/NVDA)",
                      _symbols)
        else:
            log.skip("10 symbol (EURUSD/XAUUSD/BTC/ETH/BNB/AMD/CDNS/SNPS/INTC/NVDA)",
                     "khong noi duoc terminal")

        # --- 4. Nen + tin hieu --------------------------------------
        log.section("[4] Nen M15 + tin hieu (chi tinh, KHONG dat lenh)")

        def _bars_and_signals():
            from diamondx10.signals import generate_signals
            from diamondx10.strategies import build_strategies
            cfg = ctx["cfg"]
            strategies = build_strategies(cfg.get("strategy"))
            lines = []
            for desk in DESKS:
                for sym in (cfg.get("data", {}).get("symbols", {})
                            .get(desk) or []):
                    feed = _mt5_feed_for_symbol(sym, cfg,
                                                ctx.get("terminal_path"))
                    try:
                        bars = feed.bars(60)
                        latest = feed.latest_price(sym)
                        sig = generate_signals(
                            desk, bars, symbol=sym, cfg=cfg,
                            strategies=strategies)
                        action = sig.get("action", "?")
                        lv = sig.get("levels") or {}
                        lv_txt = ""
                        if lv:
                            lv_txt = (f" entry={lv.get('entry'):.4f} "
                                      f"SL={lv.get('sl'):.4f} "
                                      f"TP={lv.get('tp'):.4f}")
                        note = (" <-- TIN HIEU DAT CHUAN"
                                if action in ("BUY", "SELL") else "")
                        lines.append(
                            f"{sym}: {len(bars)} nen, gia moi nhat "
                            f"{latest}, tin hieu {action}{lv_txt}{note}")
                    finally:
                        feed.close()
            for line in lines:
                log.log(f"  {line}")
            n_signal = sum(1 for ln in lines if "TIN HIEU DAT CHUAN" in ln)
            return (f"{len(lines)} symbol co nen + tin hieu; "
                    f"{n_signal} tin hieu BUY/SELL dat chuan")

        if mt5_ok:
            log.check("Nen + tin hieu 4 desk", _bars_and_signals)
        else:
            log.skip("Nen + tin hieu 4 desk", "khong noi duoc terminal")
        try:
            if ctx.get("mt5") is not None:
                ctx["mt5"].shutdown()
        except Exception:
            pass

        # --- 5. Kho lich su --------------------------------------------
        log.section("[5] Kho lich su (backtest tren du lieu that)")

        def _history():
            from diamondx10.data.history import HistoryStore
            cfg = ctx.get("cfg") or {}
            db_path = ((cfg.get("history") or {}).get("db_path")
                       or "data/history.db")
            full = ROOT / db_path
            if not full.exists():
                raise RuntimeError(f"chua co kho {db_path} — chay backfill "
                                   "truoc de co nen that (xem docs/history-store.md)")
            store = HistoryStore(str(full))
            counts = {}
            for desk in DESKS:
                for sym in (cfg.get("data", {}).get("symbols", {})
                            .get(desk) or []):
                    counts[sym] = store.count(sym, "M15")
            total = sum(counts.values())
            detail = ", ".join(f"{s}:{n}" for s, n in counts.items())
            return f"{total} nen M15 trong kho ({detail})"

        log.check("Kho nen OHLC local", _history)

        # --- 6. Telegram -------------------------------------------------
        log.section("[6] Telegram — gui tin thu")

        def _telegram_test():
            from diamondx10 import telegram as tg
            cfg = ctx.get("cfg") or {}
            st = tg.setup_status(cfg)
            if not st["ready"]:
                raise RuntimeError("khong gui duoc tin thu — thieu: "
                                   + "; ".join(st["missing"]))
            ok = tg.send_message(tg.format_test_message(), cfg=cfg)
            if not ok:
                raise RuntimeError("gui tin thu that bai — xem CANH BAO "
                                   "Telegram o tren (token/chat_id/mang)")
            return "tin thu da gui toi chat Telegram — kiem tra tren dien thoai"

        log.check("Gui tin nhan thu Telegram", _telegram_test)

        # --- 7. Bao cao ngay ----------------------------------------------
        log.section("[7] Bao cao ngay (chi doc)")

        def _report():
            r = subprocess.run(
                [sys.executable, "-m", "diamondx10", "report"],
                cwd=ROOT, env=_subprocess_env(),
                capture_output=True, text=True, timeout=120)
            out = (r.stdout or "") + (r.stderr or "")
            for line in out.strip().splitlines()[:60]:
                log.log(f"  {line}")
            if r.returncode != 0:
                raise RuntimeError(f"lenh report loi (exit {r.returncode})")
            return "lenh report chay duoc"

        log.check("Bao cao ngay", _report)

        # --- 8. Pytest (tuy chon) ------------------------------------------
        if args.with_tests:
            log.section("[8] Pytest")

            def _pytest():
                r = subprocess.run(
                    [sys.executable, "-m", "pytest", "tests/", "-q"],
                    cwd=ROOT, env=_subprocess_env(),
                    capture_output=True, text=True, timeout=600)
                out = (r.stdout or "") + (r.stderr or "")
                for line in out.strip().splitlines()[-25:]:
                    log.log(f"  {line}")
                if r.returncode != 0:
                    raise RuntimeError(f"pytest loi (exit {r.returncode})")
                return "pytest pass"

            log.check("Bo test cua tool", _pytest)

        # --- 9. Live once (tuy chon, can xac nhan) ---------------------------
        if args.live_once:
            log.section("[9] Live — 1 chu ky M15 cho ca 4 desk (CO THE DAT LENH DEMO)")
            try:
                confirm = input("Chay LIVE (co the dat lenh DEMO)? "
                                "Go ro 'chay live' de xac nhan: ").strip().lower()
            except EOFError:
                confirm = ""
            if confirm != "chay live":
                log.skip("Chu ky live", "nguoi dung khong xac nhan 'chay live'")
            else:
                for desk in DESKS:
                    def _live_cycle(desk=desk):
                        r = subprocess.run(
                            [sys.executable, "-m", "diamondx10", "live",
                             "--once", "--desk", desk],
                            cwd=ROOT, env=_subprocess_env(),
                            capture_output=True, text=True,
                            timeout=600)
                        out = (r.stdout or "") + (r.stderr or "")
                        for line in out.strip().splitlines()[-40:]:
                            log.log(f"  [{desk}] {line}")
                        if r.returncode != 0:
                            raise RuntimeError(
                                f"live --once desk {desk} loi "
                                f"(exit {r.returncode})")
                        return f"chu ky live desk {desk} xong"

                    log.check(f"Live --once desk {desk}", _live_cycle)
    finally:
        # --- Tong ket ------------------------------------------------------
        log.section("TONG KET")
        passed = sum(1 for _, s, _ in log.results if s == "PASS")
        failed = [(n, d) for n, s, d in log.results if s == "FAIL"]
        skipped = sum(1 for _, s, _ in log.results if s == "SKIP")
        log.log(f"PASS: {passed} | FAIL: {len(failed)} | SKIP: {skipped}")
        if failed:
            log.log("Cac buoc LOI (can sua truoc khi chay live that):")
            for name, detail in failed:
                log.log(f"  - {name}: {detail}")
        else:
            log.log("Khong co buoc nao LOI.")
        log.log(f"Log day du: {log_path}")
        log.log("Gui file log nay cho Muse de debug.")
        log.close()

    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
