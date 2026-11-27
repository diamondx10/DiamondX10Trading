"""Bai dang phan tich (analysis posts) — feed kieu Facebook tren trang chu.

Moi bai dang la 1 ket luan phan tich (BUY / SELL / NEUTRAL) cho 1
symbol, kem tom tat + drivers / risks + muc gia (neu co). Bai dang
luu o decisions/analysis-posts.json (goc repo, cung quy uoc duong dan
nhu decisions.py / synthesis.py: goc repo = parents[2] cua file nay).
File nay la file RUNTIME — khong commit.

Nguon bai dang:
- "synthesis": lenh `synthesize --publish` (hoac POST /api/publish)
  dang 1 bai / symbol sau khi tong hop Yuling. DEDUPE: neu bai moi
  nhat cua cung symbol co cung action VA cung verdict_created_utc
  thi tra lai bai cu, khong tao bai moi (khong gui Telegram lai).
- "manual": lenh `publish-post` (hoac POST /api/posts) — luon tao
  bai moi, khong dedupe.

Telegram (quy tac: moi ket luan BUY/SELL deu gui tom tat; NEUTRAL
khong gui): chi gui khi action la BUY hoac SELL, chi khi config
telegram.enabled = true, va chi la TIN THONG TIN — khong nut dat
lenh, khong tao lenh cho (lenh cho chi co tu vong live / nut
Telegram, xem listener.py). Loi gui khong bao gio lam hong viec
dang bai (log + tiep tuc).
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import telegram as telegram_mod
from .briefing import DESK_ANALYSTS
from .newsfeed import (
    NewsCardStore,
    impacts_for_symbol,
    is_test_mode,
    news_qualifies,
)

DESKS = ("forex", "xauusd", "crypto", "us_securities")
ACTIONS = ("BUY", "SELL", "NEUTRAL")
SOURCES = ("synthesis", "manual")

POST_STORE = (Path(__file__).resolve().parents[2] / "decisions"
              / "analysis-posts.json")


def _now_utc_iso():
    return datetime.now(timezone.utc).isoformat()


def _is_number(value):
    return (isinstance(value, (int, float))
            and not isinstance(value, bool))


def _clean_str_list(value, field):
    """List chuoi sach: None -> []; chuoi "a;b" -> tach; sai kieu thi
    ValueError."""
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(";")
                if item.strip()]
    if isinstance(value, list):
        if not all(isinstance(item, str) for item in value):
            raise ValueError(
                f"{field} phai la list cac chuoi, nhan {value!r}")
        return list(value)
    raise ValueError(f"{field} phai la list cac chuoi hoac chuoi "
                     f"'a;b', nhan {value!r}")


def _clean_number(value, field):
    """So (int/float) -> float; None giu None; sai kieu thi ValueError."""
    if value is None:
        return None
    if not _is_number(value):
        raise ValueError(f"{field} phai la so, nhan {value!r}")
    return float(value)


def _analyst_for_desk(cfg, desk):
    """Ten analyst phu trach desk (bang co dinh; fallback ve manager
    trong config neu desk la)."""
    if desk in DESK_ANALYSTS:
        return DESK_ANALYSTS[desk]
    manager = (((cfg or {}).get("fund") or {}).get("desks") or {}).get(desk)
    if isinstance(manager, dict) and manager.get("manager"):
        return str(manager["manager"])
    return desk


def validate_post_fields(desk, symbol, action, summary, confidence=0.0,
                         drivers=None, risks=None, entry=None, sl=None,
                         tp=None):
    """Kiem tra cac truong bai dang, tra dict da chuan hoa (chua co id /
    created_utc / analyst / source / verdict_created_utc).

    Bat ky loi nao cung raise ValueError voi thong bao ro rang.
    """
    if not isinstance(desk, str) or desk not in DESKS:
        raise ValueError(
            f"desk khong hop le: {desk!r} (chon trong {list(DESKS)})")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Thieu symbol (vd 'EURUSD').")
    if not isinstance(action, str):
        raise ValueError(f"action khong hop le: {action!r}")
    action = action.strip().upper()
    if action not in ACTIONS:
        raise ValueError(
            f"action khong hop le: {action!r} "
            "(chon BUY | SELL | NEUTRAL)")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("Thieu summary (tom tat 1-3 cau ve ket luan).")
    if not _is_number(confidence):
        raise ValueError(
            f"confidence phai la so 0..1, nhan {confidence!r}")
    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(
            f"confidence phai trong 0..1, nhan {confidence!r}")
    return {"desk": desk, "symbol": symbol.strip().upper(),
            "action": action, "summary": summary.strip(),
            "confidence": confidence,
            "drivers": _clean_str_list(drivers, "drivers"),
            "risks": _clean_str_list(risks, "risks"),
            "entry": _clean_number(entry, "entry"),
            "sl": _clean_number(sl, "sl"),
            "tp": _clean_number(tp, "tp")}


class PostStore:
    """Kho bai dang phan tich (JSON file, 1 object {"posts": [...]}).

    File chua co / hong / sai dinh dang thi doc nhu kho rong — khong
    bao gio raise khi doc. Ghi thi tao thu muc cha neu can.
    """

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else POST_STORE

    def _load(self):
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return []
        if not isinstance(raw, dict) or not isinstance(
                raw.get("posts"), list):
            return []
        return [dict(post) for post in raw["posts"]
                if isinstance(post, dict)]

    def _save(self, posts):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"posts": posts}, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def list_posts(self, limit=20, desk=None):
        """Bai dang moi nhat len dau; loc theo desk neu truyen.

        limit None thi tra tat ca; limit <= 0 thi tra [].
        """
        posts = self._load()
        if desk is not None:
            posts = [post for post in posts
                     if post.get("desk") == desk]
        indexed = sorted(
            enumerate(posts),
            key=lambda item: (item[1].get("created_utc") or "", item[0]),
            reverse=True)
        ordered = [post for _, post in indexed]
        if limit is None:
            return [dict(post) for post in ordered]
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 20
        if limit <= 0:
            return []
        return [dict(post) for post in ordered[:limit]]

    def get_post(self, post_id):
        """1 bai theo id, hoac None neu khong co."""
        for post in self._load():
            if post.get("id") == post_id:
                return dict(post)
        return None

    def publish_post(self, *, desk, symbol, action, summary,
                     confidence=0.0, drivers=None, risks=None, entry=None,
                     sl=None, tp=None, analyst=None, source="manual",
                     verdict_created_utc=None, cfg=None, news_id=None,
                     test_mode=False):
        """Dang 1 bai moi. Tra (post, created).

        created=False khi dedupe: source "synthesis" ma bai moi nhat
        cua cung symbol co cung action VA cung verdict_created_utc
        VA cung che do test thi tra lai bai cu (khong tao bai moi,
        khong gui Telegram lai). Bai manual luon tao moi (created=True).

        news_id (tuy chon): id tin da kich hoat bai nay (xem
        publish_synthesis_post) — chi ghi len bai khi truyen, bai
        khong co tin kich hoat thi khong co truong nay.

        test_mode (tuy chon): bai dang o che do TEST (xem newsfeed.
        is_test_mode) thi ghi "test_mode": true len bai va tin
        Telegram gui di kem tien to "[TEST] " — khong bao gio nham
        voi khuyen nghi that. Bai thuong khong co truong nay.

        Bai BUY/SELL moi thi gui tom tat qua Telegram (chi khi
        telegram.enabled = true); NEUTRAL khong gui. Loi gui Telegram
        khong lam hong viec dang bai.
        """
        if source not in SOURCES:
            raise ValueError(
                f"source khong hop le: {source!r} "
                f"(chon trong {list(SOURCES)})")
        cleaned = validate_post_fields(
            desk, symbol, action, summary, confidence=confidence,
            drivers=drivers, risks=risks, entry=entry, sl=sl, tp=tp)
        symbol = cleaned["symbol"]
        action = cleaned["action"]
        posts = self._load()
        if source == "synthesis":
            latest = self._latest_for_symbol(posts, symbol)
            if (latest is not None
                    and latest.get("action") == action
                    and latest.get("verdict_created_utc")
                    == verdict_created_utc
                    and bool(latest.get("test_mode")) == bool(test_mode)):
                return dict(latest), False
        if (not isinstance(analyst, str) or not analyst.strip()):
            analyst = _analyst_for_desk(cfg, desk)
        else:
            analyst = analyst.strip()
        post = dict(cleaned)
        post.update({
            "id": self._new_id(posts),
            "created_utc": _now_utc_iso(),
            "analyst": analyst,
            "source": source,
            "verdict_created_utc": verdict_created_utc,
        })
        if news_id is not None:
            post["news_id"] = news_id
        if test_mode:
            post["test_mode"] = True
        posts.append(post)
        self._save(posts)
        if action in ("BUY", "SELL"):
            self._notify(post, cfg)
        return dict(post), True

    @staticmethod
    def _latest_for_symbol(posts, symbol):
        """Bai moi nhat cua 1 symbol, hoac None neu chua co."""
        same = [post for post in posts if post.get("symbol") == symbol]
        if not same:
            return None
        indexed = sorted(
            enumerate(posts),
            key=lambda item: (item[1].get("created_utc") or "", item[0]),
            reverse=True)
        for _, post in indexed:
            if post.get("symbol") == symbol:
                return post
        return None

    @staticmethod
    def _new_id(posts):
        """Id 8 ky hex, khong trung id da co trong kho."""
        taken = {post.get("id") for post in posts}
        for _ in range(10):
            candidate = uuid.uuid4().hex[:8]
            if candidate not in taken:
                return candidate
        return uuid.uuid4().hex[:8]

    @staticmethod
    def _notify(post, cfg):
        """Gui tom tat bai BUY/SELL qua Telegram (best-effort).

        Chi gui khi telegram.enabled = true. Loi gui (thieu token /
        chat_id / mang / loi khac) chi in canh bao, khong raise.
        """
        try:
            if not telegram_mod.telegram_enabled(cfg):
                return False
            text = telegram_mod.format_post_summary(post, cfg=cfg)
            if post.get("test_mode"):
                # Bai test luon danh dau ro trong chinh tin Telegram.
                text = "[TEST] " + text
            return bool(telegram_mod.send_message(text, cfg=cfg))
        except Exception as exc:  # noqa: BLE001 — gui loi thi bao, khong crash
            print("CANH BAO: khong gui duoc tom tat bai phan tich qua "
                  f"Telegram ({exc}).")
            return False


def _synthesis_action(ta_action, syn):
    """Ket luan bai dang tu tong hop Yuling: PTKT BUY/SELL khong bi
    chan -> BUY/SELL; PTKT HOLD hoac bi chan -> NEUTRAL (khong vao
    lenh thi khong co ket luan mua/ban)."""
    if syn.get("blocked"):
        return "NEUTRAL"
    ta = (ta_action or "").strip().upper()
    if ta in ("BUY", "SELL"):
        return ta
    return "NEUTRAL"


def _synthesis_summary(ta_action, ta_reason, verdict, levels, action,
                       blocked):
    """Tom tat 1-3 cau cho bai tong hop: cau PTKT + cau PTCB (kem
    drivers / risks) + cau muc gia (chi khi BUY/SELL co levels) hoac
    cau chan lenh (khi bi chan). Tieng Viet khong dau."""
    ta = (ta_action or "").strip().upper()
    first = f"PTKT {ta} — {ta_reason.strip()}" if ta_reason else f"PTKT {ta}."
    if not first.endswith("."):
        first += "."
    if verdict is None:
        second = "Chua co nhan dinh PTCB moi."
    else:
        direction = verdict.get("direction")
        conf = verdict.get("confidence", 0.0)
        if direction == "neutral":
            second = f"PTCB trung lap (tin cay {conf:g})."
        else:
            word = "mua" if direction == "buy" else "ban"
            second = f"PTCB {word} (tin cay {conf:g})"
            drivers = verdict.get("drivers") or []
            if drivers:
                second += ": " + "; ".join(str(d) for d in drivers)
            risks = verdict.get("risks") or []
            if risks:
                second += "; rui ro: " + "; ".join(str(r) for r in risks)
            second += "."
    parts = [first, second]
    if blocked:
        parts.append("Tong hop Yuling: chan khong vao lenh.")
    elif action in ("BUY", "SELL") and levels:
        entry, sl, tp = levels.get("entry"), levels.get("sl"), levels.get("tp")
        if entry is not None and sl is not None and tp is not None:
            parts.append(f"Entry {float(entry):g}, SL {float(sl):g}, "
                         f"TP {float(tp):g}.")
    return " ".join(parts)


def publish_synthesis_post(store, cfg, desk, symbol, ta_action, ta_reason,
                           levels, verdict, syn, *, verdicts=None,
                           news_card_store=None, test_mode=None):
    """Dang 1 bai tu ket qua tong hop Yuling (xem PostStore.publish_post).

    action: BUY/SELL khi PTKT co huong va khong bi chan, NEUTRAL khi
    HOLD hoac bi chan. confidence/drivers/risks lay tu verdict (neu
    co); entry/sl/tp lay tu levels TA (chi khi BUY/SELL). Tra
    (post, created) — created=False khi dedupe tra bai cu.

    Tin kich hoat (chi khi action BUY/SELL): trong cac verdict da luu
    (verdicts, mac dinh chi verdict cua desk nay), tim nhan dinh tac
    dong tung tin cho symbol nay; tin nao du chuan
    (newsfeed.news_qualifies — direction buy/sell, tin cay >= 0.6,
    tier 1/2, tong hop dong thuan) thi bai dang kem tom tat tac dong
    do vao drivers + tom tat, va ghi "news_id" len bai. Bai BUY/SELL
    thi tom tat van gui qua Telegram theo duong hien co — KHONG co
    them lenh gui Telegram nao o day. Tin khong du chuan (tier 3,
    tin cay thap, tong hop khong dong thuan) thi khong kich hoat
    gi them — impact cua no van hien tren the tin (da gan luc luu
    verdict). verdicts / news_card_store: diem tiem cho test.

    test_mode: che do TEST (None = doc `news.test_mode` trong cfg).
    Bat len thi MOI impact buy/sell deu du chuan (bo qua nguong 0.6 /
    dong thuan / loai tier), bai dang ghi "test_mode": true va tin
    Telegram kem tien to "[TEST] ". Phan tich tac dong van la verdict
    that cua Muse — che do test chi bo cua kich hoat, khong tao
    phan tich gia.
    """
    action = _synthesis_action(ta_action, syn)
    blocked = bool(syn.get("blocked"))
    levels = levels or {}
    if test_mode is None:
        test_mode = is_test_mode(cfg)
    test_mode = bool(test_mode)
    if action in ("BUY", "SELL"):
        entry, sl, tp = (levels.get("entry"), levels.get("sl"),
                         levels.get("tp"))
    else:
        entry, sl, tp = None, None, None
    summary = _synthesis_summary(ta_action, ta_reason, verdict, levels,
                                 action, blocked)
    drivers = list((verdict or {}).get("drivers") or [])
    risks = list((verdict or {}).get("risks") or [])
    news_id = None
    if action in ("BUY", "SELL"):
        news_id, news_summary = _qualifying_news_impact(
            verdicts if verdicts is not None
            else ([verdict] if verdict else []),
            symbol, action, news_card_store, test_mode)
        if news_id is not None:
            if news_summary:
                drivers = drivers + [news_summary]
                summary = summary + f" Tin lien quan: {news_summary}"
            else:
                summary = summary + " Co tin lien quan kich hoat khuyen nghi nay."
    return store.publish_post(
        desk=desk, symbol=symbol, action=action, summary=summary,
        confidence=(verdict.get("confidence") if verdict else 0.0),
        drivers=drivers,
        risks=risks,
        entry=entry, sl=sl, tp=tp,
        analyst=(verdict.get("analyst") if verdict else None),
        source="synthesis",
        verdict_created_utc=(
            verdict.get("created_utc") if verdict else None),
        cfg=cfg, news_id=news_id, test_mode=test_mode)


def _qualifying_news_impact(verdicts, symbol, action, news_card_store,
                            test_mode=False):
    """Tim tin du chuan kich hoat bai BUY/SELL cho 1 symbol.

    Tra (news_id, summary) cua impact du chuan co do tin cay cao
    nhat, hoac (None, None) neu khong co. Tier lay tu the tin trong
    kho (khong co the thi coi nhu khong du chuan — khong doan tier);
    o che do test thi tier khong can nua (news_qualifies bo qua)
    nhung van can the tin de biet tier khi khong phai test.
    """
    impacts = impacts_for_symbol(verdicts, symbol)
    if not impacts:
        return None, None
    store = (news_card_store if news_card_store is not None
             else NewsCardStore())
    best = None
    for impact in impacts:
        try:
            card = store.get_card(impact.get("news_id"))
        except Exception:  # noqa: BLE001 — doc kho the loi thi coi nhu khong co the
            card = None
        tier = card.get("tier") if isinstance(card, dict) else None
        if tier is None and not test_mode:
            continue
        if not news_qualifies(impact, tier, action, test_mode=test_mode):
            continue
        if best is None or float(impact.get("confidence") or 0.0) > float(
                best.get("confidence") or 0.0):
            best = impact
    if best is None:
        return None, None
    summary = best.get("summary")
    return best.get("news_id"), (summary if isinstance(summary, str)
                                 else "")


def cmd_publish_post(cfg, desk, symbol, action, summary, confidence=0.0,
                     entry=None, sl=None, tp=None, drivers=None,
                     risks=None, *, store_path=None):
    """Lenh CLI `publish-post`: dang 1 bai thu cong. Tra 0 neu dang
    duoc, 1 neu loi (in loi tieng Viet ngan gon, khong traceback).

    drivers / risks: list chuoi hoac chuoi "a;b". Bai BUY/SELL thi
    gui tom tat qua Telegram (chi khi telegram.enabled = true).
    """
    try:
        post, _created = PostStore(store_path).publish_post(
            desk=desk, symbol=symbol, action=action, summary=summary,
            confidence=confidence, drivers=drivers, risks=risks,
            entry=entry, sl=sl, tp=tp, source="manual", cfg=cfg)
    except ValueError as exc:
        print(f"LOI: {exc}")
        return 1
    print(f"Da dang bai phan tich: {post['id']} — "
          f"{post['desk']}/{post['symbol']} {post['action']} "
          f"(tin cay {post['confidence']:g})")
    return 0
