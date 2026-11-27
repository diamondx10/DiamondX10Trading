"""Chu ky PTCB tu dong (muse-auto): tao briefing -> gui Muse -> doi verdict.

Lenh `muse-auto` chay dinh ky (Windows Task Scheduler) truoc phien:
moi desk: tao briefing bang chung duong `build_briefing` nhu lenh
`briefing`, gui bang `send_briefing`, doi verdict bang
`wait_for_verdict` (toi da `muse.wait_min`, mac dinh 10 phut).
Khong lap lai logic gui/doi — chi goi 2 ham co san o muse_browser.

Ma thoat:
- 0 khi TAT CA briefing da GUI duoc (thieu verdict / het gio doi chi
  la CANH BAO, khong phai loi — vong live van dung verdict cu).
- 1 khi BAT KY lenh gui nao that bai (loi trinh duyet, chua dang
  nhap, khong tim thay composer).

Het phien dang nhap: neu gui that bai vi phien Muse da het han
(khong tim thay composer — co the dang o trang dang nhap), lenh gui
them 1 canh bao Telegram (tieng Anh, theo quy tac 44) de Phu dang
nhap lai bang tay (chay `muse-send` headed 1 lan). Canh bao Telegram
la best-effort: neu Telegram chua cau hinh thi chi in ro ra, loi
Telegram KHONG bao gio che mat loi goc.

Trang thai lan chay ghi vao `decisions/fa-cycle-state.json`
(started_utc + tung desk {sent, verdict_stored, reason}) de web UI
hien thi — file nay KHONG bao gio chua token hay du lieu phien.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from . import telegram as telegram_mod
from .briefing import DESKS as BRIEFING_DESKS
from .briefing import build_briefing
from .i18n import get_language, t
from .muse_browser import (
    DEFAULT_WAIT_MIN,
    MuseBrowserError,
    send_briefing,
    wait_for_verdict,
)

FA_CYCLE_STATE = (Path(__file__).resolve().parents[2] / "decisions"
                  / "fa-cycle-state.json")

# Canh bao het phien — ban tieng Anh goc (giu nguyen de test cu van
# dung); ban hien thi lay qua session_expired_alert() theo ngon ngu
# config (mac dinh "vi").
SESSION_EXPIRED_ALERT = (
    "DiamondX10 — Muse browser session expired.\n"
    "The automatic FA cycle could not send the briefing: the Muse "
    "session is gone (sign-in page shown / composer not found).\n"
    "Please re-sign in manually: run "
    "`python -m diamondx10 muse-send --file <briefing.md> --no-wait` "
    "headed once and sign in to muse.ai in the browser window.\n"
    "The live loop keeps using the previous verdict meanwhile."
)


def session_expired_alert(lang=None, cfg=None):
    """Text canh bao het phien Muse theo ngon ngu (mac dinh "vi").

    lang thang "vi" | "en" (uu tien); khong truyen thi doc config qua
    get_language. Chi doi ngon ngu hien thi, khong doi logic chu ky.
    """
    return t("muse.session_expired",
             lang if lang is not None else get_language(cfg))

DEFAULT_SEND_TIMEOUT_SEC = 60


def _is_session_expired_error(exc):
    """True neu loi trinh duyet co ve la het phien dang nhap
    (thong bao nhac dang nhap / sign-in / login)."""
    text = str(exc or "").lower()
    return ("dang nhap" in text or "sign-in" in text
            or "sign in" in text or "login" in text
            or "log in" in text)


def _notify_session_expired(cfg):
    """Gui canh bao het phien qua Telegram (best-effort).

    Tra True neu gui duoc. Loi Telegram (chua cau hinh / mang loi)
    chi in CANH BAO, KHONG raise — khong che mat loi goc.
    """
    ok = telegram_mod.send_message(session_expired_alert(cfg=cfg), cfg=cfg)
    if ok:
        print("OK: da gui canh bao het phien Muse qua Telegram — "
              "can dang nhap lai bang tay.")
    else:
        print("CANH BAO: khong gui duoc canh bao het phien Muse qua "
              "Telegram (xem CANH BAO Telegram o tren) — hay dang nhap "
              "lai Muse bang tay (chay muse-send headed 1 lan).")
    return ok


def _write_state(state, state_path=None):
    """Ghi file trang thai chu ky; tra duong dan da ghi.

    Loi ghi (vd khong ghi duoc file) thi raise OSError — nguoi goi
    bat va chi in CANH BAO (khong doi ma thoat).
    """
    path = Path(state_path) if state_path is not None else FA_CYCLE_STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def run_muse_auto(cfg, desks, wait_min, headless=True, *, driver=None,
                  feed=None, news_fetcher=None, out_dir=None,
                  state_path=None, poll_sec=None, send_timeout_sec=None):
    """Chay 1 chu ky PTCB tu dong cho cac desk. Tra ma thoat (0/1).

    desks: list desk (vd ["forex"]). wait_min: so phut doi verdict
    toi da moi desk. headless: True = trinh duyet an (mac dinh cho
    chay dinh ky). driver/feed/news_fetcher/out_dir/state_path/
    poll_sec/send_timeout_sec: diem tiem cho test (khong truyen thi
    dung gia tri that / mac dinh).
    """
    started = datetime.now(timezone.utc)
    wait = int(wait_min)
    timeout_sec = (DEFAULT_SEND_TIMEOUT_SEC if send_timeout_sec is None
                   else int(send_timeout_sec))
    results = {}
    any_send_failed = False
    session_expired = False
    for desk in desks:
        # 1. Tao briefing (chung duong voi lenh `briefing`).
        try:
            brief = build_briefing(cfg, desk, 3, feed=feed,
                                   news_fetcher=news_fetcher,
                                   out_dir=out_dir)
        except (ValueError, ImportError, ConnectionError, OSError) as exc:
            reason = f"khong tao duoc briefing: {exc}"
            results[desk] = {"sent": False, "verdict_stored": False,
                             "reason": reason}
            print(f"LOI ({desk}): {reason}")
            any_send_failed = True
            continue
        except Exception as exc:  # noqa: BLE001 — lenh CLI khong traceback
            reason = f"khong tao duoc briefing ({exc})"
            results[desk] = {"sent": False, "verdict_stored": False,
                             "reason": reason}
            print(f"LOI ({desk}): {reason}")
            any_send_failed = True
            continue
        print(f"OK ({desk}): briefing {brief['desk']} cho "
              f"{brief['analyst']} ({brief['md_path']})")
        # 2. Gui briefing len chat Muse.
        try:
            sent = send_briefing(brief["md_path"], cfg, headless=headless,
                                 timeout_sec=timeout_sec, driver=driver)
        except MuseBrowserError as exc:
            if _is_session_expired_error(exc):
                session_expired = True
            reason = f"khong gui duoc briefing: {exc}"
            results[desk] = {"sent": False, "verdict_stored": False,
                             "reason": reason}
            print(f"LOI ({desk}): {reason}")
            any_send_failed = True
            continue
        except Exception as exc:  # noqa: BLE001 — lenh CLI khong traceback
            reason = f"khong gui duoc briefing ({exc})"
            results[desk] = {"sent": False, "verdict_stored": False,
                             "reason": reason}
            print(f"LOI ({desk}): {reason}")
            any_send_failed = True
            continue
        if not sent.get("sent"):
            if sent.get("session_expired"):
                session_expired = True
            reason = (sent.get("message")
                      or "khong gui duoc briefing.")
            results[desk] = {"sent": False, "verdict_stored": False,
                             "reason": reason}
            print(f"LOI ({desk}): {reason}")
            any_send_failed = True
            continue
        print(f"OK ({desk}): {sent.get('message')} "
              f"({sent.get('url') or ''})")
        # 3. Doi verdict (best-effort: het gio chi la CANH BAO).
        print(f"Cho verdict {desk} toi da {wait} phut ...")
        wait_kwargs = {"timeout_min": wait, "headless": headless}
        if poll_sec is not None:
            wait_kwargs["poll_sec"] = poll_sec
        verdict = wait_for_verdict(cfg, driver=driver, **wait_kwargs)
        if verdict is None:
            reason = (f"da gui briefing, het {wait} phut cho verdict — "
                      "chua co verdict moi, vong live van dung verdict "
                      "cu (neu co).")
            results[desk] = {"sent": True, "verdict_stored": False,
                             "reason": reason}
            print(f"CANH BAO ({desk}): {reason}")
        else:
            reason = (f"verdict da luu — desk {verdict['desk']} — "
                      f"direction {verdict['direction']} "
                      f"(tin cay {verdict['confidence']:g})")
            results[desk] = {"sent": True, "verdict_stored": True,
                             "reason": reason}
            print(f"OK ({desk}): {reason}")
    # 4. Ghi file trang thai (cho web UI) + canh bao het phien (neu co).
    state = {"started_utc": started.isoformat(), "desks": results}
    try:
        path = _write_state(state, state_path)
        print(f"Trang thai chu ky FA da ghi: {path}")
    except OSError as exc:
        print(f"CANH BAO: khong ghi duoc file trang thai chu ky FA: {exc}")
    if session_expired:
        _notify_session_expired(cfg)
    # 5. Tom tat tung desk + ma thoat.
    print("TOM TAT chu ky FA:")
    for desk in desks:
        entry = results[desk]
        if not entry["sent"]:
            print(f"  [{desk}] FAILED: {entry['reason']}")
        elif entry["verdict_stored"]:
            print(f"  [{desk}] SENT + verdict stored: {entry['reason']}")
        else:
            print(f"  [{desk}] SENT, chua co verdict moi: {entry['reason']}")
    if any_send_failed:
        print("LOI: co desk gui briefing that bai — xem ly do o tren.")
        return 1
    return 0


def cmd_muse_auto(cfg, desk=None, all_desks=False, wait_min=None,
                  headless=True, *, driver=None, feed=None,
                  news_fetcher=None, out_dir=None, state_path=None,
                  poll_sec=None):
    """Lenh CLI `muse-auto`: chu ky PTCB tu dong cho 1 desk hoac tat ca.

    Mac dinh chay tat ca 4 desk (khi khong truyen --desk), trinh duyet
    an (headless=True — chay dinh ky khong co desktop tuong tac).
    Tra 0 khi tat ca briefing da gui (thieu verdict chi la CANH BAO),
    1 khi bat ky lenh gui nao that bai.
    """
    desks = list(BRIEFING_DESKS) if (all_desks or desk is None) else [desk]
    muse_cfg = (cfg or {}).get("muse") or {}
    wait = (int(wait_min) if wait_min is not None
            else int(muse_cfg.get("wait_min") or DEFAULT_WAIT_MIN))
    return run_muse_auto(cfg, desks, wait, headless=headless,
                         driver=driver, feed=feed,
                         news_fetcher=news_fetcher, out_dir=out_dir,
                         state_path=state_path, poll_sec=poll_sec)
