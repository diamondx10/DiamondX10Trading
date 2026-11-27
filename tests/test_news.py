"""Test module tin thi truong (merge pattern tu ThaoResearch, viet lai
stdlib-only): parse RSS/Atom, loc theo desk, dedup SQLite, chay luot
tin voi fetcher gia (khong dung mang that)."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diamondx10.data.news import (
    NewsArticle,
    NewsStore,
    fetch_feed,
    filter_articles,
    format_news_report,
    parse_feed,
    run_news,
)

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Gold News</title>
<item><title>Gold price surges as central banks buy bullion</title>
<link>https://example.com/gold-1</link>
<description>COMEX gold futures hit a new high.</description>
<pubDate>Mon, 24 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>Bitcoin rallies after ETF inflows</title>
<link>https://example.com/btc-1</link>
<description>BTC price up 5%.</description>
<pubDate>Mon, 24 Nov 2026 11:00:00 GMT</pubDate></item>
<item><title>Sponsored: best trading course</title>
<link>https://example.com/ad-1</link>
<description>Buy our course now.</description>
<pubDate>Mon, 24 Nov 2026 12:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Markets</title>
<entry><title>Federal Reserve holds rates steady</title>
<link href="https://example.com/fed-1" rel="alternate"/>
<summary>ECB and Fed signal no change to interest rates.</summary>
<updated>2026-11-24T09:00:00Z</updated></entry>
</feed>"""

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)

CFG = {
    "max_age_days": 2,
    "filters": {
        "blacklist_keywords": ["sponsored"],
        "high_priority_keywords": ["Federal Reserve", "rate cut"],
    },
    "desks": {
        "forex": {"keywords": ["EURUSD", "Federal Reserve", "ECB",
                               "interest rate"]},
        "xauusd": {"keywords": ["gold", "bullion", "COMEX"]},
        "crypto": {"keywords": ["Bitcoin", "BTC"]},
        "us_securities": {"keywords": ["NVDA", "Nvidia"]},
    },
    "sources": [
        {"name": "Fake Gold", "url": "https://example.com/gold.rss",
         "tier": 2, "desks": ["xauusd"]},
        {"name": "Fake Markets", "url": "https://example.com/markets.atom",
         "tier": 2, "desks": ["forex"]},
    ],
}


def test_parse_rss_items():
    articles = parse_feed(RSS, "Fake Gold")
    assert len(articles) == 3
    assert articles[0].title.startswith("Gold price")
    assert articles[0].link == "https://example.com/gold-1"
    assert articles[0].source == "Fake Gold"
    assert articles[0].pub_date is not None
    assert articles[0].pub_date.year == 2026
    assert "COMEX" in articles[0].summary


def test_parse_atom_entry():
    articles = parse_feed(ATOM, "Fake Markets")
    assert len(articles) == 1
    assert articles[0].title == "Federal Reserve holds rates steady"
    assert articles[0].link == "https://example.com/fed-1"


def test_parse_bad_xml_empty():
    assert parse_feed(b"not xml at all", "X") == []
    assert parse_feed(b"", "X") == []


def test_filter_tags_desks_and_blacklist():
    articles = parse_feed(RSS, "Fake Gold")
    kept = filter_articles(articles, CFG, max_age_days=2, now=NOW)
    # Bai quang cao bi blacklist loai; 2 bai con lai moi bai 1 desk.
    assert len(kept) == 2
    gold = [a for a in kept if "xauusd" in a.desk_tags]
    btc = [a for a in kept if "crypto" in a.desk_tags]
    assert len(gold) == 1 and len(btc) == 1
    assert gold[0].is_urgent is False


def test_filter_word_boundary_no_false_match():
    # "tin" trong "continuing" hoac "ore" trong "before" khong khop.
    articles = [NewsArticle(title="Gold continues before earnings",
                            link="https://example.com/x")]
    kept = filter_articles(articles, {
        "desks": {"xauusd": {"keywords": ["tin", "ore"]}}},
        max_age_days=2, now=NOW)
    assert kept == []


def test_filter_urgency_and_old_news():
    articles = parse_feed(ATOM, "Fake Markets")
    kept = filter_articles(articles, CFG, max_age_days=2, now=NOW)
    assert len(kept) == 1
    assert kept[0].is_urgent is True  # "Federal Reserve" la tu khan
    assert "forex" in kept[0].desk_tags
    # Tin cu hon 2 ngay thi bo.
    old = [NewsArticle(title="Gold price falls",
                       link="https://example.com/old",
                       pub_date=datetime(2026, 11, 20, tzinfo=timezone.utc))]
    assert filter_articles(old, CFG, max_age_days=2, now=NOW) == []
    # Tin khong co ngay thi giu lai.
    nodate = [NewsArticle(title="Gold price falls",
                          link="https://example.com/nodate")]
    assert len(filter_articles(nodate, CFG, max_age_days=2, now=NOW)) == 1


def test_store_dedup(tmp_path):
    store = NewsStore(tmp_path / "news.db")
    a = NewsArticle(title="Gold price surges", link="https://example.com/g1")
    assert store.is_seen(a.article_hash()) is False
    store.mark_seen(a)
    assert store.is_seen(a.article_hash()) is True
    assert store.count_seen() == 1
    store.mark_seen(a)  # INSERT OR IGNORE: khong tang.
    assert store.count_seen() == 1
    store.close()


def test_run_news_fake_fetcher(tmp_path):
    feeds = {"https://example.com/gold.rss": RSS,
             "https://example.com/markets.atom": ATOM}

    def fake_fetcher(url, timeout):
        return feeds[url]

    store = NewsStore(tmp_path / "news.db")
    result = run_news(CFG, fetcher=fake_fetcher, store=store, now=NOW)
    assert result["fetched"] == 4  # 3 RSS + 1 Atom
    assert result["matched"] == 3  # loai 1 quang cao
    assert result["new"] == 3
    assert result["errors"] == []
    # Chay lai: tat ca da thay -> khong co tin moi.
    result2 = run_news(CFG, fetcher=fake_fetcher, store=store, now=NOW)
    assert result2["new"] == 0
    assert result2["matched"] == 3
    store.close()


def test_run_news_desk_filter(tmp_path):
    def fake_fetcher(url, timeout):
        return RSS if "gold" in url else ATOM

    store = NewsStore(tmp_path / "news.db")
    result = run_news(CFG, desk="xauusd", fetcher=fake_fetcher,
                      store=store, now=NOW)
    assert result["fetched"] == 3
    assert result["matched"] == 1
    assert all("xauusd" in a.desk_tags for a in result["articles"])
    store.close()


def test_run_news_fetch_error_collected(tmp_path):
    def failing_fetcher(url, timeout):
        raise RuntimeError("mang hong")

    store = NewsStore(tmp_path / "news.db")
    result = run_news(CFG, fetcher=failing_fetcher, store=store, now=NOW)
    assert result["fetched"] == 0
    assert result["new"] == 0
    assert len(result["errors"]) == 2  # 2 nguon deu loi, khong crash
    store.close()


def test_format_report_tier3_warning():
    article = NewsArticle(title="Whale buys BTC (leak)",
                          link="https://x.com/leak1",
                          source="x.com — Rich", trust_tier=3,
                          desk_tags=["crypto"])
    text = format_news_report(
        {"fetched": 1, "matched": 1, "new": 1, "errors": [],
         "articles": [article]})
    assert "RO RI — CHUA XAC MINH" in text
    assert "CHUA XAC MINH" in text
    assert "khong dung lam can cu duy nhat" in text
    assert "crypto" in text


def test_fetch_feed_sets_tier():
    articles, err = fetch_feed(
        {"name": "Fake", "url": "https://example.com/gold.rss", "tier": 2},
        opener=lambda url, timeout: RSS)
    assert err is None
    assert all(a.trust_tier == 2 for a in articles)
    articles, err = fetch_feed({"name": "No URL"}, opener=None)
    assert articles == [] and err is not None
