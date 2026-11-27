# Rui ro danh muc DiamondX10 — VaR tuong quan, Monte Carlo, stress test

> Quy tac goc: xem `docs/trading-principles.md` muc 66.
> Trang thai: **[ĐÃ CÓ — 2026-11-28]** (code: `portfolio_risk.py`,
> lenh `portfolio-risk`, muc `portfolio_risk` trong `report.py`,
> endpoint `GET /api/portfolio-risk` trong `webapi.py`).
>
> Quy uoc ngon ngu trong file nay: van viet tieng Viet co dau;
> ten khoa config / ten ham / ten symbol viet **khong dau**,
> dung nhu trong code va file YAML.
>
> Y chung: VaR danh muc tra loi cau hoi "neu thi truong xau di
> trong 1 ngay toi, danh muc dang mo co the lo bao nhieu" — co tinh
> den viec cac symbol chay cung nhau hay nguoc nhau (tuong quan),
> chu khong cong don rui ro tung symbol mot cach mu quang nhu
> truoc day (muc 25 chi co VaR lich su cua tung backtest rieng le).

```
vi the mo (equity-state.json / --demo)      kho lich su M15
  notional co dau theo symbol       ---->   log return chung timestamp
        |                                          |
        v                                          v
  weights USD (w)                       ma tran hiep phuong sai (n-1)
        |                                          |
        +-------> VaR tham so (z*sigma) <-----------+
        |       VaR lich su (phan vi P&L)
        +-------> Monte Carlo (Cholesky, sqrt(96)/ngay)
        |       Component VaR (Euler)
        +-------> Stress: shock % x notional co dau
        |
        v
  bao cao (CLI / report ngay / web UI) — CHI BAO CAO + CANH BAO,
  KHONG BAO GIO chan lenh (chan lenh van theo drawdown/kill switch)
```

## 1. Dau vao — vi the, gia, lich su

- **Vi the mo:** mac dinh doc `decisions/equity-state.json` giong
  `report.build_report` (vi the + equity hien tai tu
  `guard.fund_curve[-1]`); lenh `portfolio-risk` khong co tham so
  vi the, code goi truc tiep co the truyen `positions=[...]` (list
  dict `{desk, symbol, direction, volume, contract_size, ...}` nhu
  trong equity state). Vi the co symbol la thi bo qua kem warning,
  khong crash bao cao.
- **Notional:** `notional = volume (lot) x contract_size x gia`,
  theo dung quy uoc repo (muc 10): forex 100000, XAUUSD 100,
  crypto 1, chung khoan My 1. `signed_notional` mang dau huong:
  BUY +, SELL -. Gia lay tu tham so `prices` neu co, khong thi gia
  dong moi nhat trong kho lich su; khong co gia thi bo symbol do
  kem warning.
- **Equity:** von quy hien tai (mac dinh `fund.total_capital_usd`
  = 10000 neu chua co state). Gioi han VaR tinh tren equity nay.
- **Lich su gia:** log return M15 (`ln(close_t / close_{t-1})`) doc
  tu `HistoryStore` (`data/history.db`), **chi tren timestamp chung
  cua moi symbol** (inner-join): symbol nao thieu bar o 1 moc thi
  moc do bi loai khoi toan bo danh muc, khong noi return gia tao.
  Can it nhat 2 ky chung moi tinh duoc VaR; it hon thi cac muc VaR
  la `None` kem warning "khong co du lich su gia chung" (stress van
  tinh duoc vi khong can lich su).
- **Che do demo (`--demo`):** lap danh muc gia 10 symbol can deu,
  moi symbol `equity / 10` USD notional, tat ca BUY, gia lay tu kho
  (thieu gia thi bo symbol do). Dung de xem thu dinh dang bao cao
  khi chua co vi the mo that — con so demo KHONG phai rui ro that.

## 2. Toan hoc — 3 cach tinh VaR + component + stress

Dat `w` la vector notional co dau (USD) theo symbol, `Sigma` la ma
tran hiep phuong sai mau (chia `n-1`, cat theo chuoi ngan nhat) cua
log return M15, `sigma_p = sqrt(w' Sigma w)` la do lech chuan P&L
danh muc theo ky M15. Ca 3 cach tinh VaR deu quy ve **chan 1 ngay**
(mac dinh `mc_horizon_days = 1`): nhan voi `sqrt(96 * horizon_days)`
— 96 nen M15/ngay. Xem muc 7 ve xap xi nay.

### 2.1 VaR tham so (parametric) — gia dinh chuan

```
VaR_95  = z_95  * sigma_p  = 1.645 * sigma_p
CVaR_95 = phi(z_95) / 0.05 * sigma_p   (phi = mat do chuan)
VaR_99  = 2.33 * sigma_p
```

Chi dung 2 con so tong hop (`sigma_p`, `z`) nen tinh nhanh va on
dinh, nhung gia dinh return chuan — duoi phan phoi that day hon
chuan (xem muc 7). CVaR (expected shortfall) la muc lo trung binh
**khi da vuot VaR**, nghia la no mo ta duoi phan phoi ma VaR khong
thay: `CVaR >= VaR` luon dung.

Vi du tinh tay (test `test_parametric_var_two_assets_hand_computed`):
notional EURUSD 6000, XAUUSD 4000; sigma1 = 0.02, sigma2 = 0.03,
rho = 0.5 -> cov12 = 0.0003. `w' Sigma w` = 14400 + 14400 + 14400
= 43200 -> sigma_p = 207.85 USD/ky -> VaR95 = 341.91 USD/ky
(chua scale ngay), CVaR95 = 428.62 USD/ky.

### 2.2 VaR lich su (historical simulation) — khong gia dinh chuan

Lap chuoi P&L danh muc theo tung ky lich su: `P&L_t = sum_s w_s *
r_{s,t}` (return that cua tung symbol nhan notional co dau), roi lay
phan vi 5% (noi suy tuyen tinh, giong `risk.value_at_risk`) lam VaR
va trung binh cac ky te hon VaR lam CVaR (giong
`risk.expected_shortfall`). Khong can gia dinh chuan, nhung chi
thay duoc nhung gi lich su da xay ra — cu soc chua tung co thi
khong co trong so lieu.

Vi du tinh tay (test `test_historical_var_tiny_fixed_list`): 20 ky
-0.10 ... -0.01, 0.01 ... 0.10. Phan vi 5% noi suy: rank 0.95 ->
-0.10*0.05 + -0.09*0.95 = -0.0905 -> VaR95 = 0.0905; CVaR95 =
trung binh cac lo <= -0.0905 -> chi -0.10 -> 0.10.

### 2.3 Monte Carlo — Cholesky + scale sqrt(96)/ngay

```
Sigma_ngay = Sigma_M15 * (96 * horizon_days)
L = cholesky(Sigma_ngay);  z ~ N(0, I)
P&L_path = w' (L z)          (moi path = 1 ngay gia dinh)
VaR_95  = -phan vi 5% cua P&L;  CVaR_95 = trung binh P&L <= -VaR_95
```

Phan tich Cholesky bien cac bien chuan doc lap thanh return tuong
quan dung nhu ma tran hiep phuong sai — day la cho tuong quan di
vao MC. So path mac dinh 10000 (`mc_paths`, toi thieu 100), seed
mac dinh 42 (`DEFAULT_MC_SEED`) nen cung cau hinh + cung lich su
thi ket qua lap lai giong het nhau (test tai lap seed). Bao cao them
`mean_pnl`, `sd_pnl`, `p5/p50/p95` va `prob_breach_drawdown_pct` =
ti le path co lo >= gioi han drawdown quy (10% von, muc 12).

### 2.4 Component VaR — ai dong gop bao nhieu (Euler)

```
component_i = w_i * VaR * (Sigma w)_i / (w' Sigma w)
```

Phan bo Euler: tong cac component **bang dung** VaR tham so (sai
so lam tron), `share_pct` cho biet tung symbol chiu bao nhieu %
VaR danh muc. Vi dung notional co dau nen 1 vi the SELL co the co
component am (no lam giam VaR danh muc vi nguoc huong voi phan
con lai). Day la muc de Yuling nhin ra "tap trung rui ro dang nam
o dau" thay vi chi biet tong VaR.

### 2.5 Stress test — shock % x notional co dau

```
P&L_scenario = sum_s signed_notional_s * shock_s / 100
pnl_pct = P&L / equity * 100
breaches_drawdown = P&L <= -(10% * equity)
```

Khong can lich su, khong can phan phoi — chi la phep nhan thang.
SELL lai khi gia giam (notional am x shock am = duong). Bao cao
them 1 dong **"Ngay te nhat lich su"**: gop return theo ngay UTC,
lay ngay co P&L danh muc te nhat trong lich su (can du lich su
chung, khong thi chi ghi chu). Gioi han drawdown dung o day la
10% von quy (muc 12), khong phai gioi han VaR 2%.

### 2.6 Gioi han VaR — canh bao, khong chan

```
limit_usd = equity * portfolio_var_limit_pct / 100   (mac dinh 2%)
breached  = VaR tham so / lich su / MC (bat ky) > limit_usd
```

Mac dinh 2% von quy = 200 USD tren von 10000 USD. `breached =
True` chi them warning + note vao bao cao ("VaR vuot gioi han la
CANH BAO bao cao — khong chan lenh") va la dieu kien gui canh bao
Telegram khi chay `portfolio-risk --alert`. Chan lenh van chi theo
drawdown 10% / kill switch / gioi han quy (muc 12, 33–34).

## 3. Cau hinh (`risk:` trong `config.example.yaml`)

```yaml
risk:
  portfolio_var_limit_pct: 2.0   # (0, 100]; VaR 95% vuot muc nay thi breached
  mc_paths: 10000                # >= 100; so path Monte Carlo
  mc_horizon_days: 1             # > 0; chan du bao (ngay) cua VaR/MC
  stress_scenarios:              # shock theo %; vd -30 = -30% gia symbol do
    - {name: "Crypto crash", shocks: {BTCUSD: -30, ETHUSD: -30, BNBUSD: -30}}
    - {name: "Co phieu My crash", shocks: {AMD: -20, NVDA: -20, INTC: -20, CDNS: -20, SNPS: -20}}
    - {name: "Vang tang manh", shocks: {XAUUSD: 10}}
    - {name: "Vang giam manh", shocks: {XAUUSD: -10}}
    - {name: "USD manh len", shocks: {EURUSD: -2}}
    - {name: "Tat ca rui ro giam", shocks: {EURUSD: -10, XAUUSD: -10, BTCUSD: -10, ETHUSD: -10, BNBUSD: -10, AMD: -10, CDNS: -10, SNPS: -10, INTC: -10, NVDA: -10}}
    - {name: "Soc kieu 2020", shocks: {AMD: -30, NVDA: -30, INTC: -30, CDNS: -30, SNPS: -30, BTCUSD: -40, ETHUSD: -40, BNBUSD: -40, XAUUSD: 5, EURUSD: -3}}
```

- Thieu muc `risk.stress_scenarios` trong config thi dung 7 kich
  ban mac dinh giong het tren (`DEFAULT_STRESS_SCENARIOS`).
- `validate_portfolio_risk_config` bao loi LOUD (ValueError) khi
  cau hinh sai: `portfolio_var_limit_pct` ngoai (0, 100],
  `mc_paths` < 100, `mc_horizon_days` <= 0, scenario thieu
  `name`/`shocks` hoac co symbol la.
- Chi 10 symbol duoc chap nhan: EURUSD, XAUUSD, BTCUSD, ETHUSD,
  BNBUSD, AMD, CDNS, SNPS, INTC, NVDA (`KNOWN_SYMBOLS`).

### Them 1 kich ban stress moi

Them 1 muc vao list `risk.stress_scenarios` trong `config.yaml`
local (copy tu `config.example.yaml` roi sua — khong sua truc tiep
`config.example.yaml` tren may live). Vi du — soc rieng cua desk
forex + vang cung luc:

```yaml
risk:
  stress_scenarios:
    - name: "EUR sup + vang giam"
      shocks:
        EURUSD: -5
        XAUUSD: -15
```

Quy tac viet scenario:

- `name` la chuoi khong rong, duy nhat thi de doc (trung ten van
  chay, nhung bao cao kho phan biet).
- `shocks` la dict `{SYMBOL: shock_pct}`, shock am = gia giam.
  Symbol nao khong co trong danh muc 10 symbol thi bao loi LOUD
  luc load — khong bao gio lang le bo qua (loi chinh ta symbol la
  loi nguy hiem: scenario tuong co shock nhung that ra khong).
- Shock tren symbol khong co vi the mo thi P&L = 0 cho symbol do
  (khong bao loi) — scenario van chay binh thuong cho cac symbol
  con lai.
- Dat shock theo bien dong that cua symbol: EURUSD -2% da la soc
  lon (1 ngay), BTCUSD -30% thi co that trong lich su crypto.
  Shock cang lon cang de `breaches_drawdown = True` — do la muc
  dich cua stress test, khong phai loi.

## 4. Chay tren Windows — backfill truoc, roi moi xem VaR

Tren may Windows (MT5 Exness demo mo san, xem `docs/dx10-flow.md`):

```powershell
cd D:\DiamondX\DiamondX10Trading
$env:PYTHONPATH = "src"
```

1. **Backfill lich su truoc** — khong co lich su thi VaR la `None`
   (xem muc 1). Can du dai de ma tran tuong quan co y nghia (muc 7:
   toi thieu 90 ngay):

   ```powershell
   python -m diamondx10 backfill --desk forex --days 90
   python -m diamondx10 backfill --desk xauusd --days 90
   python -m diamondx10 backfill --desk crypto --days 90
   python -m diamondx10 backfill --desk us_securities --days 90
   ```

   Kiem tra kho co bar: `python -m diamondx10 export-bars` hoac
   xem `data/history.db` co bar M15 cho tung symbol dang mo.
2. **Xem bao cao rui ro:**

   ```powershell
   python -m diamondx10 portfolio-risk
   python -m diamondx10 portfolio-risk --demo        # xem thu khi chua co vi the that
   python -m diamondx10 portfolio-risk --mc 2000     # it path hon cho nhanh (toi thieu 100)
   python -m diamondx10 portfolio-risk --alert       # chi gui Telegram khi vuot gioi han
   ```

   Ma thoat 0 tru khi loi cau hinh (tra 1, khong traceback).
   Khong co vi the mo (va khong `--demo`) thi in trang thai rong,
   VaR 0.0, tra 0.
3. **Bao cao ngay** (`report --save`) tu co muc "Rui ro danh muc
   (VaR / Monte Carlo / stress)": VaR 3 cach + gioi han, MC p5 +
   xac suat vuot drawdown, component VaR lon nhat, stress te nhat.
   Khong co vi the thi muc in "khong co vi the mo".
4. **Web UI:** tab Quan ly / `GET /api/portfolio-risk` tra cung
   bao cao dang JSON (khi chua co vi the / lich su thi tra payload
   rong `has_positions: False`, VaR 0.0 — khong bao gio 500).

## 5. Test

```bash
PYTHONPATH=src /tmp/dx-venv/bin/python -m pytest tests/test_portfolio_risk.py -q
```

41 test (stdlib + pytest, khong mang, khong MT5 that): Cholesky
2x2/3x3 tinh tay + ma tran khong xac dinh duong; VaR tham so 2
tai san tinh tay (341.91 / 428.62 USD); VaR lich su tren list 20
gia tri co dinh (0.0905 / 0.10); component VaR cong lai dung VaR
danh muc (ca muc ham lan muc bao cao); tuong quan (duong cheo 1,
doi xung, +-1 hoan hao); log return tu kho (ln(101/100),
inner-join timestamp chung); stress = exposure x shock + co
breach o muc bao cao; khong vi the / thieu lich su thoai hoa; kiem
tra cau hinh (symbol la, mc_paths < 100, limit <= 0); MC cung seed
-> giong het, khac seed -> khac; CLI `--demo` (subprocess +
in-process); muc `portfolio_risk` trong `build_report` (khong vi
the + co vi the).

## 6. File lien quan

- `src/diamondx10/portfolio_risk.py` — `build_portfolio_risk_report`,
  `log_returns_from_store`, `covariance_matrix`,
  `correlation_matrix`, `cholesky`, `parametric_var`,
  `historical_var`, `monte_carlo_var`, `component_var`,
  `apply_stress`, `load_stress_scenarios`,
  `validate_portfolio_risk_config`, `format_portfolio_risk_report`.
- `src/diamondx10/__main__.py` — lenh `portfolio-risk`
  (`cmd_portfolio_risk`, `format_portfolio_risk_alert`) + parser
  `--mc / --horizon-days / --demo / --alert`.
- `src/diamondx10/report.py` — `_portfolio_risk_section` /
  `_format_portfolio_risk_lines` (muc `portfolio_risk` trong
  `build_report` / `format_report`).
- `src/diamondx10/webapi.py` — `GET /api/portfolio-risk`
  (+ `_empty_portfolio_risk_report` khi chua co vi the/lich su).
- `config.example.yaml` — muc `risk:` (`portfolio_var_limit_pct`,
  `mc_paths`, `mc_horizon_days`, `stress_scenarios`).
- `docs/trading-principles.md` muc 66 — quy tac rui ro danh muc.
- `docs/history-store.md` — kho nen OHLC local, backfill (muc 29).
- `docs/fund-risk-ops.md` — gioi han quy / kill switch / bao cao
  ngay (muc 33–35) — cac cong CHAN lenh, khac voi VaR o day.
- `tests/test_portfolio_risk.py` — test muc nay.

## 7. Gioi han that — doc truoc khi tin bat ky con so VaR nao

- **VaR khong phai bao dam.** VaR95 = 200 USD khong co nghia la
  "lo toi da 200 USD". No co nghia la: neu ngay mai giong nhu qua
  khu (cung phan phoi, cung tuong quan) thi co 95% kha nang lo
  khong qua 200 USD — va 5% kha nang lo HON the, co the hon rat
  nhieu. 1 ngay trong 20 ngay giao dich se vuot VaR95 theo dinh
  nghia. Dung VaR de so sanh muc rui ro giua cac ngay, khong dung
  no de dam bao von an toan.
- **CVaR mo ta duoi, VaR thi khong.** Hai danh muc co cung VaR95
  co the co duoi rat khac nhau: mot cai lo vuot VaR thi dung o
  210 USD, cai kia co the lo 2000 USD. Doc CVaR95 kem VaR95 —
  CVaR cang lon so voi VaR thi duoi cang day, cang nguy hiem.
- **Monte Carlo gia dinh return chuan nen danh gia THAP duoi day
  (fat tails), nhat la crypto.** Return that co duoi day hon chuan
  rat nhieu: BTCUSD -30% trong 1 ngay da xay ra, phan phoi chuan
  voi sigma ngay ~5% gan nhu khong bao gio sinh ra so do. MC o day
  chi dung de uoc luong bac do va de so sanh — soc that phai xem o
  stress test (muc 2.5) va VaR lich su (muc 2.2), khong xem o MC.
- **Tuong quan tang vot trong khung hoang.** Ma tran tuong quan
  tinh tu lich su yen binh se noi EURUSD / XAUUSD / BTCUSD gan
  nhu khong lien quan — den luc khung hoang, tat ca cung roi mot
  luc (tuong quan -> 1) va VaR danh muc that se lon hon VaR tinh
  tu tuong quan binh thuong rat nhieu. Do chinh la viec stress
  scenario "Tat ca rui ro giam" / "Soc kieu 2020" ton tai: dung
  chung thay cho viec tin tuong quan lich su.
- **Scale sqrt(96) la xap xi, va no danh gia CAO bien dong ngay
  cua FX/co phieu.** 1 ngay co 96 nen M15 chi dung khi thi truong
  giao dich 24/7 (crypto gan dung). Forex nghi cuoi tuan, co phieu
  My chi giao dich trong phien — nhan sigma M15 voi sqrt(96) se
  thoi phong VaR ngay cua chung. Con so VaR la uoc luong bao cao,
  khong phai du bao bien dong ngay mai.
- **Du lieu gia lap thi moi con so deu vo nghia.** Voi du lieu
  random-walk mo phong, tuong quan giua cac symbol ~0, VaR chi
  phan anh do lech chuan gia tao — khong noi len dieu gi ve rui ro
  that. Can lich su that (backfill it nhat 90 ngay, xem muc 4)
  truoc khi tin bat ky con so nao trong bao cao nay; duoi 90 ngay
  thi ma tran tuong quan chua on dinh va VaR lich su chua thay du
  soc.
- **VaR tinh tren vi the HIEN TAI, khong phai vi the NGAY MAI.**
  Mo them 1 lenh la VaR doi ngay; bao cao nay khong du bao rui ro
  cua lenh sap mo (muon biet thi chay lai sau khi mo lenh). No
  cung khong tinh phi, truot gia, gap gia mo cua hay thanh khoan
  (khong ban duoc) — tat ca deu lam lo that lon hon VaR.
- **Bao cao-only v1, khong chan lenh.** Vuot gioi han VaR chi la
  canh bao de Yuling/Phu xem xet giam vi the bang tay. Khong co
  co che tu dong nao dong lenh hay giam size theo VaR o v1 —
  quyet dinh do van la cua nguoi, theo drawdown/kill switch
  (muc 12, 33–34).
