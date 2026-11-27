"""Test tim terminal MT5 (auto-scan) — khong can terminal that, khong can
mang: gia lap Windows bang monkeypatch mt5_feed._is_windows (True) +
bien moi truong tro toi thu muc tam.

(Luu y: KHONG gia lap bang monkeypatch os.name="nt" — pathlib khoa
WindowsPath.__new__ theo os.name LUC IMPORT pathlib, nen tren Linux
ma os.name bi doi thi moi phep Path / "con" deu raise
NotImplementedError. _is_windows() doc os.name luc goi nen la diem
gia lap dung — xem mt5_feed.py.)
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from diamondx10.data import mt5_feed as mt5_feed_mod
from diamondx10.data.mt5_feed import (
    KNOWN_TERMINAL_PATHS,
    MT5Feed,
    find_mt5_terminal,
    resolve_mt5_terminal_path,
)
from diamondx10.data.providers import build_feed

REPO_ROOT = Path(__file__).resolve().parent.parent


class _FakeMT5:
    """MT5 gia, ghi lai duong dan truyen vao initialize()."""

    TIMEFRAME_M15 = 15

    def __init__(self, ok=True):
        self.ok = ok
        self.init_path = "NOT-CALLED"
        self.init_calls = []

    def initialize(self, path=None):
        self.init_path = path
        self.init_calls.append(path)
        return self.ok

    def login(self, login, password=None, server=None):
        return True

    def last_error(self):
        return (0, "ok")

    def symbol_info(self, symbol):
        return SimpleNamespace(name=symbol)

    def symbol_select(self, symbol, enable):
        return True

    def shutdown(self):
        return True


@pytest.fixture
def win_roots(tmp_path, monkeypatch):
    """Gia lap Windows: _is_windows() -> True + 4 bien moi truong goc
    tro ve thu muc tam (trong, chua co terminal)."""
    monkeypatch.setattr(mt5_feed_mod, "_is_windows", lambda: True)
    monkeypatch.delenv("MT5_TERMINAL_PATH", raising=False)
    roots = {
        "pf": tmp_path / "ProgramFiles",
        "pfx86": tmp_path / "Program Files (x86)",
        "local": tmp_path / "Local",
    }
    for d in roots.values():
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ProgramFiles", str(roots["pf"]))
    monkeypatch.setenv("ProgramFiles(x86)", str(roots["pfx86"]))
    monkeypatch.setenv("ProgramW6432", str(roots["pf"]))
    monkeypatch.setenv("LOCALAPPDATA", str(roots["local"]))
    return roots


def _make_terminal(base, folder):
    """Tao file terminal64.exe gia trong base/folder, tra duong dan."""
    p = Path(base) / folder / "terminal64.exe"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    return p


# --- find_mt5_terminal: duong dan da biet -------------------------------
def test_known_paths_user_exness_first():
    assert KNOWN_TERMINAL_PATHS[0] == "MetaTrader 5 EXNESS/terminal64.exe"
    assert KNOWN_TERMINAL_PATHS[1] == "MetaTrader 5/terminal64.exe"


def test_find_exact_exness_folder(win_roots):
    pf = win_roots["pf"]
    _make_terminal(pf, "MetaTrader 5")
    exness = _make_terminal(pf, "MetaTrader 5 EXNESS")
    assert find_mt5_terminal() == exness


def test_find_falls_back_to_program_files_x86(win_roots):
    exness = _make_terminal(win_roots["pfx86"], "MetaTrader 5 EXNESS")
    assert find_mt5_terminal() == exness


def test_find_returns_none_when_nothing_exists(win_roots):
    assert find_mt5_terminal() is None


def test_find_none_on_non_windows(tmp_path, monkeypatch):
    # Khong gia lap Windows: tren Linux that, du co terminal trong
    # thu muc goc thi van tra None.
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    _make_terminal(tmp_path, "MetaTrader 5 EXNESS")
    assert find_mt5_terminal() is None


def test_find_with_explicit_search_roots(tmp_path, monkeypatch):
    monkeypatch.setattr(mt5_feed_mod, "_is_windows", lambda: True)
    exness = _make_terminal(tmp_path, "MetaTrader 5 EXNESS")
    assert find_mt5_terminal(search_roots=[tmp_path]) == exness


# --- find_mt5_terminal: quet 1 cap ---------------------------------------
def test_find_scan_prefers_exness_folder(win_roots):
    pf = win_roots["pf"]
    _make_terminal(pf, "Some MT5 Pro")
    _make_terminal(pf, "MetaTrader Clone")
    exness = _make_terminal(pf, "Acme Exness Tools")
    assert find_mt5_terminal() == exness


def test_find_scan_prefers_metatrader_over_mt5(win_roots):
    pf = win_roots["pf"]
    _make_terminal(pf, "Some MT5 Pro")
    mt = _make_terminal(pf, "MetaTrader Clone")
    assert find_mt5_terminal() == mt


def test_find_scan_ignores_unrelated_folder(win_roots):
    _make_terminal(win_roots["pf"], "Random Broker")
    assert find_mt5_terminal() is None


# --- resolve_mt5_terminal_path: ghi de env / config -----------------------
def test_resolve_env_override_wins_over_scan(win_roots, tmp_path, monkeypatch):
    _make_terminal(win_roots["pf"], "MetaTrader 5 EXNESS")
    custom = tmp_path / "custom" / "terminal64.exe"
    custom.parent.mkdir(parents=True, exist_ok=True)
    custom.write_bytes(b"")
    monkeypatch.setenv("MT5_TERMINAL_PATH", str(custom))
    assert resolve_mt5_terminal_path() == custom


def test_resolve_config_terminal_path_wins_over_scan(win_roots, tmp_path):
    _make_terminal(win_roots["pf"], "MetaTrader 5 EXNESS")
    custom = tmp_path / "custom" / "terminal64.exe"
    custom.parent.mkdir(parents=True, exist_ok=True)
    custom.write_bytes(b"")
    cfg = {"mt5": {"terminal_path": str(custom)}}
    assert resolve_mt5_terminal_path(cfg=cfg) == custom


def test_resolve_env_beats_config(win_roots, tmp_path, monkeypatch):
    env_path = tmp_path / "env" / "terminal64.exe"
    cfg_path = tmp_path / "cfg" / "terminal64.exe"
    for p in (env_path, cfg_path):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")
    monkeypatch.setenv("MT5_TERMINAL_PATH", str(env_path))
    cfg = {"mt5": {"terminal_path": str(cfg_path)}}
    assert resolve_mt5_terminal_path(cfg=cfg) == env_path


def test_resolve_missing_override_falls_back_to_scan(win_roots, monkeypatch):
    exness = _make_terminal(win_roots["pf"], "MetaTrader 5 EXNESS")
    monkeypatch.setenv("MT5_TERMINAL_PATH", "/khong/co/file/terminal64.exe")
    assert resolve_mt5_terminal_path() == exness


def test_resolve_none_when_nothing(win_roots):
    assert resolve_mt5_terminal_path() is None
    assert resolve_mt5_terminal_path(cfg={"mt5": {"terminal_path": ""}}) is None


# --- MT5Feed: truyen path qua initialize() --------------------------------
def test_mt5feed_passes_explicit_path(tmp_path):
    fake = _FakeMT5()
    custom = tmp_path / "terminal64.exe"
    custom.write_bytes(b"")
    feed = MT5Feed("EURUSD", login=123, server="Exness-MT5Trial7",
                   mt5_module=fake, path=custom)
    assert fake.init_path == str(custom)
    assert feed.terminal_path == custom


def test_mt5feed_auto_scans_on_windows(win_roots):
    fake = _FakeMT5()
    exness = _make_terminal(win_roots["pf"], "MetaTrader 5 EXNESS")
    feed = MT5Feed("EURUSD", login=123, server="Exness-MT5Trial7",
                   mt5_module=fake)
    assert fake.init_path == str(exness)
    assert feed.terminal_path == exness


def test_mt5feed_plain_initialize_when_no_path_on_linux():
    fake = _FakeMT5()
    MT5Feed("EURUSD", login=123, server="Exness-MT5Trial7", mt5_module=fake)
    assert fake.init_path is None


def test_mt5feed_configured_path_failure_raises_no_fallback(tmp_path):
    fake = _FakeMT5(ok=False)
    custom = tmp_path / "terminal64.exe"
    custom.write_bytes(b"")
    with pytest.raises(ConnectionError, match="terminal_path"):
        MT5Feed("EURUSD", login=123, server="Exness-MT5Trial7",
                mt5_module=fake, path=custom)
    # Chi goi initialize(path=...) 1 lan — KHONG tu doi sang
    # initialize() khong duong dan.
    assert fake.init_calls == [str(custom)]


def test_mt5feed_configured_path_failure_message_guides_user(tmp_path):
    fake = _FakeMT5(ok=False)
    custom = tmp_path / "terminal64.exe"
    custom.write_bytes(b"")
    with pytest.raises(ConnectionError, match="quickstart"):
        MT5Feed("EURUSD", login=123, server="Exness-MT5Trial7",
                mt5_module=fake, path=custom)


# --- build_feed: truyen terminal_path tu config ----------------------------
def test_build_feed_passes_config_terminal_path(tmp_path):
    fake = _FakeMT5()
    custom = tmp_path / "terminal64.exe"
    custom.write_bytes(b"")
    cfg = {"data": {"provider": "mt5", "symbols": {"forex": ["EURUSD"]}},
           "mt5": {"login": 123, "server": "Exness-MT5Trial7",
                   "terminal_path": str(custom)}}
    feed = build_feed(cfg, "forex", mt5_module=fake)
    assert feed.symbol == "EURUSD"
    assert fake.init_path == str(custom)


# --- config.example.yaml ---------------------------------------------------
def test_config_example_has_empty_terminal_path():
    with open(REPO_ROOT / "config.example.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg["mt5"]["terminal_path"] == ""
