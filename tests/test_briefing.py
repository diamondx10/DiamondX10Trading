"""Test briefing PTCB (briefing.py): md + json, tin theo tier, macro,
verdict template, loi sach khi thieu config / khong co MT5.

Dung feed gia + fetcher tin gia, khong dung mang that hay MT5 that.
"""
import copy
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.briefing import build_briefing, cmd_briefing
from diamondx10.config import DEFAULT

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

RSS_GOLD = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Gold News</title>
<item><title>Gold price surges as central banks buy bullion</title>
<link>https://example.com/gold-1</link>
<description>COMEX gold futures hit a new high.</description>
</item></channel></rss>"""

RSS_BTC = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Crypto News</title>
<item><title>Bitcoin rallies after ETF inflows</title>
<link>https://example.com/btc-1</link>
<description>BTC price up 5 percent.</description>
</item></channel></rss>"""

RSS_CHIPS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Chips News</title>
<item><title>NVDA earnings beat as AI chip demand surges</title>
<link>https://example.com/nvda-1</link>
<description>Nvidia reports strong earnings.</description>
</item></channel></rss>"""

FEEDS = {
    "forex-t2": RSS_T2_FOREX,
    "forex-t3": RSS_T3_FOREX,
    "gold": RSS_GOLD,
    "btc": RSS_BTC,
    "chips": RSS_CHIPS,
}


def fake_fetcher(url, timeout):
    for key, payload in FEEDS.items():
        if key in url:
            return payload
    raise RuntimeError(f"khong co feed gia cho {url}")


NEWS_CFG = {
    "max_age_days": 3,
    "filters": {
        "blacklist_keywords": ["sponsored"],
        "high_priority_keywords": ["Federal Reserve", "rate cut"],
    },
    "desks": {
        "forex": {"keywords": ["EURUSD", "euro", "ECB", "Federal Reserve",
                               "Fed", "interest rate"]},
        "xauusd": {"keywords": ["gold", "XAUUSD", "bullion", "COMEX"]},
        "crypto": {"keywords": ["Bitcoin", "BTC", "Ethereum", "ETH"]},
        "us_securities": {"keywords": ["NVDA", "Nvidia", "AMD", "AI chip",
                                       "earnings"]},
    },
    "sources": [
        {"name": "Fake Forex T2", "url": "https://example.com/forex-t2.rss",
         "tier": 2, "desks": ["forex"]},
        {"name": "Fake Forex T3", "url": "https://example.com/forex-t3.rss",
         "tier": 3, "desks": ["forex"]},
        {"name": "Fake Gold", "url": "https://example.com/gold.rss",
         "tier": 2, "desks": ["xauusd"]},
        {"name": "Fake BTC", "url": "https://example.com/btc.rss",
         "tier": 2, "desks": ["crypto"]},
        {"name": "Fake Chips", "url": "https://example.com/chips.rss",
         "tier": 2, "desks": ["us_securities"]},
    ],
}


def base_cfg(news=True, macro=None, provider="simulated"):
    cfg = copy.deepcopy(DEFAULT)
    cfg["data"] = {
        "provider": provider,
        "symbols": {
            "forex": ["EURUSD"],
            "us_securities": ["AMD", "CDNS", "SNPS", "INTC", "NVDA"],
            "xauusd": ["XAUUSD"],
            "crypto": ["BTCUSD", "BNBUSD", "ETHUSD"],
        },
    }
    if news:
        cfg["news"] = copy.deepcopy(NEWS_CFG)
    if macro is not None:
        cfg["macro"] = dict(macro)
    return cfg


def trend_bars(n=60, start=100.0):
    """Nen theo mau tang lap lai — cho tin hieu BUY that."""
    closes, c = [], start
    for i in range(n):
        c += (0.2, 0.2, -0.25)[i % 3]
        closes.append(round(c, 2))
    return [{"time": 1700000000 + i * 900, "open": cl - 0.05,
             "high": cl + 0.5, "low": cl - 0.5, "close": cl}
            for i, cl in enumerate(closes)]


class FakeFeed:
    """Feed gia: 60 nen tang + gia moi nhat la close bar cuoi."""

    def __init__(self, bars=None):
        self._bars = bars if bars is not None else trend_bars()

    def bars(self, n=60):
        return list(self._bars[-n:])

    def latest_price(self, symbol):
        return self._bars[-1]["close"]


def test_build_briefing_writes_md_and_json(tmp_path):
    result = build_briefing(base_cfg(), "forex", feed=FakeFeed(),
                            news_fetcher=fake_fetcher, out_dir=tmp_path)
    assert result["desk"] == "forex"
    assert result["analyst"] == "Yuling Pan"
    assert result["symbols"] == ["EURUSD"]
    assert result["generated_utc"]
    md_path = Path(result["md_path"])
    json_path = Path(result["json_path"])
    assert re.match(r"briefing-forex-\d{8}-\d{4}\.md$", md_path.name)
    assert json_path.name == md_path.name.replace(".md", ".json")
    assert md_path.exists() and json_path.exists()
    assert md_path.parent == tmp_path


def test_build_briefing_default_simulated_feed(tmp_path):
    """feed=None: dung lua chon feed theo config (simulated tren Linux)."""
    result = build_briefing(base_cfg(), "forex",
                            news_fetcher=fake_fetcher, out_dir=tmp_path)
    assert result["desk"] == "forex"
    assert Path(result["md_path"]).exists()
    data = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert data["symbols"][0]["symbol"] == "EURUSD"
    assert data["symbols"][0]["price"] > 0


def test_md_and_json_ta_summary(tmp_path):
    result = build_briefing(base_cfg(), "forex", feed=FakeFeed(),
                            news_fetcher=fake_fetcher, out_dir=tmp_path)
    md = Path(result["md_path"]).read_text(encoding="utf-8")
    data = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    sym = data["symbols"][0]
    assert sym["action"] == "BUY"
    assert sym["price"] == FakeFeed().latest_price("EURUSD")
    assert sym["regime"]["regime"] in ("TRENDING", "TRANSITIONAL", "RANGING")
    assert "Yuling Pan" in md
    assert "EURUSD" in md
    assert str(sym["price"]) in md
    assert f"Tin hieu: {sym['action']}" in md
    assert sym["reason"] in md
    assert f"Regime: {sym['regime']['regime']}" in md


def test_md_news_grouped_by_tier_and_tier3_warning(tmp_path):
    result = build_briefing(base_cfg(), "forex", feed=FakeFeed(),
                            news_fetcher=fake_fetcher, out_dir=tmp_path)
    md = Path(result["md_path"]).read_text(encoding="utf-8")
    data = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert "Tier 1" in md and "Tier 2" in md and "Tier 3" in md
    assert "CHINH THONG" in md and "BAO CHI" in md
    assert "CHUA XAC MINH" in md
    assert "Federal Reserve holds rates steady" in md
    assert "Euro leak: ECB insider hints at rate move" in md
    assert [a["title"] for a in data["news"]["tier_2"]] == [
        "Federal Reserve holds rates steady"]
    assert [a["title"] for a in data["news"]["tier_3"]] == [
        "Euro leak: ECB insider hints at rate move"]
    assert data["news"]["tier_3"][0]["trust_tier"] == 3
    assert "CHUA XAC MINH" in data["news"]["tier_3"][0]["trust_label"]


def test_md_and_json_verdict_template(tmp_path):
    result = build_briefing(base_cfg(), "forex", feed=FakeFeed(),
                            news_fetcher=fake_fetcher, out_dir=tmp_path)
    md = Path(result["md_path"]).read_text(encoding="utf-8")
    data = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    for field in ("desk", "analyst", "direction", "confidence",
                  "drivers", "risks", "note", "created_utc"):
        assert field in md
        assert field in data["verdict_template"]
    assert data["verdict_template"]["desk"] == "forex"
    assert data["verdict_template"]["analyst"] == "Yuling Pan"
    assert data["verdict_template"]["direction"] in ("buy", "sell", "neutral")
    assert 0 <= data["verdict_template"]["confidence"] <= 1
    assert isinstance(data["verdict_template"]["drivers"], list)
    assert isinstance(data["verdict_template"]["risks"], list)
    # Khoi JSON trong md phai parse duoc va khop verdict_template.
    block = re.search(r"```json\n(.*?)\n```", md, re.S).group(1)
    assert json.loads(block) == data["verdict_template"]


def test_missing_news_config_raises(tmp_path):
    with pytest.raises(ValueError, match="chua co news: trong config"):
        build_briefing(base_cfg(news=False), "forex", feed=FakeFeed(),
                       news_fetcher=fake_fetcher, out_dir=tmp_path)


def test_cmd_briefing_missing_news_returns_1_no_traceback(tmp_path, capsys):
    rc = cmd_briefing(base_cfg(news=False), "forex", feed=FakeFeed(),
                      news_fetcher=fake_fetcher, out_dir=tmp_path)
    assert rc == 1
    out = capsys.readouterr().out
    assert "LOI" in out
    assert "chua co news: trong config" in out
    assert "Traceback" not in out
    assert list(tmp_path.glob("briefing-*.md")) == []


def test_macro_present_and_absent(tmp_path):
    macro = {"dxy": 101.0, "us10y": 4.2, "vix": 17.0, "spx": 5900.0}
    result = build_briefing(base_cfg(macro=macro), "forex", feed=FakeFeed(),
                            news_fetcher=fake_fetcher, out_dir=tmp_path)
    md = Path(result["md_path"]).read_text(encoding="utf-8")
    data = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert "VI MO" in md
    assert "DXY: 101.0" in md
    assert data["macro"] is not None
    assert data["macro"]["snapshot"]["dxy"] == 101.0
    assert data["macro"]["edges"]["EURUSD"]["score"] is not None

    result2 = build_briefing(base_cfg(), "forex", feed=FakeFeed(),
                             news_fetcher=fake_fetcher, out_dir=tmp_path)
    md2 = Path(result2["md_path"]).read_text(encoding="utf-8")
    data2 = json.loads(Path(result2["json_path"]).read_text(encoding="utf-8"))
    assert "VI MO" not in md2
    assert data2["macro"] is None


def test_cmd_briefing_all_desks(tmp_path, capsys):
    rc = cmd_briefing(base_cfg(), all_desks=True, feed=FakeFeed(),
                      news_fetcher=fake_fetcher, out_dir=tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    mds = sorted(tmp_path.glob("briefing-*.md"))
    assert len(mds) == 4
    assert len(list(tmp_path.glob("briefing-*.json"))) == 4
    all_md = "".join(p.read_text(encoding="utf-8") for p in mds)
    for analyst in ("Yuling Pan", "Yumi", "Rich", "Kathy"):
        assert analyst in all_md
        assert analyst in out
    for desk in ("forex", "xauusd", "crypto", "us_securities"):
        assert any(f"briefing-{desk}-" in p.name for p in mds)


def test_patterns_included_when_present(tmp_path, monkeypatch):
    import diamondx10.briefing as briefing_mod

    def fake_signals(desk, bars, **kwargs):
        return {"action": "BUY", "reason": "test pattern",
                "regime": {"regime": "TRENDING", "direction": "BULLISH",
                           "adx": 30.0, "volatility": "NORMAL",
                           "confidence": 0.6},
                "patterns": [{"name": "Double Top", "direction": "bearish"}],
                "levels": {"entry": 100.0, "sl": 99.0, "tp": 102.0,
                           "atr": 0.5},
                "strategy": "default"}

    monkeypatch.setattr(briefing_mod, "generate_signals", fake_signals)
    result = build_briefing(base_cfg(), "forex", feed=FakeFeed(),
                            news_fetcher=fake_fetcher, out_dir=tmp_path)
    md = Path(result["md_path"]).read_text(encoding="utf-8")
    data = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert "Double Top" in md
    assert data["symbols"][0]["patterns"] == [
        {"name": "Double Top", "direction": "bearish"}]


def test_cmd_briefing_no_mt5_returns_1(tmp_path, capsys):
    """Provider mt5 tren Linux (khong co goi MetaTrader5): loi sach, rc=1."""
    rc = cmd_briefing(base_cfg(provider="mt5"), "forex",
                      news_fetcher=fake_fetcher, out_dir=tmp_path)
    assert rc == 1
    out = capsys.readouterr().out
    assert "LOI" in out
    assert "Traceback" not in out
    assert list(tmp_path.glob("briefing-*.md")) == []
