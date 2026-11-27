"""Test quickstart.py — chi test cac ham thuan / kiem tra, khong chay
lenh tuong tac hay pip install that."""

import importlib.util
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_quickstart():
    spec = importlib.util.spec_from_file_location(
        "quickstart_under_test", REPO_ROOT / "quickstart.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


qs = load_quickstart()


# --- parse_login ------------------------------------------------------
@pytest.mark.parametrize("raw, expected", [
    ("987654321", 987654321),
    ("  123  ", 123),
    ("", None),
    ("abc", None),
    ("12.3", None),
    ("123abc", None),
])
def test_parse_login(raw, expected):
    assert qs.parse_login(raw) == expected


# --- is_supported_python ----------------------------------------------
@pytest.mark.parametrize("version, expected", [
    ((3, 10), True),
    ((3, 11), True),
    ((3, 12), True),
    ((3, 9), False),
    ((2, 7), False),
])
def test_is_supported_python(version, expected):
    assert qs.is_supported_python(version) is expected


# --- find_mt5_terminal -------------------------------------------------
def test_find_mt5_terminal_none_on_linux(monkeypatch):
    monkeypatch.setattr(qs.os, "name", "posix")
    assert qs.find_mt5_terminal() is None


def test_find_mt5_terminal_is_package_function():
    """quickstart dung 1 ham duy nhat trong package, khong viet lai."""
    assert qs.find_mt5_terminal.__module__ == "diamondx10.data.mt5_feed"
    assert (qs.resolve_mt5_terminal_path.__module__
            == "diamondx10.data.mt5_feed")


# --- check_terminal (fake mt5 module) ----------------------------------
class _FakeMT5Ok:
    def __init__(self):
        self.shutdown_called = False
        self.init_path = "NOT-CALLED"

    def initialize(self, path=None):
        self.init_path = path
        return True

    def terminal_info(self):
        return None

    def shutdown(self):
        self.shutdown_called = True


class _FakeMT5Fail:
    def initialize(self, path=None):
        return False


class _FakeMT5Error:
    def initialize(self, path=None):
        raise RuntimeError("no terminal")


def test_check_terminal_ok():
    fake = _FakeMT5Ok()
    ok, msg = qs.check_terminal(fake)
    assert ok is True
    assert "Noi duoc" in msg
    assert fake.shutdown_called is True
    assert fake.init_path is None


def test_check_terminal_passes_path_to_initialize():
    fake = _FakeMT5Ok()
    ok, msg = qs.check_terminal(fake, path="/tmp/x/terminal64.exe")
    assert ok is True
    assert fake.init_path == "/tmp/x/terminal64.exe"


def test_check_terminal_passes_path_object():
    fake = _FakeMT5Ok()
    ok, _msg = qs.check_terminal(fake, path=Path("/tmp/x/terminal64.exe"))
    assert ok is True
    assert fake.init_path == "/tmp/x/terminal64.exe"


def test_check_terminal_initialize_false():
    ok, msg = qs.check_terminal(_FakeMT5Fail())
    assert ok is False
    assert "Khong noi duoc" in msg


def test_check_terminal_initialize_raises():
    ok, msg = qs.check_terminal(_FakeMT5Error())
    assert ok is False
    assert "loi" in msg


def test_check_terminal_no_module(monkeypatch):
    # Tren Linux khong co goi MetaTrader5 that -> ImportError -> False.
    ok, msg = qs.check_terminal(None)
    assert ok is False


# --- _write_config (khong ghi mat khau) --------------------------------
def test_write_config_no_password(tmp_path, monkeypatch):
    shutil.copy(REPO_ROOT / "config.example.yaml",
                tmp_path / "config.example.yaml")
    monkeypatch.setattr(qs, "ROOT", tmp_path)
    qs._write_config("Exness-MT5Trial6", 123456789)
    text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert "provider: mt5" in text
    assert "login: 123456789" in text
    assert 'server: "Exness-MT5Trial6"' in text
    # Khong co gia tri mat khau nao: chi duoc co ten bien moi truong
    # (password_env: MT5_PASSWORD), khong co dong "password: <gia tri>".
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("password:"):
            assert stripped in ("password:", "password: ''", 'password: ""'), line
    assert "987654321" not in text


# --- quickstart.bat ------------------------------------------------------
def test_quickstart_bat_bootstraps_python():
    """quickstart.bat phai ton tai va tu lo duoc Python: tim python san,
    neu khong co thi cai qua winget hoac tai tu python.org, roi chay
    quickstart.py kem tham so nguoi dung truyen."""
    bat = (REPO_ROOT / "quickstart.bat").read_text(encoding="utf-8")
    assert "winget" in bat
    assert "python.org/ftp/python" in bat
    assert "quickstart.py" in bat
    assert "%*" in bat
    assert "(3, 10)" in bat
    assert "InstallAllUsers=0" in bat

# --- Telegram: giu lai cai dat + cap nhat muc telegram --------------------
def test_apply_telegram_to_config_text_replaces_block():
    text = ("data:\n  provider: mt5\ntelegram:\n  enabled: false\n"
            "  chat_id: \"\"\n  bot_token_env: DIAMONDX10_TELEGRAM_TOKEN\n"
            "other:\n  x: 1\n")
    out = qs._apply_telegram_to_config_text(text, True, "1234567890")
    assert "  enabled: true" in out
    assert '  chat_id: "1234567890"' in out
    assert "  provider: mt5" in out
    assert "  x: 1" in out
    assert out.count("telegram:") == 1


def test_apply_telegram_to_config_text_appends_when_missing():
    text = "fund:\n  name: DiamondX10\n"
    out = qs._apply_telegram_to_config_text(text, True, "123")
    assert out.count("telegram:") == 1
    assert '  chat_id: "123"' in out
    assert "fund:\n  name: DiamondX10" in out


def test_write_config_preserves_telegram(tmp_path, monkeypatch):
    shutil.copy(REPO_ROOT / "config.example.yaml",
                tmp_path / "config.example.yaml")
    monkeypatch.setattr(qs, "ROOT", tmp_path)
    qs._write_config("Exness-MT5Trial6", 123456789, True, "1234567890")
    text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert "  enabled: true" in text
    assert '  chat_id: "1234567890"' in text


# --- _write_config: ghi terminal_path (dau /) ------------------------------
def test_write_config_writes_terminal_path_forward_slashes(tmp_path, monkeypatch):
    shutil.copy(REPO_ROOT / "config.example.yaml",
                tmp_path / "config.example.yaml")
    monkeypatch.setattr(qs, "ROOT", tmp_path)
    qs._write_config("Exness-MT5Trial6", 123456789, terminal_path=
                     "C:\\Program Files\\MetaTrader 5 EXNESS\\terminal64.exe")
    text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert ('terminal_path: "C:/Program Files/MetaTrader 5 '
            'EXNESS/terminal64.exe"') in text
    assert "terminal_path: \"\"" not in text
    assert "\\" not in [ln for ln in text.splitlines()
                        if "terminal_path" in ln][0]


def test_write_config_no_terminal_path_leaves_default(tmp_path, monkeypatch):
    shutil.copy(REPO_ROOT / "config.example.yaml",
                tmp_path / "config.example.yaml")
    monkeypatch.setattr(qs, "ROOT", tmp_path)
    qs._write_config("Exness-MT5Trial6", 123456789)
    text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert 'terminal_path: ""' in text


def test_apply_terminal_path_to_config_text_inserts_when_missing():
    text = "mt5:\n  login: 123\n  timeframe: M15\n"
    out = qs._apply_terminal_path_to_config_text(
        text, "C:\\Program Files\\MetaTrader 5 EXNESS\\terminal64.exe")
    assert ('terminal_path: "C:/Program Files/MetaTrader 5 '
            'EXNESS/terminal64.exe"') in out
    assert out.count("terminal_path:") == 1


def test_apply_terminal_path_to_config_text_adds_mt5_block():
    text = "fund:\n  name: DiamondX10\n"
    out = qs._apply_terminal_path_to_config_text(text, "/tmp/terminal64.exe")
    assert out.count("mt5:") == 1
    assert 'terminal_path: "/tmp/terminal64.exe"' in out


def test_update_telegram_config_patches_only_telegram(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("mt5:\n  login: 123\n  server: \"Exness-MT5Trial6\"\n",
                        encoding="utf-8")
    monkeypatch.setattr(qs, "ROOT", tmp_path)
    qs._update_telegram_config("1234567890")
    text = cfg_path.read_text(encoding="utf-8")
    assert "  login: 123" in text
    assert '  chat_id: "1234567890"' in text
    assert "  enabled: true" in text


def test_read_existing_config_reads_telegram(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "mt5:\n  login: 123\n  server: \"Exness-MT5Trial6\"\n"
        "telegram:\n  enabled: true\n  chat_id: \"1234567890\"\n",
        encoding="utf-8")
    monkeypatch.setattr(qs, "ROOT", tmp_path)
    login, server, tg_enabled, tg_chat_id = qs._read_existing_config()
    assert login == "123"
    assert server == "Exness-MT5Trial6"
    assert tg_enabled is True
    assert tg_chat_id == "1234567890"


# --- _run_cli: tien trinh con phai thay duoc package ----------------------
def test_run_cli_sets_pythonpath(monkeypatch):
    seen = {}

    class FakeResult:
        returncode = 0

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["env"] = kwargs.get("env") or {}
        return FakeResult()

    monkeypatch.setattr(qs.subprocess, "run", fake_run)
    assert qs._run_cli(["report"]) == 0
    assert seen["argv"][1] == "-m" and seen["argv"][2] == "diamondx10"
    pythonpath = seen["env"].get("PYTHONPATH", "")
    assert str(qs.ROOT / "src") in pythonpath


# --- _child_env / _run_test_suite -----------------------------------------
def test_child_env_includes_src(monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    env = qs._child_env()
    assert str(qs.ROOT / "src") in env["PYTHONPATH"]
    monkeypatch.setenv("PYTHONPATH", "/mot/duong/dan")
    env = qs._child_env()
    assert env["PYTHONPATH"].startswith(str(qs.ROOT / "src"))
    assert "/mot/duong/dan" in env["PYTHONPATH"]


def test_run_test_suite_returns_code(monkeypatch):
    seen = {}

    class FakeResult:
        def __init__(self, rc):
            self.returncode = rc

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return FakeResult(0)

    monkeypatch.setattr(qs.subprocess, "run", fake_run)
    assert qs._run_test_suite() == 0
    assert seen["argv"][1].endswith("test_run.py")

    def fake_run_fail(argv, **kwargs):
        return FakeResult(1)

    monkeypatch.setattr(qs.subprocess, "run", fake_run_fail)
    assert qs._run_test_suite() == 1

# --- mt5.symbol_suffix: map symbol chuan -> ten broker (Trial *m) --------
# Cac fake nay cai dat DUNG hop dong cua mt5_feed (resolve_mt5_symbol /
# build_symbol_map) de test phan noi cua quickstart, khong phu thuoc
# vao viec ham that da co trong mt5_feed hay chua.
from types import SimpleNamespace

import yaml


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


def _install_fake_symbol_map(monkeypatch):
    from diamondx10.data import mt5_feed
    monkeypatch.setattr(mt5_feed, "resolve_mt5_symbol",
                        _fake_resolve_mt5_symbol, raising=False)
    monkeypatch.setattr(mt5_feed, "build_symbol_map",
                        _fake_build_symbol_map, raising=False)


_CFG_SYMBOLS = {"data": {"symbols": {
    "forex": ["EURUSD"],
    "xauusd": ["XAUUSD"],
    "crypto": ["BTCUSD"],
    "us_securities": ["NVDA"],
}}}
_ALL_M = ["EURUSDm", "XAUUSDm", "BTCUSDm", "NVDAm"]
_ALL_CANON = ["EURUSD", "XAUUSD", "BTCUSD", "NVDA"]


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
    assert qs._mt5_symbol_suffix(cfg) == expected


def test_check_demo_symbols_trial_only_m(monkeypatch, capsys):
    _install_fake_symbol_map(monkeypatch)
    feed = SimpleNamespace(mt5=_FakeMT5Symbols(_ALL_M))
    mapping, missing = qs.check_demo_symbols(
        feed, _CFG_SYMBOLS, "Exness-MT5Trial7", None)
    assert missing == []
    assert mapping == {"EURUSD": "EURUSDm", "XAUUSD": "XAUUSDm",
                       "BTCUSD": "BTCUSDm", "NVDA": "NVDAm"}
    out = capsys.readouterr().out
    assert "[co] EURUSD -> EURUSDm (desk forex)" in out
    assert "[co] XAUUSD -> XAUUSDm (desk xauusd)" in out
    assert "[co] BTCUSD -> BTCUSDm (desk crypto)" in out
    assert "[co] NVDA -> NVDAm (desk us_securities)" in out


def test_check_demo_symbols_real_no_suffix(monkeypatch, capsys):
    _install_fake_symbol_map(monkeypatch)
    feed = SimpleNamespace(mt5=_FakeMT5Symbols(_ALL_CANON))
    mapping, missing = qs.check_demo_symbols(
        feed, _CFG_SYMBOLS, "Exness-MT5Real", None)
    assert missing == []
    assert mapping["EURUSD"] == "EURUSD"
    out = capsys.readouterr().out
    assert "[co] EURUSD -> EURUSD (desk forex)" in out
    assert "EURUSDm" not in out


def test_check_demo_symbols_explicit_suffix_overrides_server(
        monkeypatch, capsys):
    _install_fake_symbol_map(monkeypatch)
    feed = SimpleNamespace(mt5=_FakeMT5Symbols(_ALL_M))
    mapping, missing = qs.check_demo_symbols(
        feed, _CFG_SYMBOLS, "Exness-MT5Real", "m")
    assert missing == []
    assert mapping["EURUSD"] == "EURUSDm"
    out = capsys.readouterr().out
    assert "[co] EURUSD -> EURUSDm (desk forex)" in out


def test_check_demo_symbols_missing_names_both_tried(monkeypatch, capsys):
    _install_fake_symbol_map(monkeypatch)
    feed = SimpleNamespace(mt5=_FakeMT5Symbols([]))
    mapping, missing = qs.check_demo_symbols(
        feed, _CFG_SYMBOLS, "Exness-MT5Trial7", None)
    assert mapping["EURUSD"] is None
    assert "EURUSD" in missing
    out = capsys.readouterr().out
    assert "[THIEU] EURUSD (desk forex)" in out
    # Loi phai neu ca 2 ten da thu + ten server.
    assert "EURUSDm" in out and "EURUSD" in out
    assert "Exness-MT5Trial7" in out


def test_write_config_preserves_symbol_suffix(tmp_path, monkeypatch):
    shutil.copy(REPO_ROOT / "config.example.yaml",
                tmp_path / "config.example.yaml")
    monkeypatch.setattr(qs, "ROOT", tmp_path)
    qs._write_config("Exness-MT5Trial6", 123456789)
    text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert 'symbol_suffix: "auto"' in text
    # Danh sach symbol chuan khong doi.
    assert 'forex: ["EURUSD"]' in text
    assert 'crypto: ["BTCUSD", "BNBUSD", "ETHUSD"]' in text


# --- main() buoc 5: Trial chi co *m -> pass, truyen symbol_suffix -------
class _FakeMT5FeedTrial:
    """MT5Feed gia: chi co symbol *m, tai khoan DEMO, ghi lai kwargs."""

    seen = []

    def __init__(self, symbol, login=None, password=None, server=None,
                 timeframe="M15", mt5_module=None, path=None,
                 symbol_suffix=None):
        self.symbol = symbol
        self.login = login
        self.server = server
        self.symbol_suffix = symbol_suffix
        self.mt5 = _FakeMT5Symbols(
            ["EURUSDm", "XAUUSDm", "BTCUSDm", "BNBUSDm", "ETHUSDm",
             "AMDm", "CDNSm", "SNPSm", "INTCm", "NVDAm"])
        type(self).seen.append(self)

    def account_info(self):
        return SimpleNamespace(login=987654321, server="Exness-MT5Trial7",
                               balance=10000.0, trade_mode=0)

    def close(self):
        pass


def test_main_step5_trial_only_m_symbols_pass(monkeypatch, tmp_path, capsys):
    _install_fake_symbol_map(monkeypatch)
    from diamondx10.data import mt5_feed
    import diamondx10.config as config_mod

    shutil.copy(REPO_ROOT / "config.example.yaml",
                tmp_path / "config.example.yaml")
    monkeypatch.setattr(qs, "ROOT", tmp_path)
    monkeypatch.setattr(qs, "_pip_install", lambda *a, **k: True)
    monkeypatch.setattr(qs, "_ensure_pip", lambda: None)
    monkeypatch.setattr(qs, "check_terminal",
                        lambda mt5_module=None, path=None: (True, "ok"))
    monkeypatch.setattr(qs, "resolve_mt5_terminal_path",
                        lambda cfg=None: None)
    monkeypatch.setattr(qs, "_run_cli", lambda argv: 0)

    def fake_ask(prompt, default=None):
        if "Server" in prompt:
            return "Exness-MT5Trial7"
        if "login" in prompt.lower():
            return "987654321"
        return ""

    monkeypatch.setattr(qs, "_ask", fake_ask)
    monkeypatch.setattr(qs, "_ask_password", lambda *a, **k: "mat-khau-gia")
    monkeypatch.setattr(qs, "_ask_secret", lambda *a, **k: "")
    monkeypatch.setattr(mt5_feed, "MT5Feed", _FakeMT5FeedTrial)

    def fake_load_config(path=None):
        cfg_path = Path(path) if path is not None else tmp_path / "config.yaml"
        if not cfg_path.exists():
            return {}
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    monkeypatch.setattr(config_mod, "load_config", fake_load_config)
    _FakeMT5FeedTrial.seen.clear()
    old_pw = qs.os.environ.get("MT5_PASSWORD")
    try:
        rc = qs.main(["--skip-install", "--skip-tests"])
    finally:
        if old_pw is None:
            qs.os.environ.pop("MT5_PASSWORD", None)
        else:
            qs.os.environ["MT5_PASSWORD"] = old_pw
    out = capsys.readouterr().out
    assert rc == 0
    # Buoc 5 pass tren Trial chi co *m, in dung mapping tim duoc.
    assert "[co] EURUSD -> EURUSDm (desk forex)" in out
    assert "[co] XAUUSD -> XAUUSDm (desk xauusd)" in out
    assert "[co] BTCUSD -> BTCUSDm (desk crypto)" in out
    # MT5Feed nhan symbol_suffix None (auto) tu config.
    assert _FakeMT5FeedTrial.seen, "buoc 5 chua tao MT5Feed"
    assert _FakeMT5FeedTrial.seen[0].symbol_suffix is None
    # Config local ghi ra giu symbol_suffix mac dinh.
    text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert 'symbol_suffix: "auto"' in text

# --- Tich hop API THAT cua mt5_feed (khong fake map) -----------------------
def test_check_demo_symbols_real_api_trial(capsys):
    """Dung build_symbol_map THAT: Trial chi co *m -> map dung."""
    feed = SimpleNamespace(mt5=_FakeMT5Symbols(_ALL_M))
    mapping, missing = qs.check_demo_symbols(
        feed, _CFG_SYMBOLS, "Exness-MT5Trial7", None)
    assert missing == []
    assert mapping["EURUSD"] == "EURUSDm"
    out = capsys.readouterr().out
    assert "[co] EURUSD -> EURUSDm (desk forex)" in out


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


def test_main_step5_real_mt5feed_trial_only_m(monkeypatch, tmp_path, capsys):
    """Buoc 5 qua MT5Feed THAT + build_symbol_map THAT.

    Terminal gia chi co *m; MT5Feed that phai tu doi EURUSD -> EURUSDm
    (symbol_suffix=None = auto theo server Trial) neu khong buoc 5
    da loi ValueError o symbol chuan.
    """
    from diamondx10.data import mt5_feed
    import diamondx10.config as config_mod

    shutil.copy(REPO_ROOT / "config.example.yaml",
                tmp_path / "config.example.yaml")
    monkeypatch.setattr(qs, "ROOT", tmp_path)
    monkeypatch.setattr(qs, "_pip_install", lambda *a, **k: True)
    monkeypatch.setattr(qs, "_ensure_pip", lambda: None)
    monkeypatch.setattr(qs, "check_terminal",
                        lambda mt5_module=None, path=None: (True, "ok"))
    monkeypatch.setattr(qs, "resolve_mt5_terminal_path",
                        lambda cfg=None: None)
    monkeypatch.setattr(qs, "_run_cli", lambda argv: 0)

    def fake_ask(prompt, default=None):
        if "Server" in prompt:
            return "Exness-MT5Trial7"
        if "login" in prompt.lower():
            return "987654321"
        return ""

    monkeypatch.setattr(qs, "_ask", fake_ask)
    monkeypatch.setattr(qs, "_ask_password", lambda *a, **k: "mat-khau-gia")
    monkeypatch.setattr(qs, "_ask_secret", lambda *a, **k: "")
    monkeypatch.setattr(mt5_feed, "load_mt5",
                        lambda mt5_module=None: _FakeMT5TerminalTrial())

    def fake_load_config(path=None):
        cfg_path = Path(path) if path is not None else tmp_path / "config.yaml"
        if not cfg_path.exists():
            return {}
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    monkeypatch.setattr(config_mod, "load_config", fake_load_config)
    old_pw = qs.os.environ.get("MT5_PASSWORD")
    try:
        rc = qs.main(["--skip-install", "--skip-tests"])
    finally:
        if old_pw is None:
            qs.os.environ.pop("MT5_PASSWORD", None)
        else:
            qs.os.environ["MT5_PASSWORD"] = old_pw
    out = capsys.readouterr().out
    assert rc == 0
    assert "[co] EURUSD -> EURUSDm (desk forex)" in out
    assert "[co] XAUUSD -> XAUUSDm (desk xauusd)" in out
    assert "[co] BTCUSD -> BTCUSDm (desk crypto)" in out
    assert "[co] NVDA -> NVDAm (desk us_securities)" in out
