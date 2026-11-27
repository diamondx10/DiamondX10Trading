"""Dieu khien trinh duyet Muse (muse.ai) bang Playwright de gui briefing
va doi verdict PTCB.

dx10 la CLI KHONG CO cua so GUI — "nhung" o day nghia la dx10 mo va
dieu khien 1 cua so Chromium (headed de user nhin thay va dang nhap),
KHONG phai panel trinh duyet nam trong dx10.

Quy tac bao mat:
- Profile trinh duyet (muse.profile_dir, mac dinh data/muse-profile)
  giu session dang nhap cua user. Tool CHI truyen duong dan profile
  cho Playwright, KHONG BAO GIO doc, in hay copy file session trong
  do, va KHONG BAO GIO hoi mat khau Muse: lan dang nhap dau tien user
  tu dang nhap TAY trong cua so trinh duyet headed.
- Khong co token / mat khau / URL chua ID trong code hay config.

Playwright la dependency TUY CHON, import LAZY (chi trong ham mo
trinh duyet) de dx10 chay binh thuong khi chua cai. Chua cai thi ham
mo trinh duyet raise MuseBrowserError huong dan chay `muse-setup`.

Selector: best-effort, uu tien locator theo role/text cua Playwright
(composer textbox, file input, nut Send, khoi tin nhan assistant, khoi
code ```json). Neu muse.ai doi giao dien, cac selector nay co the can
cap nhat — khi khong nhan dien duoc cau truc trang, ham se bao loi ro
rang thay vi doan mo.
"""
import json
import re
import time
from pathlib import Path

from .synthesis import save_verdict, validate_verdict

DEFAULT_CHAT_URL = "https://muse.ai"
DEFAULT_PROFILE_DIR = "data/muse-profile"
DEFAULT_WAIT_MIN = 10

SETUP_MESSAGE = (
    "Playwright hoac Chromium chua cai — chay: "
    "python -m diamondx10 muse-setup"
)

DEFAULT_PROMPT = (
    "Ban la analyst phu trach desk trong briefing dinh kem. "
    "Hay doc ky file briefing va phan tich nhu analyst cua desk do. "
    "Tra ve DUY NHAT 1 object JSON nam trong 1 khoi ```json, theo dung "
    "mau verdict JSON trong file briefing (desk, analyst, direction "
    "buy | sell | neutral, confidence 0..1, drivers, risks, note, "
    "created_utc). Khong them giai thich ngoai khoi JSON."
)

# Selector uu tien theo role/text; thu lan luot cho toi khi thay.
COMPOSER_SELECTORS = ("textarea", "[contenteditable='true']",
                      "[role='textbox']")
ASSISTANT_MESSAGE_SELECTORS = (
    "[data-message-author-role='assistant']",
    "[data-testid*='assistant']",
    "[class*='assistant']",
)

_FENCED_JSON_RE = re.compile(r"```json\s*(.*?)\s*```",
                             re.DOTALL | re.IGNORECASE)
_FENCED_ANY_RE = re.compile(r"```\s*(.*?)\s*```", re.DOTALL)


class MuseBrowserError(Exception):
    """Loi mo/dieu khien trinh duyet Muse (Playwright thieu, Chromium
    thieu, khong mo duoc trang, khong nhan dien duoc giao dien)."""


# --- Config ---

def _muse_cfg(cfg):
    """Muc `muse:` trong config ({} neu chua co)."""
    return (cfg or {}).get("muse") or {}


def _chat_url(cfg):
    return _muse_cfg(cfg).get("chat_url") or DEFAULT_CHAT_URL


def _profile_dir(cfg):
    """Duong dan profile; tuong doi thi tinh tu goc repo."""
    raw = _muse_cfg(cfg).get("profile_dir") or DEFAULT_PROFILE_DIR
    path = Path(raw)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return path


def _headless(cfg, headless):
    """headless=None -> lay tu config muse.headless (mac dinh False)."""
    if headless is not None:
        return bool(headless)
    return bool(_muse_cfg(cfg).get("headless", False))


# --- Mo trinh duyet (helper dung chung cho send + wait) ---

class _BrowserSession:
    """1 context Chromium persistent + 1 tab; dong sach khi xong."""

    def __init__(self, context, page, chat_url, playwright=None):
        self.context = context
        self.page = page
        self.chat_url = chat_url
        self._playwright = playwright

    def close(self):
        close = getattr(self.context, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 — dong trinh duyet loi thi thoi
                pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:  # noqa: BLE001 — dung Playwright loi thi thoi
                pass


def _new_page(context):
    """Tab moi cua context; fallback ve tab dau tien neu co."""
    new_page = getattr(context, "new_page", None)
    if callable(new_page):
        return new_page()
    pages = getattr(context, "pages", None) or []
    if pages:
        return pages[0]
    raise MuseBrowserError(
        "Khong mo duoc tab moi trong trinh duyet Muse.")


def _open_page(cfg, headless=None, driver=None):
    """Mo persistent context + tab, tra _BrowserSession.

    driver: doi tuong co launch_persistent_context (dung cho test —
    neu truyen thi khong import playwright). Khong truyen thi import
    playwright LAZY o day; thieu Playwright/Chromium thi raise
    MuseBrowserError huong dan chay `muse-setup`.
    """
    profile_dir = _profile_dir(cfg)
    profile_dir.mkdir(parents=True, exist_ok=True)
    headless = _headless(cfg, headless)
    chat_url = _chat_url(cfg)
    if driver is not None:
        context = driver.launch_persistent_context(
            user_data_dir=str(profile_dir), headless=headless)
        return _BrowserSession(context, _new_page(context), chat_url)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise MuseBrowserError(SETUP_MESSAGE) from None
    try:
        playwright = sync_playwright().start()
    except Exception as exc:  # noqa: BLE001 — Playwright loi khoi dong
        raise MuseBrowserError(
            f"Khong khoi dong duoc Playwright: {exc} — {SETUP_MESSAGE}"
        ) from None
    try:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir), headless=headless)
    except Exception as exc:  # noqa: BLE001 — Chromium chua cai / loi mo
        try:
            playwright.stop()
        except Exception:  # noqa: BLE001 — dung Playwright loi thi thoi
            pass
        raise MuseBrowserError(
            f"Khong mo duoc Chromium: {exc} — {SETUP_MESSAGE}"
        ) from None
    return _BrowserSession(context, _new_page(context), chat_url,
                           playwright=playwright)


def _goto(page, url):
    """Mo URL; thu co wait_until, khong duoc thi goto don gian."""
    try:
        page.goto(url, wait_until="domcontentloaded")
    except TypeError:
        page.goto(url)


def _page_url(page):
    """URL hien tai cua tab (thuoc tinh hoac ham tuy driver)."""
    try:
        url = getattr(page, "url", "")
        return url() if callable(url) else str(url or "")
    except Exception:  # noqa: BLE001 — khong doc duoc URL thi de trong
        return ""


def _wait_for_selector(page, selector, timeout_ms):
    """Cho selector xuat hien; True neu thay, False neu het thoi gian."""
    wait = getattr(page, "wait_for_selector", None)
    if callable(wait):
        try:
            wait(selector, timeout=timeout_ms)
            return True
        except Exception:  # noqa: BLE001 — het thoi gian / loi cho
            return False
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:  # noqa: BLE001 — locator loi thi cho tiep
            pass
        time.sleep(0.5)
    return False


def _locator_count(locator):
    """So phan tu cua locator; 0 neu khong dem duoc."""
    try:
        return int(locator.count())
    except Exception:  # noqa: BLE001 — khong dem duoc thi coi nhu 0
        return 0


# --- Gui briefing ---

def _find_composer(page, timeout_sec):
    """Tim o nhap tin nhan (composer); None neu het thoi gian khong thay."""
    per_selector = max(5, int(timeout_sec) // len(COMPOSER_SELECTORS))
    for selector in COMPOSER_SELECTORS:
        if _wait_for_selector(page, selector, per_selector * 1000):
            return page.locator(selector).first
    return None


def _type_prompt(page, composer, prompt):
    """Nhap prompt vao composer; fallback click + go phim."""
    try:
        composer.fill(prompt)
        return True
    except Exception:  # noqa: BLE001 — fill khong duoc thi go tay
        pass
    try:
        composer.click()
        page.keyboard.type(prompt)
        return True
    except Exception:  # noqa: BLE001 — go phim cung khong duoc
        return False


def _attach_file(page, file_path):
    """Dinh kem file qua input[type=file]; True neu dinh kem duoc."""
    try:
        inputs = page.locator("input[type='file']")
        if _locator_count(inputs) > 0:
            inputs.first.set_input_files(str(file_path))
            return True
    except Exception:  # noqa: BLE001 — thu cach khac
        pass
    # Thu bam nut dinh kem / tai len de hien input file roi thu lai.
    get_by_role = getattr(page, "get_by_role", None)
    if callable(get_by_role):
        try:
            button = get_by_role(
                "button",
                name=re.compile("attach|dinh kem|tai len|upload",
                                re.IGNORECASE))
            if _locator_count(button) > 0:
                button.first.click()
                time.sleep(1)
                inputs = page.locator("input[type='file']")
                if _locator_count(inputs) > 0:
                    inputs.first.set_input_files(str(file_path))
                    return True
        except Exception:  # noqa: BLE001 — khong bam duoc nut dinh kem
            pass
    return False


def _click_send(page):
    """Bam nut Send; fallback nut submit, cuoi cung phim Enter."""
    get_by_role = getattr(page, "get_by_role", None)
    if callable(get_by_role):
        try:
            button = get_by_role(
                "button", name=re.compile("send|gui", re.IGNORECASE))
            if _locator_count(button) > 0:
                button.first.click()
                return True
        except Exception:  # noqa: BLE001 — thu cach khac
            pass
    try:
        submit = page.locator("button[type='submit']")
        if _locator_count(submit) > 0:
            submit.first.click()
            return True
    except Exception:  # noqa: BLE001 — thu phim Enter
        pass
    try:
        page.keyboard.press("Enter")
        return True
    except Exception:  # noqa: BLE001 — khong gui duoc
        return False


def send_briefing(file_path, cfg, prompt=None, headless=None,
                  timeout_sec=120, *, driver=None):
    """Gui file briefing len chat Muse, tra dict ket qua.

    Tra {"sent": bool, "url": str, "message": str}. sent False khi
    khong tim thay composer / khong dinh kem duoc file / khong bam
    duoc nut gui (message giai thich ro ly do). Khong tim thay
    composer thi them "session_expired": True — dau hieu phien dang
    nhap Muse co the da het han (dang o trang dang nhap), lenh goi
    (vd `muse-auto`) dung co nay de gui canh bao Telegram + huong dan
    dang nhap lai bang tay. Thieu Playwright hoac Chromium thi raise
    MuseBrowserError huong dan chay `muse-setup` (KHONG tu cai dat
    gi). File khong ton tai thi raise FileNotFoundError.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Khong tim thay file briefing {file_path}")
    session = _open_page(cfg, headless=headless, driver=driver)
    try:
        _goto(session.page, session.chat_url)
        composer = _find_composer(session.page, timeout_sec)
        if composer is None:
            return {
                "sent": False,
                "session_expired": True,
                "url": _page_url(session.page),
                "message": (
                    "Khong tim thay o nhap tin nhan (composer) tren "
                    f"{session.chat_url} sau {timeout_sec} giay — co the "
                    "ban chua dang nhap Muse. Hay chay headed 1 lan "
                    "(khong --headless), dang nhap vao muse.ai TAY trong "
                    "cua so trinh duyet, mo chat chinh, roi chay lai lenh "
                    "gui. Neu da dang nhap ma van loi, giao dien muse.ai "
                    "co the da doi — can cap nhat selector trong "
                    "muse_browser.py."
                ),
            }
        if not _attach_file(session.page, path):
            return {
                "sent": False,
                "url": _page_url(session.page),
                "message": (
                    "Khong tim thay o dinh kem file (input file / nut "
                    "Attach) tren trang chat — giao dien muse.ai co the "
                    "da doi. Hay dinh kem file briefing TAY trong cua so "
                    "trinh duyet roi gui, hoac cap nhat selector trong "
                    "muse_browser.py."
                ),
            }
        if not _type_prompt(session.page, composer,
                            prompt or DEFAULT_PROMPT):
            return {
                "sent": False,
                "url": _page_url(session.page),
                "message": (
                    "Khong nhap duoc prompt vao o nhap tin nhan — giao "
                    "dien muse.ai co the da doi. Hay nhap prompt TAY "
                    "trong cua so trinh duyet roi gui."
                ),
            }
        if not _click_send(session.page):
            return {
                "sent": False,
                "url": _page_url(session.page),
                "message": (
                    "Khong bam duoc nut gui (Send) — giao dien muse.ai "
                    "co the da doi. Hay bam gui TAY trong cua so trinh "
                    "duyet."
                ),
            }
        time.sleep(2)
        return {
            "sent": True,
            "url": _page_url(session.page),
            "message": f"Da gui file briefing {path.name} toi Muse.",
        }
    finally:
        session.close()


# --- Doi verdict ---

def _assistant_locator(page):
    """Locator cac tin nhan assistant; None neu khong nhan dien duoc
    cau truc tin nhan tren trang."""
    for selector in ASSISTANT_MESSAGE_SELECTORS:
        try:
            locator = page.locator(selector)
        except Exception:  # noqa: BLE001 — thu selector tiep theo
            continue
        if _locator_count(locator) > 0:
            return locator
    return None


def _assistant_count(page):
    """So tin nhan assistant hien co (0 neu khong nhan dien duoc)."""
    locator = _assistant_locator(page)
    return _locator_count(locator) if locator is not None else 0


def _message_text(locator, index):
    """Text cua tin nhan assistant thu `index` ("" neu khong doc duoc)."""
    try:
        return locator.nth(index).inner_text() or ""
    except Exception:  # noqa: BLE001 — thu text_content
        pass
    try:
        return locator.nth(index).text_content() or ""
    except Exception:  # noqa: BLE001 — khong doc duoc tin nhan
        return ""


def _new_assistant_texts(page, baseline_count):
    """Text cac tin nhan assistant xuat hien SAU baseline (theo thu tu)."""
    locator = _assistant_locator(page)
    if locator is None:
        return []
    total = _locator_count(locator)
    return [_message_text(locator, i)
            for i in range(baseline_count, total)]


def _extract_json_candidates(text):
    """Cac chuoi JSON trong cac khoi ``` (uu tien khoi ```json)."""
    candidates = _FENCED_JSON_RE.findall(text or "")
    if candidates:
        return candidates
    return [block for block in _FENCED_ANY_RE.findall(text or "")
            if block.strip().startswith("{")]


def wait_for_verdict(cfg, timeout_min=10, poll_sec=10, *, driver=None,
                     store_path=None, headless=None):
    """Doi verdict JSON trong chat Muse, luu vao kho neu hop le.

    Chi xet cac tin nhan assistant xuat hien SAU luc bat dau doi
    (khong lay lai verdict cu). Lay khoi ```json CUOI CUNG trong tin
    nhan moi nhat, parse + validate bang synthesis.validate_verdict,
    luu bang synthesis.save_verdict roi tra verdict (dict). Het thoi
    gian / khong co khoi JSON / verdict khong hop le thi in ly do ro
    rang va tra None — KHONG BAO GIO luu verdict chua validate.
    headless=None -> lay tu config muse.headless (mac dinh False);
    `muse-auto` truyen headless=True de ca luong doi cung chay ngam.
    Fallback tay: user copy verdict tu chat roi chay
    `verdict --file <verdict.json>`.
    """
    try:
        session = _open_page(cfg, headless=headless, driver=driver)
    except MuseBrowserError as exc:
        print(f"LOI: {exc}")
        return None
    try:
        try:
            _goto(session.page, session.chat_url)
        except Exception as exc:  # noqa: BLE001 — khong mo duoc trang chat
            print(f"LOI: khong mo duoc {session.chat_url}: {exc}")
            return None
        baseline = _assistant_count(session.page)
        deadline = time.monotonic() + max(1, int(timeout_min)) * 60
        last_reason = (
            "chua thay tin nhan assistant moi nao co khoi ```json verdict."
        )
        while True:
            for text in reversed(
                    _new_assistant_texts(session.page, baseline)):
                candidates = _extract_json_candidates(text)
                if not candidates:
                    continue
                for raw in reversed(candidates):
                    try:
                        data = json.loads(raw)
                    except ValueError as exc:
                        last_reason = (
                            "tim thay khoi ```json nhung khong doc duoc "
                            f"JSON: {exc}"
                        )
                        continue
                    try:
                        verdict = validate_verdict(data)
                    except ValueError as exc:
                        last_reason = (
                            "verdict trong chat khong hop le: "
                            f"{exc} — can Muse tra dung mau JSON trong "
                            "briefing."
                        )
                        continue
                    save_verdict(verdict, store_path)
                    print(f"OK: da luu verdict — desk {verdict['desk']} — "
                          f"direction {verdict['direction']} "
                          f"(tin cay {verdict['confidence']:g})")
                    return verdict
                last_reason = (
                    "tin nhan assistant moi khong co khoi ```json verdict "
                    "hop le."
                )
            if time.monotonic() >= deadline:
                break
            time.sleep(max(1, int(poll_sec)))
        print(f"LOI: het {timeout_min} phut cho verdict — {last_reason}")
        print("Fallback tay: copy khoi JSON verdict tu chat Muse, luu ra "
              "file, roi chay: python -m diamondx10 verdict --file "
              "<verdict.json>")
        return None
    finally:
        session.close()
