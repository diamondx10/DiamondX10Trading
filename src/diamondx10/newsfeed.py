"""The tin tuc (news feed) — the tin da lay ve + nhan dinh tac dong
tung tin (per-item impact verdict) cua Muse.

Moi the tin (news card) la 1 bai bao da lay ve qua `data.news` /
`briefing`, luu o decisions/news-cards.json (goc repo, cung quy uoc
duong dan nhu posts.py / synthesis.py: goc repo = parents[2] cua
file nay). File nay la file RUNTIME — khong commit.

The tin:
  {"id": MD5(title+link) tu Article.article_hash(),
   "title", "link", "source", "summary",
   "tier": 1|2|3, "desk": "forex"|"xauusd"|"crypto"|"us_securities",
   "analyst": ten analyst phu trach desk,
   "published_utc": ISO hoac None, "created_utc": ISO,
   "impact": None hoac {"impact": "positive"|"negative"|"neutral",
     "direction": "buy"|"sell"|"neutral", "confidence": 0..1,
     "summary": "...", "affected_symbol": "<SYM>" hoac None,
     "verdict_created_utc": ISO}}

Nhan dinh tac dong tung tin nam trong verdict PTCB cua desk
(`synthesis.validate_verdict`, truong "news_impacts") va duoc gan
len the tin khi verdict duoc luu (xem synthesis.cmd_verdict va
muse_auto.run_muse_auto). Gan impact CHI hien thi tren the tin —
KHONG gui Telegram o day.

Quy tac Telegram (chuan da chot, xem docs/analysis-workflow.md
muc 2d): 1 tin chi kich hoat khuyen nghi Telegram khi verdict tac
dong cua no la buy/sell voi do tin cay >= 0.6, tin thuoc tier 1
hoac 2, VA tong hop Yuling cua desk dong thuan (rule 40: PTCB mot
minh khong tao lenh). Tin tier 3 (ro ri) KHONG BAO GIO kich hoat
Telegram mot minh. Telegram chi gui qua duong dang bai hien co
(posts.publish_synthesis_post, `synthesize --publish`) — module
nay khong goi Telegram.

Module nay CHI dung thu vien chuan (json, pathlib, datetime),
khong import diamondx10 — tranh vong lap import (briefing,
synthesis, posts, muse_auto deu dung no).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

NEWS_CARD_STORE = (Path(__file__).resolve().parents[2] / "decisions"
                   / "news-cards.json")

DESKS = ("forex", "xauusd", "crypto", "us_securities")

CARD_FIELDS = ("id", "title", "link", "source", "summary", "tier",
               "desk", "analyst", "published_utc", "created_utc",
               "impact")

IMPACT_VALUES = ("positive", "negative", "neutral")
DIRECTION_VALUES = ("buy", "sell", "neutral")

# Nguong tin cay chuan de 1 tin du dieu kien kich hoat Telegram
# (cung nguong fa_high_confidence mac dinh cua tong hop Yuling).
IMPACT_TRIGGER_CONFIDENCE = 0.6


def _now_utc_iso():
    return datetime.now(timezone.utc).isoformat()


def _is_number(value):
    return (isinstance(value, (int, float))
            and not isinstance(value, bool))


def _clean_tier(value):
    """Tier 1|2|3; sai kieu / ngoai khoang thi ve 2 (BAO CHI)."""
    if isinstance(value, bool):
        return 2
    try:
        tier = int(value)
    except (TypeError, ValueError):
        return 2
    return tier if tier in (1, 2, 3) else 2


def _clean_card(card):
    """The tin ve dung shape chuan (chi 11 truong); thieu truong thi
    dien gia tri mac dinh. Card khong co id (chuoi khong rong) thi
    tra None — bo qua, khong bao gio raise."""
    if not isinstance(card, dict):
        return None
    card_id = card.get("id")
    if not isinstance(card_id, str) or not card_id.strip():
        return None
    created = card.get("created_utc")
    if not isinstance(created, str) or not created.strip():
        created = _now_utc_iso()
    impact = card.get("impact")
    if impact is not None and not isinstance(impact, dict):
        impact = None
    return {
        "id": card_id,
        "title": card.get("title") if isinstance(card.get("title"), str)
        else "",
        "link": card.get("link") if isinstance(card.get("link"), str)
        else "",
        "source": card.get("source") if isinstance(card.get("source"), str)
        else "",
        "summary": card.get("summary") if isinstance(card.get("summary"), str)
        else "",
        "tier": _clean_tier(card.get("tier")),
        "desk": card.get("desk") if isinstance(card.get("desk"), str)
        else "",
        "analyst": card.get("analyst") if isinstance(card.get("analyst"), str)
        else "",
        "published_utc": (card.get("published_utc")
                          if isinstance(card.get("published_utc"), str)
                          else None),
        "created_utc": created,
        "impact": dict(impact) if isinstance(impact, dict) else None,
    }


class NewsCardStore:
    """Kho the tin (JSON file, 1 object {"cards": [...]}).

    File chua co / hong / sai dinh dang thi doc nhu kho rong — khong
    bao gio raise khi doc. Ghi thi tao thu muc cha neu can.
    """

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else NEWS_CARD_STORE

    def _load(self):
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return []
        if not isinstance(raw, dict) or not isinstance(
                raw.get("cards"), list):
            return []
        cards = []
        for item in raw["cards"]:
            cleaned = _clean_card(item)
            if cleaned is not None:
                cards.append(cleaned)
        return cards

    def _save(self, cards):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"cards": cards}, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def publish_cards(self, cards):
        """Dang cac the tin moi. Tra (created_count, skipped_count).

        Dedupe theo id: 1 bai bao chi co 1 the (desk dau tien thang —
        the da co thi giu nguyen desk/analyst cu, lan lay sau cung id
        bi bo qua, khong bao gio tao the thu hai). Card khong co id
        cung tinh la skipped. Khong bao gio raise.
        """
        existing = self._load()
        seen = {card["id"] for card in existing}
        created, skipped = 0, 0
        for card in cards or []:
            cleaned = _clean_card(card)
            if cleaned is None or cleaned["id"] in seen:
                skipped += 1
                continue
            seen.add(cleaned["id"])
            existing.append(cleaned)
            created += 1
        if created:
            self._save(existing)
        return created, skipped

    def list_cards(self, limit=50, desk=None):
        """The tin moi nhat len dau; loc theo desk neu truyen.

        limit None thi tra tat ca; limit <= 0 thi tra [].
        """
        cards = self._load()
        if desk is not None:
            cards = [card for card in cards if card.get("desk") == desk]
        indexed = sorted(
            enumerate(cards),
            key=lambda item: (item[1].get("created_utc") or "", item[0]),
            reverse=True)
        ordered = [card for _, card in indexed]
        if limit is None:
            return [dict(card) for card in ordered]
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 50
        if limit <= 0:
            return []
        return [dict(card) for card in ordered[:limit]]

    def get_card(self, news_id):
        """1 the theo id, hoac None neu khong co."""
        if not isinstance(news_id, str):
            return None
        for card in self._load():
            if card.get("id") == news_id:
                return dict(card)
        return None

    def attach_impacts(self, news_impacts, verdict_created_utc):
        """Gan nhan dinh tac dong len the tin. Tra so the khop.

        news_impacts: list dict tu verdict (moi muc co "news_id").
        verdict_created_utc: ISO cua verdict chua cac impact do —
        ghi vao impact cua the (thay cho truong rieng cua muc neu
        co). news_id la thi khong khop the nao, khong tao the moi,
        khong raise. Impact moi hon ghi de impact cu tren cung the.
        Muc impact thieu truong thi dien mac dinh, khong raise.
        Chi ghi file khi co it nhat 1 the khop.
        """
        impacts = news_impacts or []
        if not isinstance(impacts, list):
            return 0
        cards = self._load()
        by_id = {card["id"]: card for card in cards}
        matched = 0
        for item in impacts:
            if not isinstance(item, dict):
                continue
            news_id = item.get("news_id")
            if not isinstance(news_id, str) or news_id not in by_id:
                continue
            impact = item.get("impact")
            if impact not in IMPACT_VALUES:
                impact = "neutral"
            direction = item.get("direction")
            if direction not in DIRECTION_VALUES:
                direction = "neutral"
            confidence = item.get("confidence")
            if not _is_number(confidence):
                confidence = 0.0
            else:
                confidence = min(1.0, max(0.0, float(confidence)))
            summary = item.get("summary")
            if not isinstance(summary, str):
                summary = ""
            affected = item.get("affected_symbol")
            if affected is not None and not isinstance(affected, str):
                affected = None
            by_id[news_id]["impact"] = {
                "impact": impact,
                "direction": direction,
                "confidence": confidence,
                "summary": summary,
                "affected_symbol": affected,
                "verdict_created_utc": verdict_created_utc,
            }
            matched += 1
        if matched:
            self._save(cards)
        return matched


def is_test_mode(cfg):
    """Che do TEST co bat khong? Doc co `news.test_mode` trong config.

    Mac dinh TAT (False). Che do test: moi tin co verdict tac dong
    deu duoc dang + gui khuyen nghi Telegram, bo qua cac cua chuan
    0.6 / dong thuan tong hop / loai tier (xem news_qualifies).
    Web UI (nut Manager) ghi dung khoa nay; CLI `--test-mode` bat
    tam 1 lan, khong ghi vao config.
    """
    news_cfg = (cfg or {}).get("news") or {}
    if not isinstance(news_cfg, dict):
        return False
    return bool(news_cfg.get("test_mode", False))


def news_qualifies(impact, tier, synthesis_action, *, test_mode=False):
    """1 tin co du chuan kich hoat khuyen nghi Telegram khong?

    Chuan da chot: direction buy/sell (khong phai neutral), do tin
    cay >= 0.6, tier 1 hoac 2 (tier 3 ro ri khong bao gio du), VA
    tong hop Yuling dong thuan — synthesis_action "BUY" voi buy,
    "SELL" voi sell. synthesis_action None / "HOLD" / nguoc chieu
    thi False. Ham thuan tuy — khong doc file, khong raise.

    test_mode=True (che do TEST, xem is_test_mode): bo qua TAT CA
    cua tren — bat ky impact buy/sell nao cung du chuan (khong can
    0.6, khong can tong hop dong thuan, ke ca tier 3). Direction
    neutral thi KHONG BAO GIO du chuan (khong co khuyen nghi de
    gui), ke ca o che do test.
    """
    if not isinstance(impact, dict):
        return False
    direction = impact.get("direction")
    if direction not in ("buy", "sell"):
        return False
    if test_mode:
        return True
    confidence = impact.get("confidence")
    if not _is_number(confidence):
        return False
    if float(confidence) < IMPACT_TRIGGER_CONFIDENCE:
        return False
    if _clean_tier(tier) not in (1, 2):
        return False
    if not isinstance(synthesis_action, str):
        return False
    expected = "BUY" if direction == "buy" else "SELL"
    return synthesis_action.strip().upper() == expected


def impacts_for_symbol(verdicts, symbol):
    """Gom nhan dinh tac dong tung tin cho 1 symbol tu cac verdict
    da luu: cac muc "news_impacts" co affected_symbol == symbol.

    verdicts: list verdict dict (hoac None -> []). So sanh symbol
    khong phan biet hoa/thuong va khoang trang. Tra list dict (ban
    sao) — verdict nao khong co news_impacts thi bo qua, khong raise.
    """
    if not verdicts or not isinstance(symbol, str):
        return []
    wanted = symbol.strip().upper()
    if not wanted:
        return []
    out = []
    for verdict in verdicts:
        if not isinstance(verdict, dict):
            continue
        impacts = verdict.get("news_impacts") or []
        if not isinstance(impacts, list):
            continue
        for item in impacts:
            if not isinstance(item, dict):
                continue
            affected = item.get("affected_symbol")
            if (isinstance(affected, str)
                    and affected.strip().upper() == wanted):
                out.append(dict(item))
    return out
