"""Test kho the tin + chuan kich hoat Telegram (newsfeed.py) va viec
briefing / lenh `news` dang the tin.

Khong mang that, khong MT5 that — fetcher/feed gia, file dung tmp_path.
"""
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.__main__ import _cmd_news
from diamondx10.briefing import _article_dict, build_briefing
from diamondx10.config import DEFAULT
from diamondx10.data.news import NewsArticle, NewsStore
from diamondx10.newsfeed import (
    NEWS_CARD_STORE,
    NewsCardStore,
    impacts_for_symbol,
    is_test_mode,
    news_qualifies,
)

CREATED = "2026-11-27T10:00:00+00:00"


def _card(card_id="abc123", **over):
    base = {"id": card_id, "title": "Fed holds rates",
            "link": "https://example.com/fed-1", "source": "Fake Forex",
            "summary": "Fed keeps rates steady.", "tier": 2,
            "desk": "forex", "analyst": "Yuling Pan",
            "published_utc": "2026-11-27T09:00:00+00:00",
            "created_utc": CREATED, "impact": None}
    base.update(over)
    return base


def _impact(news_id="abc123", **over):
    base = {"news_id": news_id, "impact": "positive", "direction": "buy",
            "confidence": 0.7, "summary": "Fed dovish, EUR up.",
            "affected_symbol": "EURUSD"}
    base.update(over)
    return base


# --- Tao the / dedupe ---

def test_publish_creates_card_with_exact_shape(tmp_path):
    store = NewsCardStore(tmp_path / "news-cards.json")
    created, skipped = store.publish_cards([_card()])
    assert (created, skipped) == (1, 0)
    cards = store.list_cards()
    assert len(cards) == 1
    card = cards[0]
    assert set(card.keys()) == {"id", "title", "link", "source", "summary",
                                "tier", "desk", "analyst", "published_utc",
                                "created_utc", "impact"}
    assert card["id"] == "abc123"
    assert card["tier"] == 2
    assert card["desk"] == "forex"
    assert card["analyst"] == "Yuling Pan"
    assert card["impact"] is None


def test_publish_same_article_twice_creates_one_card(tmp_path):
    store = NewsCardStore(tmp_path / "news-cards.json")
    assert store.publish_cards([_card()]) == (1, 0)
    assert store.publish_cards([_card()]) == (0, 1)
    assert len(store.list_cards()) == 1


def test_publish_same_id_second_desk_skipped_first_desk_kept(tmp_path):
    store = NewsCardStore(tmp_path / "news-cards.json")
    assert store.publish_cards([_card(desk="forex")]) == (1, 0)
    # Cung bai bao nhung briefing desk khac lay ve sau: khong tao the moi.
    created, skipped = store.publish_cards(
        [_card(desk="xauusd", analyst="Yumi")])
    assert (created, skipped) == (0, 1)
    cards = store.list_cards()
    assert len(cards) == 1
    assert cards[0]["desk"] == "forex"
    assert cards[0]["analyst"] == "Yuling Pan"


def test_publish_card_without_id_skipped_never_raises(tmp_path):
    store = NewsCardStore(tmp_path / "news-cards.json")
    assert store.publish_cards([{"title": "khong co id"}]) == (0, 1)
    assert store.publish_cards(None) == (0, 0)
    assert store.list_cards() == []


def test_corrupt_or_missing_store_loads_empty(tmp_path):
    path = tmp_path / "news-cards.json"
    store = NewsCardStore(path)
    assert store.list_cards() == []
    assert store.get_card("abc123") is None
    path.write_text("{khong phai json", encoding="utf-8")
    assert store.list_cards() == []
    assert store.get_card("abc123") is None
    path.write_text(json.dumps({"khong": "phai kho the"}),
                    encoding="utf-8")
    assert store.list_cards() == []
    # Ghi de kho hong van duoc.
    assert store.publish_cards([_card()]) == (1, 0)


# --- List / get ---

def test_list_newest_first_and_desk_filter(tmp_path):
    store = NewsCardStore(tmp_path / "news-cards.json")
    store.publish_cards([
        _card("id-old", created_utc="2026-11-27T08:00:00+00:00"),
        _card("id-new", desk="xauusd", analyst="Yumi",
              created_utc="2026-11-27T09:00:00+00:00"),
        _card("id-mid", created_utc="2026-11-27T08:30:00+00:00"),
    ])
    assert [c["id"] for c in store.list_cards()] == [
        "id-new", "id-mid", "id-old"]
    assert [c["id"] for c in store.list_cards(desk="forex")] == [
        "id-mid", "id-old"]
    assert [c["id"] for c in store.list_cards(desk="xauusd")] == ["id-new"]
    assert [c["id"] for c in store.list_cards(limit=2)] == [
        "id-new", "id-mid"]
    assert store.list_cards(limit=0) == []
    assert len(store.list_cards(limit=None)) == 3
    assert store.get_card("id-mid")["title"] == "Fed holds rates"
    assert store.get_card("khong-co") is None


def test_store_default_path_is_repo_decisions():
    assert NEWS_CARD_STORE.name == "news-cards.json"
    assert NEWS_CARD_STORE.parent.name == "decisions"


# --- Gan impact ---

def test_attach_impacts_matching_id(tmp_path):
    store = NewsCardStore(tmp_path / "news-cards.json")
    store.publish_cards([_card()])
    matched = store.attach_impacts(
        [_impact()], "2026-11-27T10:30:00+00:00")
    assert matched == 1
    card = store.get_card("abc123")
    assert card["impact"] == {
        "impact": "positive", "direction": "buy", "confidence": 0.7,
        "summary": "Fed dovish, EUR up.", "affected_symbol": "EURUSD",
        "verdict_created_utc": "2026-11-27T10:30:00+00:00"}


def test_attach_impacts_unknown_id_matches_nothing_no_crash(tmp_path):
    path = tmp_path / "news-cards.json"
    store = NewsCardStore(path)
    store.publish_cards([_card()])
    assert store.attach_impacts([_impact(news_id="la-hoan-toan")],
                                CREATED) == 0
    assert store.attach_impacts([{"khong": "co news_id"}], CREATED) == 0
    assert store.attach_impacts(None, CREATED) == 0
    assert store.attach_impacts("khong-phai-list", CREATED) == 0
    assert store.get_card("abc123")["impact"] is None
    # Khong co the nao khop thi khong tao file moi (kho trong).
    empty = NewsCardStore(tmp_path / "trong.json")
    assert empty.attach_impacts([_impact()], CREATED) == 0
    assert not (tmp_path / "trong.json").exists()


def test_attach_impacts_newer_verdict_overwrites(tmp_path):
    store = NewsCardStore(tmp_path / "news-cards.json")
    store.publish_cards([_card()])
    store.attach_impacts([_impact(confidence=0.7)], "2026-11-27T10:00:00+00:00")
    store.attach_impacts(
        [_impact(confidence=0.9, summary="Fed rat dovish.")],
        "2026-11-27T11:00:00+00:00")
    card = store.get_card("abc123")
    assert card["impact"]["confidence"] == 0.9
    assert card["impact"]["summary"] == "Fed rat dovish."
    assert card["impact"]["verdict_created_utc"] == "2026-11-27T11:00:00+00:00"


# --- news_qualifies: ma tran chuan da chot ---

@pytest.mark.parametrize("impact,tier,action,expected", [
    (_impact(direction="buy", confidence=0.7), 1, "BUY", True),
    (_impact(direction="buy", confidence=0.7), 2, "BUY", True),
    (_impact(direction="sell", confidence=0.9), 1, "SELL", True),
    (_impact(direction="buy", confidence=0.6), 1, "BUY", True),  # dung nguong
    (_impact(direction="buy", confidence=0.5), 1, "BUY", False),  # duoi nguong
    (_impact(direction="buy", confidence=0.7), 1, "HOLD", False),
    (_impact(direction="buy", confidence=0.7), 1, "SELL", False),  # nguoc
    (_impact(direction="sell", confidence=0.7), 1, "BUY", False),  # nguoc
    (_impact(direction="buy", confidence=0.9), 3, "BUY", False),  # tier 3
    (_impact(direction="buy", confidence=0.9), 3, "SELL", False),
    (_impact(direction="neutral", confidence=0.9), 1, "BUY", False),
    (_impact(direction="neutral", confidence=0.9), 1, "SELL", False),
    (_impact(direction="buy", confidence=0.7), 1, None, False),
    (_impact(direction="buy", confidence="cao"), 1, "BUY", False),
    ({"direction": "buy"}, 1, "BUY", False),  # thieu confidence
    (None, 1, "BUY", False),
])
def test_news_qualifies_matrix(impact, tier, action, expected):
    assert news_qualifies(impact, tier, action) is expected


@pytest.mark.parametrize("impact,tier,action,expected", [
    # Che do TEST: bo qua nguong 0.6, dong thuan, loai tier.
    (_impact(direction="buy", confidence=0.5), 1, "BUY", True),
    (_impact(direction="buy", confidence=0.1), 3, "HOLD", True),
    (_impact(direction="sell", confidence=0.9), 3, "BUY", True),  # nguoc + tier 3
    (_impact(direction="buy", confidence=0.7), 2, None, True),
    (_impact(direction="buy", confidence=0.7), None, "BUY", True),
    # Neutral thi KHONG BAO GIO du — ke ca che do test.
    (_impact(direction="neutral", confidence=0.9), 1, "BUY", False),
    (_impact(direction="neutral", confidence=0.9), 3, None, False),
    (None, 1, "BUY", False),
])
def test_news_qualifies_test_mode_bypasses_gates(impact, tier, action,
                                                expected):
    assert news_qualifies(impact, tier, action,
                          test_mode=True) is expected


def test_is_test_mode_reads_config_flag():
    assert is_test_mode({}) is False
    assert is_test_mode(None) is False
    assert is_test_mode({"news": {}}) is False
    assert is_test_mode({"news": {"test_mode": False}}) is False
    assert is_test_mode({"news": {"test_mode": True}}) is True
    assert is_test_mode({"news": None}) is False
    assert is_test_mode({"news": {"test_mode": 1}}) is True


# --- impacts_for_symbol ---

def test_impacts_for_symbol_collects_matching_only():
    verdicts = [
        {"desk": "forex", "news_impacts": [
            _impact(news_id="a", affected_symbol="EURUSD"),
            _impact(news_id="b", affected_symbol="GBPUSD")]},
        {"desk": "xauusd", "news_impacts": [
            _impact(news_id="c", affected_symbol="eurusd")]},
        {"desk": "crypto"},  # khong co news_impacts
    ]
    got = impacts_for_symbol(verdicts, "EURUSD")
    assert [item["news_id"] for item in got] == ["a", "c"]
    assert impacts_for_symbol(verdicts, "XAUUSD") == []
    assert impacts_for_symbol(None, "EURUSD") == []
    assert impacts_for_symbol([], "EURUSD") == []


# --- Briefing dang the tin ---

RSS_T2_FOREX = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Forex News</title>
<item><title>Federal Reserve holds rates steady</title>
<link>https://example.com/fed-1</link>
<description>ECB and Fed signal no change to interest rates.</description>
</item></channel></rss>"""

RSS_T3_FOREX = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Leaks</title>
<item><title>Euro leak: ECB insider hints at rate move</title>
<link>https://x.com/leak-euro-1</link>
<description>Unverified euro rumour from social media.</description>
</item></channel></rss>"""

FEEDS = {"forex-t2": RSS_T2_FOREX, "forex-t3": RSS_T3_FOREX}


def fake_fetcher(url, timeout):
    for key, payload in FEEDS.items():
        if key in url:
            return payload
    raise RuntimeError(f"khong co feed gia cho {url}")


NEWS_CFG = {
    "filters": {"blacklist_keywords": ["sponsored"],
                "high_priority_keywords": ["Federal Reserve"]},
    "desks": {
        "forex": {"keywords": ["EURUSD", "euro", "ECB", "Federal Reserve",
                               "Fed", "interest rate"]},
    },
    "sources": [
        {"name": "Fake Forex T2", "url": "https://example.com/forex-t2.rss",
         "tier": 2, "desks": ["forex"]},
        {"name": "Fake Forex T3", "url": "https://example.com/forex-t3.rss",
         "tier": 3, "desks": ["forex"]},
    ],
}


def base_cfg():
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {"provider": "simulated",
                   "symbols": {"forex": ["EURUSD"]}}
    cfg["news"] = copy.deepcopy(NEWS_CFG)
    return cfg


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


def test_article_dict_has_id_matching_article_hash():
    article = NewsArticle(title="Fed holds rates",
                          link="https://example.com/fed-1",
                          summary="Fed keeps rates steady.",
                          source="Fake Forex", trust_tier=2)
    data = _article_dict(article)
    assert data["id"] == article.article_hash()
    assert data["trust_tier"] == 2


def test_build_briefing_creates_two_cards_awaiting_analysis(tmp_path):
    cards = NewsCardStore(tmp_path / "news-cards.json")
    result = build_briefing(base_cfg(), "forex", feed=FakeFeed(),
                            news_fetcher=fake_fetcher, out_dir=tmp_path,
                            news_card_store=cards)
    assert result["desk"] == "forex"
    listed = cards.list_cards()
    assert len(listed) == 2
    assert {c["tier"] for c in listed} == {2, 3}
    assert all(c["desk"] == "forex" for c in listed)
    assert all(c["analyst"] == "Yuling Pan" for c in listed)
    assert all(c["impact"] is None for c in listed)
    titles = {c["title"] for c in listed}
    assert "Federal Reserve holds rates steady" in titles
    assert "Euro leak: ECB insider hints at rate move" in titles
    # Chay briefing lan nua: dedupe — khong tao the moi.
    build_briefing(base_cfg(), "forex", feed=FakeFeed(),
                   news_fetcher=fake_fetcher, out_dir=tmp_path,
                   news_card_store=cards)
    assert len(cards.list_cards()) == 2


def test_briefing_md_lists_news_ids_and_template_has_impacts(tmp_path):
    cards = NewsCardStore(tmp_path / "news-cards.json")
    result = build_briefing(base_cfg(), "forex", feed=FakeFeed(),
                            news_fetcher=fake_fetcher, out_dir=tmp_path,
                            news_card_store=cards)
    md = Path(result["md_path"]).read_text(encoding="utf-8")
    data = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    for card in cards.list_cards():
        assert f"news_id: {card['id']}" in md
    assert all("id" in a for a in data["news"]["tier_2"])
    assert all("id" in a for a in data["news"]["tier_3"])
    template = data["verdict_template"]
    assert isinstance(template["news_impacts"], list)
    assert len(template["news_impacts"]) == 1
    example = template["news_impacts"][0]
    assert set(example.keys()) == {"news_id", "impact", "direction",
                                   "confidence", "summary",
                                   "affected_symbol",
                                   "verdict_created_utc"}
    assert example["impact"] in ("positive", "negative", "neutral")
    assert example["direction"] in ("buy", "sell", "neutral")
    assert 0 <= example["confidence"] <= 1
    # Khoi JSON trong md phai parse duoc va khop verdict_template.
    import re
    block = re.search(r"```json\n(.*?)\n```", md, re.S).group(1)
    assert json.loads(block) == template


def test_cmd_news_publishes_cards_and_dedupes(tmp_path):
    cards = NewsCardStore(tmp_path / "news-cards.json")
    news_store = NewsStore(tmp_path / "news-history.db")
    cfg = base_cfg()
    try:
        rc = _cmd_news(cfg, desk="forex", days=3, include_seen=False,
                       fetcher=fake_fetcher, news_card_store=cards,
                       store=news_store)
        assert rc == 0
        assert len(cards.list_cards()) == 2
        # Lan 2 hien ca tin da xem: tin ve lai nhung the dedupe.
        rc = _cmd_news(cfg, desk="forex", days=3, include_seen=True,
                       fetcher=fake_fetcher, news_card_store=cards,
                       store=news_store)
        assert rc == 0
        assert len(cards.list_cards()) == 2
    finally:
        news_store.close()


def test_cmd_news_without_news_config_returns_1(tmp_path):
    cards = NewsCardStore(tmp_path / "news-cards.json")
    assert _cmd_news({"data": {}}, news_card_store=cards) == 1
    assert cards.list_cards() == []
