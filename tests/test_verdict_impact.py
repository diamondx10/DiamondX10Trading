"""Test nhan dinh tac dong tung tin trong verdict PTCB
(synthesis.validate_verdict / cmd_verdict) + duong kich hoat
Telegram qua dang bai (`synthesize --publish`).

Khong mang that, khong MT5 that, khong gui Telegram that — Telegram
duoc gia bang ham fake (outbox list), feed mo phong, file dung tmp_path.
"""
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import diamondx10.muse_auto as muse_auto_mod
from diamondx10 import posts as posts_mod
from diamondx10.muse_auto import run_muse_auto
from diamondx10.newsfeed import NewsCardStore
from diamondx10.posts import PostStore
from diamondx10.synthesis import (
    cmd_synthesize,
    cmd_verdict,
    load_verdicts,
    save_verdict,
    validate_verdict,
)

NOW = datetime.now(timezone.utc).isoformat()
CFG_TG = {"telegram": {"enabled": True, "chat_id": "1234567890"},
          "language": "vi"}


def _verdict(**over):
    base = {"desk": "forex", "analyst": "Yuling Pan",
            "direction": "buy", "confidence": 0.8,
            "drivers": ["ECB giu lai suat"], "risks": ["CPI cao"],
            "note": "EUR manh len", "created_utc": NOW}
    base.update(over)
    return base


def _impact(news_id="news-t1", **over):
    base = {"news_id": news_id, "impact": "positive", "direction": "buy",
            "confidence": 0.7, "summary": "Fed dovish, EUR up.",
            "affected_symbol": "EURUSD"}
    base.update(over)
    return base


def _card(card_id, tier, **over):
    base = {"id": card_id, "title": f"Tin {card_id}",
            "link": f"https://example.com/{card_id}", "source": "Fake",
            "summary": f"Tom tat {card_id}.", "tier": tier,
            "desk": "forex", "analyst": "Yuling Pan",
            "published_utc": NOW, "created_utc": NOW, "impact": None}
    base.update(over)
    return base


class FakeTelegram:
    def __init__(self):
        self.outbox = []

    def send_message(self, text, cfg=None, **kwargs):
        self.outbox.append(text)
        return True


@pytest.fixture
def fake_tg(monkeypatch):
    fake = FakeTelegram()
    monkeypatch.setattr(posts_mod.telegram_mod, "send_message",
                        fake.send_message)
    return fake


def trend_bars(n=60, start=100.0):
    """Nen tang lap lai — cho tin hieu TA BUY."""
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


def _sim_cfg(symbols):
    cfg = copy.deepcopy(CFG_TG)
    cfg["data"] = {"provider": "simulated",
                   "symbols": {"forex": symbols}}
    return cfg


# --- validate_verdict: news_impacts ---

def test_validate_verdict_accepts_valid_news_impacts():
    verdict = validate_verdict(_verdict(
        news_impacts=[_impact(), _impact(
            news_id="news-t3", direction="sell", confidence=0.9,
            affected_symbol=None)]))
    assert len(verdict["news_impacts"]) == 2
    assert verdict["news_impacts"][0]["news_id"] == "news-t1"
    assert verdict["news_impacts"][1]["affected_symbol"] is None


def test_validate_verdict_absent_news_impacts_defaults_empty():
    verdict = validate_verdict(_verdict())
    assert verdict["news_impacts"] == []


def test_validate_verdict_accepts_unknown_news_id():
    # Verdict co the nhac tin chua co tren feed — van hop le.
    verdict = validate_verdict(
        _verdict(news_impacts=[_impact(news_id="chua-co-tren-feed")]))
    assert verdict["news_impacts"][0]["news_id"] == "chua-co-tren-feed"


@pytest.mark.parametrize("bad_impacts", [
    [_impact(direction="hold")],  # direction sai
    [_impact(direction="BUY")],  # direction phai chu thuong
    [_impact(confidence=1.5)],  # confidence vuot 1
    [_impact(confidence=-0.1)],  # confidence am
    [_impact(confidence="cao")],  # confidence khong phai so
    [_impact(confidence=True)],  # bool khong phai so
    [_impact(news_id="")],  # news_id rong
    [_impact(news_id=123)],  # news_id khong phai chuoi
    [{}],  # thieu news_id
    [_impact(impact="tot")],  # impact sai
    [_impact(summary=123)],  # summary khong phai chuoi
    [_impact(affected_symbol=123)],  # affected_symbol sai kieu
    ["khong-phai-dict"],  # muc khong phai dict
    "khong-phai-list",  # news_impacts khong phai list
    [_impact(verdict_created_utc="khong-phai-iso")],
])
def test_validate_verdict_rejects_bad_news_impacts(bad_impacts):
    with pytest.raises(ValueError):
        validate_verdict(_verdict(news_impacts=bad_impacts))


def test_invalid_news_impacts_verdict_never_stored(tmp_path):
    store = tmp_path / "verdicts.json"
    with pytest.raises(ValueError):
        save_verdict(_verdict(news_impacts=[_impact(confidence=2.0)]),
                     store)
    assert not store.exists()
    # Verdict hop le luu duoc, giu nguyen news_impacts khi doc lai.
    save_verdict(_verdict(news_impacts=[_impact()]), store)
    assert load_verdicts(store)["forex"]["news_impacts"][0]["news_id"] \
        == "news-t1"


def test_save_verdict_has_no_side_effect_on_cards(tmp_path):
    # save_verdict CHI luu verdict — khong tu gan len the tin.
    cards = NewsCardStore(tmp_path / "news-cards.json")
    cards.publish_cards([_card("news-t1", 1)])
    store = tmp_path / "verdicts.json"
    save_verdict(_verdict(news_impacts=[_impact()]), store)
    assert cards.get_card("news-t1")["impact"] is None


# --- cmd_verdict: gan impact len the khi luu ---

def test_cmd_verdict_attaches_impacts_to_cards(tmp_path):
    cards = NewsCardStore(tmp_path / "news-cards.json")
    cards.publish_cards([_card("news-t1", 1), _card("news-t3", 3)])
    verdict_file = tmp_path / "verdict.json"
    verdict_file.write_text(json.dumps(_verdict(news_impacts=[
        _impact("news-t1"), _impact(
            "news-t3", direction="buy", confidence=0.9,
            summary="Ro ri: ECB sap cat lai.")])), encoding="utf-8")
    store = tmp_path / "verdicts.json"
    assert cmd_verdict({}, str(verdict_file), store_path=store,
                       news_card_store=cards) == 0
    assert load_verdicts(store)["forex"]["news_impacts"][0]["news_id"] \
        == "news-t1"
    assert cards.get_card("news-t1")["impact"]["direction"] == "buy"
    assert cards.get_card("news-t1")["impact"]["confidence"] == 0.7
    assert (cards.get_card("news-t1")["impact"]["verdict_created_utc"]
            == NOW)
    assert cards.get_card("news-t3")["impact"]["confidence"] == 0.9


def test_cmd_verdict_unknown_news_id_stored_but_matches_nothing(tmp_path):
    cards = NewsCardStore(tmp_path / "news-cards.json")
    cards.publish_cards([_card("news-t1", 1)])
    verdict_file = tmp_path / "verdict.json"
    verdict_file.write_text(json.dumps(_verdict(news_impacts=[
        _impact(news_id="chua-co-tren-feed")])), encoding="utf-8")
    store = tmp_path / "verdicts.json"
    assert cmd_verdict({}, str(verdict_file), store_path=store,
                       news_card_store=cards) == 0
    assert cards.get_card("news-t1")["impact"] is None


def test_cmd_verdict_invalid_impacts_rejects_whole_file(tmp_path):
    cards = NewsCardStore(tmp_path / "news-cards.json")
    verdict_file = tmp_path / "verdict.json"
    verdict_file.write_text(json.dumps(_verdict(news_impacts=[
        _impact(confidence=2.0)])), encoding="utf-8")
    store = tmp_path / "verdicts.json"
    assert cmd_verdict({}, str(verdict_file), store_path=store,
                       news_card_store=cards) == 1
    assert not store.exists()


# --- muse_auto: gan impact sau khi doi verdict ---

def test_muse_auto_attaches_impacts_after_verdict(tmp_path, monkeypatch):
    cards = NewsCardStore(tmp_path / "news-cards.json")
    cards.publish_cards([_card("news-t1", 1)])
    monkeypatch.setattr(
        muse_auto_mod, "build_briefing",
        lambda *a, **k: {"desk": "forex", "analyst": "Yuling Pan",
                         "md_path": str(tmp_path / "b.md")})
    monkeypatch.setattr(
        muse_auto_mod, "send_briefing",
        lambda *a, **k: {"sent": True, "message": "da gui",
                         "url": "https://muse.ai"})
    monkeypatch.setattr(
        muse_auto_mod, "wait_for_verdict",
        lambda *a, **k: _verdict(news_impacts=[_impact()]))
    rc = run_muse_auto(_sim_cfg(["EURUSD"]), ["forex"], 10,
                       feed=FakeFeed(), out_dir=tmp_path,
                       state_path=tmp_path / "fa-state.json",
                       news_card_store=cards)
    assert rc == 0
    assert cards.get_card("news-t1")["impact"]["direction"] == "buy"
    assert (cards.get_card("news-t1")["impact"]["verdict_created_utc"]
            == NOW)


# --- Duong dang bai: kich hoat Telegram ---

def _setup_publish(tmp_path, verdict, cards):
    store = tmp_path / "verdicts.json"
    save_verdict(verdict, store)
    post_store = PostStore(tmp_path / "posts.json")
    news_store = NewsCardStore(tmp_path / "news-cards.json")
    news_store.publish_cards(cards)
    return store, post_store, news_store


def test_publish_trigger_tier1_qualifying_sends_one_telegram(tmp_path,
                                                             fake_tg):
    # TA BUY + FA buy 0.8 + impact tier 1 buy 0.7 -> bai BUY kem tin.
    store, post_store, news_store = _setup_publish(
        tmp_path,
        _verdict(news_impacts=[_impact("news-t1"),
                               _impact("news-t3", confidence=0.9,
                                       summary="Ro ri: ECB sap cat lai.")]),
        [_card("news-t1", 1), _card("news-t3", 3)])
    rc = cmd_synthesize(_sim_cfg(["EURUSD"]), "forex", store_path=store,
                        out_path=tmp_path / "synthesis.json",
                        feed_factory=lambda sym: FakeFeed(),
                        publish=True, post_store=post_store,
                        news_card_store=news_store)
    assert rc == 0
    posts = post_store.list_posts()
    assert len(posts) == 1
    assert posts[0]["action"] == "BUY"
    assert posts[0]["news_id"] == "news-t1"
    assert "Fed dovish, EUR up." in posts[0]["drivers"]
    assert "Tin lien quan: Fed dovish, EUR up." in posts[0]["summary"]
    # Telegram: dung 1 tin — cho tin tier 1, khong co tin cho tier 3.
    assert len(fake_tg.outbox) == 1
    assert "EURUSD" in fake_tg.outbox[0]
    assert "BUY" in fake_tg.outbox[0]
    assert "Fed dovish, EUR up." in fake_tg.outbox[0]
    assert "Ro ri: ECB sap cat lai." not in fake_tg.outbox[0]


def test_publish_tier3_only_no_news_trigger_but_post_still_sends(tmp_path,
                                                                 fake_tg):
    # Chi co impact tier 3: bai BUY van dang + gui nhu thuong, nhung
    # khong kem tin kich hoat nao.
    store, post_store, news_store = _setup_publish(
        tmp_path,
        _verdict(news_impacts=[_impact(
            "news-t3", confidence=0.9,
            summary="Ro ri: ECB sap cat lai.")]),
        [_card("news-t3", 3)])
    rc = cmd_synthesize(_sim_cfg(["EURUSD"]), "forex", store_path=store,
                        out_path=tmp_path / "synthesis.json",
                        feed_factory=lambda sym: FakeFeed(),
                        publish=True, post_store=post_store,
                        news_card_store=news_store)
    assert rc == 0
    posts = post_store.list_posts()
    assert len(posts) == 1
    assert posts[0]["action"] == "BUY"
    assert "news_id" not in posts[0]
    assert "Ro ri: ECB sap cat lai." not in posts[0]["drivers"]
    assert len(fake_tg.outbox) == 1  # tom tat bai, khong phai tin tier 3
    assert "Ro ri" not in fake_tg.outbox[0]


def test_publish_synthesis_disagrees_no_news_trigger_no_telegram(tmp_path,
                                                                 fake_tg):
    # TA BUY nhung FA sell 0.8 -> bi chan -> bai NEUTRAL, khong tin nao.
    store, post_store, news_store = _setup_publish(
        tmp_path,
        _verdict(direction="sell", confidence=0.8,
                 news_impacts=[_impact("news-t1", direction="sell",
                                       confidence=0.9,
                                       summary="Fed hawkish, EUR down.")]),
        [_card("news-t1", 1)])
    rc = cmd_synthesize(_sim_cfg(["EURUSD"]), "forex", store_path=store,
                        out_path=tmp_path / "synthesis.json",
                        feed_factory=lambda sym: FakeFeed(),
                        publish=True, post_store=post_store,
                        news_card_store=news_store)
    assert rc == 0
    posts = post_store.list_posts()
    assert len(posts) == 1
    assert posts[0]["action"] == "NEUTRAL"
    assert "news_id" not in posts[0]
    assert fake_tg.outbox == []


def test_publish_impact_opposite_direction_no_news_trigger(tmp_path,
                                                          fake_tg):
    # FA buy + TA BUY -> bai BUY, nhung impact lai la sell -> khong
    # du chuan (tong hop khong dong thuan voi huong cua tin).
    store, post_store, news_store = _setup_publish(
        tmp_path,
        _verdict(news_impacts=[_impact(
            "news-t1", impact="negative", direction="sell",
            confidence=0.9, summary="Fed hawkish, EUR down.")]),
        [_card("news-t1", 1)])
    rc = cmd_synthesize(_sim_cfg(["EURUSD"]), "forex", store_path=store,
                        out_path=tmp_path / "synthesis.json",
                        feed_factory=lambda sym: FakeFeed(),
                        publish=True, post_store=post_store,
                        news_card_store=news_store)
    assert rc == 0
    posts = post_store.list_posts()
    assert posts[0]["action"] == "BUY"
    assert "news_id" not in posts[0]
    assert len(fake_tg.outbox) == 1
    assert "Fed hawkish" not in fake_tg.outbox[0]


def test_publish_no_double_send_on_republish(tmp_path, fake_tg):
    store, post_store, news_store = _setup_publish(
        tmp_path, _verdict(news_impacts=[_impact("news-t1")]),
        [_card("news-t1", 1)])
    kwargs = {"store_path": store, "feed_factory": lambda sym: FakeFeed(),
              "publish": True, "post_store": post_store,
              "news_card_store": news_store}
    assert cmd_synthesize(_sim_cfg(["EURUSD"]), "forex",
                          out_path=tmp_path / "s1.json", **kwargs) == 0
    first = post_store.list_posts()
    assert len(first) == 1
    assert first[0]["news_id"] == "news-t1"
    assert cmd_synthesize(_sim_cfg(["EURUSD"]), "forex",
                          out_path=tmp_path / "s2.json", **kwargs) == 0
    second = post_store.list_posts()
    assert len(second) == 1
    assert second[0]["id"] == first[0]["id"]
    assert len(fake_tg.outbox) == 1


# --- Che do TEST (news.test_mode / --test-mode) ---

def _nonqualifying_verdict():
    """Verdict co 2 impact deu KHONG du chuan thuong: 1 tin tier 1
    nhung tin cay 0.5, 1 tin tier 3 huong sell (nguoc tong hop BUY)
    tin cay 0.9."""
    return _verdict(news_impacts=[
        _impact("news-t1", confidence=0.5,
                summary="Fed dovish nhe, EUR len chut."),
        _impact("news-t3", impact="negative", direction="sell",
                confidence=0.9, summary="Ro ri: ECB sap cat lai.")])

def _nonqualifying_cards():
    return [_card("news-t1", 1), _card("news-t3", 3)]


def test_publish_test_mode_sends_nonqualifying_with_test_marking(
        tmp_path, fake_tg):
    # Che do TEST bat qua config: ca 2 tin khong du chuan thuong van
    # duoc dang + gui, danh dau [TEST] ro rang.
    store, post_store, news_store = _setup_publish(
        tmp_path, _nonqualifying_verdict(), _nonqualifying_cards())
    cfg = _sim_cfg(["EURUSD"])
    cfg["news"] = {"test_mode": True}
    rc = cmd_synthesize(cfg, "forex", store_path=store,
                        out_path=tmp_path / "synthesis.json",
                        feed_factory=lambda sym: FakeFeed(),
                        publish=True, post_store=post_store,
                        news_card_store=news_store)
    assert rc == 0
    posts = post_store.list_posts()
    assert len(posts) == 1
    assert posts[0]["action"] == "BUY"
    # Impact tin cay cao nhat (tier 3 sell 0.9) thang trong che do test.
    assert posts[0]["news_id"] == "news-t3"
    assert "Ro ri: ECB sap cat lai." in posts[0]["drivers"]
    assert posts[0]["test_mode"] is True
    # /api/posts tra nguyen dict bai dang da luu nen co test_mode.
    assert len(fake_tg.outbox) == 1
    assert fake_tg.outbox[0].startswith("[TEST] ")
    assert "EURUSD" in fake_tg.outbox[0]
    assert "BUY" in fake_tg.outbox[0]
    assert "Ro ri: ECB sap cat lai." in fake_tg.outbox[0]


def test_publish_test_mode_off_same_setup_no_news_trigger(
        tmp_path, fake_tg):
    # Cung setup, che do TEST tat: chuan 0.6 ap dung, khong co tin
    # nao kich hoat, bai thuong khong danh dau [TEST].
    store, post_store, news_store = _setup_publish(
        tmp_path, _nonqualifying_verdict(), _nonqualifying_cards())
    rc = cmd_synthesize(_sim_cfg(["EURUSD"]), "forex", store_path=store,
                        out_path=tmp_path / "synthesis.json",
                        feed_factory=lambda sym: FakeFeed(),
                        publish=True, post_store=post_store,
                        news_card_store=news_store)
    assert rc == 0
    posts = post_store.list_posts()
    assert len(posts) == 1
    assert posts[0]["action"] == "BUY"
    assert "news_id" not in posts[0]
    assert "test_mode" not in posts[0]
    assert len(fake_tg.outbox) == 1
    assert not fake_tg.outbox[0].startswith("[TEST] ")


def test_publish_test_mode_cli_flag_overrides_config(tmp_path, fake_tg):
    # --test-mode (test_mode=True) bat cho lan chay nay du config tat.
    store, post_store, news_store = _setup_publish(
        tmp_path, _nonqualifying_verdict(), _nonqualifying_cards())
    cfg = _sim_cfg(["EURUSD"])
    cfg["news"] = {"test_mode": False}
    rc = cmd_synthesize(cfg, "forex", store_path=store,
                        out_path=tmp_path / "synthesis.json",
                        feed_factory=lambda sym: FakeFeed(),
                        publish=True, post_store=post_store,
                        news_card_store=news_store, test_mode=True)
    assert rc == 0
    posts = post_store.list_posts()
    assert posts[0]["news_id"] == "news-t3"
    assert posts[0]["test_mode"] is True
    assert len(fake_tg.outbox) == 1
    assert fake_tg.outbox[0].startswith("[TEST] ")


def test_publish_test_mode_neutral_impact_never_triggers(tmp_path, fake_tg):
    # Impact neutral: ke ca che do test cung khong kich hoat tin nao.
    store, post_store, news_store = _setup_publish(
        tmp_path,
        _verdict(news_impacts=[_impact(
            "news-t1", impact="neutral", direction="neutral",
            confidence=0.9, summary="Tin trung lap, khong doi huong.")]),
        [_card("news-t1", 1)])
    cfg = _sim_cfg(["EURUSD"])
    cfg["news"] = {"test_mode": True}
    rc = cmd_synthesize(cfg, "forex", store_path=store,
                        out_path=tmp_path / "synthesis.json",
                        feed_factory=lambda sym: FakeFeed(),
                        publish=True, post_store=post_store,
                        news_card_store=news_store)
    assert rc == 0
    posts = post_store.list_posts()
    assert posts[0]["action"] == "BUY"
    assert "news_id" not in posts[0]
    assert posts[0]["test_mode"] is True  # bai test van danh dau
    assert len(fake_tg.outbox) == 1
    assert fake_tg.outbox[0].startswith("[TEST] ")
    assert "Tin trung lap" not in fake_tg.outbox[0]


def test_publish_test_mode_hold_neutral_post_never_sends(tmp_path, fake_tg):
    # PTKT HOLD (feed mo phong forex) -> bai NEUTRAL, khong gui
    # Telegram du che do test co bat.
    store = tmp_path / "verdicts.json"
    save_verdict(_verdict(news_impacts=[_impact("news-t1")]), store)
    post_store = PostStore(tmp_path / "posts.json")
    news_store = NewsCardStore(tmp_path / "news-cards.json")
    news_store.publish_cards([_card("news-t1", 1)])
    cfg = _sim_cfg(["EURUSD"])
    cfg["news"] = {"test_mode": True}
    rc = cmd_synthesize(cfg, "forex", store_path=store,
                        out_path=tmp_path / "synthesis.json",
                        publish=True, post_store=post_store,
                        news_card_store=news_store)
    assert rc == 0
    posts = post_store.list_posts()
    assert len(posts) == 1
    assert posts[0]["action"] == "NEUTRAL"
    assert "news_id" not in posts[0]
    assert fake_tg.outbox == []
