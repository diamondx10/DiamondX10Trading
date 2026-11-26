#!/usr/bin/env python3
"""DiamondX10 quickstart — chay nhanh tool quant voi MT5 DEMO (Exness).

Lam gi:
  1. Cai cac goi can thiet: requirements.txt (pyyaml, pytest)
     + MetaTrader5 (chi chay tren Windows — MT5 terminal cung phai
     chay tren cung may).
  2. Hoi thong tin dang nhap luc chay: server demo, so login demo,
     mat khau demo (nhap an, khong hien len man hinh).
  3. Ghi cau hinh vao config.yaml LOCAL (file nay da gitignore,
     khong bao gio len GitHub). MAT KHAU KHONG GHI VAO FILE —
     no chi nam trong bo nho cua tien trinh nay (bien MT5_PASSWORD)
     de dang nhap MT5, tat script la mat.
  4. Dang nhap MT5, kiem tra chac chan la tai khoan DEMO (tu choi
     tai khoan that), kiem tra symbol, roi chay dry-run tin hieu
     cho 4 desk (Forex / XAUUSD / Crypto / US securities).
     Mac dinh KHONG dat lenh. Muon dat lenh demo thi chay xong
     phai go ro "dat lenh" de xac nhan.

Chay:  python3 quickstart.py
       python3 quickstart.py --skip-install   (bo qua buoc cai goi)
       python3 quickstart.py --trade          (hoi them co dat lenh demo khong)
"""

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_SERVER = "Exness-MT5Trial6"
DESKS = ["forex", "xauusd", "crypto", "us_securities"]


def _pip_install(args, label):
    print(f"[1/5] Cai {label} ...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", *args],
        check=False,
    )
    if r.returncode != 0:
        print(f"  ! Cai {label} that bai (exit {r.returncode}).")
        return False
    print(f"  OK: {label} da cai xong.")
    return True


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


def _read_existing_config():
    """Doc login/server cu trong config.yaml neu co (de goi y mac dinh)."""
    cfg_path = ROOT / "config.yaml"
    login, server = "", ""
    if cfg_path.exists():
        for line in cfg_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s.startswith("login:"):
                login = s.split(":", 1)[1].strip()
            elif s.startswith("server:"):
                server = s.split(":", 1)[1].strip().strip('"').strip("'")
    return login, server


def _write_config(server, login):
    """Ghi config.yaml tu config.example.yaml; KHONG ghi mat khau."""
    example = ROOT / "config.example.yaml"
    text = example.read_text(encoding="utf-8")
    text = text.replace("provider: simulated", "provider: mt5")
    text = text.replace("login: 0", f"login: {login}")
    text = text.replace('server: ""', f'server: "{server}"')
    (ROOT / "config.yaml").write_text(text, encoding="utf-8")
    print("  OK: da ghi config.yaml (local, gitignore — khong len GitHub).")
    print("      Mat khau KHONG co trong file nay.")


def _run_cli(argv):
    """Chay lenh diamondx10 that (tai su dung code da test)."""
    env = dict(os.environ)
    r = subprocess.run(
        [sys.executable, "-m", "diamondx10", *argv],
        cwd=ROOT, env=env, check=False,
    )
    return r.returncode


def main(argv=None):
    p = argparse.ArgumentParser(description="DiamondX10 quickstart (MT5 DEMO)")
    p.add_argument("--skip-install", action="store_true",
                   help="bo qua buoc cai goi pip")
    p.add_argument("--trade", action="store_true",
                   help="sau dry-run, hoi co dat lenh DEMO theo tin hieu khong")
    args = p.parse_args(argv)

    print("DiamondX10 quickstart — MT5 DEMO (Exness), KHONG bao gio lenh that")
    print("=" * 68)

    # --- 1. Cai goi -------------------------------------------------
    if args.skip_install:
        print("[1/5] Bo qua buoc cai goi (--skip-install).")
    else:
        _pip_install(["-r", str(ROOT / "requirements.txt")], "requirements.txt")
        if not _pip_install(["MetaTrader5"], "MetaTrader5 (Windows)"):
            print("  -> MetaTrader5 chi cai duoc tren Windows.")
            print("     Ban dang chay tren:", sys.platform)
            print("     Hay chay script nay tren may Windows co MT5 terminal,")
            print("     dang nhap tai khoan DEMO tren MT5 terminal truoc.")
            return 1

    # --- 2. Hoi thong tin dang nhap --------------------------------
    print("[2/5] Thong tin dang nhap MT5 demo")
    old_login, old_server = _read_existing_config()
    server = _ask("Server demo Exness (vd Exness-MT5Trial6)",
                  old_server or DEFAULT_SERVER)
    while True:
        login = _ask("So login demo Exness", old_login or None)
        if login.isdigit():
            break
        print("  Login phai la so (vd 414594165). Nhap lai.")
    password = _ask_password()
    if not password:
        print("  ! Chua nhap mat khau — khong dang nhap duoc MT5.")
        return 1
    # Chi giu trong bo nho tien trinh nay; tat script la mat.
    os.environ["MT5_PASSWORD"] = password

    # --- 3. Ghi config.yaml (khong mat khau) ------------------------
    print("[3/5] Ghi cau hinh local")
    _write_config(server, login)

    # --- 4. Dang nhap MT5 + kiem tra demo + symbol ------------------
    print("[4/5] Ket noi MT5 va kiem tra tai khoan DEMO")
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
        feed = MT5Feed(first_symbol, login=int(login), server=server)
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

    # --- 5. Dry-run tin hieu 4 desk ---------------------------------
    print("[5/5] Dry-run tin hieu 4 desk (chi in tin hieu, KHONG dat lenh)")
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
    else:
        print("Xong dry-run 4 desk. Khong co lenh nao duoc dat.")
        print("Xem lich su tin hieu: decisions/decisions-log.csv")

    if args.trade:
        confirm = _ask("Dat lenh DEMO theo tin hieu vua roi? Go ro 'dat lenh' de xac nhan",
                       "")
        if confirm.strip().lower() == "dat lenh":
            print("Dat lenh DEMO theo tin hieu (chi tai khoan demo, co chan an toan):")
            for desk in DESKS:
                _run_cli(["mt5-trade", "--desk", desk])
        else:
            print("Khong dat lenh. Ket thuc.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
