#!/usr/bin/env python3
"""DiamondX10 quickstart — chay nhanh tool quant voi MT5 DEMO (Exness).

Thu tu chay (co y): CHUAN BI XONG moi hoi thong tin dang nhap.
  0. Kiem tra Python >= 3.10.
  1. Tu dong cai cac goi can thiet: requirements.txt (pyyaml, pytest)
     + MetaTrader5 (chi cai duoc tren Windows). Cai loi thi dung ngay,
     chua hoi gi ve tai khoan.
  2. Quet tim MT5 terminal (uu tien: bien moi truong MT5_TERMINAL_PATH,
     roi mt5.terminal_path trong config.yaml cu, roi cac duong dan da
     biet — truoc het C:/Program Files/MetaTrader 5 EXNESS/terminal64.exe
     — roi quet 1 cap trong Program Files / Program Files (x86) /
     ProgramW6432 / LOCALAPPDATA, uu tien thu muc co ten "Exness")
     roi kiem tra noi duoc khong (mt5.initialize(path=...)). Tim thay
     thi ghi duong dan vao config.yaml o buoc 4. Terminal chua cai /
     chua mo thi dung ngay va huong dan cai/mo, chua hoi gi ve tai khoan.
  3. Hoi thong tin dang nhap luc chay: server demo, so login demo,
     mat khau demo (nhap an, khong hien len man hinh).
  4. Ghi cau hinh vao config.yaml LOCAL (file nay da gitignore,
     khong bao gio len GitHub). MAT KHAU KHONG GHI VAO FILE —
     no chi nam trong bo nho cua tien trinh nay (bien MT5_PASSWORD)
     de dang nhap MT5, tat script la mat.
  5. Dang nhap MT5, kiem tra chac chan la tai khoan DEMO (tu choi
     tai khoan that), kiem tra symbol.
  6. Dry-run tin hieu cho 4 desk (Forex / XAUUSD / Crypto /
     US securities). Mac dinh KHONG dat lenh.
  7. Cai dat Telegram (hoi token bot + chat_id, ghi config local)
     roi chay bo kiem tra test_run.py (chi kiem tra, KHONG dat
     lenh; log ghi ra logs/test-run-*.log). Co buoc LOI thi hoi co
     tiep tuc khong — khong tiep tuc thi dung lai truoc khi dat
     lenh/chay live.
  8. Tuy chon:
     - --trade: hoi them co dat lenh DEMO theo tin hieu khong
       (go ro "dat lenh" moi dat).
     - --live-once: chay 1 chu ky live M15 cho ca 4 desk (co the
       dat lenh DEMO theo tin hieu, go ro "chay live" moi chay).
     - --live: chay vong lap live M15 lien tuc cho 1 desk (chon
       desk luc chay, Ctrl+C de dung; go ro "chay live" moi chay).

Chay:  python quickstart.py
       python quickstart.py --skip-install   (bo qua buoc cai goi pip)
       python quickstart.py --check-only     (chi buoc 0-2: cai goi +
                                             kiem tra terminal, khong
                                             hoi dang nhap)
       python quickstart.py --skip-tests     (bo qua buoc kiem tra test_run.py)
       python quickstart.py --trade          (them buoc dat lenh demo)
       python quickstart.py --live-once      (them 1 chu ky live 4 desk)
       python quickstart.py --live           (them vong lap live 1 desk)

       Tren Windows khong can Python san: nhap doi vao quickstart.bat —
       file .bat tu tim/cai Python 3.12 roi chay quickstart.py o tren.

Luu y: MT5 terminal va tool Python phai chay tren CUNG 1 may Windows.
"""

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

# Tim terminal MT5: dung 1 ham duy nhat trong package (khong viet lai
# o day) — xem src/diamondx10/data/mt5_feed.py.
from diamondx10.data.mt5_feed import (  # noqa: E402
    find_mt5_terminal, resolve_mt5_terminal_path)

MIN_PYTHON = (3, 10)
DEFAULT_SERVER = "Exness-MT5Trial6"
DESKS = ["forex", "xauusd", "crypto", "us_securities"]


# ---------------------------------------------------------------- helpers
def is_supported_python(version=None):
    """True neu Python >= 3.10 (code dung cu phap `X | None`)."""
    version = version if version is not None else sys.version_info[:2]
    return tuple(version) >= MIN_PYTHON


def parse_login(value):
    """So login demo hop le: chi gom chu so. Tra int, sai thi None."""
    value = (value or "").strip()
    if value.isdigit():
        return int(value)
    return None


def _pip_install(args, label):
    print(f"  Cai {label} ...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", *args],
        check=False,
    )
    if r.returncode != 0:
        print(f"  ! Cai {label} that bai (exit {r.returncode}).")
        return False
    print(f"  OK: {label} da cai xong.")
    return True


def _ensure_pip():
    """Dam bao pip ton tai; nang cap pip neu duoc (loi thi bo qua)."""
    r = subprocess.run([sys.executable, "-m", "pip", "--version"],
                       check=False, capture_output=True)
    if r.returncode != 0:
        print("  pip chua co — thu cai bang ensurepip ...")
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"],
                       check=False)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        check=False, capture_output=True,
    )


def check_terminal(mt5_module=None, path=None):
    """Kiem tra MT5 terminal co noi duoc khong (chua can dang nhap).

    Tra (ok, message). mt5_module de truyen vao khi test; None thi
    import that goi MetaTrader5. path: duong dan terminal64.exe (tim
    duoc o buoc quet) — co thi goi mt5.initialize(path=...), khong
    thi goi initialize() khong duong dan.
    """
    if mt5_module is None:
        try:
            import MetaTrader5 as mt5_module
        except ImportError:
            return False, ("Chua cai duoc goi MetaTrader5. "
                           "Goi nay chi cai duoc tren Windows.")
    try:
        if path is not None:
            ok = mt5_module.initialize(path=str(path))
        else:
            ok = mt5_module.initialize()
    except Exception as exc:  # noqa: BLE001 — terminal co the loi du kieu
        return False, f"mt5.initialize() loi: {exc}"
    if not ok:
        return False, ("Khong noi duoc voi MT5 terminal. Hay mo MT5 "
                       "terminal tren may nay (va dang nhap tai khoan "
                       "DEMO trong terminal) roi chay lai script.")
    try:
        info = mt5_module.terminal_info()
        detail = ""
        if info is not None:
            detail = (f" (terminal {getattr(info, 'name', '')} "
                      f"{getattr(info, 'version', '')} "
                      f"build {getattr(info, 'build', '')})")
        return True, f"Noi duoc voi MT5 terminal.{detail}"
    finally:
        try:
            mt5_module.shutdown()
        except Exception:  # noqa: BLE001 — shutdown loi thi bo qua
            pass


def _ask(prompt, default=None):
    """Hoi 1 gia tri; Enter thi lay mac dinh (neu co)."""
    hint = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{hint}: ").strip()
    except EOFError:
        value = ""
    return value or (default or "")


def _ask_password(prompt="Mat khau demo MT5 (nhap an, khong luu vao file)"):
    """Nhap mat khau an; chi giu trong bo nho tien trinh nay."""
    try:
        return getpass.getpass(f"{prompt}: ")
    except Exception:
        # Khong co tty (vd chay qua pipe): dung input thuong.
        print("  (khong an duoc ky tu — mat khau se hien khi go)")
        return _ask(prompt)


def _ask_secret(prompt):
    """Nhap token an (Enter de bo qua); chi giu trong bo nho."""
    try:
        return getpass.getpass(f"{prompt}: ")
    except Exception:
        return _ask(prompt)


def _read_existing_config():
    """Doc login/server + muc telegram cu trong config.yaml neu co.

    Tra (login, server, telegram_enabled, telegram_chat_id) de goi y
    mac dinh va giu lai cai dat Telegram khi ghi lai config.
    """
    cfg_path = ROOT / "config.yaml"
    login, server = "", ""
    tg_enabled, tg_chat_id = False, ""
    if cfg_path.exists():
        in_telegram = False
        for line in cfg_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            if not line.startswith((" ", "\t")):
                in_telegram = s.startswith("telegram:")
            if s.startswith("login:"):
                login = s.split(":", 1)[1].strip()
            elif s.startswith("server:"):
                server = s.split(":", 1)[1].strip().strip('"').strip("'")
            elif in_telegram and s.startswith("enabled:"):
                tg_enabled = s.split(":", 1)[1].strip().lower() == "true"
            elif in_telegram and s.startswith("chat_id:"):
                tg_chat_id = s.split(":", 1)[1].strip().strip('"').strip("'")
    return login, server, tg_enabled, tg_chat_id


def _apply_telegram_to_config_text(text, enabled, chat_id):
    """Ap dung muc telegram (enabled/chat_id) vao noi dung config.yaml.

    Tim khoi `telegram:` o cap cao nhat roi doi 2 dong enabled/chat_id
    trong khoi do; khong co khoi thi them moi o cuoi file. Cac muc khac
    giu nguyen (khong ghi de toan bo file).
    """
    lines = text.splitlines()
    out = []
    in_telegram = False
    seen_telegram = False
    seen_enabled = False
    seen_chat_id = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue
        if not line.startswith((" ", "\t")):
            if in_telegram:
                if not seen_enabled:
                    out.append(f"  enabled: {'true' if enabled else 'false'}")
                if not seen_chat_id:
                    out.append(f'  chat_id: "{chat_id}"')
                in_telegram = False
            if stripped.startswith("telegram:"):
                in_telegram = True
                seen_telegram = True
                seen_enabled = False
                seen_chat_id = False
            out.append(line)
            continue
        if in_telegram:
            if stripped.startswith("enabled:"):
                out.append(f"  enabled: {'true' if enabled else 'false'}")
                seen_enabled = True
                continue
            if stripped.startswith("chat_id:"):
                out.append(f'  chat_id: "{chat_id}"')
                seen_chat_id = True
                continue
        out.append(line)
    if in_telegram:
        if not seen_enabled:
            out.append(f"  enabled: {'true' if enabled else 'false'}")
        if not seen_chat_id:
            out.append(f'  chat_id: "{chat_id}"')
    elif not seen_telegram:
        if out and out[-1].strip():
            out.append("")
        out.append("telegram:")
        out.append(f"  enabled: {'true' if enabled else 'false'}")
        out.append(f'  chat_id: "{chat_id}"')
        out.append("  bot_token_env: DIAMONDX10_TELEGRAM_TOKEN")
    return "\n".join(out) + "\n"


def _update_telegram_config(chat_id, enabled=True):
    """Ghi muc telegram vao config.yaml local (khong doi muc khac)."""
    cfg_path = ROOT / "config.yaml"
    text = cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else ""
    text = _apply_telegram_to_config_text(text, enabled, chat_id)
    cfg_path.write_text(text, encoding="utf-8")


def _apply_terminal_path_to_config_text(text, terminal_path):
    """Ghi duong dan terminal vao muc mt5: cua noi dung config.yaml.

    Duong dan Windows ghi bang dau / (vd C:/Program Files/MetaTrader 5
    EXNESS/terminal64.exe) de YAML doc duoc. Tim khoi `mt5:` o cap cao
    nhat roi doi dong terminal_path trong khoi do; khong co dong thi
    chen them; khong co khoi mt5 thi them moi o cuoi file.
    """
    value = str(terminal_path).replace("\\", "/")
    line = f'  terminal_path: "{value}"'
    lines = text.splitlines()
    out = []
    in_mt5 = False
    seen_mt5 = False
    seen_path = False
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            out.append(raw)
            continue
        if not raw.startswith((" ", "\t")):
            if in_mt5 and not seen_path:
                out.append(line)
                seen_path = True
            in_mt5 = stripped.startswith("mt5:")
            if in_mt5:
                seen_mt5 = True
                seen_path = False
            out.append(raw)
            continue
        if in_mt5 and stripped.startswith("terminal_path:"):
            out.append(line)
            seen_path = True
            continue
        out.append(raw)
    if in_mt5 and not seen_path:
        out.append(line)
        seen_path = True
    elif not seen_mt5:
        if out and out[-1].strip():
            out.append("")
        out.append("mt5:")
        out.append(line)
    return "\n".join(out) + "\n"


def _write_config(server, login, telegram_enabled=False, telegram_chat_id="",
                  terminal_path=None):
    """Ghi config.yaml tu config.example.yaml; KHONG ghi mat khau.

    Giu lai cai dat Telegram cu (enabled/chat_id) neu co, de ghi lai
    config khong tat mat canh bao da bat. terminal_path: duong dan
    terminal64.exe tim duoc o buoc 2 — co thi ghi vao muc mt5: (dau /),
    khong co thi giu mac dinh trong file mau (terminal_path: "").
    """
    example = ROOT / "config.example.yaml"
    text = example.read_text(encoding="utf-8")
    text = text.replace("provider: simulated", "provider: mt5")
    text = text.replace("login: 0", f"login: {login}")
    text = text.replace('server: ""', f'server: "{server}"')
    text = _apply_telegram_to_config_text(text, telegram_enabled,
                                          telegram_chat_id)
    if terminal_path is not None:
        text = _apply_terminal_path_to_config_text(text, terminal_path)
    (ROOT / "config.yaml").write_text(text, encoding="utf-8")
    print("  OK: da ghi config.yaml (local, gitignore — khong len GitHub).")
    print("      Mat khau KHONG co trong file nay.")


def _child_env():
    """Env cho tien trinh con: them src/ vao PYTHONPATH de
    `python -m diamondx10` tim duoc package (tien trinh con KHONG ke
    thua sys.path cua tien trinh nay)."""
    env = dict(os.environ)
    src = str(ROOT / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src + (os.pathsep + existing if existing else "")
    return env


def _run_cli(argv):
    """Chay lenh diamondx10 that (tai su dung code da test).

    Tien trinh con KHONG ke thua sys.path cua tien trinh nay, nen phai
    them src/ vao PYTHONPATH — neu khong `python -m diamondx10` se loi
    "No module named diamondx10" khi chay tren may that.
    """
    r = subprocess.run(
        [sys.executable, "-m", "diamondx10", *argv],
        cwd=ROOT, env=_child_env(), check=False,
    )
    return r.returncode


def _run_test_suite():
    """Chay bo kiem tra test_run.py (chi kiem tra, KHONG dat lenh).

    Tra exit code cua test_run.py (0 = tat ca PASS, 1 = co buoc LOI).
    Log chi tiet ghi ra logs/test-run-*.log; ket qua hien truc tiep
    tren man hinh khi chay.
    """
    print("  Chay bo kiem tra test_run.py (chi kiem tra, KHONG dat lenh) ...")
    r = subprocess.run([sys.executable, str(ROOT / "test_run.py")],
                       cwd=ROOT, env=_child_env(), check=False)
    return r.returncode


# ---------------------------------------------------------------- main
def main(argv=None):
    p = argparse.ArgumentParser(description="DiamondX10 quickstart (MT5 DEMO)")
    p.add_argument("--skip-install", action="store_true",
                   help="bo qua buoc cai goi pip")
    p.add_argument("--check-only", action="store_true",
                   help="chi kiem tra san sang (cai goi + terminal), "
                        "khong hoi dang nhap")
    p.add_argument("--trade", action="store_true",
                   help="sau dry-run, hoi co dat lenh DEMO theo tin hieu khong")
    p.add_argument("--live-once", action="store_true",
                   help="sau dry-run, chay 1 chu ky live M15 cho ca 4 desk "
                        "(co the dat lenh DEMO)")
    p.add_argument("--live", action="store_true",
                   help="sau dry-run, chay vong lap live M15 lien tuc cho "
                        "1 desk (Ctrl+C de dung)")
    p.add_argument("--skip-tests", action="store_true",
                   help="bo qua buoc kiem tra test_run.py o buoc 7")
    args = p.parse_args(argv)

    print("DiamondX10 quickstart — MT5 DEMO (Exness), KHONG bao gio lenh that")
    print("=" * 68)

    # --- 0. Python ---------------------------------------------------
    print("[0/8] Kiem tra Python")
    if not is_supported_python():
        print(f"  ! Can Python >= 3.10, may nay dang chay "
              f"{sys.version_info.major}.{sys.version_info.minor}.")
        print("    Tai Python 3.10+ tai python.org roi chay lai script.")
        return 1
    print(f"  OK: Python {sys.version_info.major}.{sys.version_info.minor} "
          f"tren {sys.platform}.")

    # --- 1. Cai goi (tu dong) ----------------------------------------
    print("[1/8] Cai cac goi can thiet (tu dong)")
    if args.skip_install:
        print("  Bo qua buoc cai goi (--skip-install).")
    else:
        _ensure_pip()
        if not _pip_install(["-r", str(ROOT / "requirements.txt")],
                            "requirements.txt"):
            print("  ! Khong cai duoc requirements.txt — dung lai, "
                  "kiem tra mang / pip roi chay lai.")
            return 1
        if not _pip_install(["MetaTrader5"], "MetaTrader5 (Windows)"):
            print("  -> MetaTrader5 chi cai duoc tren Windows.")
            print(f"     Ban dang chay tren: {sys.platform}")
            print("     Hay chay script nay tren may Windows co MT5 terminal.")
            return 1

    # --- 2. Kiem tra MT5 terminal (truoc khi hoi dang nhap) -----------
    print("[2/8] Kiem tra MT5 terminal (chua hoi dang nhap)")
    try:
        from diamondx10.config import load_config
        _existing_cfg = load_config(ROOT / "config.yaml")
        if not isinstance(_existing_cfg, dict):
            _existing_cfg = {}
    except Exception:  # noqa: BLE001 — chua co yaml/config thi quet chay
        _existing_cfg = {}
    terminal = resolve_mt5_terminal_path(cfg=_existing_cfg)
    if terminal is not None:
        print(f"  Tim thay terminal: {terminal}")
    else:
        print("  Khong tim thay file terminal64.exe o vi tri mac dinh — "
              "co the terminal cai o cho khac, van thu noi tiep.")
    ok, msg = check_terminal(path=terminal)
    print(f"  {'OK' if ok else '!'}: {msg}")
    if not ok:
        print("  Hay cai MT5 terminal (tai tu Exness), mo len, dang nhap")
        print("  tai khoan DEMO trong terminal roi chay lai script.")
        print("  (Cac buoc sau — hoi dang nhap, dry-run, live — chua chay.)")
        return 1

    if args.check_only:
        print("=" * 68)
        print("May da SAN SANG: goi da cai, noi duoc MT5 terminal.")
        print("Chay lai khong co --check-only de nhap dang nhap va dry-run:")
        print("  python quickstart.py")
        return 0

    # --- 3. Hoi thong tin dang nhap (chi hoi khi may da san sang) -----
    print("[3/8] Thong tin dang nhap MT5 demo (may da san sang)")
    old_login, old_server, old_tg_enabled, old_tg_chat_id = _read_existing_config()
    server = _ask("Server demo Exness (vd Exness-MT5Trial6)",
                  old_server or DEFAULT_SERVER)
    while True:
        raw = _ask("So login demo Exness", old_login or None)
        login = parse_login(raw)
        if login is not None:
            break
        print("  Login phai la so (vd: 123456789). Nhap lai.")
    password = _ask_password()
    if not password:
        print("  ! Chua nhap mat khau — khong dang nhap duoc MT5.")
        return 1
    # Chi giu trong bo nho tien trinh nay; tat script la mat.
    os.environ["MT5_PASSWORD"] = password

    # --- 4. Ghi config.yaml (khong mat khau) --------------------------
    print("[4/8] Ghi cau hinh local")
    _write_config(server, login, old_tg_enabled, old_tg_chat_id,
                  terminal_path=terminal)

    # --- 5. Dang nhap MT5 + kiem tra demo + symbol --------------------
    print("[5/8] Ket noi MT5 va kiem tra tai khoan DEMO")
    try:
        from diamondx10.config import load_config
        from diamondx10.data.mt5_feed import MT5Feed
        from diamondx10.execution import account_is_demo
    except ImportError as exc:
        print(f"  LOI: {exc}")
        return 1
    cfg = load_config()
    first_symbol = (cfg.get("data", {}).get("symbols", {}) or {}).get("forex", ["EURUSD"])[0]
    try:
        feed = MT5Feed(first_symbol, login=int(login), server=server,
                       path=terminal)
    except (ImportError, ConnectionError, ValueError) as exc:
        print(f"  LOI: {exc}")
        return 1
    try:
        account = feed.account_info()
        if not account_is_demo(None, account, server):
            print("  TU CHOI: tai khoan dang dang nhap KHONG phai demo — dung lai.")
            return 1
        print(f"  OK: tai khoan DEMO — login {getattr(account, 'login', login)}, "
              f"server {getattr(account, 'server', server)}, "
              f"so du {getattr(account, 'balance', '?')}")
        print("  Symbol tren server demo:")
        for desk in DESKS:
            symbols = (cfg.get("data", {}).get("symbols", {}) or {}).get(desk) or []
            for sym in symbols:
                ok = feed.mt5.symbol_info(sym) is not None
                print(f"    [{'co' if ok else 'THIEU'}] {sym} (desk {desk})")
    finally:
        feed.close()

    # --- 6. Dry-run tin hieu 4 desk -----------------------------------
    print("[6/8] Dry-run tin hieu 4 desk (chi in tin hieu, KHONG dat lenh)")
    failed = 0
    for desk in DESKS:
        print(f"--- desk {desk} ---")
        rc = _run_cli(["mt5-dry-run", "--desk", desk])
        if rc != 0:
            failed += 1
            print(f"  ! dry-run desk {desk} loi (exit {rc})")
    print("=" * 68)
    if failed:
        print(f"Xong, co {failed} desk dry-run loi — xem thong bao tren.")
        return 1
    print("Xong dry-run 4 desk. Khong co lenh nao duoc dat.")
    print("Xem lich su tin hieu: decisions/decisions-log.csv")

    # --- 7. Telegram + chay bo test -------------------------------------
    print("[7/8] Cai dat Telegram + chay bo kiem tra (test_run.py)")
    token = _ask_secret("Telegram bot token de nhan khuyen nghi mua/ban "
                        "(Enter de bo qua, token chi giu trong bo nho)")
    if token:
        os.environ["DIAMONDX10_TELEGRAM_TOKEN"] = token
    chat_id = _ask("Chat ID Telegram nhan khuyen nghi mua/ban "
                   "(Enter de bo qua)",
                   old_tg_chat_id or None)
    if chat_id:
        _update_telegram_config(chat_id)
        print(f"  OK: da bat canh bao Telegram ve chat {chat_id} "
              "(config.yaml local).")
        if token:
            print("  Se gui khuyen nghi mua/ban khi co tin hieu dat chuan.")
        else:
            print("  ! Chua co token bot — buoc kiem tra Telegram se bao "
                  "thieu token; dat bien moi truong "
                  "DIAMONDX10_TELEGRAM_TOKEN truoc khi chay live.")
    else:
        print("  Bo qua Telegram (buoc kiem tra Telegram se bao thieu chat_id).")
    if args.skip_tests:
        print("  Bo qua bo kiem tra (--skip-tests).")
    else:
        rc = _run_test_suite()
        if rc != 0:
            print("=" * 68)
            print("Bo kiem tra co buoc LOI (xem TONG KET o tren).")
            print("Sua theo huong dan trong log truoc khi dat lenh/chay live.")
            confirm = _ask("Tiep tuc bat chap cac loi tren? "
                           "Go ro 'tiep tuc' de xac nhan", "")
            if confirm.strip().lower() != "tiep tuc":
                print("Dung lai. Log kiem tra: logs/test-run-*.log")
                return 1
            print("Tiep tuc theo yeu cau cua ban (cac loi tren van con).")
        else:
            print("Bo kiem tra PASS het — may da san sang.")

    # --- 8. Tuy chon: dat lenh demo / chay live ------------------------
    print("[8/8] Buoc tuy chon")
    if args.trade:
        confirm = _ask("Dat lenh DEMO theo tin hieu vua roi? Go ro 'dat lenh' de xac nhan",
                       "")
        if confirm.strip().lower() == "dat lenh":
            print("Dat lenh DEMO theo tin hieu (chi tai khoan demo, co chan an toan):")
            for desk in DESKS:
                _run_cli(["mt5-trade", "--desk", desk])
        else:
            print("Khong dat lenh. Ket thuc.")

    if args.live_once or args.live:
        confirm = _ask("Chay LIVE (co the dat lenh DEMO theo tin hieu)? "
                       "Go ro 'chay live' de xac nhan", "")
        if confirm.strip().lower() != "chay live":
            print("Khong chay live. Ket thuc.")
            return 0
        if args.live_once:
            print("Chay 1 chu ky live M15 cho ca 4 desk ...")
            for desk in DESKS:
                print(f"--- live --once desk {desk} ---")
                _run_cli(["live", "--once", "--desk", desk])
        else:
            desk = _ask("Chay vong lap live cho desk nao? "
                        "(forex/xauusd/crypto/us_securities)",
                        "forex")
            if desk not in DESKS:
                print(f"  ! Desk '{desk}' khong dung — dung lai.")
                return 1
            print(f"Chay vong lap live M15 desk {desk} (Ctrl+C de dung) ...")
            try:
                _run_cli(["live", "--desk", desk])
            except KeyboardInterrupt:
                print("\nDa dung vong live (Ctrl+C).")
    else:
        print("Chay live sau nay:")
        print("  python quickstart.py --live-once   # 1 chu ky M15, ca 4 desk")
        print("  python quickstart.py --live        # vong lap lien tuc, 1 desk")
        print("  python -m diamondx10 live --once --desk forex   # 1 chu ky, 1 desk")
        print("  python -m diamondx10.dashboard     # xem dashboard (chi doc)")
        print("Dat lich tu dong moi 15 phut (Task Scheduler, Windows):")
        print('  schtasks /create /tn "DiamondX10-live-forex" /tr '
              '"python -m diamondx10 live --once --desk forex" /sc minute /mo 15')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
