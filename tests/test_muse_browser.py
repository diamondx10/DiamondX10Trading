"""Test trinh duyet Muse (muse_browser.py): gui briefing + doi verdict.

Khong trinh duyet that, khong mang, khong Playwright that — dung
FakeBrowser/FakePage ghi lai cac cuoc goi (goto/attach/type/click)
va DOM gia cho trich xuat verdict. Neu module muse_browser chua
co (core agent chua xong) thi toan bo file nay duoc skip, khong
lam do suite hien tai.

Quy uoc: chuoi tieng Viet KHONG dau; file that chi dung tmp_path.
"""
import contextlib
import io
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

muse_browser = pytest.importorskip("diamondx10.muse_browser")
import diamondx10.briefing as briefing_mod
import diamondx10.synthesis as synthesis_mod
from diamondx10.__main__ import _cmd_briefing_send, main
from diamondx10.synthesis import load_verdicts

DEFAULT_CHAT_URL = "https://muse.ai"
GREETING = "Chao Phu, toi co the giup gi cho ban hom nay?"


# --- Du lieu gia ---

def _valid_verdict(desk="forex", **over):
    base = {"desk": desk, "analyst": "Yuling Pan",
            "direction": "buy", "confidence": 0.8,
            "drivers": ["ECB giu lai suat"], "risks": ["CPI cao"],
            "note": "EUR manh len",
            "created_utc": datetime.now(timezone.utc).isoformat()}
    base.update(over)
    return base


def _verdict_message(payload):
    """1 tin nhan tro ly chua khoi ```json (payload: dict hoac str JSON)."""
    if isinstance(payload, dict):
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = payload
    return "Phan tich xong. Verdict cua toi:\n```json\n" + text + "\n```"


def _two_block_message():
    """Tin moi co 2 khoi json: khoi CU (sell) roi khoi MOI (buy).

    Spec: wait_for_verdict lay khoi json CUOI CUNG -> phai tra buy.
    """
    old = _valid_verdict(direction="sell", confidence=0.6)
    new = _valid_verdict(direction="buy", confidence=0.8)
    return ("Ban nhap truoc:\n```json\n"
            + json.dumps(old, ensure_ascii=False) + "\n```\n"
            + "Chot lai:\n```json\n"
            + json.dumps(new, ensure_ascii=False) + "\n```")


def _make_briefing_file(tmp_path, name="briefing-forex-20261127-1000.md"):
    path = tmp_path / name
    path.write_text("# BRIEFING PHAN TICH — DESK FOREX\n\nEURUSD: BUY\n",
                    encoding="utf-8")
    return path


# --- Fake trinh duyet (duck-typed theo Playwright sync API) ---

class FakeElement:
    """1 node DOM gia: chi can inner_text / text_content."""

    def __init__(self, text):
        self._text = text

    def inner_text(self):
        return self._text

    def text_content(self):
        return self._text


class FakeLocator:
    """Ket qua cua page.locator(selector): fill/type/click/attach/doc.

    count(): selector tin nhan assistant -> so tin nhan hien co
    (moi lan doc se sang muc ke tiep cua kich ban); selector cau truc
    (textarea / input file / nut gui) -> 1 neu phan tu co, 0 neu
    composer khong xuat hien. nth(i) doc tin nhan thu i.
    """

    def __init__(self, page, selector, index=None):
        self.page = page
        self.selector = selector
        self.index = index

    def _need_composer(self):
        if not self.page.composer_present:
            raise RuntimeError(
                "khong tim thay o soan tin Muse (composer)")

    def _is_message_selector(self):
        sel = str(self.selector or "")
        return ("assistant" in sel or "message" in sel
                or "data-testid" in sel)

    def nth(self, index):
        return FakeLocator(self.page, self.selector, index=index)

    def count(self):
        if self._is_message_selector():
            return len(self.page.peek_messages())
        return 1 if self.page.composer_present else 0

    def wait_for(self, state=None, timeout=None):
        self.page.calls.append(("wait_for", self.selector, state, timeout))
        self._need_composer()

    def fill(self, text, **kw):
        self.page.calls.append(("fill", self.selector, text))
        self._need_composer()

    def type(self, text, **kw):
        self.page.calls.append(("type", self.selector, text))
        self._need_composer()

    def click(self, **kw):
        self.page.calls.append(("click", self.selector))
        self._need_composer()

    def press(self, key, **kw):
        self.page.calls.append(("press", self.selector, key))
        self._need_composer()

    def set_input_files(self, files, **kw):
        self.page.calls.append(("attach", self.selector, files))
        self._need_composer()

    def inner_text(self):
        if self.index is not None:
            msgs = self.page.peek_messages()
            return msgs[self.index] if 0 <= self.index < len(msgs) else ""
        return self.page.read_messages_text()

    def text_content(self):
        if self.index is not None:
            msgs = self.page.peek_messages()
            return msgs[self.index] if 0 <= self.index < len(msgs) else ""
        return self.page.read_messages_text()

    def all_inner_texts(self):
        return list(self.page.next_messages())

    def all_text_contents(self):
        return list(self.page.next_messages())

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def is_visible(self):
        return bool(self.page.composer_present)

    def locator(self, selector):
        return FakeLocator(self.page, selector)


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    def type(self, text, **kw):
        self.page.calls.append(("type", "keyboard", text))
        if not self.page.composer_present:
            raise RuntimeError(
                "khong tim thay o soan tin Muse (composer)")

    def press(self, key, **kw):
        self.page.calls.append(("press", "keyboard", key))
        if not self.page.composer_present:
            raise RuntimeError(
                "khong tim thay o soan tin Muse (composer)")


class FakePage:
    """1 tab gia: ghi lai goto/fill/type/click/attach; doc tin nhan
    theo kich ban (script): moi lan doc se sang muc ke tiep, muc
    cuoi lap lai — mo phong Muse tra loi sau vai dot poll."""

    def __init__(self, messages=None, script=None, composer_present=True,
                 clock=None):
        self.calls = []
        self.composer_present = composer_present
        self._messages = list(messages or [])
        self._script = list(script) if script is not None else None
        self._script_pos = 0
        self.keyboard = FakeKeyboard(self)
        self.url = ""
        # Dong ho gia (neu co): moi lan code sleep() de poll thi DOM
        # sang muc ke tiep cua kich ban — doc tin nhan chi la quan
        # sat, khong tu lam thay doi DOM.
        self._clock = clock
        if clock is not None:
            clock.listeners.append(self.advance)

    def advance(self):
        """Sang muc ke tiep cua kich ban (goi khi het 1 dot poll)."""
        if (self._script is not None
                and self._script_pos < len(self._script) - 1):
            self._script_pos += 1

    def peek_messages(self):
        if self._script is not None and self._script:
            idx = min(self._script_pos, len(self._script) - 1)
            return list(self._script[idx])
        return list(self._messages)

    def next_messages(self):
        return self.peek_messages()

    def read_messages_text(self):
        return "\n\n".join(self.peek_messages())

    def _need_composer(self):
        if not self.composer_present:
            raise RuntimeError(
                "khong tim thay o soan tin Muse (composer)")

    def goto(self, url, **kw):
        self.calls.append(("goto", url))
        self.url = str(url)
        return None

    def locator(self, selector):
        self.calls.append(("locator", selector))
        return FakeLocator(self, selector)

    def get_by_role(self, role, name=None, **kw):
        self.calls.append(("get_by_role", role, str(name)))
        return FakeLocator(self, f"role:{role}:{name}")

    def fill(self, selector, text, **kw):
        self.calls.append(("fill", selector, text))
        self._need_composer()

    def type(self, selector, text, **kw):
        self.calls.append(("type", selector, text))
        self._need_composer()

    def click(self, selector, **kw):
        self.calls.append(("click", selector))
        self._need_composer()

    def press(self, selector, key, **kw):
        self.calls.append(("press", selector, key))
        self._need_composer()

    def set_input_files(self, selector, files, **kw):
        self.calls.append(("attach", selector, files))
        self._need_composer()

    def wait_for_selector(self, selector, **kw):
        self.calls.append(("wait_for_selector", selector))
        if not self.composer_present:
            raise TimeoutError("composer khong xuat hien")

    def wait_for_timeout(self, timeout):
        self.calls.append(("wait", timeout))

    def inner_text(self, selector="body"):
        return self.read_messages_text()

    def text_content(self, selector="body"):
        return self.read_messages_text()

    def query_selector_all(self, selector):
        return [FakeElement(t) for t in self.next_messages()]

    def query_selector(self, selector):
        msgs = self.next_messages()
        return FakeElement(msgs[-1]) if msgs else None

    def content(self):
        return "<html><body>" + self.read_messages_text() + "</body></html>"

    def evaluate(self, expr, *args):
        if isinstance(expr, str) and ("innerText" in expr
                                      or "textContent" in expr):
            return self.read_messages_text()
        return None

    def new_page(self, *args, **kw):
        return self

    def close(self):
        self.calls.append(("close",))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class FakeBrowser:
    """Driver gia: vua la factory (goi duoc), vua la trinh duyet, vua
    la page — ung voi moi cach core agent co the tieu thu `driver`:
    driver() / driver(headless=..., user_data_dir=...) /
    driver.new_page() / driver.chromium.launch(...) / dung truc tiep
    nhu page (goto/fill/click). Moi kwarg nhan duoc (headless,
    profile_dir, ...) deu duoc ghi lai de test khang dinh."""

    def __init__(self, page=None):
        self.page = page if page is not None else FakePage()
        self.calls = self.page.calls
        self.factory_calls = []
        self.headless = None
        self.profile_dir = None

    def _record_factory(self, kind, args, kwargs):
        self.factory_calls.append((kind, args, dict(kwargs)))
        if "headless" in kwargs:
            self.headless = kwargs["headless"]
        for key in ("profile_dir", "user_data_dir", "user_data",
                    "data_dir"):
            if key in kwargs:
                self.profile_dir = kwargs[key]

    def __call__(self, *args, **kwargs):
        self._record_factory("call", args, kwargs)
        return self

    def launch(self, *args, **kwargs):
        self._record_factory("launch", args, kwargs)
        return self

    def launch_persistent_context(self, *args, **kwargs):
        self._record_factory("launch_persistent_context", args, kwargs)
        return self

    def new_context(self, *args, **kwargs):
        self._record_factory("new_context", args, kwargs)
        return self

    def new_page(self, *args, **kwargs):
        self._record_factory("new_page", args, kwargs)
        return self.page

    @property
    def chromium(self):
        return self

    @property
    def context(self):
        return self

    @property
    def keyboard(self):
        return self.page.keyboard

    @property
    def url(self):
        return self.page.url

    def goto(self, url, **kw):
        return self.page.goto(url, **kw)

    def locator(self, selector):
        return self.page.locator(selector)

    def get_by_role(self, role, name=None, **kw):
        return self.page.get_by_role(role, name=name, **kw)

    def fill(self, selector, text, **kw):
        return self.page.fill(selector, text, **kw)

    def type(self, selector, text, **kw):
        return self.page.type(selector, text, **kw)

    def click(self, selector, **kw):
        return self.page.click(selector, **kw)

    def set_input_files(self, selector, files, **kw):
        return self.page.set_input_files(selector, files, **kw)

    def wait_for_selector(self, selector, **kw):
        return self.page.wait_for_selector(selector, **kw)

    def wait_for_timeout(self, timeout):
        return self.page.wait_for_timeout(timeout)

    def inner_text(self, selector="body"):
        return self.page.inner_text(selector)

    def text_content(self, selector="body"):
        return self.page.text_content(selector)

    def query_selector_all(self, selector):
        return self.page.query_selector_all(selector)

    def query_selector(self, selector):
        return self.page.query_selector(selector)

    def content(self):
        return self.page.content()

    def evaluate(self, expr, *args):
        return self.page.evaluate(expr, *args)

    def close(self):
        self.page.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def received_values(self):
        """Tat ca gia tri (args + kwargs) ma driver da nhan, dang str."""
        vals = []
        for _kind, args, kwargs in self.factory_calls:
            vals.extend(str(v) for v in list(args))
            vals.extend(str(v) for v in kwargs.values())
        return vals


# --- Tien ich cho test ---

def _typed_texts(fake):
    texts = []
    for call in fake.calls:
        if call[0] in ("fill", "type") and len(call) >= 3:
            texts.append(str(call[2]))
    return texts


def _attached_files(fake):
    files = []
    for call in fake.calls:
        if call[0] == "attach":
            value = call[2]
            if isinstance(value, (list, tuple)):
                files.extend(str(v) for v in value)
            else:
                files.append(str(value))
    return files


def _submitted(fake):
    """Da bam nut gui (click) hoac Enter (press Enter) hay chua."""
    clicked = any(c[0] == "click" for c in fake.calls)
    pressed_enter = any(c[0] == "press" and len(c) >= 3
                        and str(c[2]).lower() == "enter"
                        for c in fake.calls)
    return clicked or pressed_enter


def _split_verdict_result(result):
    """wait_for_verdict co the tra verdict / None / (verdict, reason)
    / {"verdict": ..., "reason": ...} — tach ve (verdict, reason)."""
    if isinstance(result, tuple) and len(result) == 2:
        return result[0], result[1]
    if isinstance(result, dict) and "verdict" in result:
        return result.get("verdict"), result.get("reason")
    return result, None


def _patch_verdict_store(monkeypatch, tmp_path):
    """Do kho verdict ve tmp (khong dong vao decisions/ that)."""
    store = tmp_path / "fundamental-verdicts.json"
    monkeypatch.setattr(synthesis_mod, "VERDICT_STORE", store)
    monkeypatch.setattr(muse_browser, "VERDICT_STORE", store,
                        raising=False)
    return store


def _assert_nothing_stored(store):
    if not store.exists():
        return
    raw = store.read_text(encoding="utf-8").strip()
    assert raw in ("", "{}") or json.loads(raw) in ({}, {"verdicts": []})


class FakeClock:
    """Dong ho gia: sleep() se tang moc thoi gian thay vi doi that —
    vong poll ket thuc ngay lap tuc ma van dung han timeout. Moi lan
    sleep() cung bao cho cac FakePage dang ky (listeners) de DOM gia
    chuyen sang muc ke tiep — mo phong Muse tra loi sau vai dot poll."""

    def __init__(self):
        self.now = 1000000.0
        self.listeners = []

    def sleep(self, seconds):
        self.now += float(seconds or 0)
        for notify in list(self.listeners):
            notify()

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


def _cli_help_text(argv):
    """Text help cua 1 lenh con (argparse in ra stdout roi exit)."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            main(argv)
    except SystemExit:
        pass
    return buf.getvalue()


_CLI_HELP_CACHE = {}


def _cli_has(argv, marker):
    """Lenh con co ton tai + co flag/marker trong help khong."""
    key = (tuple(argv), marker)
    if key not in _CLI_HELP_CACHE:
        _CLI_HELP_CACHE[key] = marker in _cli_help_text(list(argv))
    return _CLI_HELP_CACHE[key]


def _patch_send(monkeypatch, fake):
    """Thay send_briefing o moi namespace co the goi no."""
    monkeypatch.setattr(muse_browser, "send_briefing", fake)
    monkeypatch.setattr("diamondx10.__main__.send_briefing", fake,
                        raising=False)
    monkeypatch.setattr(briefing_mod, "send_briefing", fake,
                        raising=False)


def _patch_wait(monkeypatch, fake):
    """Thay wait_for_verdict o moi namespace co the goi no."""
    monkeypatch.setattr(muse_browser, "wait_for_verdict", fake)
    monkeypatch.setattr("diamondx10.__main__.wait_for_verdict", fake,
                        raising=False)
    monkeypatch.setattr(briefing_mod, "wait_for_verdict", fake,
                        raising=False)


# --- 1-2. Luong gui: URL, attach file, go prompt, bam gui ---

def test_send_briefing_visits_default_chat_url_attaches_file_types_prompt_and_clicks_send(tmp_path, fake_clock):
    md = _make_briefing_file(tmp_path)
    fake = FakeBrowser()
    result = muse_browser.send_briefing(str(md), {}, driver=fake)
    assert result["sent"] is True
    assert result["url"] == DEFAULT_CHAT_URL
    assert "message" in result
    assert ("goto", DEFAULT_CHAT_URL) in fake.calls
    attached = _attached_files(fake)
    assert attached, "khong co cuoc goi attach file nao"
    assert any(Path(f).name == md.name for f in attached)
    assert any(t.strip() for t in _typed_texts(fake)), \
        "khong co prompt nao duoc go"
    assert _submitted(fake), "khong bam nut gui / Enter sau khi go prompt"


def test_send_briefing_uses_config_chat_url(tmp_path, fake_clock):
    md = _make_briefing_file(tmp_path)
    fake = FakeBrowser()
    url = "https://muse.ai/chat/abc123"
    result = muse_browser.send_briefing(
        str(md), {"muse": {"chat_url": url}}, driver=fake)
    assert result["sent"] is True
    assert result["url"] == url
    assert ("goto", url) in fake.calls


def test_send_briefing_custom_prompt_and_headless_passed_to_driver(tmp_path, fake_clock):
    md = _make_briefing_file(tmp_path)
    fake = FakeBrowser()
    prompt = "Hay phan tich briefing dinh kem va tra verdict JSON."
    result = muse_browser.send_briefing(
        str(md), {"muse": {"chat_url": DEFAULT_CHAT_URL}},
        prompt=prompt, headless=True, driver=fake)
    assert result["sent"] is True
    assert prompt in _typed_texts(fake), \
        f"prompt tuy chinh khong duoc go (da go: {_typed_texts(fake)})"
    assert fake.headless is True, \
        f"headless=True khong duoc truyen toi driver: {fake.factory_calls}"


def test_send_briefing_composer_missing_returns_not_sent_with_clear_message(tmp_path):
    """Composer khong xuat hien -> gui that ro rang, KHONG treo.

    LUY Y (khac spec ban dau — spec ghi "raise"): code that tra
    {"sent": False, "url", "message"} kem ly do ro rang thay vi
    raise. Test nay khang dinh hanh vi that cua code.
    """
    md = _make_briefing_file(tmp_path)
    fake = FakeBrowser(FakePage(composer_present=False))
    result = muse_browser.send_briefing(str(md), {}, timeout_sec=5,
                                        driver=fake)
    assert result["sent"] is False
    assert result["url"] == DEFAULT_CHAT_URL
    assert "composer" in result["message"].lower()
    assert "dang nhap" in result["message"].lower()


# --- 4-7. Doi verdict: trich xuat, luu, cac truong hop loi ---

def test_wait_for_verdict_extracts_last_json_block_and_stores_it(
        monkeypatch, tmp_path, fake_clock):
    store = _patch_verdict_store(monkeypatch, tmp_path)
    old = _verdict_message(_valid_verdict(
        desk="crypto", analyst="Rich", direction="sell", confidence=0.7))
    script = [[GREETING, old],
              [GREETING, old, _two_block_message()]]
    fake = FakeBrowser(FakePage(script=script, clock=fake_clock))
    verdict, _reason = _split_verdict_result(
        muse_browser.wait_for_verdict({}, timeout_min=0.01, poll_sec=0.01,
                                      driver=fake,
                                      store_path=store))
    assert verdict is not None
    assert verdict["desk"] == "forex"
    assert verdict["direction"] == "buy"
    assert verdict["confidence"] == 0.8
    saved = load_verdicts(store).get("forex")
    assert saved is not None
    assert saved["direction"] == "buy"
    assert saved["confidence"] == 0.8
    # Khoi JSON cu (crypto) khong duoc luu — chi lay khoi CUOI CUNG.
    assert "crypto" not in load_verdicts(store)


def test_wait_for_verdict_no_json_block_returns_none_and_stores_nothing(
        monkeypatch, tmp_path, fake_clock):
    store = _patch_verdict_store(monkeypatch, tmp_path)
    plain = ("Toi se phan tich ky hon va tra loi sau.\n"
             "```text\nkhong phai json\n```")
    script = [[GREETING], [GREETING, plain]]
    fake = FakeBrowser(FakePage(script=script, clock=fake_clock))
    verdict, reason = _split_verdict_result(
        muse_browser.wait_for_verdict({}, timeout_min=0.01, poll_sec=0.01,
                                      driver=fake,
                                      store_path=store))
    assert verdict is None
    if reason is not None:
        assert str(reason).strip()
    _assert_nothing_stored(store)


@pytest.mark.parametrize("payload", [
    json.dumps(_valid_verdict(direction="hold"), ensure_ascii=False),
    json.dumps(_valid_verdict(confidence=1.5), ensure_ascii=False),
    json.dumps(_valid_verdict(desk="stocks"), ensure_ascii=False),
    "[1, 2, 3]",
    "{khong phai json",
])
def test_wait_for_verdict_invalid_json_block_returns_none_and_stores_nothing(
        monkeypatch, tmp_path, fake_clock, payload):
    store = _patch_verdict_store(monkeypatch, tmp_path)
    script = [[GREETING], [GREETING, _verdict_message(payload)]]
    fake = FakeBrowser(FakePage(script=script, clock=fake_clock))
    verdict, reason = _split_verdict_result(
        muse_browser.wait_for_verdict({}, timeout_min=0.01, poll_sec=0.01,
                                      driver=fake,
                                      store_path=store))
    assert verdict is None
    if reason is not None:
        assert str(reason).strip()
    _assert_nothing_stored(store)


def test_wait_for_verdict_timeout_no_new_messages_returns_none(
        monkeypatch, tmp_path, fake_clock):
    store = _patch_verdict_store(monkeypatch, tmp_path)
    fake = FakeBrowser(FakePage(messages=[GREETING], clock=fake_clock))
    verdict, reason = _split_verdict_result(
        muse_browser.wait_for_verdict({}, timeout_min=0.01, poll_sec=0.01,
                                      driver=fake,
                                      store_path=store))
    assert verdict is None
    if reason is not None:
        assert str(reason).strip()
    _assert_nothing_stored(store)


# --- 8. Thieu Playwright -> loi ro rang, nhac muse-setup ---

def test_send_briefing_missing_playwright_raises_error_mentioning_muse_setup(
        monkeypatch, tmp_path):
    md = _make_briefing_file(tmp_path)
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(Exception, match="muse-setup"):
        muse_browser.send_briefing(str(md), {}, driver=None)


# --- 9. Profile dir: mac dinh + tuy chinh ---

def test_send_briefing_default_profile_dir(tmp_path, fake_clock):
    md = _make_briefing_file(tmp_path)
    fake = FakeBrowser()
    result = muse_browser.send_briefing(str(md), {}, driver=fake)
    assert result["sent"] is True
    values = [v.replace("\\", "/") for v in fake.received_values()]
    assert any(v.endswith("data/muse-profile") for v in values), \
        f"driver khong nhan profile_dir mac dinh data/muse-profile: {values}"


def test_send_briefing_custom_profile_dir_from_config(tmp_path, fake_clock):
    md = _make_briefing_file(tmp_path)
    fake = FakeBrowser()
    custom = tmp_path / "prof-dir"
    result = muse_browser.send_briefing(
        str(md), {"muse": {"profile_dir": str(custom)}},
        driver=fake)
    assert result["sent"] is True
    values = fake.received_values()
    assert any(str(custom) in v for v in values), \
        f"driver khong nhan profile_dir tuy chinh: {values}"


# --- 10. briefing --send ---

def _fake_build_briefing(md, json_path):
    def fake_build(cfg, desk, days=3, **kw):
        return {"desk": desk, "analyst": "Yuling Pan",
                "symbols": ["EURUSD"],
                "generated_utc": "2026-11-27T10:00:00+00:00",
                "md_path": str(md), "json_path": str(json_path)}
    return fake_build


def test_cmd_briefing_send_calls_send_briefing(monkeypatch, tmp_path):
    """briefing --send: tao briefing roi gui tung file.

    LUY Y: --send khong nam trong briefing.cmd_briefing ma nam trong
    __main__._cmd_briefing_send, dung binding build_briefing cua
    __main__ (from .briefing import) — patch dung namespace do.
    """
    md = _make_briefing_file(tmp_path)
    json_path = tmp_path / "briefing-forex-20261127-1000.json"
    json_path.write_text("{}", encoding="utf-8")
    calls = []

    def fake_send(file_path, cfg=None, **kw):
        calls.append(str(file_path))
        return {"sent": True, "url": DEFAULT_CHAT_URL, "message": "da gui"}

    monkeypatch.setattr("diamondx10.__main__.build_briefing",
                        _fake_build_briefing(md, json_path))
    _patch_send(monkeypatch, fake_send)
    assert _cmd_briefing_send({}, "forex") == 0
    assert calls == [str(md)]


def test_briefing_cli_send_calls_send_briefing(monkeypatch, tmp_path):
    if not _cli_has(["briefing", "--help"], "--send"):
        pytest.skip("lenh briefing chua co flag --send")
    md = _make_briefing_file(tmp_path)
    json_path = tmp_path / "briefing-forex-20261127-1000.json"
    json_path.write_text("{}", encoding="utf-8")
    calls = []

    def fake_send(file_path, cfg=None, **kw):
        calls.append(str(file_path))
        return {"sent": True, "url": DEFAULT_CHAT_URL, "message": "da gui"}

    monkeypatch.setattr("diamondx10.__main__.build_briefing",
                        _fake_build_briefing(md, json_path))
    _patch_send(monkeypatch, fake_send)
    assert main(["briefing", "--desk", "forex", "--send"]) == 0
    assert calls == [str(md)]


def test_briefing_cli_without_send_does_not_call_send_briefing(
        monkeypatch, tmp_path):
    md = _make_briefing_file(tmp_path)
    json_path = tmp_path / "briefing-forex-20261127-1000.json"
    json_path.write_text("{}", encoding="utf-8")
    calls = []

    def fake_send(file_path, cfg=None, **kw):
        calls.append(str(file_path))
        return {"sent": True, "url": DEFAULT_CHAT_URL, "message": "da gui"}

    monkeypatch.setattr(briefing_mod, "build_briefing",
                        _fake_build_briefing(md, json_path))
    _patch_send(monkeypatch, fake_send)
    assert main(["briefing", "--desk", "forex"]) == 0
    assert calls == []


# --- 11. muse-send CLI: exit code ---

def _muse_send_setup(monkeypatch, tmp_path, wait_result):
    """Patch send/wait gia cho lenh muse-send; tra (md_path, wait_calls)."""
    _patch_verdict_store(monkeypatch, tmp_path)
    md = _make_briefing_file(tmp_path)
    sent = {}

    def fake_send(file_path, cfg=None, **kw):
        sent["file"] = str(file_path)
        return {"sent": True, "url": DEFAULT_CHAT_URL, "message": "da gui"}

    wait_calls = []

    def fake_wait(cfg=None, **kw):
        wait_calls.append(kw)
        return wait_result

    _patch_send(monkeypatch, fake_send)
    _patch_wait(monkeypatch, fake_wait)
    return md, sent, wait_calls


def test_muse_send_cli_verdict_stored_returns_0(monkeypatch, tmp_path):
    if not _cli_has(["muse-send", "--help"], "--file"):
        pytest.skip("lenh muse-send chua dang ky")
    md, sent, _calls = _muse_send_setup(monkeypatch, tmp_path,
                                         _valid_verdict())
    assert main(["muse-send", "--file", str(md), "--wait-min", "1"]) == 0
    assert sent["file"] == str(md)


def test_muse_send_cli_timeout_returns_1(monkeypatch, tmp_path):
    if not _cli_has(["muse-send", "--help"], "--file"):
        pytest.skip("lenh muse-send chua dang ky")
    md, _sent, _calls = _muse_send_setup(monkeypatch, tmp_path, None)
    assert main(["muse-send", "--file", str(md), "--wait-min", "1"]) == 1


def test_muse_send_cli_no_wait_returns_0_without_waiting(
        monkeypatch, tmp_path):
    if not _cli_has(["muse-send", "--help"], "--file"):
        pytest.skip("lenh muse-send chua dang ky")
    md, sent, wait_calls = _muse_send_setup(monkeypatch, tmp_path, None)
    assert main(["muse-send", "--file", str(md), "--no-wait"]) == 0
    assert sent["file"] == str(md)
    assert wait_calls == [], "co --no-wait ma van doi verdict"


# --- muse-setup CLI ---

def _patch_subprocess_run(monkeypatch, runs, returncode):
    def fake_run(cmd, **kw):
        runs.append([str(c) for c in cmd])
        if returncode != 0 and kw.get("check"):
            raise subprocess.CalledProcessError(returncode, cmd)
        return subprocess.CompletedProcess(cmd, returncode)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(muse_browser, "run", fake_run, raising=False)
    monkeypatch.setattr("diamondx10.__main__.run", fake_run,
                        raising=False)


def test_muse_setup_installs_playwright_and_chromium(monkeypatch, capsys):
    if not _cli_has(["muse-setup", "--help"], "muse-setup"):
        pytest.skip("lenh muse-setup chua dang ky")
    runs = []
    _patch_subprocess_run(monkeypatch, runs, 0)
    assert main(["muse-setup"]) == 0
    assert runs, "muse-setup khong goi subprocess.run (patch khong trung?)"
    joined = [" ".join(r) for r in runs]
    assert any("playwright" in line and "install" in line
               for line in joined), f"khong cai playwright: {joined}"
    assert any("chromium" in line for line in joined), \
        f"khong cai chromium: {joined}"
    out = capsys.readouterr().out
    assert "muse" in out.lower(), "muse-setup khong in buoc tiep theo"


def test_muse_setup_install_failure_returns_1(monkeypatch, capsys):
    if not _cli_has(["muse-setup", "--help"], "muse-setup"):
        pytest.skip("lenh muse-setup chua dang ky")
    runs = []
    _patch_subprocess_run(monkeypatch, runs, 1)
    assert main(["muse-setup"]) == 1
    assert runs, "muse-setup khong goi subprocess.run (patch khong trung?)"
    assert "LOI" in capsys.readouterr().out
