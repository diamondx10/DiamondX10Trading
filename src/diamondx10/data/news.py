"""Tin tuc thi truong — lay tin RSS, loc theo desk, phan tang do tin cay.

Mau (pattern) lay tu repo ThaoResearch: core/crawler.py (retry +
backoff khi GET), core/filter_engine.py (loc keyword word-boundary,
blacklist, urgency), utils/database.py (dedup MD5 + SQLite),
models/article.py (Article). Viet lai bang thu vien chuan
(urllib + xml.etree + sqlite3 + hashlib), khong them dependency.

Khac biet quan trong so voi ban goc (ghi ro de khong lap lai han che
cua no):
- Catalog viet lai cho 4 desk DiamondX (forex / vang / crypto /
  chung khoan My) — catalog goc la 41 mat hang nong san/hang hoa.
- Them PHAN TANG DO TIN CAY (ban goc khong co): tier 1 CHINH THONG
  (Fed/ECB/USDA... — doc thu cong, khong co feed tu dong), tier 2
  BAO CHI (feed RSS cua Bloomberg/FT/WSJ... va Google News),
  tier 3 RO RI (x.com — Rich tim thu cong, LUON danh dau
  CHUA XAC MINH, khong dung lam can cu duy nhat cho quyet dinh
  giao dich, theo docs/trading-foundation.md §2).
- KHONG trich "gia" tu tieu de bao de lam gia giao dich (ban goc lam
  vay qua regex) — gia chi lay tu MT5 (Phase A da chot MT5-only).
- Chi doc + in canh bao; khong tu gui Telegram. Gui tin hieu van
  qua bot Telegram DiamondX10 cua Kathy, theo quy trinh nhom.
"""
import hashlib
import re
import sqlite3
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

# Phan tang do tin cay nguon tin (xem docs/market-news.md).
TRUST_TIERS = {
    1: "CHINH THONG",
    2: "BAO CHI",
    3: "RO RI — CHUA XAC MINH",
}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    "DiamondX10/1.0"
)
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
BACKOFF_BASE = 2  # cho 2s, 4s
INTER_REQUEST_DELAY = 2  # giay giua 2 request thanh cong
MAX_ARTICLES_PER_SOURCE = 50

# Lich su dedup mac dinh (file RUNTIME — da them vao .gitignore).
DEFAULT_STORE_PATH = Path(__file__).resolve().parents[2] / "data" / "news-history.db"


@dataclass
class NewsArticle:
    title: str
    link: str
    pub_date: object = None  # datetime (aware) hoac None neu khong co
    summary: str = ""
    source: str = ""
    desk_tags: list = field(default_factory=list)
    trust_tier: int = 2
    is_urgent: bool = False

    def article_hash(self):
        """MD5(title + link) — khoa dedup, giong Article.compute_hash()
        cua ThaoResearch."""
        raw = (self.title + "|" + self.link).encode("utf-8")
        return hashlib.md5(raw).hexdigest()

    def trust_label(self):
        return TRUST_TIERS.get(self.trust_tier, "BAO CHI")


# --- Lay feed (urllib, retry + backoff) ---

def fetch_url(url, timeout=REQUEST_TIMEOUT, max_retries=MAX_RETRIES,
              opener=None):
    """GET 1 URL, retry toi da max_retries voi backoff 2^n giay.
    Tra bytes hoac None khi that bai (timeout, 5xx sau het retry,
    4xx, DNS/SSL). Khong bao gio raise — giong _http_get cua
    ThaoResearch. `opener`: ham (url, timeout) -> bytes, dung cho test."""
    if opener is not None:
        try:
            return opener(url, timeout)
        except Exception:
            return None
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 429 and attempt < max_retries:
                    time.sleep(BACKOFF_BASE ** attempt)
                    continue
                if resp.status != 200:
                    return None
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < max_retries:
                time.sleep(BACKOFF_BASE ** attempt)
                continue
            return None
        except Exception:
            if attempt < max_retries:
                time.sleep(BACKOFF_BASE ** attempt)
                continue
            return None
    return None


def _strip_html(text):
    """Bo the HTML, gon khoang trang (thay BeautifulSoup)."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", clean).strip()


def _parse_date(raw):
    """Parse ngay gio RSS/Atom; tra datetime aware (UTC) hoac None."""
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _text(node, tag):
    child = node.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _atom_link(node):
    """Link cua 1 entry Atom: <link href=...> (uu tien rel=alternate).
    Tim ca dang co namespace Atom va khong co namespace."""
    links = node.findall("{http://www.w3.org/2005/Atom}link")
    links += node.findall("link")
    for link in links:
        href = (link.get("href") or "").strip()
        if href and link.get("rel") in (None, "alternate"):
            return href
    return ""


def parse_feed(xml_bytes, source_name):
    """Parse RSS 2.0 (<channel>/<item>) hoac Atom (<entry>) thanh
    list[NewsArticle]. Toi da MAX_ARTICLES_PER_SOURCE bai/nguon.
    Tra [] neu XML hong hoac khong co bai nao."""
    if not xml_bytes:
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    tag = root.tag.split("}")[-1]
    articles = []
    if tag == "feed":
        items = root.findall("{http://www.w3.org/2005/Atom}entry")
        if not items:
            items = root.findall("entry")
        for entry in items[:MAX_ARTICLES_PER_SOURCE]:
            ns = "{http://www.w3.org/2005/Atom}"
            title = _text(entry, ns + "title") or _text(entry, "title")
            link = _atom_link(entry)
            summary = (_text(entry, ns + "summary")
                       or _text(entry, "summary"))
            pub = (_text(entry, ns + "updated") or _text(entry, "updated")
                   or _text(entry, ns + "published")
                   or _text(entry, "published"))
            if not title or not link:
                continue
            articles.append(NewsArticle(
                title=title, link=link,
                pub_date=_parse_date(pub),
                summary=_strip_html(summary)[:500], source=source_name))
    else:
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else []
        for item in items[:MAX_ARTICLES_PER_SOURCE]:
            title = _text(item, "title")
            link = _text(item, "link")
            summary = _text(item, "description") or _text(item, "summary")
            pub = _text(item, "pubDate") or _text(item, "updated")
            if not title or not link:
                continue
            articles.append(NewsArticle(
                title=title, link=link,
                pub_date=_parse_date(pub),
                summary=_strip_html(summary)[:500], source=source_name))
    return articles


def fetch_feed(source, opener=None):
    """Lay 1 nguon tin (dict {name, url, tier, desks}): tra
    (articles, error) — error la None khi thanh cong. Khong raise."""
    name = source.get("name") or source.get("url") or "?"
    url = source.get("url") or ""
    if not url:
        return [], f"{name}: thieu url"
    raw = fetch_url(url, opener=opener)
    if raw is None:
        return [], f"{name}: khong lay duoc feed ({url})"
    articles = parse_feed(raw, name)
    for a in articles:
        a.trust_tier = int(source.get("tier", 2))
    return articles, None


# --- Loc tin theo desk ---

def _keyword_pattern(keyword):
    """Matcher word-boundary (copy y tuong _keyword_pattern cua
    ThaoResearch): "tin" khong khop "continuing", "ore" khong khop
    "before". Dung (?<!\\w)/(?!\\w) thay cho \\b de keyword co dau
    gach noi ("soybean-oil", "S&P 500") van khop dung."""
    kw = (keyword or "").strip().lower()
    if not kw:
        return None
    return re.compile(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", re.IGNORECASE)


def _matches_any(text, keywords):
    for kw in keywords or []:
        pat = _keyword_pattern(kw)
        if pat is not None and pat.search(text):
            return True
    return False


def filter_articles(articles, news_cfg, max_age_days=2, now=None):
    """Loc tin theo 4 buoc (mau tu apply_filters cua ThaoResearch,
    bo buoc trich gia tu text):
    1. Blacklist (bo).
    2. Gan tag desk theo keywords (khong khop desk nao thi bo).
    3. Bo tin cu hon max_age_days (tin khong co ngay thi giu lai).
    4. Urgency neu khop high-priority keywords.
    Tra list bai da loc (cung object, da gan desk_tags/is_urgent)."""
    news_cfg = news_cfg or {}
    filters = news_cfg.get("filters") or {}
    blacklist = [str(k) for k in (filters.get("blacklist_keywords") or [])]
    high_priority = [str(k) for k in
                     (filters.get("high_priority_keywords") or [])]
    desks_cfg = news_cfg.get("desks") or {}
    desk_keywords = {}
    for desk, spec in desks_cfg.items():
        desk_keywords[desk] = [str(k) for k in (spec or {}).get("keywords") or []]
    now = now or datetime.now(timezone.utc)
    kept = []
    for article in articles:
        text = f"{article.title} {article.summary}"
        if _matches_any(text, blacklist):
            continue
        tags = [d for d, kws in desk_keywords.items()
                if _matches_any(text, kws)]
        if not tags:
            continue
        article.desk_tags = tags
        pub = article.pub_date
        if pub is not None:
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            age_days = (now - pub).total_seconds() / 86400.0
            if age_days > max_age_days:
                continue
        article.is_urgent = _matches_any(text, high_priority)
        kept.append(article)
    return kept


# --- Dedup bang SQLite (mau tu utils/database.py cua ThaoResearch) ---

class NewsStore:
    """Lich su tin da xem: dedup theo MD5(title + link), INSERT OR
    IGNORE. File SQLite o data/news-history.db (runtime, gitignore)."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else DEFAULT_STORE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), timeout=10)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS seen_articles ("
            "  article_hash TEXT PRIMARY KEY,"
            "  article_title TEXT, article_url TEXT,"
            "  desks TEXT, trust_tier INTEGER, source TEXT,"
            "  pub_date TEXT, seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")")
        self._conn.commit()

    def close(self):
        self._conn.close()

    def is_seen(self, article_hash):
        row = self._conn.execute(
            "SELECT 1 FROM seen_articles WHERE article_hash = ? LIMIT 1",
            (article_hash,)).fetchone()
        return row is not None

    def mark_seen(self, article):
        pub = article.pub_date.isoformat() if article.pub_date else None
        self._conn.execute(
            "INSERT OR IGNORE INTO seen_articles (article_hash, "
            "  article_title, article_url, desks, trust_tier, source, "
            "  pub_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (article.article_hash(), article.title, article.link,
             ",".join(article.desk_tags), article.trust_tier,
             article.source, pub))
        self._conn.commit()

    def count_seen(self):
        row = self._conn.execute(
            "SELECT COUNT(*) FROM seen_articles").fetchone()
        return int(row[0]) if row else 0


# --- Chay 1 luot lay tin ---

def run_news(news_cfg, desk=None, max_age_days=2, fetcher=None,
             store=None, include_seen=False, now=None):
    """Chay 1 luot: lay tat ca nguon bat trong config (loc theo desk
    neu truyen), loc tin, dedup qua store. Tra dict {fetched, matched,
    new, errors, articles} — articles la tin MOI (chua thay) da loc,
    hoac tat ca tin da loc neu include_seen=True.

    fetcher: ham (url, timeout) -> bytes, dung cho test (khong truyen
    thi dung urllib that). store: NewsStore (khong truyen thi mo
    store mac dinh)."""
    news_cfg = news_cfg or {}
    sources = [s for s in (news_cfg.get("sources") or [])
               if s.get("enabled", True)]
    if desk:
        sources = [s for s in sources
                   if desk in (s.get("desks") or [])]
    if store is None:
        store = NewsStore()
        own_store = True
    else:
        own_store = False
    fetched = []
    errors = []
    try:
        for source in sources:
            articles, err = fetch_feed(source, opener=fetcher)
            if err:
                errors.append(err)
                continue
            fetched.extend(articles)
            if fetcher is None:
                # Chi delay khi dung mang that (lich su voi server);
                # test dung fetcher gia thi khong delay.
                time.sleep(INTER_REQUEST_DELAY)
        matched = filter_articles(fetched, news_cfg, max_age_days, now)
        if desk:
            # Chi giu tin gan tag desk da chon (filter_articles gan tag
            # theo MỌI desk trong config, nen can loc them 1 buoc).
            matched = [a for a in matched if desk in a.desk_tags]
        new = []
        for article in matched:
            if store.is_seen(article.article_hash()):
                if include_seen:
                    new.append(article)
                continue
            store.mark_seen(article)
            new.append(article)
        return {"fetched": len(fetched), "matched": len(matched),
                "new": len(new), "errors": errors, "articles": new}
    finally:
        if own_store:
            store.close()


def format_news_report(result, desk=None):
    """In ket qua run_news() thanh van ban (tieng Viet), gom theo desk.
    Tin tier 3 luon kem canh bao CHUA XAC MINH."""
    articles = result["articles"]
    lines = ["DiamondX10 — TIN THI TRUONG MOI",
             f"Lay duoc {result['fetched']} bai, loc duoc "
             f"{result['matched']} bai, moi: {result['new']} bai."]
    if result["errors"]:
        lines.append("Loi lay tin:")
        for err in result["errors"]:
            lines.append(f"  - {err}")
    if not articles:
        lines.append("(Khong co tin moi.)")
        return "\n".join(lines)
    desks = ["forex", "xauusd", "crypto", "us_securities"]
    if desk:
        desks = [desk]
    for d in desks:
        items = [a for a in articles if d in a.desk_tags]
        if not items:
            continue
        lines.append(f"== {d} ({len(items)} tin) ==")
        for a in items:
            flag = " [KHAN]" if a.is_urgent else ""
            lines.append(f"  - [{a.trust_label()}]{flag} {a.title}")
            lines.append(f"    {a.source} | {a.link}")
            if a.summary:
                lines.append(f"    {a.summary[:200]}")
            if a.trust_tier == 3:
                lines.append("    CANH BAO: tin ro ri CHUA XAC MINH — "
                             "khong dung lam can cu duy nhat cho quyet "
                             "dinh giao dich.")
    return "\n".join(lines)
