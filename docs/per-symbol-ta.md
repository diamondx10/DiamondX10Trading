# Tham so TA rieng theo symbol + mo hinh quy tac cung / quy tac mem

> Tai lieu cho bang `strategy.per_symbol` va danh sach
> `strategy.soft_rules` trong `config.example.yaml`
> (xem `docs/trading-principles.md` muc 61–62).
> Trang thai: **[ĐÃ CÓ — 2026-11-27]**.
>
> Quy tac goc khong doi: ca 4 desk dung chung mot quy tac tin hieu
> (giao cat SMA + loc RSI + SL/TP theo ATR, muc 4). Nhung gi o day
> chi **tinh chinh con so** cho tung symbol (vd he so ATR, nguong
> RSI, gate ADX) va **them quy tac mem** (block / require / scale)
> — khong thay loai tin hieu, khong them chien luoc moi, khong doi
> quy tac rui ro.
>
> Quy uoc ngon ngu trong file nay: van viet tieng Viet co dau;
> ten khoa config / ten rule / ten condition viet **khong dau**,
> dung nhu trong code va file YAML.

## 1. Tom tat nghien cuu theo lop

### EURUSD (Forex — Yuling)

EURUSD la cap tien te bien dong thap nhat trong danh muc, chay theo
phien London / New York va theo chenh lech lai suat Fed–ECB. Vi
bien dong thap nen giao cat nhanh SMA5/20 tao nhieu tin hieu gia
(whipsaw) tren M15; ban nay dung giao cat cham hon (8/21) + gate
ADX >= 20 de chi giao dich khi co xu huong that. Loc theo phien
giao dich **chua co trong code** (xem muc 3.4): neu can cam mo
lenh ngoai phien thi dung co che cung `no_trade_events`, khong
dung soft rule.

### XAUUSD (Vang — Yumi)

Vang bien dong gap 2–3 lan Forex, chay manh theo phien My, theo
lai suat thuc USD va dong USD. Stop phai rong (2,0 x ATR), TP
ngan lai (1,5 x) vi vang dao chieu nhanh sau khi chay manh. RSI
khong dung khung 70/30 co dien: cua BUY 55–75 / SELL 25–45 lay
duong 50 lam truc dong luong (RSI vuot 55 moi mua, thay vi doi
qua ban 30), va nguong cuc doan 85/15 thay cho 80/20 de khong
dung lenh nguoc xu huong vang dang chay. Gate ADX manh nhat danh
muc (30+): khong co xu huong manh thi dung ngoai.

### Crypto — BTCUSD / ETHUSD / BNBUSD (Rich)

Crypto chay 24/7, khong co phien dong/mo cua, bien dong lon va
xu huong keo dai theo dong tien vi mo (BTC) va he sinh thai
(ETH/BNB). Day la lop duy nhat **bat gate ADX theo mac dinh
cua bang** (BTC/ETH 25, BNB 20): mo hinh dong luong 9/21 + RSI
+ ADX la mo hinh M15 da cong bo cho crypto, khong phai phat
minh cua dx10. ETH bien dong theo gio cao hon BTC nen TP ngan
hon (1,5 x) va loc ATR% cao hon (0,0015); BNB it ben xu huong
hon BTC nen dung giao cat cham 10/30, stop chuan.

### Chung khoan My — AMD / CDNS / SNPS / INTC / NVDA (Kathy)

Chung khoan My chi chay trong phien My va nhay manh quanh bao
cao thu nhap (earnings) — earnings blackout la bat buoc va van
dung co che cung `no_trade_events` do Kathy bo sung lich (khong
phai soft rule). Trong bang: NVDA va AMD la 2 ma momentum beta
cao (cua RSI rong 55–75, stop/trail rong, ADX 20–25); INTC
nguoc lai — co xu huong yeu, de dao chieu ve trung binh nen
dung giao cat cham nhat, cua RSI hep nhat (chi mua duoi 65,
chi ban tren 35), TP ngan nhat; CDNS va SNPS **giu nguyen
mac dinh chung** vi chua co co so tach rieng.

## 2. Bang tham so day du

Thu tu uu tien khi resolve (xem `strategies/registry.py`
`resolve_strategy_params`): **mac dinh da chot < tham so chung
< ghi de cua lop theo desk < ghi de desk trong config
< ghi de symbol trong config**. Chi nhung truong khac mac
dinh chung moi liet ke; con lai thua huong mac dinh.

Mac dinh chung (khong ghi de): SMA 5/20, RSI(14) BUY 50–70 /
SELL 30–50, cuc doan 80/20, `atr_sl_mult` 1,5, `tp_mult` 2,0,
`trail_mult` 1,5, `adx_min` 0 (gate TAT), `min_atr_pct` 0,0
(gate TAT). Ghi de desk duy nhat: crypto `atr_sl_mult` 2,0,
`trail_mult` 2,0.

| Symbol | SMA fast/slow | RSI BUY / SELL | RSI cuc doan | atr_sl / tp / trail | adx_min | min_atr_pct | Ly do (1 dong) |
|---|---|---|---|---|---|---|---|
| EURUSD | 8 / 21 | 50–70 / 30–50 (chung) | 80 / 20 (chung) | 1,5 / 2,0 / 1,5 (chung) | 20 | 0,0001 | Giao cat cham + ADX >= 20 cat whipsaw M15 tren cap bien dong thap nhat; con lai = mac dinh chung. |
| XAUUSD | 10 / 30 | 55–75 / 25–45 | 85 / 15 | 2,0 / 1,5 / 2,0 | 30 | 0,0003 | Xu huong cham nhat + stop/RSI rong nhat cho bien dong gap 2–3 lan Forex; 85/15 chan fading xu huong vang. |
| BTCUSD | 9 / 21 | 55–75 / 25–45 | 85 / 15 | 2,0 / 2,0 / 2,0 | 25 | 0,0010 | Dong luong nhanh 9/21 + ADX >= 25 la mo hinh M15 crypto da cong bo; 2,0 x ATR chiu duoc spike 24/7. |
| ETHUSD | 9 / 21 | 55–75 / 25–45 | 85 / 15 | 2,0 / 1,5 / 2,0 | 25 | 0,0015 | Giong BTC nhung bien dong theo gio cao hon nen TP ngan hon (1,5 x) va loc ATR% cao hon. |
| BNBUSD | 10 / 30 | 50–70 / 30–50 (chung) | 80 / 20 (chung) | 2,0 / 2,0 / 2,0 (desk crypto) | 20 | 0,0010 | Bien dong gan BTC nhung it ben xu huong hon nen giao cat cham 10/30, stop chuan. |
| AMD | 8 / 21 | 55–75 / 25–45 | 85 / 15 | 1,5 / 2,0 / 1,5 (chung) | 20 | 0,0020 | Momentum beta cao: cua RSI rong de lenh thang chay; 1,5 x ATR giu stop trong phien. |
| NVDA | 9 / 21 | 55–75 / 25–45 | 85 / 15 | 2,0 / 2,0 / 2,0 | 25 | 0,0020 | Beta cao nhat: stop/trail rong nhat + gate ADX manh nhat; earnings blackout bat buoc. |
| INTC | 10 / 30 | mua duoi 65 / ban tren 35 | 80 / 20 (chung) | 2,0 / 1,5 / 2,0 | 20 | 0,0015 | De dao chieu ve trung binh / xu huong yeu: giao cat cham nhat, cua RSI hep nhat, TP ngan nhat, trail rong nhat. |
| CDNS | 5 / 20 (chung) | 50–70 / 30–50 (chung) | 80 / 20 (chung) | 1,5 / 2,0 / 1,5 (chung) | 0 (tat) | 0,0 (tat) | Khong ghi de — giu mac dinh chung. |
| SNPS | 5 / 20 (chung) | 50–70 / 30–50 (chung) | 80 / 20 (chung) | 1,5 / 2,0 / 1,5 (chung) | 0 (tat) | 0,0 (tat) | Khong ghi de — giu mac dinh chung. |

Hai gate theo tham so (`strategies/base.py`, ap truoc khi tra
BUY/SELL, cho ca 4 desk):

- `adx_min` > 0: ADX(14) < `adx_min` → HOLD ("khong du xu huong").
  ADX khong tinh duoc (chua du bar) thi gate cho qua — khong doan
  mo tren du lieu thieu.
- `min_atr_pct` > 0: ATR(14)/gia < `min_atr_pct` → HOLD ("bien dong
  qua thap"). Gia tri 0 / 0,0 nghia la gate TAT (hanh vi cu).

## 3. Mo hinh quy tac cung / quy tac mem

### 3.1 Quy tac cung (hard rules) — KHONG BAO GIO ghi de tu muc `strategy:`

Cac khoa sau, o **bat ky cap nao** duoi `strategy:`, deu bi chan
(`strategies/soft_rules.py` `HARD_RULE_KEYS`,
`check_hard_rule_keys`):

- **Rui ro / von / drawdown** (`risk:`): `risk`,
  `risk_per_symbol_pct`, `per_symbol_pct`,
  `max_risk_per_trade_pct`, `max_drawdown_pct`, `desk_warning_pct`,
  `fund_daily_loss_pct`, `max_open_positions_fund`,
  `max_open_positions_desk`, `default_stop_loss_pct`,
  `default_take_profit_pct`.
- **Kill switch / demo-only / gioi han lenh**: `kill_switch`,
  `demo_only`, `max_daily_trades`, `daily_trade_limit`,
  `max_trades_per_day`, `max_trades_per_symbol_per_day`.
- **Cua so cam giao dich**: `no_trade_events`.
- **PTCB / tong hop Yuling** (`synthesis:`): `synthesis`,
  `require_fa`, `verdict_max_age_hours`, `fa_high_confidence`.
- **Lenh cho Telegram** (`telegram:` / `trading:`): `telegram`,
  `pending_order_ttl_min`, `max_entry_deviation_pct`,
  `require_confirmation`, `chat_id`, `bot_token_env`.
- **Ten cac muc cap cao khac** (khong bao gio la tham so strategy):
  `fund`, `live`, `mt5`, `news`, `backtest`, `history`, `muse`,
  `data`.

Doi cac so nay chi duoc o muc goc cua no (`risk:` /
`synthesis:` / `telegram:` / `mt5:` / `no_trade_events:`...)
va chi khi Phu duyet. Gap khoa cung trong `strategy:` thi
`ValueError` neu ro ten khoa — khong bao gio lang le bo qua
hay lang le ap dung. Kiem tra chay o duong resolve
(`resolve_strategy_params` / `resolve_soft_rules`) **va**
luc `load_config`.

### 3.2 Quy tac mem (soft rules) — duoc phep lam gi

Mot soft rule chi duoc lam 1 trong 3 viec, tren tin hieu BUY/SELL
(HOLD truyen vao thi tra nguyen — soft rule khong tao lenh):

| Effect | Dieu kien dung | Dieu kien sai |
|---|---|---|
| `block` | BUY/SELL → HOLD, ly do neu ten rule | Khong doi gi |
| `require` | Khong doi gi | BUY/SELL → HOLD, ly do neu ten rule |
| `{type: scale, factor: x}` (0 < x ≤ 1) | Size nhan voi `factor` (chi giam) | Khong doi gi |

Danh gia o 1 diem duy nhat: `Strategy.signal()` qua
`Strategy._apply_soft_rules()` (Donchian dung chung helper).
Rule block dau tien chan se thang, cac rule sau khong danh
gia nua; nhieu rule scale thi factor nhan don (van ≤ 1,0).
Size sau scale nam trong `levels["size_scale"]`; live nhan
volume theo do (lam tron xuong buoc 0,01 lot); backtest nhan
units theo do. Moi duong (live, backtest, compare/sweep,
signals) deu di qua `build_strategy` /
`build_strategy_for_symbol` nen deu thay soft rule.

### 3.3 Quy tac mem KHONG BAO GIO duoc lam

- **Tang size** vuot size cung da tinh (`factor` > 1 bi tu choi
  luc validate; scale chi duoc giam).
- **Doi % rui ro, SL/TP, hay bat ky khoa cung nao** (muc 3.1) —
  ke ca viet khoa cung **ben trong** 1 soft rule cung bi chan.
- **Bo qua bat ky gate cung nao**: drawdown, kill switch, gioi
  han quy, 1 lenh/symbol/ngay, cua so cam giao dich, mau thuan
  PTCB manh, kiem tra ky quy, chan demo-only. Soft rule chi
  chay **sau** khi tin hieu da vuot qua cac gate do o duong
  signal, va truoc khi dat lenh thi cac gate live van chay
  day du.
- **Tao lenh vao** khi PTKT la HOLD — giong quy tac 40 (PTCB
  mot minh khong tao lenh), soft rule cung vay.
- **Ap dung ngoai scope** cua no (`scope` khong khop thi rule
  bi loai luc resolve, khong phai luc danh gia).

### 3.4 Dieu kien cua so thoi gian / phien KHONG co o v1

Bar `time` o du lieu mo phong chi la chi so 0..N (khong phai
epoch), con o MT5 la epoch UTC — khong co moc thoi gian dang
tin cay chung de danh gia phien London / New York trong duong
signal. Vi vay v1 khong co condition kieu phien / gio. Loc
phien / earnings blackout van dung co che cung san co:
`no_trade_events` (xem `config.example.yaml`).

## 4. Schema `soft_rules` + vi du + cach them rule moi

### 4.1 Schema day du

```yaml
strategy:
  soft_rules:
    - name: <ten duy nhat, bat buoc>
      scope: {desk: forex|xauusd|crypto|us_securities}  # tuy chon
      #   hoac {symbol: EURUSD|XAUUSD|BTCUSD|ETHUSD|BNBUSD|
      #                 AMD|CDNS|SNPS|INTC|NVDA}
      #   bo qua scope = ap cho moi symbol; chi duoc 1 trong 2
      condition: {type: <loai>, ...}   # xem bang duoi
      effect: block                    # hoac require
      #   hoac {type: scale, factor: 0.5}   # 0 < factor <= 1
```

Bang condition (v1) — tat ca tinh tu chi bao trong duong signal:

| `type` | Tham so | Khoang hop le | Nghia (True khi...) |
|---|---|---|---|
| `rsi_range` | `low`, `high` | 0–100, `low` < `high` | RSI(14) trong `[low, high]` |
| `sma_cross` | `direction: bullish` \| `bearish` | — | SMA fast > slow (bullish) / < slow (bearish) |
| `adx_min` | `value` | 0–100 | ADX(14) >= `value` |
| `adx_max` | `value` | 0–100 | ADX(14) <= `value` |
| `atr_pct_min` | `value` | 0 < `value` ≤ 0,05 | ATR(14)/gia >= `value` |
| `atr_pct_max` | `value` | 0 < `value` ≤ 0,05 | ATR(14)/gia <= `value` |
| `pattern` | `name` | xem duoi | Mau hinh `name` xuat hien trong bars |

Ten `pattern` chap nhan: `doji`, `bullish_engulfing`,
`bearish_engulfing`, `hammer`, `shooting_star`, `morning_star`,
`evening_star`, `resistance`, `support`, `double_top`,
`double_bottom`, `breakout_up`, `breakout_down`
(xem `patterns.py` `detect_patterns`).

Chi bao khong tinh duoc (VD ADX khi chua du bar) thi condition
ve chi bao do = False — khong bao gio doan mo.

### 4.2 Vi du copy-paste duoc (3 rule mau trong `config.example.yaml`)

```yaml
strategy:
  soft_rules:
    # XAUUSD: bien dong dot bien — ATR% vuot 0.5% thi khong mo lenh moi.
    - {name: xauusd-vol-spike-block, scope: {symbol: XAUUSD},
       condition: {type: atr_pct_min, value: 0.005}, effect: block}
    # Crypto: xu huong yeu (ADX <= 25) thi giam mot nua size.
    - {name: crypto-adx-weak-scale, scope: {desk: crypto},
       condition: {type: adx_max, value: 25},
       effect: {type: scale, factor: 0.5}}
    # EURUSD: khong co xu huong (ADX <= 20) thi khong vao lenh trend.
    - {name: eurusd-weak-trend-block, scope: {symbol: EURUSD},
       condition: {type: adx_max, value: 20}, effect: block}
```

Bo comment (`#`) o 3 dong tren trong `config.example.yaml`
de dung; chep nguyen khoi nay sang `config.yaml` local cung
duoc. Ca 3 rule da co test chay dung nhu viet
(`tests/test_soft_rules.py`,
`tests/test_soft_rules_integration.py`).

### 4.3 Cach them rule moi cua ban (5 buoc)

1. **Chon scope**: bo qua (moi symbol), `{desk: ...}` (ca
   desk), hay `{symbol: ...}` (1 ma). Rule cang hep cang de
   ly giai sau nay.
2. **Chon condition** trong bang muc 4.1. Chi dung nhung gi
   co trong bang — khong co condition gio/phien o v1 (muc 3.4).
3. **Chon effect**: `block` (chan han khi dieu kien dung),
   `require` (chi cho phep khi dieu kien dung), hay
   `scale` giam size (VD `factor: 0.5`). Khong co cach nao
   tang size bang soft rule.
4. **Dat ten duy nhat, noi ro y do** (VD
   `nvda-earnings-week-scale`) — ten rule xuat hien trong ly
   do HOLD / log nen ten tot la tai lieu song.
5. **Kiem tra truoc khi chay live**: chay
   `PYTHONPATH=src python -m pytest tests/test_soft_rules.py
   tests/test_soft_rules_integration.py -q` (neu them rule
   vao test thi cang tot), roi chay `backtest --strategy
   default` / `compare_strategies` tren du lieu that xem
   rule doi bao nhieu lenh truoc khi cho no cham vao vong
   live.

### 4.4 Rule go sai bao loi LOUD — khong lang le bo qua

`validate_soft_rules` (goi o moi duong resolve) raise
`ValueError` neu ro ten rule + khoa loi khi gap bat ky loi
nao sau: khong phai list / rule khong phai dict, khoa khong
biet trong rule / condition / effect, thieu `name` /
`condition` / `effect`, trung ten, scope sai (ca desk +
symbol, desk/symbol khong biet), condition sai type / sai
khoa / vuot khoang / `low` >= `high` / `direction` la /
pattern khong biet, effect la / `scale` thieu `factor` /
`factor` ngoai (0, 1], khoa cung (muc 3.1) lan trong rule.
Loi no ra luc resolve — tuc la ngay khi tin hieu / live /
backtest dau tien doc config do, khong phai luc lenh that
da dat. **Ngoai le can biet:** `load_config()` mot minh
chi kiem tra quy tac cung; soft rule go sai van doc duoc
file, loi chi no khi resolve (xem test
`test_invalid_soft_rule_yaml_fails_loud_at_resolve`).
Rule hop le nhung scope khong khop symbol thi chi don gian
khong ap dung — do khong phai loi.

## 5. Ghi chu kiem chung trung thuc (honest limit)

Bang muc 2 va mo hinh muc 3 la **diem xuat phat theo tai
lieu / thuc hanh, KHONG phai bang chung sinh loi**:

- Nguong `min_atr_pct` va gate ADX lay tu khoang dien hinh
  da cong bo (nguon muc 6), **chua kiem chung tren chinh
  symbol cua dx10**.
- Kiem chung that can: backfill MT5 tren Windows + walk-forward
  `compare` / `sweep` xep hang OOS (chi tinh doan test),
  **~50–100 lenh / symbol** moi co y nghia thong ke; it lenh
  hon thi chi doc nhu goi y, khong phai ket luan.
- **Neu walk-forward cho thay mac dinh chung thang ghi de
  rieng symbol thi GIU MAC DINH.** Ghi de chi ton tai khi
  bang chung OOS ung ho no; khong giu ghi de vi "nghe hop ly".
- Du lieu mo phong theo desk (moi symbol cung chuoi gia)
  chi dung de kiem tra logic (rule co chay, size co giam,
  lenh co bi chan) — khong phai bang chung hieu suat that.

## 6. Nguon

- MQL5 London Breakout Pro https://www.mql5.com/ja/market/product/147093
- Pro-Scalper XAUUSD https://www.pro-scalper.com/questions/which-is-the-best-indicator-for-xauusd
- Camovia gold https://www.camovia.com/en/blog/best-indicator-for-gold-trading/
- Capital.com ADX https://capital.com/en-int/learn/technical-analysis/average-directional-index
- ForexBite ATR https://www.forexbite.com/learn/risk-management/average-true-range/
- Arconomy BTCUSD M15 https://arconomy.app/blog/2026-03-16-btcusd-stoch-rsi-multi-indicator
- TradingView EMA 9/21 + RSI + ADX https://www.tradingview.com/script/MH4CUy8g/
- AlertaChart BTC timing https://www.alertachart.com/best-time-to-trade-bitcoin
- TradePiko earnings https://www.tradepiko.com/blog/trading-around-earnings
- American Dream Trading ORB https://www.americandreamtrading.com/blog/opening-range-breakout/

## 7. File lien quan

- `config.example.yaml` — muc `strategy:` (bang `per_symbol`,
  3 rule vi du comment, ghi chu HONEST LIMIT).
- `src/diamondx10/strategies/soft_rules.py` — `HARD_RULE_KEYS`,
  `check_hard_rule_keys`, `validate_soft_rules`,
  `resolve_soft_rules`, `evaluate_condition`,
  `apply_soft_rules`.
- `src/diamondx10/strategies/registry.py` —
  `resolve_strategy_params` (thu tu uu tien),
  `build_strategy_for_symbol`.
- `src/diamondx10/strategies/base.py` — `Strategy.signal`,
  gate `adx_min` / `min_atr_pct`, `_apply_soft_rules`.
- `src/diamondx10/signals.py` — `generate_signals`
  (them `size_scale`, `params` khi co symbol).
- `src/diamondx10/live.py` — `process_symbol` (volume nhan
  `size_scale`, lam tron xuong buoc 0,01 lot; volume truyen
  tay khong bi scale).
- `src/diamondx10/backtest.py` — `run_backtest` (trade co
  `size_scale`, units nhan `size_scale`), `compare_strategies`,
  `sweep_params` (chi xep hang theo OOS).
- `docs/strategy-engine.md` — registry, per-symbol, walk-forward
  + so sanh + sweep, canh bao overfitting.
- `docs/trading-principles.md` muc 4, 30, 61, 62.
- `docs/multi-timeframe-ta.md` — loc xu huong H1 tai su dung tham
  so per-symbol da resolve (SMA/ADX) cho tung symbol (muc 64).
- `tests/test_soft_rules.py`, `tests/test_soft_rules_integration.py`.
