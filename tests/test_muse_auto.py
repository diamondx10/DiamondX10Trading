"""Test chu ky PTCB tu dong (muse_auto.py + lenh `muse-auto`).

Khong trinh duyet that, khong mang, khong Playwright that — dung
FakeBrowser/FakePage rieng cua file nay (ho tro nth() de doc tin
nhan tro ly) + Telegram gia. File that chi dung tmp_path.

Quy uoc: chuoi tieng Viet KHONG dau; tin nhan Telegram la tieng Anh.
"""
import contextlib
import copy
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import diamondx10.muse_auto as muse_auto_mod
import diamondx10.muse_browser as muse_browser
import diamondx10.synthesis as synthesis_mod
from diamondx10.__main__ import main
from diamondx10.config import DEFAULT
from diamondx10.muse_auto import cmd_muse_auto
from diamondx10.synthesis import load_verdicts

DEFAULT_CHAT_URL = "https://muse.ai"
GREETING = "Chao Phu, toi co the giup gi cho ban hom nay?"


def _valid_verdict(desk="forex", **over):
    base = {"desk": desk, "analyst": "Yuling Pan",
            "direction": "buy", "confidence": 0.8,
            "drivers": ["ECB giu lai suat"], "risks": ["CPI cao"],
            "note": "EUR manh len",
            "created_utc": datetime.now(timezone.utc).isoformat()}
    base.update(over)
    return base


def _verdict_message(payload):
    if isinstance(payload, dict):
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = payload
    return "Phan tich xong. Verdict cua toi:\n```json\n" + text + "\n```"


# --- Feed gia + tin gia cho build_briefing that ---

def trend_bars(n=60, start=100.0):
    closes, c = [], start
    for i in range(n):
        c += (0.2, 0.2, -0.25)[i % 3]
        closes.append(round(c, 2))
    return [{"time": 1700000000 + i * 900, "open": cl - 0.05,
             "high": cl + 0.5, "low": cl - 0.5, "close": cl}
            for i, cl in enumerate(closes)]


class FakeFeed:
    def __init__(self, bars=None):
        self._bars = bars if bars is not None else trend_bars()

    def bars(self, n=60):
        return list(self._bars[-n:])

    def latest_price(self, symbol):
        return self._bars[-1]["close"]


RSS_FOREX = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Forex News</title>
<item><title>Federal Reserve holds rates steady</title>
<link>https://example.com/fed-1</link>
<description>ECB and Fed signal no change to interest rates.</description>
</item></channel></rss>"""


def fake_fetcher(url, timeout):
    if "forex" in url:
        return RSS_FOREX
    raise RuntimeError(f"khong co feed gia cho {url}")


NEWS_CFG = {
    "max_age_days": 3,
    "filters": {"blacklist_keywords": ["sponsored"],
                "high_priority_keywords": ["Federal Reserve"]},
    "desks": {"forex": {"keywords": ["EURUSD", "euro", "ECB",
                                     "Federal Reserve", "Fed",
                                     "interest rate"]}},
    "sources": [{"name": "Fake Forex", "url": "https://example.com/forex.rss",
                 "tier": 2, "desks": ["forex"]}],
}


def base_cfg():
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": {"forex": ["EURUSD"],
                               "xauusd": ["XAUUSD"],
                               "crypto": ["BTCUSD"],
                               "us_securities": ["NVDA"]}}
    cfg["news"] = copy.deepcopy(NEWS_CFG)
    cfg["muse"] = {"chat_url": DEFAULT_CHAT_URL,
                   "profile_dir": "data/muse-profile",
                   "headless": False, "wait_min": 10}
    cfg["telegram"] = {"enabled": True, "chat_id": "1234567890"}
    cfg["language"] = "en"
    return cfg


# --- Fake trinh duyet (duck-typed theo Playwright sync API) ---

ASSISTANT_MARKERS = ("assistant",)


class FakeElement:
    def __init__(self, text):
        self._text = text

    def inner_text(self):
        return self._text

    def text_content(self):
        return self._text


class FakeLocator:
    """Locator gia: count() = 1 cho phan tu giao dien (composer /
    input file / nut gui) khi composer co mat; = so tin nhan tro ly
    cho selector tin nhan. nth(i) doc tin nhan tro ly thu i."""

    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    def _is_assistant(self):
        return any(m in self.selector for m in ASSISTANT_MARKERS)

    def count(self):
        if self._is_assistant():
            return len(self.page.peek_messages())
        return 1 if self.page.composer_present else 0

    def nth(self, index):
        msgs = self.page.peek_messages()
        text = msgs[index] if 0 <= index < len(msgs) else ""
        return FakeElement(text)

    @property
    def first(self):
        return self

    def fill(self, text, **kw):
        self.page.calls.append(("fill", self.selector, text))
        if not self.page.composer_present:
            raise RuntimeError("khong tim thay o soan tin Muse (composer)")

    def click(self, **kw):
        self.page.calls.append(("click", self.selector))
        if not self.page.composer_present:
            raise RuntimeError("khong tim thay o soan tin Muse (composer)")

    def set_input_files(self, files, **kw):
        self.page.calls.append(("attach", self.selector, files))
        if not self.page.composer_present:
            raise RuntimeError("khong tim thay o soan tin Muse (composer)")


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    def type(self, text, **kw):
        self.page.calls.append(("type", "keyboard", text))

    def press(self, key, **kw):
        self.page.calls.append(("press", "keyboard", key))


class FakePage:
    """1 tab gia: script la list cac khung tin nhan tro ly; moi lan
    doc (peek) se sang khung ke tiep, khung cuoi lap lai — mo phong
    Muse tra loi sau khi gui."""

    def __init__(self, script=None, composer_present=True):
        self.calls = []
        self.composer_present = composer_present
        self._script = list(script) if script is not None else [[GREETING]]
        self._pos = 0
        self.keyboard = FakeKeyboard(self)
        self.url = ""

    def peek_messages(self):
        idx = min(self._pos, len(self._script) - 1)
        frame = list(self._script[idx])
        if self._pos < len(self._script) - 1:
            self._pos += 1
        return frame

    def goto(self, url, **kw):
        self.calls.append(("goto", url))
        self.url = str(url)
        return None

    def locator(self, selector):
        self.calls.append(("locator", selector))
        return FakeLocator(self, selector)

    def get_by_role(self, role, **kw):
        self.calls.append(("get_by_role", role))
        return FakeLocator(self, "button")

    def wait_for_selector(self, selector, **kw):
        self.calls.append(("wait_for_selector", selector))
        if not self.composer_present:
            raise TimeoutError("composer khong xuat hien")

    def close(self):
        self.calls.append(("close",))


class FakeBrowser:
    """Driver gia: launch_persistent_context -> chinh no (context),
    new_page -> FakePage; ghi lai headless + profile_dir."""

    def __init__(self, page=None):
        self.page = page if page is not None else FakePage()
        self.calls = self.page.calls
        self.headless = None
        self.profile_dir = None

    def launch_persistent_context(self, *args, **kwargs):
        if "headless" in kwargs:
            self.headless = kwargs["headless"]
        if "user_data_dir" in kwargs:
            self.profile_dir = kwargs["user_data_dir"]
        return self

    def new_page(self, *args, **kwargs):
        return self.page

    def close(self):
        self.page.close()


class FakeClock:
    """Dong ho gia: sleep() tang moc thoi gian thay vi doi that."""

    def __init__(self):
        self.now = 1000000.0

    def sleep(self, seconds):
        self.now += float(seconds or 0)

    def monotonic(self):
        return self.now

    def time(self):
        return self.now + 1700000000.0


@pytest.fixture
def fake_clock(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(time, "sleep", clock.sleep)
    monkeypatch.setattr(time, "monotonic", clock.monotonic)
    monkeypatch.setattr(time, "time", clock.time)
    return clock


def _patch_verdict_store(monkeypatch, tmp_path):
    store = tmp_path / "fundamental-verdicts.json"
    monkeypatch.setattr(synthesis_mod, "VERDICT_STORE", store)
    return store


def _assert_nothing_stored(store):
    if not store.exists():
        return
    raw = store.read_text(encoding="utf-8").strip()
    assert raw in ("", "{}") or json.loads(raw) in ({}, {"verdicts": []})


def _read_state(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _cli_help_text(argv):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            main(argv)
    except SystemExit:
        pass
    return buf.getvalue()


# --- 1. Happy path: briefing that -> gui that -> verdict that luu ---

def test_muse_auto_happy_path(monkeypatch, tmp_path, fake_clock, capsys):
    store = _patch_verdict_store(monkeypatch, tmp_path)
    state_path = tmp_path / "fa-cycle-state.json"
    out_dir = tmp_path / "briefings"
    script = [[GREETING]] * 8 + [[GREETING,
                                  _verdict_message(_valid_verdict())]]
    fake = FakeBrowser(FakePage(script=script))
    rc = cmd_muse_auto(base_cfg(), desk="forex", wait_min=1,
                       headless=True, driver=fake, feed=FakeFeed(),
                       news_fetcher=fake_fetcher, out_dir=out_dir,
                       state_path=state_path, poll_sec=0.01)
    assert rc == 0
    out = capsys.readouterr().out
    assert "[forex] SENT + verdict stored" in out
    assert "direction buy" in out
    # Verdict da luu vao kho (chi qua wait_for_verdict that).
    saved = load_verdicts(store).get("forex")
    assert saved is not None
    assert saved["direction"] == "buy"
    assert saved["confidence"] == 0.8
    # Briefing that da ghi ra file.
    assert list(out_dir.glob("briefing-forex-*.md")), \
        "khong co file briefing .md nao duoc tao"
    # State file dung dinh dang, khong chua token / session.
    state = _read_state(state_path)
    assert set(state) == {"started_utc", "desks"}
    assert set(state["desks"]) == {"forex"}
    entry = state["desks"]["forex"]
    assert entry == {"sent": True, "verdict_stored": True,
                     "reason": entry["reason"]}
    assert entry["sent"] is True and entry["verdict_stored"] is True
    assert "buy" in entry["reason"]
    assert "token" not in json.dumps(state).lower()
    assert fake.headless is True, "muse-auto phai gui headless=True"


def test_muse_auto_headless_default_true_and_headed_flag(
        monkeypatch, tmp_path):
    """cmd_muse_auto mac dinh headless=True; --headed (headless=False)
    truyen False toi send_briefing."""
    seen = {}

    def fake_send(file_path, cfg=None, **kw):
        seen["headless"] = kw.get("headless")
        return {"sent": True, "url": DEFAULT_CHAT_URL, "message": "da gui"}

    def fake_wait(cfg=None, **kw):
        return _valid_verdict()

    def fake_build(cfg, desk, days=3, **kw):
        md = tmp_path / f"briefing-{desk}.md"
        md.write_text("# briefing\n", encoding="utf-8")
        return {"desk": desk, "analyst": "Yuling Pan", "symbols": ["EURUSD"],
                "generated_utc": "2026-11-27T10:00:00+00:00",
                "md_path": str(md), "json_path": str(tmp_path / "b.json")}

    monkeypatch.setattr(muse_auto_mod, "send_briefing", fake_send)
    monkeypatch.setattr(muse_auto_mod, "wait_for_verdict", fake_wait)
    monkeypatch.setattr(muse_auto_mod, "build_briefing", fake_build)
    monkeypatch.setattr(muse_auto_mod, "FA_CYCLE_STATE",
                        tmp_path / "fa-cycle-state.json")
    assert main(["muse-auto", "--desk", "forex", "--wait-min", "1"]) == 0
    assert seen["headless"] is True, \
        "mac dinh muse-auto phai headless (chay dinh ky khong desktop)"
    assert main(["muse-auto", "--desk", "forex", "--wait-min", "1",
                 "--headed"]) == 0
    assert seen["headless"] is False, \
        "--headed phai truyen headless=False toi send_briefing"


def test_muse_auto_help_shows_flags():
    text = _cli_help_text(["muse-auto", "--help"])
    for flag in ("--desk", "--all", "--wait-min", "--headless", "--headed"):
        assert flag in text, f"help cua muse-auto thieu flag {flag}"


# --- 2. Gui that bai (khong thay composer) -> canh bao Telegram + exit 1 ---

def test_muse_auto_send_failure_alerts_telegram_and_returns_1(
        monkeypatch, tmp_path, fake_clock, capsys):
    store = _patch_verdict_store(monkeypatch, tmp_path)
    state_path = tmp_path / "fa-cycle-state.json"
    fake = FakeBrowser(FakePage(composer_present=False))
    calls = []

    def fake_telegram(text, **kw):
        calls.append(text)
        return True

    monkeypatch.setattr(muse_auto_mod.telegram_mod, "send_message",
                        fake_telegram)
    rc = cmd_muse_auto(base_cfg(), desk="forex", wait_min=1,
                       headless=True, driver=fake, feed=FakeFeed(),
                       news_fetcher=fake_fetcher,
                       out_dir=tmp_path / "briefings",
                       state_path=state_path, poll_sec=0.01)
    assert rc == 1
    assert len(calls) == 1, "het phien phai gui dung 1 canh bao Telegram"
    assert "session expired" in calls[0].lower()
    assert "re-sign in" in calls[0].lower()
    out = capsys.readouterr().out
    assert "[forex] FAILED" in out
    _assert_nothing_stored(store)
    state = _read_state(state_path)
    entry = state["desks"]["forex"]
    assert entry["sent"] is False and entry["verdict_stored"] is False
    assert entry["reason"].strip()


def test_send_briefing_composer_missing_marks_session_expired(
        monkeypatch, tmp_path):
    """Co session_expired trong dict tra ve — co ma muse-auto nhan
    dien het phien (them nho vao muse_browser.py, khong doi signature)."""
    md = tmp_path / "briefing-forex-20261127-1000.md"
    md.write_text("# BRIEFING\n", encoding="utf-8")
    fake = FakeBrowser(FakePage(composer_present=False))
    result = muse_browser.send_briefing(str(md), {}, timeout_sec=5,
                                        driver=fake)
    assert result["sent"] is False
    assert result.get("session_expired") is True


def test_muse_auto_send_raises_session_error_still_alerts(
        monkeypatch, tmp_path, capsys):
    """Neu send_briefing raise loi dang nhap (thay vi tra dict) thi
    van canh bao Telegram + exit 1."""
    calls = []

    def fake_send(file_path, cfg=None, **kw):
        raise muse_browser.MuseBrowserError(
            "Khong tim thay o nhap tin nhan — co the ban chua dang nhap Muse.")

    def fake_build(cfg, desk, days=3, **kw):
        md = tmp_path / f"briefing-{desk}.md"
        md.write_text("# briefing\n", encoding="utf-8")
        return {"desk": desk, "analyst": "Yuling Pan", "symbols": ["EURUSD"],
                "generated_utc": "2026-11-27T10:00:00+00:00",
                "md_path": str(md), "json_path": str(tmp_path / "b.json")}

    monkeypatch.setattr(muse_auto_mod, "send_briefing", fake_send)
    monkeypatch.setattr(muse_auto_mod, "build_briefing", fake_build)
    monkeypatch.setattr(muse_auto_mod.telegram_mod, "send_message",
                        lambda text, **kw: calls.append(text) or True)
    rc = cmd_muse_auto(base_cfg(), desk="forex", wait_min=1,
                       state_path=tmp_path / "fa-cycle-state.json")
    assert rc == 1
    assert len(calls) == 1
    assert "session expired" in calls[0].lower()


def test_muse_auto_telegram_unconfigured_still_returns_1(
        monkeypatch, tmp_path, capsys):
    """Telegram chua cau hinh (khong token/chat_id) thi chi in ro —
    loi Telegram khong che mat loi gui goc."""
    cfg = base_cfg()
    cfg["telegram"] = {"enabled": False}
    monkeypatch.delenv("DIAMONDX10_TELEGRAM_TOKEN", raising=False)
    fake = FakeBrowser(FakePage(composer_present=False))
    rc = cmd_muse_auto(cfg, desk="forex", wait_min=1, headless=True,
                       driver=fake, feed=FakeFeed(),
                       news_fetcher=fake_fetcher,
                       out_dir=tmp_path / "briefings",
                       state_path=tmp_path / "fa-cycle-state.json")
    assert rc == 1
    out = capsys.readouterr().out
    assert "LOI (forex)" in out, "loi gui goc phai in ra ro rang"
    assert "CANH BAO" in out


# --- 3. Het gio doi verdict -> exit 0 (CANH BAO), khong luu gi ---

def test_muse_auto_verdict_timeout_returns_0_with_warning(
        monkeypatch, tmp_path, fake_clock, capsys):
    store = _patch_verdict_store(monkeypatch, tmp_path)
    state_path = tmp_path / "fa-cycle-state.json"
    telegram_calls = []
    monkeypatch.setattr(muse_auto_mod.telegram_mod, "send_message",
                        lambda text, **kw: telegram_calls.append(text)
                        or True)
    fake = FakeBrowser(FakePage(script=[[GREETING]]))
    rc = cmd_muse_auto(base_cfg(), desk="forex", wait_min=0.01,
                       headless=True, driver=fake, feed=FakeFeed(),
                       news_fetcher=fake_fetcher,
                       out_dir=tmp_path / "briefings",
                       state_path=state_path, poll_sec=0.01)
    assert rc == 0, "het gio doi verdict chi la CANH BAO, khong phai loi"
    out = capsys.readouterr().out
    assert "CANH BAO (forex)" in out
    assert "[forex] SENT, chua co verdict moi" in out
    assert telegram_calls == [], \
        "het gio doi verdict khong phai het phien — khong gui Telegram"
    _assert_nothing_stored(store)
    state = _read_state(state_path)
    entry = state["desks"]["forex"]
    assert entry["sent"] is True and entry["verdict_stored"] is False
    assert entry["reason"].strip()


# --- 4. Tao briefing that bai -> exit 1, ghi state ---

def test_muse_auto_briefing_build_failure_returns_1(
        monkeypatch, tmp_path, capsys):
    cfg = base_cfg()
    cfg.pop("news", None)  # thieu muc news: -> build_briefing raise
    fake = FakeBrowser()
    state_path = tmp_path / "fa-cycle-state.json"
    rc = cmd_muse_auto(cfg, desk="forex", wait_min=1, headless=True,
                       driver=fake, feed=FakeFeed(),
                       news_fetcher=fake_fetcher,
                       out_dir=tmp_path / "briefings",
                       state_path=state_path)
    assert rc == 1
    assert "LOI (forex)" in capsys.readouterr().out
    state = _read_state(state_path)
    entry = state["desks"]["forex"]
    assert entry["sent"] is False and entry["verdict_stored"] is False
    assert "news" in entry["reason"]
