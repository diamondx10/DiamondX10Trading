# Hồ sơ merge — repo DiamondX10 cũ + ThaoResearch vào DiamondX10Trading

> Ngày merge: 2026-11-27. Làm việc **local only, không push GitHub,
> không sửa 2 repo nguồn**. Baseline trước merge: pytest 106 passed.
> Sau merge: **156 passed** (106 cũ + 50 mới), 0 lỗi.
>
> Nguyên tắc merge (theo yêu cầu của Phu): **tài liệu giao dịch của
> DiamondX10 là quan trọng nhất** — reflect vào docs của tool
> (trading-principles.md, trading-foundation.md, phase0-desk-rules.md)
> kèm nguồn, và reflect vào code ở chỗ nào doc hàm ý một quy tắc cụ
> thể. **ThaoResearch lấy phần lấy thông tin thị trường** — thành
> module tin thật trong data layer + docs. Chỉ reflect những gì khớp
> quy tắc nhóm đã chốt; mâu thuẫn thì ghi ở mục "Cần Phu quyết", không
> tự đổi quy tắc.

## 1. Inventory ngắn gọn 2 repo nguồn

### DiamondX10 (diamondx10/DiamondX10) — HEAD `490e7b72`, 26/07/2026

- Repo quant cũ của nhóm: **260 file, ~505 MB** (62 PDF tài liệu ~480 MB
  trong `Material/`), 10 commit 27/06–26/07/2026, không động ~4 tháng.
- MVP quant chạy được end-to-end: vòng lặp 5 phút, đa khung M30/H4/D1,
  MT5 5000 bar (fallback yfinance nếu < 100 bar) → regime → macro →
  3 chiến lược → aggregator → RiskManager → Synthesizer → Telegram +
  báo cáo md → đặt lệnh nếu `AUTO_TRADE_MODE=True` (mặc định False).
- Chiến lược: TrendFollowing (EMA 12/26 + ADX), MeanReversion
  (RSI < 30 + giá dưới Bollinger Band dưới), Breakout (Donchian 20 +
  volume). Aggregator vote 0,4/0,3/0,3; Synthesizer Tech 60% + Fund 40%.
- Risk: SL 2,0×ATR / TP 3,0×ATR, risk 2%/lệnh, drawdown ngày 5% / tuần
  10%, VaR 95/99% + stress test (khởi tạo nhưng `run.py` không gọi
  `.analyze()`), Kelly 25% + risk parity (trong rule YAML).
- X10 Engine: 8 tham số radar → 30+ giá trị nội suy (SL/TP/Kelly...),
  18 rule YAML có nguồn sách; nhưng `run.py` chỉ khởi tạo adapter,
  không dùng — không có "confidence override" như README nói.
- Backtest: 2 engine mâu thuẫn nhau (walk-forward SL từ biên độ bar,
  lot cố định 0,01, P&L ×100000 sai với vàng; engine kia ×100 đúng
  vàng nhưng slippage khai mà không dùng).
- API/Frontend: FastAPI 8 endpoint nhưng **là stub** (`/analyze` trả
  mock, `/config/update` không làm gì); frontend React poll endpoint
  mock nên không có dữ liệu thật. TUI Textual dùng
  `MockTradingEngine` với **tín hiệu/giá ngẫu nhiên**.
- Test: 11 file, 175 hàm test; thiếu `test_fundamental.py`,
  `test_synthesizer.py` dù PROGRESS ghi ✅; không test X10/MT5Trader/
  Telegram/API/KB.
- **Inventory đầy đủ (61 KB):**
  `~/workspace/diamondx-repos/DiamondX10-inventory-2026-11-27.md`.

### ThaoResearch (diamondx10/ThaoResearch) — ref `72e9bb87…`

- **Không phải tool quant.** App desktop Tkinter (v1.0.0, Python 3.10+,
  PyInstaller .exe ~35 MB) crawl tin tức hàng hóa qua RSS (trọng tâm:
  dầu đậu nành; 41 mặt hàng, 105 nguồn) rồi gửi cảnh báo Telegram cho
  khách hàng mua hàng; có hệ thống license key thương mại.
- Không có test (chỉ script smoke `_test_open.py` thủ công). 0 kết quả
  tìm kiếm cho backtest/MT5/strategy/RSI/MACD/signal/crypto/forex/
  EURUSD/BTCUSD/XAUUSD/NVDA/earnings/CPI/FOMC/macro/twitter/x.com.
- Pipeline `main.py::job_execute()`: crawl (ThreadPoolExecutor) →
  chuẩn hóa ngày về Asia/Ho_Chi_Minh → lọc theo cửa sổ ngày +
  `apply_filters` → `Notifier.send_alert` với dedup MD5.
- Không có phân tầng độ tin cậy cho nguồn tin. "Giá" là số trích từ
  tiêu đề bài báo qua regex, **không phải giá thị trường thật**.
- Tin tức lấy qua RSS/HTML công khai, **không cần credential**; chỉ
  đầu ra Telegram cần `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`.

## 2. Đã merge — tài liệu nào reflect vào đâu, luồng tin nào thành gì

### A. Từ DiamondX10 (tài liệu + quy tắc → docs + code)

| Tài liệu / quy tắc nguồn | Reflect vào đâu | Trạng thái |
|---|---|---|
| Regime ADX (≥ 25 trending, 15–25 transitional, < 15 ranging) + ATR percentile 20/80 + hướng SMA20/50 (`regime_detector.py`) | `models/quant.py`: `adx()`, `atr_percentile()`, `classify_regime()`, `detect_regime()`; `signals.py` thêm khóa `"regime"`; `trading-principles.md` mục 21; `trading-foundation.md` §3 | [ĐÃ CÓ] — chỉ bối cảnh, không chặn tín hiệu |
| Macro edge DXY/US10Y/VIX/SPX (`macro_edge.py`: bảng tương quan + trọng số 0,35/0,25/0,25/0,15) | `models/macro.py`: `macro_edge()` (hàm thuần); `report.py` in mục vĩ mô khi config có `macro:`; `config.example.yaml` mục `macro:` (để comment); `trading-principles.md` mục 22 | [ĐÃ CÓ] — chỉ bối cảnh, snapshot do Yuling cung cấp |
| Walk-forward validation (`walk_forward.py`: train 252 / test 63 / bước 63) | `backtest.py`: `run_walk_forward()` + `format_walk_forward_report()` chạy trên engine backtest của tool; CLI `backtest --walk-forward [--train-bars] [--test-bars] [--step-bars]`; `docs/backtest.md`; `trading-principles.md` mục 24 | [ĐÃ CÓ] — ý tưởng lấy, code viết lại (không copy code gốc) |
| VaR/CVaR lịch sử (`portfolio_risk.py`: VaR 95/99%, CVaR, guard < 20 returns) | `risk.py`: `value_at_risk()`, `expected_shortfall()`; `backtest.py` `compute_metrics()` thêm `var_95_pct`/`cvar_95_pct`; `docs/backtest.md`; `trading-principles.md` mục 25 | [ĐÃ CÓ] — chỉ số báo cáo, không chặn lệnh |
| Breakout Donchian 20 (`breakout.py`: Donchian 20 + lọc ATR) | `strategies/breakout.py`: `DonchianBreakout` (kế thừa `Strategy`, dùng lại SL/TP ATR + trailing + thoát đảo chiều của lớp cơ sở); CLI `backtest --strategy donchian`; `trading-principles.md` mục 23; `phase0-desk-rules.md` mục theo dõi | [ĐÃ CÓ] — chỉ backtest so sánh, chưa dùng live |
| Kelly 25% + risk parity (`rules/_reviewed/risk`) | `trading-principles.md` mục 27 | [NGHIÊN CỨU] — chưa áp dụng, mâu thuẫn bảng risk cố định |
| Chốt lời từng phần TP1 2,0×ATR / TP2 3,0×ATR (Master Plan, `Document/Overview.txt`) | `trading-principles.md` mục 28 | [CẦN CHỐT] — mâu thuẫn TP duy nhất 2×SL |
| Khung phân tích cơ bản/vĩ mô + phân công desk | `trading-foundation.md` §2 (luồng tin) và §3 (bối cảnh kỹ thuật) | [ĐÃ CÓ] trong docs |

### B. Từ ThaoResearch (luồng lấy tin → module thật + docs)

| Luồng / pattern nguồn | Thành gì trong tool |
|---|---|
| `core/crawler.py`: retry 3, backoff 2^n, timeout 10s, delay 2s, xử lý 429/4xx/5xx, tối đa 50 bài/nguồn | `data/news.py`: `fetch_url()` (urllib), `fetch_feed()` — stdlib, không thêm dependency |
| `core/filter_engine.py`: blacklist → keyword word-boundary → urgency; `apply_date_window` | `data/news.py`: `filter_articles()` (blacklist → tag desk → lọc tuổi tin → urgency); `docs/market-news.md` |
| `utils/database.py`: SQLite `history.db`, dedup MD5, INSERT OR IGNORE | `data/news.py`: `NewsStore` (SQLite `data/news-history.db`, đã thêm vào `.gitignore`) |
| `models/article.py`: Article dataclass, `compute_hash`, format tin nhắn | `data/news.py`: `NewsArticle` (title/link/pub_date/summary/source/desk_tags/trust_tier/is_urgent), `article_hash()` |
| `core/default_catalog.py`: 41 Google News feed + 38 publisher feed (URL đã kiểm chứng 2026-11-09) | `config.example.yaml` mục `news:` — 12 nguồn viết lại cho 4 desk DiamondX (URL feed trực tiếp giữ nguyên; truy vấn Google News theo đúng mẫu của catalog) |
| Không có trong nguồn — **bổ sung bắt buộc** | **Phân tầng độ tin cậy tier 1/2/3** (`TRUST_TIERS`, `trust_label()`): tier 3 rò rỉ luôn gắn nhãn CHƯA XÁC MINH; `docs/market-news.md` |
| Lệnh CLI mới | `news [--desk] [--days] [--all]` trong `__main__.py`; `run_news()` + `format_news_report()` |

### C. File đổi / thêm (toàn bộ local, chưa commit/push)

**Code mới:**
- `src/diamondx10/models/quant.py` — thêm `_true_ranges()`,
  `atr_series()`, `_ewm()`, `adx()`, `atr_percentile()`,
  `classify_regime()`, `detect_regime()` + hằng ADX/ATR percentile.
- `src/diamondx10/models/macro.py` — mới: `macro_edge()` + bảng tương
  quan/trọng số/miền giá trị.
- `src/diamondx10/strategies/breakout.py` — mới: `DonchianBreakout`.
- `src/diamondx10/data/news.py` — mới: `NewsArticle`, `fetch_url`,
  `parse_feed`, `fetch_feed`, `filter_articles`, `NewsStore`,
  `run_news`, `format_news_report`.
- `src/diamondx10/signals.py` — `generate_signals()` thêm khóa
  `"regime"` (bối cảnh, không đổi tín hiệu).
- `src/diamondx10/risk.py` — thêm `value_at_risk()`,
  `expected_shortfall()` + `_percentile()`.
- `src/diamondx10/backtest.py` — `compute_metrics()` thêm
  `var_95_pct`/`cvar_95_pct`; thêm `_pick_strategy()`,
  `run_walk_forward()`, `format_walk_forward_report()`; `run_backtest()`
  thêm tham số `strategy_name`.
- `src/diamondx10/report.py` — thêm `_macro_section()` + in mục vĩ mô.
- `src/diamondx10/__main__.py` — lệnh `news`; cờ `--strategy`,
  `--walk-forward`, `--train-bars`, `--test-bars`, `--step-bars` cho
  `backtest`.

**Config/docs:**
- `config.example.yaml` — mục `news:` (12 nguồn, từ khóa 4 desk) +
  mục `macro:` (để comment).
- `.gitignore` — thêm `data/news-history.db`.
- `docs/trading-principles.md` — mục 7 mới (quy tắc 21–28), mục 8/9
  đổi số, checklist bổ sung 5 mục, tài liệu liên quan bổ sung.
- `docs/trading-foundation.md` — §2 thêm luồng lấy tin + phân tầng;
  §3 thêm bối cảnh regime/macro/Donchian.
- `docs/phase0-desk-rules.md` — mục theo dõi thêm 4 ứng viên từ repo cũ.
- `docs/backtest.md` — cờ mới, mục walk-forward, VaR/CVaR.
- `docs/market-news.md` — mới: catalog, tier, luồng, từ khóa, chu kỳ.
- `docs/merge-diamondx10-2026-11-27.md` — mới: file này.
- `README.md` — cập nhật danh sách lệnh + cấu trúc.

**Test mới (50 test, không dùng mạng thật):**
- `tests/test_regime.py` (10): ADX cao/thấp, ngưỡng regime, hướng,
  ATR percentile mặc định 50,0, confidence trong [0, 1].
- `tests/test_macro.py` (8): DXY mạnh → vàng tiêu cực, VIX cao → vàng
  tích cực (theo bảng tương quan), EURUSD, midpoint neutral, clamp
  [−1, 1], symbol chưa có mô hình, thiếu snapshot.
- `tests/test_breakout.py` (7): phá đỉnh → BUY, phá đáy → SELL,
  trong kênh → HOLD, biến động thấp → HOLD, SL/TP theo ATR, kế thừa
  trailing/reversal của lớp cơ sở.
- `tests/test_var.py` (6): VaR/CVaR trên chuỗi biết trước, toàn lãi →
  0, < 2 returns → None, VaR99 ≥ VaR95, có mặt trong `compute_metrics`.
- `tests/test_walkforward.py` (7): 7 cửa sổ trên 100 bar, OOS gộp =
  tổng lệnh test, thiếu bar → lỗi, Donchian, strategy lạ → lỗi,
  format báo cáo, độ dài đường equity OOS, CLI `--walk-forward` /
  `--strategy`.
- `tests/test_news.py` (12): parse RSS/Atom, XML hỏng → [], lọc tag
  desk + blacklist + urgency + tuổi tin, word-boundary không khớp sai,
  dedup SQLite, `run_news` với fetcher giả (lần 2 không còn tin mới),
  lọc theo desk, lỗi fetch được gom không crash, cảnh báo tier 3,
  `fetch_feed` gắn tier.

## 3. Đã xem nhưng KHÔNG merge + lý do

### Từ DiamondX10

| Tính năng | Lý do không merge |
|---|---|
| `MT5Trader` — đặt lệnh thật qua `mt5.order_send` (magic 20260726, spread 50, slippage 20) | **Không có demo-guard, server là Real** — vi phạm demo-only. Tool đã có `execution.place_demo_order` với guard demo-only. |
| `config.yaml` / `Document/Overview.txt` chứa credential MT5 thật | **Secret — chỉ báo riêng, không copy** (xem mục 5). |
| FastAPI + React frontend (8 endpoint) | Endpoint là stub (mock / không làm gì); frontend poll mock nên không có dữ liệu thật. Không thêm năng lực thật. |
| X10 Engine (radar 8 tham số → 30+ giá trị nội suy, 18 rule YAML, LLM) | Trong repo gốc cũng **không được nối vào luồng chạy** (`run.py` chỉ khởi tạo adapter); cần OpenRouter key + tốn phí; giá trị nội suy mâu thuẫn tham số đã chốt (SL 2,34×, TP 3,68×, risk 2%, Kelly 0,346...). |
| TUI Textual (`standalone_tool`) | `MockTradingEngine` sinh tín hiệu/giá ngẫu nhiên (2400±20) — chỉ mô phỏng, README gốc tự thừa nhận. |
| EMA 12/26 hoặc 20/50 + RSI 30/70 thay SMA5/20 + RSI 50–70/30–50 | Mâu thuẫn quy tắc đã chốt (mục 4–5 trading-principles.md). Ghi để Phu quyết nếu muốn đổi. |
| Risk 2%/lệnh, SL 2,0×ATR, TP 3,0×ATR, DD 15%, DD ngày 5%/tuần 10% | Mâu thuẫn quy tắc đã chốt (risk 1% + bảng theo symbol, SL 1,5×, TP 2×SL, DD quỹ 10% + cảnh báo desk 5%). Ghi để Phu quyết. |
| Code walk-forward gốc copy nguyên | Lot cố định 0,01, SL từ biên độ bar (không phải ATR), P&L ×100000 sai với vàng. Chỉ lấy ý tưởng, viết lại trên engine của tool. |
| Deflated Sharpe (bootstrap tự chế) | Tool đã có Sharpe; bản bootstrap tự chế không có cơ sở kiểm chứng. |
| Stress test gốc (`base_vol × shock × 10`) | Công thức quá yếu, không có ý nghĩa. Không lấy. |
| Pairs trading (rule R_STR_004, z > 2, corr > 0,70) | Chỉ là rule YAML, chưa có code; cần hạ tầng tương quan — ghi [NGHIÊN CỨU], Phu quyết sau. |
| Macro qua yfinance (DXY/US10Y/VIX/SPX) | Nhóm đã chốt **MT5-only** cho dữ liệu (2026-11-27). `macro_edge` là hàm thuần, nhận snapshot — nguồn live (yfinance hay nhập tay) để Phu quyết. |
| LLM (OpenRouter model free) + KB BM25 từ PDF | Cần API key + tốn phí, không khớp kiến trúc hiện tại (không có LLM trong tool). Không lấy. |
| NY-session gating cho LLM trả phí | Không áp dụng khi không dùng LLM. |

### Từ ThaoResearch

| Tính năng | Lý do không merge |
|---|---|
| GUI Tkinter + PyInstaller build + i18n | Tool quant là CLI; GUI desktop không khớp kiến trúc. |
| Hệ thống license key thương mại | Không liên quan tool nội bộ của nhóm. |
| `scripts/embed_credentials.py` (nhúng token vào .exe) | **Anti-pattern bảo mật** — tác giả tự ghi "obfuscated, not secret". Không lấy. |
| Trích "giá" từ tiêu đề báo qua regex | Không phải giá thật; giá chỉ từ MT5 (Phase A đã chốt MT5-only). |
| Catalog nguyên vẹn (41 mặt hàng nông sản/hàng hóa) | Không liên quan 4 desk DiamondX; chỉ lấy pattern + URL feed đã kiểm chứng, viết lại catalog cho 4 desk. |
| Cơ chế Telegram token của repo gốc (`.env` + `TELEGRAM_BOT_TOKEN`) | Tool dùng bot Telegram DiamondX10 sẵn có của Kathy (helper riêng); không copy cơ chế token. |
| Scheduler APScheduler (3 phút giờ làm việc / 10 phút tối / 30 phút cuối tuần) | Chưa nối vào Phase D (live loop + Telegram alerts); chu kỳ chạy tin hiện là thủ công trước phiên — ghi vào `docs/market-news.md`. |

## 4. Điểm khác biệt có chủ ý so với code gốc (đã ghi trong code/docs)

1. **MacroEdge nhân −1 cho VIX:** bản gốc đảo dấu edge vàng so với
   chính bảng tương quan của nó (VIX lên → vàng lên, +0,40). Merge bỏ
   phép nhân −1, edge = độ lệch chuẩn hóa × tương quan kỳ vọng.
2. **VaR dùng `abs()`:** bản gốc trả VaR dương ngay cả khi lịch sử
   toàn lãi. Merge trả 0 khi không có lỗ (VaR là mức lỗ, không có lỗ
   thì bằng 0).
3. **Walk-forward viết lại:** không copy engine gốc (lot cố định,
   SL từ biên độ bar, P&L ×100000). Chạy trên `_run_segment` của tool
   (sizing theo risk, SL/TP ATR, phí + trượt giá như backtest thường).
4. **Donchian bỏ xác nhận khối lượng + retest:** bar của tool không có
   volume; retest ở bản gốc mặc định tắt. Lọc ATR/gia < 0,3% của bản
   gốc (giảm điểm còn 0,5) chuyển thành HOLD.
5. **Regime chỉ là bối cảnh:** bản gốc dùng regime để nhân hệ số
   (×0,2/×0,5) vào điểm chiến lược; merge không nhân gì vào tín hiệu —
   regime chỉ in kèm. Dùng để chặn/giảm lệnh cần Phu duyệt.
6. **Tin tức thêm phân tầng độ tin cậy:** repo gốc không có; merge
   thêm tier 1/2/3 theo quy tắc nhóm (tin rò rỉ = CHƯA XÁC MINH).

## 5. ⚠️ CẢNH BÁO SECRET — repo DiamondX10 cũ chứa credential thật

**Không copy, không merge, chỉ báo cáo.** Trong repo DiamondX10 cũ có
credential MT5 thật đã commit vào git:

- `config.yaml`: login + **password** + server MT5 — **server là Real,
  không phải Demo**.
- `Document/Overview.txt`: mục "Secrets" + §5.1/5.2/5.4 — login +
  password + server MT5 (login khác với trong `config.yaml`), OpenRouter
  API key, Telegram bot token (lặp lại nhiều lần).
- `README.md`: khối `.env` ví dụ có login MT5 (server Demo/Trial)
  trông như số thật.
- `telegram_setup.py`: đọc token từ `.env` nhưng **in token ra console**.

Đề nghị Phu: **đổi mật khẩu MT5 + thu hồi OpenRouter key + thu hồi
Telegram token đó** (vì đã commit công khai trong lịch sử git của repo
đó — xóa file ở HEAD không xóa được lịch sử). Tool DiamondX10Trading
không dùng bất kỳ credential nào trong số đó.

## 6. Cần Phu quyết

1. **Risk 2% / SL 2,0×ATR / TP 3,0×ATR / DD 15%** (repo cũ) vs quy tắc
   đã chốt (risk 1% + bảng theo symbol, SL 1,5×, TP 2×SL, DD quỹ 10% +
   cảnh báo desk 5%) — có đổi không?
2. **EMA 12/26 hoặc 20/50 + RSI 30/70** (repo cũ) vs SMA5/20 + RSI
   50–70/30–50 đã chốt — có đổi không?
3. **Chốt lời từng phần TP1/TP2** vs TP duy nhất 2×SL hiện tại.
4. **Kelly 25% + risk parity** vs bảng rủi ro cố định theo symbol.
5. **Donchian breakout dùng live không** — cần bằng chứng walk-forward
   trên dữ liệu thật (MT5) trước.
6. **Dùng regime ADX để chặn/giảm lệnh không** — hiện chỉ là bối cảnh.
7. **Nguồn dữ liệu vĩ mô live cho macro edge:** yfinance (repo cũ
   dùng) hay Yuling nhập tay snapshot — nhóm đã chốt MT5-only cho
   dữ liệu giá, nhưng vĩ mô không có trên MT5.
8. **Pairs trading** (rule R_STR_004) — có làm không, cần hạ tầng
   tương quan.
9. **Secret ở mục 5:** đổi mật khẩu MT5 + thu hồi key/token đã commit
   trong repo DiamondX10 cũ.
10. **Nhịp chạy tin + gửi Telegram tự động** (Phase D): hiện `news`
    chạy tay trước phiên; có nối vào live loop + gửi cảnh báo qua bot
    Telegram của Kathy không?

## 7. Kiểm chứng

```bash
cd ~/workspace/diamondx-repos/DiamondX10Trading
PYTHONPATH=src /tmp/dx-venv/bin/python -m pytest tests/ -q
# 156 passed (106 cũ + 50 mới), 0.46s
PYTHONPATH=src /tmp/dx-venv/bin/python -m diamondx10 backtest --desk forex --days 30 --walk-forward
PYTHONPATH=src /tmp/dx-venv/bin/python -m diamondx10 backtest --desk xauusd --days 30 --strategy donchian
PYTHONPATH=src /tmp/dx-venv/bin/python -m diamondx10 signals --desk forex   # co khoa "regime"
PYTHONPATH=src /tmp/dx-venv/bin/python -m diamondx10 news --desk xauusd    # can mang (feed RSS that)
```

Lưu ý: `news` với feed thật cần mạng; test dùng fetcher giả nên
không cần mạng. Backtest/walk-forward trên dữ liệu mô phỏng — kết quả
0 lệnh trên 30–50 bar là bình thường (random walk ngắn), chỉ dùng để
kiểm tra logic, không phải hiệu suất thật.
