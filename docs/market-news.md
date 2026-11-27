# Tin tức thị trường theo desk

> Lấy tin RSS công khai, lọc theo desk, phân tầng độ tin cậy.
> Tin chỉ là **bối cảnh** cho người phụ trách desk đọc trước khi duyệt
> tín hiệu — không tự đổi tín hiệu, không tự đặt lệnh, không lấy "giá"
> từ tiêu đề báo (giá chỉ từ MT5).
>
> Nguồn pattern: repo ThaoResearch (`core/crawler.py`,
> `core/filter_engine.py`, `utils/database.py`, `models/article.py`),
> viết lại bằng thư viện chuẩn (urllib + xml.etree + sqlite3), catalog
> viết lại cho 4 desk DiamondX. Xem
> `docs/merge-diamondx10-2026-11-27.md`.

## Chạy

```bash
python3 -m diamondx10 news                    # tat ca desk, tin 2 ngay gan nhat
python3 -m diamondx10 news --desk xauusd      # chi desk vang
python3 -m diamondx10 news --desk crypto --days 1
python3 -m diamondx10 news --all             # hien ca tin da xem truoc do
```

- `--desk`: forex | xauusd | crypto | us_securities (mặc định: tất cả).
- `--days`: chỉ lấy tin trong N ngày gần nhất (mặc định 2).
- `--all`: hiện cả tin đã xem trước đó (mặc định chỉ hiện tin mới).
- Cấu hình trong `config.yaml` / `config.example.yaml` (mục `news`):
  từ khóa từng desk, blacklist, từ khóa khẩn, danh sách nguồn.

## Luồng lấy tin (`src/diamondx10/data/news.py`)

1. **Fetch** (`fetch_feed`, `fetch_url`): GET từng feed RSS/Atom,
   retry tối đa 3 lần với backoff 2^n giây, timeout 10s, delay 2s giữa
   các request, tối đa 50 bài/nguồn. Lỗi từng nguồn chỉ ghi vào báo
   cáo, không làm hỏng cả lượt chạy. Không bao giờ raise khi lấy tin.
2. **Parse** (`parse_feed`): RSS 2.0 (`<channel>/<item>`) và Atom
   (`<entry>`, `<link href>`), lấy title/link/summary/pubDate.
3. **Lọc** (`filter_articles`): theo thứ tự — blacklist (loại) →
   gắn tag desk theo từ khóa (word-boundary, không khớp desk nào thì
   loại) → loại tin cũ hơn `max_age_days` (tin không có ngày thì giữ) →
   đánh dấu khẩn nếu khớp từ khóa high-priority.
4. **Dedup** (`NewsStore`): MD5(title + link), SQLite
   `data/news-history.db` (file runtime, đã gitignore), INSERT OR
   IGNORE — tin đã xem không hiện lại trừ khi dùng `--all`.
5. **In** (`format_news_report`): gom theo desk, mỗi tin ghi tier +
   nguồn + link + tóm tắt; tin tier 3 kèm cảnh báo CHƯA XÁC MINH.

## Phân tầng độ tin cậy — bắt buộc

Repo ThaoResearch gốc **không có** phân tầng nguồn — đây là bổ sung
bắt buộc theo quy tắc nhóm (tin rò rỉ phải ghi rõ chưa xác minh,
xem `docs/trading-foundation.md` §2).

| Tier | Nhãn | Nguồn | Cách lấy |
|---|---|---|---|
| 1 | CHÍNH THỐNG | Fed/ECB/SEC, báo cáo chính thức, ngân hàng trung ương | **Đọc tay** (Yuling) — không có feed tự động |
| 2 | BÁO CHÍ | Bloomberg, FT, WSJ, Investing.com, Nasdaq, Mining.com, OilPrice, Guardian, Google News | Feed RSS tự động (danh sách dưới) |
| 3 | RÒ RỈ — CHƯA XÁC MINH | x.com, tin đồn crypto | **Tìm tay** (Rich) — không có feed tự động, **không làm căn cứ duy nhất** cho quyết định giao dịch |

## Nguồn tin (tier 2, đã kiểm chứng URL)

| Nguồn | Desk | URL |
|---|---|---|
| Google News — Gold | xauusd | `news.google.com/rss/search?q=gold+price+OR+"gold+futures"+OR+bullion+OR+"central+bank+gold"+when:30d&hl=en-US&gl=US&ceid=US:en` |
| Google News — Fed/ECB/CPI | forex | `news.google.com/rss/search?q="Federal+Reserve"+OR+ECB+OR+"interest+rate+decision"+OR+CPI+when:7d&hl=en-US&gl=US&ceid=US:en` |
| Google News — Bitcoin | crypto | `news.google.com/rss/search?q=Bitcoin+OR+Ethereum+OR+BNB+price+when:7d&hl=en-US&gl=US&ceid=US:en` |
| Google News — AI chips/earnings | us_securities | `news.google.com/rss/search?q=NVDA+OR+Nvidia+OR+AMD+OR+semiconductor+earnings+when:7d&hl=en-US&gl=US&ceid=US:en` |
| Bloomberg — Markets | forex, us_securities | `https://feeds.bloomberg.com/markets/news.rss` |
| WSJ — Markets | forex, us_securities | `https://feeds.a.dj.com/rss/RSSMarketsMain.xml` |
| FT — Commodities | xauusd | `https://www.ft.com/commodities?format=rss` |
| Investing.com — Commodities | xauusd | `https://www.investing.com/rss/news_11.rss` |
| Nasdaq — Commodities | xauusd, us_securities | `https://www.nasdaq.com/feed/rssoutbound?category=Commodities` |
| Mining.com | xauusd | `https://www.mining.com/feed/` |
| OilPrice.com | xauusd, forex | `https://oilprice.com/rss/main` |
| Guardian — Commodities | xauusd | `https://www.theguardian.com/business/commodities/rss` |

URL feed trực tiếp lấy từ catalog của ThaoResearch (đã kiểm chứng
ngày 2026-11-09 trong repo đó); các truy vấn Google News theo đúng
mẫu của catalog đó (`news.google.com/rss/search?q=...&hl=en-US&gl=US&ceid=US:en`).

## Từ khóa theo desk (mặc định trong config)

- **forex (Yuling):** EURUSD, euro, ECB, Federal Reserve, Fed, dollar
  index, DXY, CPI, inflation, interest rate.
- **xauusd (Yumi):** gold, XAUUSD, bullion, COMEX, central bank gold,
  troy ounce, LBMA.
- **crypto (Rich):** Bitcoin, BTC, Ethereum, ETH, BNB, Binance, crypto,
  cryptocurrency.
- **us_securities (Kathy):** NVDA, Nvidia, AMD, Intel, INTC, Cadence,
  CDNS, Synopsys, SNPS, semiconductor, AI chip, earnings.
- **Từ khóa khẩn** (đánh dấu [KHAN]): Federal Reserve, FOMC, interest
  rate decision, CPI, Nonfarm, rate cut, rate hike, earnings,
  ECB rate decision.
- **Blacklist** (loại): sponsored, advertisement, advertorial,
  giveaway, promo code.

Khớp từ khóa theo **word-boundary** (`(?<!\w)kw(?!\w)`): "tin" không
khớp "continuing", "ore" không khớp "before".

## Chu kỳ chạy

- Trước phiên giao dịch + trước giờ tin lớn (CPI/FOMC/Nonfarm).
- Tin khẩn (tier 1/2, từ khóa [KHAN]) do người phụ trách desk đọc ngay;
  tin tier 3 chỉ đọc sau khi có nguồn tier 1/2 xác nhận.
- Gửi tín hiệu ra ngoài vẫn qua bot Telegram DiamondX10 của Kathy,
  theo quy trình nhóm — module tin **không tự gửi Telegram**.

## Giới hạn phải biết

- Không có feed X/Twitter, Telegram channel, Binance/CoinGecko, lịch
  kinh tế trong module này — tin rò rỉ và tin chính thống vẫn đọc tay.
- Không trích "giá" từ tiêu đề báo (repo gốc làm vậy qua regex) —
  giá chỉ lấy từ MT5 (Phase A đã chốt MT5-only).
- Không có GUI, không có license, không nhúng credential (repo gốc có
  `scripts/embed_credentials.py` — không lấy, xem hồ sơ merge).
- Feed RSS có thể chết/đổi URL theo thời gian — nếu `news` báo lỗi lấy
  tin cho một nguồn, kiểm tra URL đó trước khi sửa config.
