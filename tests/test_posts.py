"""Test kho bai dang phan tich (posts.py) + tom tat Telegram + lenh
`synthesize --publish` / `publish-post`.

Khong mang that, khong MT5 that, khong gui Telegram that — Telegram
duoc gia bang ham fake (outbox list), feed mo phong.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10 import posts as posts_mod
from diamondx10.posts import (
    PostStore,
    cmd_publish_post,
    publish_synthesis_post,
)
from diamondx10.synthesis import cmd_synthesize, save_verdict
from diamondx10.telegram import format_post_summary

CFG_TG = {"telegram": {"enabled": True, "chat_id": "1234567890"},
          "language": "vi"}
CFG_TG_OFF = {"telegram": {"enabled": False, "chat_id": "1234567890"},
              "language": "vi"}


def _verdict(**over):
    base = {"desk": "crypto", "analyst": "Rich",
            "direction": "buy", "confidence": 0.8,
            "drivers": ["BTC vuot khang cu"], "risks": ["FOMC sap hop"],
            "note": "",
            "created_utc": datetime.now(timezone.utc).isoformat()}
    base.update(over)
    return base


def _post_dict(**over):
    base = {"desk": "forex", "symbol": "EURUSD", "action": "BUY",
            "summary": "PTKT BUY, PTCB mua.", "confidence": 0.8,
            "drivers": ["ECB giu lai suat"], "risks": ["CPI cao"],
            "entry": 1.10, "sl": 1.05, "tp": 1.20,
            "analyst": "Yuling Pan"}
    base.update(over)
    return base


class FakeTelegram:
    """Gui gia: ghi text vao outbox, tra True (khong goi mang)."""

    def __init__(self, fail=False):
        self.outbox = []
        self.fail = fail

    def send_message(self, text, cfg=None, **kwargs):
        if self.fail:
            raise RuntimeError("mang loi gia")
        self.outbox.append(text)
        return True


@pytest.fixture
def fake_tg(monkeypatch):
    fake = FakeTelegram()
    monkeypatch.setattr(posts_mod.telegram_mod, "send_message",
                        fake.send_message)
    return fake


# --- Dang bai co ban ---

def test_publish_creates_post_with_all_fields(tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    post, created = store.publish_post(cfg=CFG_TG, **_post_dict())
    assert created is True
    assert re.fullmatch(r"[0-9a-f]{8}", post["id"])
    assert post["desk"] == "forex"
    assert post["analyst"] == "Yuling Pan"
    assert post["symbol"] == "EURUSD"
    assert post["action"] == "BUY"
    assert post["confidence"] == 0.8
    assert post["summary"] == "PTKT BUY, PTCB mua."
    assert post["drivers"] == ["ECB giu lai suat"]
    assert post["risks"] == ["CPI cao"]
    assert post["entry"] == 1.10 and post["sl"] == 1.05
    assert post["tp"] == 1.20
    assert post["source"] == "manual"
    assert post["verdict_created_utc"] is None
    datetime.fromisoformat(post["created_utc"].replace("Z", "+00:00"))
    # Doc lai tu file: dung 1 bai, dung truong.
    assert len(store.list_posts()) == 1
    assert store.get_post(post["id"])["summary"] == "PTKT BUY, PTCB mua."


def test_publish_defaults_analyst_from_desk(tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    post, _ = store.publish_post(cfg=CFG_TG, desk="crypto",
                                 symbol="BTCUSD", action="SELL",
                                 summary="PTKT SELL.")
    assert post["analyst"] == "Rich"


def test_publish_validates_bad_input(tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    with pytest.raises(ValueError, match="desk"):
        store.publish_post(cfg=CFG_TG, **_post_dict(desk="stocks"))
    with pytest.raises(ValueError, match="action"):
        store.publish_post(cfg=CFG_TG, **_post_dict(action="HOLD"))
    with pytest.raises(ValueError, match="summary"):
        store.publish_post(cfg=CFG_TG, **_post_dict(summary="   "))
    with pytest.raises(ValueError, match="confidence"):
        store.publish_post(cfg=CFG_TG, **_post_dict(confidence=1.5))
    with pytest.raises(ValueError, match="symbol"):
        store.publish_post(cfg=CFG_TG, **_post_dict(symbol=""))
    assert store.list_posts() == []


def test_get_post_missing_returns_none(tmp_path):
    store = PostStore(tmp_path / "posts.json")
    assert store.get_post("deadbeef") is None


# --- Telegram: chi BUY/SELL gui, NEUTRAL khong gui ---

def test_publish_buy_sends_telegram_once(tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    store.publish_post(cfg=CFG_TG, **_post_dict())
    assert len(fake_tg.outbox) == 1
    assert "EURUSD" in fake_tg.outbox[0]
    assert "BUY" in fake_tg.outbox[0]


def test_publish_sell_sends_telegram(tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    store.publish_post(cfg=CFG_TG, **_post_dict(action="SELL"))
    assert len(fake_tg.outbox) == 1
    assert "SELL" in fake_tg.outbox[0]


def test_publish_neutral_sends_nothing(tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    store.publish_post(cfg=CFG_TG, **_post_dict(action="NEUTRAL"))
    assert fake_tg.outbox == []


def test_publish_telegram_disabled_sends_nothing(tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    store.publish_post(cfg=CFG_TG_OFF, **_post_dict())
    assert fake_tg.outbox == []
    assert len(store.list_posts()) == 1


def test_publish_telegram_error_does_not_break_publish(tmp_path, monkeypatch):
    fake = FakeTelegram(fail=True)
    monkeypatch.setattr(posts_mod.telegram_mod, "send_message",
                        fake.send_message)
    store = PostStore(tmp_path / "posts.json")
    post, created = store.publish_post(cfg=CFG_TG, **_post_dict())
    assert created is True
    assert post["action"] == "BUY"
    assert len(store.list_posts()) == 1


# --- Dedupe (synthesis) vs manual luon tao moi ---

def test_synthesis_dedupe_same_action_same_verdict(tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    verdict = _verdict()
    first, created1 = store.publish_post(
        cfg=CFG_TG, source="synthesis", verdict_created_utc=verdict["created_utc"],
        **_post_dict(desk="crypto", symbol="BTCUSD", action="BUY"))
    assert created1 is True
    second, created2 = store.publish_post(
        cfg=CFG_TG, source="synthesis", verdict_created_utc=verdict["created_utc"],
        **_post_dict(desk="crypto", symbol="BTCUSD", action="BUY"))
    assert created2 is False
    assert second["id"] == first["id"]
    assert len(store.list_posts()) == 1
    # Khong gui Telegram lai khi dedupe.
    assert len(fake_tg.outbox) == 1


def test_synthesis_changed_action_creates_new_post(tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    created_at = _verdict()["created_utc"]
    store.publish_post(cfg=CFG_TG, source="synthesis",
                       verdict_created_utc=created_at,
                       **_post_dict(desk="crypto", symbol="BTCUSD",
                                    action="BUY"))
    post, created = store.publish_post(
        cfg=CFG_TG, source="synthesis", verdict_created_utc=created_at,
        **_post_dict(desk="crypto", symbol="BTCUSD", action="SELL"))
    assert created is True
    assert len(store.list_posts()) == 2
    assert len(fake_tg.outbox) == 2


def test_synthesis_changed_verdict_creates_new_post(tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    old = (datetime.now(timezone.utc)
           - timedelta(hours=5)).isoformat()
    new = datetime.now(timezone.utc).isoformat()
    store.publish_post(cfg=CFG_TG, source="synthesis",
                       verdict_created_utc=old,
                       **_post_dict(desk="crypto", symbol="BTCUSD",
                                    action="BUY"))
    post, created = store.publish_post(
        cfg=CFG_TG, source="synthesis", verdict_created_utc=new,
        **_post_dict(desk="crypto", symbol="BTCUSD", action="BUY"))
    assert created is True
    assert len(store.list_posts()) == 2


def test_manual_always_creates_new_post(tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    first, _ = store.publish_post(cfg=CFG_TG, **_post_dict())
    second, created = store.publish_post(cfg=CFG_TG, **_post_dict())
    assert created is True
    assert second["id"] != first["id"]
    assert len(store.list_posts()) == 2


# --- List / get ---

def test_list_newest_first_desk_filter_limit(tmp_path):
    store = PostStore(tmp_path / "posts.json")
    path = tmp_path / "posts.json"
    seed = [
        _post_dict(desk="forex", symbol="EURUSD", action="BUY",
                   created_utc="2026-11-27T08:00:00+00:00"),
        _post_dict(desk="crypto", symbol="BTCUSD", action="SELL",
                   created_utc="2026-11-27T09:00:00+00:00"),
        _post_dict(desk="forex", symbol="EURUSD", action="NEUTRAL",
                   created_utc="2026-11-27T10:00:00+00:00"),
    ]
    seeded = []
    for i, item in enumerate(seed):
        row = dict(item)
        row.update({"id": f"0000000{i}", "source": "manual",
                    "verdict_created_utc": None})
        seeded.append(row)
    path.write_text(json.dumps({"posts": seeded}, ensure_ascii=False),
                    encoding="utf-8")
    rows = store.list_posts()
    assert [row["created_utc"] for row in rows] == [
        "2026-11-27T10:00:00+00:00", "2026-11-27T09:00:00+00:00",
        "2026-11-27T08:00:00+00:00"]
    assert [row["id"] for row in store.list_posts(limit=2)] == [
        "00000002", "00000001"]
    forex = store.list_posts(desk="forex")
    assert [row["id"] for row in forex] == ["00000002", "00000000"]
    assert store.list_posts(desk="crypto")[0]["symbol"] == "BTCUSD"
    assert store.list_posts(limit=0) == []
    assert len(store.list_posts(limit=None)) == 3


def test_corrupt_or_missing_store_loads_empty(tmp_path, fake_tg):
    missing = PostStore(tmp_path / "khong-co.json")
    assert missing.list_posts() == []
    corrupt = tmp_path / "hong.json"
    corrupt.write_text("{khong phai json", encoding="utf-8")
    assert PostStore(corrupt).list_posts() == []
    wrong_shape = tmp_path / "sai.json"
    wrong_shape.write_text(json.dumps({"posts": "khong phai list"}),
                           encoding="utf-8")
    assert PostStore(wrong_shape).list_posts() == []
    # Dang bai vao file hong van duoc (ghi de).
    post, created = PostStore(corrupt).publish_post(
        cfg=CFG_TG, **_post_dict())
    assert created is True
    assert len(PostStore(corrupt).list_posts()) == 1


# --- Tom tat Telegram: ca 2 ngon ngu ---

def test_format_post_summary_both_languages():
    post = _post_dict()
    post.update({"id": "abcdef01", "created_utc": "2026-11-27T10:00:00Z",
                 "source": "manual", "verdict_created_utc": None})
    vi = format_post_summary(post, lang="vi")
    en = format_post_summary(post, lang="en")
    for text in (vi, en):
        assert "EURUSD" in text
        assert "BUY" in text
        assert "1.1" in text
        assert "0.8" in text
        assert "PTKT BUY" in text
    assert "Độ tin cậy" in vi
    assert "Confidence" in en
    assert "Tóm tắt" in vi
    assert "Summary" in en
    # Khong co muc gia thi khong co dong Entry/SL/TP.
    neutral = _post_dict(action="NEUTRAL", entry=None, sl=None, tp=None)
    text = format_post_summary(neutral, lang="en")
    assert "Entry" not in text
    assert "SL" not in text


def test_format_post_summary_uses_config_language():
    post = _post_dict()
    assert "Confidence" in format_post_summary(
        post, cfg={"language": "en"})
    assert "Độ tin cậy" in format_post_summary(
        post, cfg={"language": "vi"})
    assert "Độ tin cậy" in format_post_summary(post, cfg={})


# --- publish_synthesis_post (don vi tong hop) ---

def test_publish_synthesis_buy_maps_levels_and_verdict(tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    verdict = _verdict()
    syn = {"recommendation": "MUA", "size": 1.0, "blocked": False,
           "rationale": "PTKT: BUY; PTCB: buy", "fa_status": "ok"}
    post, created = publish_synthesis_post(
        store, CFG_TG, "crypto", "BTCUSD", "BUY",
        "SMA5 tren SMA20, RSI 55", {"entry": 60000.0, "sl": 59000.0,
                                    "tp": 62000.0, "atr": 500.0},
        verdict, syn)
    assert created is True
    assert post["action"] == "BUY"
    assert post["analyst"] == "Rich"
    assert post["confidence"] == 0.8
    assert post["drivers"] == ["BTC vuot khang cu"]
    assert post["entry"] == 60000.0
    assert post["verdict_created_utc"] == verdict["created_utc"]
    assert post["source"] == "synthesis"
    assert "PTKT BUY" in post["summary"]
    assert "BTC vuot khang cu" in post["summary"]
    assert "60000" in post["summary"]
    assert len(fake_tg.outbox) == 1


def test_publish_synthesis_blocked_becomes_neutral_no_telegram(
        tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    verdict = _verdict(direction="sell", confidence=0.9)
    syn = {"recommendation": "KHONG MUA", "size": 0.0, "blocked": True,
           "rationale": "PTCB mau thuan manh", "fa_status": "ok"}
    post, created = publish_synthesis_post(
        store, CFG_TG, "crypto", "BTCUSD", "BUY", "SMA5 tren SMA20",
        {"entry": 60000.0, "sl": 59000.0, "tp": 62000.0, "atr": 500.0},
        verdict, syn)
    assert created is True
    assert post["action"] == "NEUTRAL"
    assert post["entry"] is None
    assert fake_tg.outbox == []


def test_publish_synthesis_hold_neutral_no_levels(tmp_path, fake_tg):
    store = PostStore(tmp_path / "posts.json")
    verdict = _verdict()
    syn = {"recommendation": "CHO", "size": 0.0, "blocked": False,
           "rationale": "PTKT HOLD", "fa_status": "ok"}
    post, _ = publish_synthesis_post(
        store, CFG_TG, "forex", "EURUSD", "HOLD", "SMA5 == SMA20", {},
        verdict, syn)
    assert post["action"] == "NEUTRAL"
    assert fake_tg.outbox == []


# --- cmd_publish_post (CLI) ---

def test_cmd_publish_post_buy_sends_and_returns_0(tmp_path, fake_tg,
                                                  capsys):
    store_path = tmp_path / "posts.json"
    rc = cmd_publish_post(CFG_TG, "forex", "EURUSD", "BUY",
                          "PTKT BUY, PTCB mua.", confidence=0.7,
                          entry=1.10, sl=1.05, tp=1.20,
                          drivers="ECB giu lai suat;USD yeu",
                          risks="CPI cao", store_path=store_path)
    assert rc == 0
    assert len(PostStore(store_path).list_posts()) == 1
    assert len(fake_tg.outbox) == 1
    assert "Da dang bai phan tich" in capsys.readouterr().out


def test_cmd_publish_post_bad_action_returns_1(tmp_path, capsys):
    rc = cmd_publish_post(CFG_TG, "forex", "EURUSD", "HOLD",
                          "Tom tat.", store_path=tmp_path / "posts.json")
    assert rc == 1
    assert "LOI" in capsys.readouterr().out


# --- cmd_synthesize --publish ---

def _sim_cfg(desk, symbols):
    return {"data": {"provider": "simulated",
                     "symbols": {desk: symbols}},
            "telegram": {"enabled": True, "chat_id": "1234567890"},
            "language": "vi"}


def test_cmd_synthesize_publish_buy_sends_telegram(tmp_path, fake_tg):
    # Feed mo phong crypto -> TA BUY; verdict buy 0.8 -> MUA -> bai BUY.
    store = tmp_path / "verdicts.json"
    save_verdict(_verdict(), store)
    post_store = PostStore(tmp_path / "posts.json")
    out_path = tmp_path / "synthesis.json"
    rc = cmd_synthesize(_sim_cfg("crypto", ["BTCUSD"]), "crypto",
                        store_path=store, out_path=out_path,
                        publish=True, post_store=post_store)
    assert rc == 0
    posts = post_store.list_posts()
    assert len(posts) == 1
    post = posts[0]
    assert post["symbol"] == "BTCUSD"
    assert post["action"] == "BUY"
    assert post["source"] == "synthesis"
    assert post["entry"] is not None
    assert "PTKT BUY" in post["summary"]
    assert len(fake_tg.outbox) == 1
    assert "BTCUSD" in fake_tg.outbox[0]
    assert "BUY" in fake_tg.outbox[0]


def test_cmd_synthesize_publish_sell_and_neutral(tmp_path, fake_tg):
    # Feed mo phong xauusd -> TA SELL; verdict sell 0.8 -> bai SELL.
    store = tmp_path / "verdicts.json"
    save_verdict(_verdict(desk="xauusd", analyst="Yumi",
                          direction="sell", confidence=0.8), store)
    post_store = PostStore(tmp_path / "posts.json")
    rc = cmd_synthesize(_sim_cfg("xauusd", ["XAUUSD"]), "xauusd",
                        store_path=store,
                        out_path=tmp_path / "synthesis.json",
                        publish=True, post_store=post_store)
    assert rc == 0
    posts = post_store.list_posts()
    assert len(posts) == 1 and posts[0]["action"] == "SELL"
    assert len(fake_tg.outbox) == 1

    # Feed mo phong forex -> TA HOLD; verdict buy -> bai NEUTRAL,
    # khong gui them Telegram.
    save_verdict(_verdict(desk="forex", analyst="Yuling Pan",
                          direction="buy", confidence=0.8), store)
    forex_store = PostStore(tmp_path / "posts-forex.json")
    rc = cmd_synthesize(_sim_cfg("forex", ["EURUSD"]), "forex",
                        store_path=store,
                        out_path=tmp_path / "synthesis-forex.json",
                        publish=True, post_store=forex_store)
    assert rc == 0
    forex_posts = forex_store.list_posts()
    assert len(forex_posts) == 1
    assert forex_posts[0]["action"] == "NEUTRAL"
    assert len(fake_tg.outbox) == 1  # van 1 — NEUTRAL khong gui


def test_cmd_synthesize_publish_dedupe_second_run(tmp_path, fake_tg):
    store = tmp_path / "verdicts.json"
    save_verdict(_verdict(), store)
    post_store = PostStore(tmp_path / "posts.json")
    cfg = _sim_cfg("crypto", ["BTCUSD"])
    kwargs = {"store_path": store, "publish": True,
              "post_store": post_store}
    assert cmd_synthesize(cfg, "crypto", out_path=tmp_path / "s1.json",
                          **kwargs) == 0
    first = post_store.list_posts()
    assert len(first) == 1
    assert cmd_synthesize(cfg, "crypto", out_path=tmp_path / "s2.json",
                          **kwargs) == 0
    second = post_store.list_posts()
    assert len(second) == 1
    assert second[0]["id"] == first[0]["id"]
    assert len(fake_tg.outbox) == 1


def test_cmd_synthesize_without_publish_creates_no_posts(tmp_path, fake_tg):
    store = tmp_path / "verdicts.json"
    save_verdict(_verdict(), store)
    post_path = tmp_path / "posts.json"
    rc = cmd_synthesize(_sim_cfg("crypto", ["BTCUSD"]), "crypto",
                        store_path=store,
                        out_path=tmp_path / "synthesis.json",
                        posts_path=post_path)
    assert rc == 0
    assert not post_path.exists()
    assert fake_tg.outbox == []
