"""Test test_run.py — bo kiem tra chan doan (khong goi MT5/Telegram that).

main() chay that tren Linux: cac buoc MT5 se FAIL/SKIP gon gang (khong
co goi MetaTrader5), log van ghi day du va tra exit code 1.
"""
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_test_run():
    spec = importlib.util.spec_from_file_location(
        "test_run_under_test", REPO_ROOT / "test_run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tr = load_test_run()


def test_redact_for_test_hides_token(monkeypatch):
    monkeypatch.setenv("DIAMONDX10_TELEGRAM_TOKEN", "token-bi-mat-123")
    monkeypatch.setenv("MT5_PASSWORD", "mat-khau-bi-mat")
    text = "token=token-bi-mat-123 pass=mat-khau-bi-mat binh thuong"
    out = tr.redact_for_test(text)
    assert "token-bi-mat-123" not in out
    assert "mat-khau-bi-mat" not in out
    assert "***" in out
    assert "binh thuong" in out


def test_redact_for_test_no_secrets(monkeypatch):
    monkeypatch.delenv("DIAMONDX10_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("MT5_PASSWORD", raising=False)
    assert tr.redact_for_test("khong co gi nhay cam") == "khong co gi nhay cam"


def test_diag_logger_check_pass_fail_skip(tmp_path):
    log = tr.DiagLogger(tmp_path / "t.log")

    def _ok():
        return "mo ta pass"

    def _bad():
        raise ValueError("loi gia de test")

    assert log.check("buoc pass", _ok) is True
    assert log.check("buoc fail", _bad) is False
    log.skip("buoc skip", "ly do skip")
    log.close()
    states = [s for _, s, _ in log.results]
    assert states == ["PASS", "FAIL", "SKIP"]
    text = (tmp_path / "t.log").read_text(encoding="utf-8")
    assert "PASS: mo ta pass" in text
    assert "FAIL" in text and "loi gia de test" in text
    assert "SKIP: ly do skip" in text


def test_main_on_linux_writes_log_and_exits_nonzero(tmp_path, monkeypatch):
    # Khong co token that — buoc Telegram se FAIL truoc khi gui (khong
    # goi mang). Khong co MT5 tren Linux — cac buoc MT5 FAIL/SKIP.
    monkeypatch.delenv("DIAMONDX10_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("MT5_PASSWORD", raising=False)
    rc = tr.main(["--out", str(tmp_path)])
    assert rc == 1
    logs = list(tmp_path.glob("test-run-*.log"))
    assert len(logs) == 1
    text = logs[0].read_text(encoding="utf-8")
    assert "TONG KET" in text
    assert "FAIL" in text
    assert "MT5 terminal" in text
    assert "Khong co buoc nao LOI" not in text


def test_subprocess_env_includes_src(monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    env = tr._subprocess_env()
    assert str(tr.ROOT / "src") in env["PYTHONPATH"]
    monkeypatch.setenv("PYTHONPATH", "/mot/duong/dan")
    env = tr._subprocess_env()
    assert env["PYTHONPATH"].startswith(str(tr.ROOT / "src"))
    assert "/mot/duong/dan" in env["PYTHONPATH"]

# --- mt5.symbol_suffix: map symbol chuan -> ten broker (Trial *m) --------
# Cac fake nay cai dat DUNG hop dong cua mt5_feed (resolve_mt5_symbol /
# build_symbol_map) de test phan noi cua test_run, khong phu thuoc vao
# viec ham that da co trong mt5_feed hay chua.
from types import SimpleNamespace

import pytest


def _fake_resolve_mt5_symbol(symbol, server, suffix=None):
    if suffix is not None:
        return symbol + suffix
    if "trial" in (server or "").lower():
        return symbol + "m"
    return symbol


def _fake_build_symbol_map(mt5, symbols, server, suffix=None):
    out = {}
    for sym in symbols:
        out[sym] = None
        for cand in (_fake_resolve_mt5_symbol(sym, server, suffix), sym):
            if mt5.symbol_info(cand) is not None:
                out[sym] = cand
                break
    return out


class _FakeMT5Symbols:
    """Fake MT5 chi biet symbol_info (True neu ten co trong tap hop)."""

    def __init__(self, available):
        self.available = set(available)

    def symbol_info(self, name):
        return SimpleNamespace(name=name) if name in self.available else None


class _ListLog:
    """Log gia chi thu dong log (de test check_demo_symbol_map)."""

    def __init__(self):
        self.lines = []

    def log(self, msg=""):
        self.lines.append(str(msg))


def _install_fake_symbol_map(monkeypatch):
    from diamondx10.data import mt5_feed
    monkeypatch.setattr(mt5_feed, "resolve_mt5_symbol",
                        _fake_resolve_mt5_symbol, raising=False)
    monkeypatch.setattr(mt5_feed, "build_symbol_map",
                        _fake_build_symbol_map, raising=False)


_SYMBOLS_CFG = {
    "forex": ["EURUSD"],
    "xauusd": ["XAUUSD"],
    "crypto": ["BTCUSD"],
    "us_securities": ["NVDA"],
}


@pytest.mark.parametrize("cfg, expected", [
    ({}, None),
    ({"mt5": {}}, None),
    ({"mt5": {"symbol_suffix": "auto"}}, None),
    ({"mt5": {"symbol_suffix": "AUTO"}}, None),
    ({"mt5": {"symbol_suffix": None}}, None),
    ({"mt5": {"symbol_suffix": "m"}}, "m"),
    ({"mt5": {"symbol_suffix": ""}}, ""),
])
def test_mt5_symbol_suffix(cfg, expected):
    assert tr._mt5_symbol_suffix(cfg) == expected


def test_check_demo_symbol_map_trial_only_m(monkeypatch):
    _install_fake_symbol_map(monkeypatch)
    log = _ListLog()
    mapping, missing = tr.check_demo_symbol_map(
        _FakeMT5Symbols(["EURUSDm", "XAUUSDm", "BTCUSDm", "NVDAm"]),
        _SYMBOLS_CFG, "Exness-MT5Trial7", None, log=log)
    assert missing == []
    assert mapping == {"EURUSD": "EURUSDm", "XAUUSD": "XAUUSDm",
                       "BTCUSD": "BTCUSDm", "NVDA": "NVDAm"}
    assert "  EURUSD -> EURUSDm (desk forex)" in log.lines
    assert "  XAUUSD -> XAUUSDm (desk xauusd)" in log.lines
    assert "  BTCUSD -> BTCUSDm (desk crypto)" in log.lines


def test_check_demo_symbol_map_real_no_suffix(monkeypatch):
    _install_fake_symbol_map(monkeypatch)
    log = _ListLog()
    mapping, missing = tr.check_demo_symbol_map(
        _FakeMT5Symbols(["EURUSD", "XAUUSD", "BTCUSD", "NVDA"]),
        _SYMBOLS_CFG, "Exness-MT5Real", None, log=log)
    assert missing == []
    assert mapping["EURUSD"] == "EURUSD"
    assert "  EURUSD -> EURUSD (desk forex)" in log.lines
    assert not any("EURUSDm" in ln for ln in log.lines)


def test_check_demo_symbol_map_explicit_suffix_overrides_server(monkeypatch):
    _install_fake_symbol_map(monkeypatch)
    mapping, missing = tr.check_demo_symbol_map(
        _FakeMT5Symbols(["EURUSDm", "XAUUSDm", "BTCUSDm", "NVDAm"]),
        _SYMBOLS_CFG, "Exness-MT5Real", "m")
    assert missing == []
    assert mapping["EURUSD"] == "EURUSDm"


def test_check_demo_symbol_map_missing_names_both_tried(monkeypatch):
    _install_fake_symbol_map(monkeypatch)
    log = _ListLog()
    mapping, missing = tr.check_demo_symbol_map(
        _FakeMT5Symbols([]), _SYMBOLS_CFG, "Exness-MT5Trial7", None,
        log=log)
    assert mapping["EURUSD"] is None
    assert ("EURUSD", "forex", ["EURUSDm", "EURUSD"]) in missing
    # Chuoi loi buoc 3 phai neu ca 2 ten da thu + ten server.
    detail = tr._missing_symbols_detail(missing, "Exness-MT5Trial7")
    assert "EURUSDm" in detail and "EURUSD" in detail
    assert "Exness-MT5Trial7" in detail
    assert "desk forex" in detail
    assert any("EURUSDm" in ln and "EURUSD" in ln for ln in log.lines)


def test_mt5_feed_for_symbol_passes_suffix(monkeypatch):
    from diamondx10.data import mt5_feed

    seen = {}

    class FakeFeed:
        def __init__(self, symbol, login=None, server=None, path=None,
                     symbol_suffix=None, **kwargs):
            seen.update(symbol=symbol, login=login, server=server,
                        path=path, symbol_suffix=symbol_suffix)

    monkeypatch.setattr(mt5_feed, "MT5Feed", FakeFeed)
    cfg = {"mt5": {"login": 987654321, "server": "Exness-MT5Trial7",
                   "symbol_suffix": "auto"}}
    tr._mt5_feed_for_symbol("EURUSD", cfg, "/tmp/terminal64.exe")
    assert seen["symbol"] == "EURUSD"
    assert seen["login"] == 987654321
    assert seen["server"] == "Exness-MT5Trial7"
    assert seen["path"] == "/tmp/terminal64.exe"
    assert seen["symbol_suffix"] is None  # "auto" -> None

    cfg["mt5"]["symbol_suffix"] = "m"
    tr._mt5_feed_for_symbol("EURUSD", cfg, None)
    assert seen["symbol_suffix"] == "m"

    cfg["mt5"]["symbol_suffix"] = ""
    tr._mt5_feed_for_symbol("EURUSD", cfg, None)
    assert seen["symbol_suffix"] == ""

# --- Tich hop API THAT cua mt5_feed (khong fake map) -----------------------
def test_check_demo_symbol_map_real_api_trial():
    """Dung build_symbol_map THAT: Trial chi co *m -> map dung."""
    log = _ListLog()
    mapping, missing = tr.check_demo_symbol_map(
        _FakeMT5Symbols(["EURUSDm", "XAUUSDm", "BTCUSDm", "NVDAm"]),
        _SYMBOLS_CFG, "Exness-MT5Trial7", None, log=log)
    assert missing == []
    assert mapping["EURUSD"] == "EURUSDm"
    assert "  EURUSD -> EURUSDm (desk forex)" in log.lines


class _FakeMT5TerminalTrial:
    """Terminal MT5 gia: server Trial, chi co symbol *m, tai khoan DEMO."""

    AVAILABLE = {"EURUSDm", "XAUUSDm", "BTCUSDm", "BNBUSDm", "ETHUSDm",
                 "AMDm", "CDNSm", "SNPSm", "INTCm", "NVDAm"}

    def initialize(self, path=None):
        return True

    def login(self, login, password=None, server=None):
        return True

    def account_info(self):
        return SimpleNamespace(login=987654321, server="Exness-MT5Trial7",
                               balance=10000.0, trade_mode=0)

    def symbol_info(self, name):
        return SimpleNamespace(name=name) if name in self.AVAILABLE else None

    def symbol_select(self, name, enable):
        return name in self.AVAILABLE

    def last_error(self):
        return (0, "ok")

    def shutdown(self):
        return True


def test_mt5_feed_for_symbol_real_mt5feed_trial(monkeypatch):
    """_mt5_feed_for_symbol qua MT5Feed THAT: EURUSD -> EURUSDm."""
    from diamondx10.data import mt5_feed

    monkeypatch.setattr(mt5_feed, "load_mt5",
                        lambda mt5_module=None: _FakeMT5TerminalTrial())
    cfg = {"mt5": {"login": 987654321, "server": "Exness-MT5Trial7",
                   "symbol_suffix": "auto"}}
    feed = tr._mt5_feed_for_symbol("EURUSD", cfg, None)
    try:
        assert feed.symbol == "EURUSD"
        assert feed.symbol_suffix is None
        assert feed.broker_symbol("EURUSD") == "EURUSDm"
    finally:
        feed.close()
