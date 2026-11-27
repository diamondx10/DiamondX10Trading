# Vong hoc TA DiamondX10 — ghi lai, cham diem, xem xet, de xuat, kiem dinh

Tool khong chi chay tin hieu roi quen: moi khuyen nghi mua/ban duoc
ghi lai kem day du boi canh, cham diem bang gia that chay sau do,
tong ket thanh bai hoc theo tung lat cat, roi moi de xuat tinh chinh
tham so. De xuat KHONG BAO GIO tu ap — Phu duyet tay tung de xuat,
kiem dinh out-of-sample (OOS) truoc khi tin.

Quy tac goc: xem `docs/trading-principles.md` muc 63.

> Trang thai 2026-11-27: ca 3 phan da co trong code (`outcomes.py`,
> `evaluator.py`, `ta_review.py`; lenh `evaluate-signals` /
> `ta-review`) — kiem chung end-to-end bang
> `tests/test_learning_loop_e2e.py` (win + loss + timeout,
> de xuat `validated: false` khi chua co lich su OOS).

```
live / backtest              evaluate-signals              ta-review
  ghi khuyen nghi   ---->      cham diem tu nen   ---->     bai hoc
  + boi canh day du            M15 that sau lenh           + de xuat
  (signal-outcomes             (win / loss /                 (chua du mau
   .jsonl)                      timeout, MFE/MAE)             thi khong de xuat)
        |                            |                            |
        v                            v                            v
  decisions/                   decisions/                   decisions/
  signal-outcomes.jsonl        signal-outcomes-             ta-tuning-proposals-
                               evaluated.jsonl              <YYYYMMDD>.yaml
                                                                     |
                                                              ta-review --apply
                                                              (go chu xac nhan,
                                                               Phu duyet tay)
                                                                     |
                                                                     v
                                                              config.yaml
                                                              (strategy.per_symbol
                                                               / soft_rules)
                                                                     |
                                                              chay lai + so sanh
```

## 1. Buoc 1 — chay live / backtest de ghi lai khuyen nghi

Moi khuyen nghi BUY/SELL vuot qua moi gate va tro thanh TRADED
(lenh demo da dat) hoac RECOMMENDED (lenh cho xac nhan, che do
`--recommend-only`) duoc ghi 1 dong JSON vao
`decisions/signal-outcomes.jsonl` (file runtime, da gitignore).
HOLD khong ghi — khong co lenh thi khong co ket qua de cham diem;
lenh bi chan truoc khi qua het gate cung khong ghi.

```bash
python -m diamondx10 live --once --recommend-only --desk forex
python -m diamondx10 backtest --desk forex --days 30
```

1 ban ghi gom (xem `src/diamondx10/outcomes.py`):

- Dinh danh + lenh: `id`, `created_utc`, `desk`, `symbol`, `action`
  (BUY/SELL), `status` (TRADED / RECOMMENDED / BLOCKED...),
  `entry`, `sl`, `tp`, `volume`, `risk_usd`, `manager`, `time`,
  `size_scale`, `pending_id`.
- Boi canh TA luc ra tin hieu (`context`): `rsi`, `sma_fast`,
  `sma_slow`, `sma_relation`, `atr`, `atr_sl_mult`, `regime`, `adx`,
  `patterns`, `pattern_score`, `strategy_name`, `resolved_params`
  (tham so that da ap sau khi giai per-symbol), `soft_rules` (rule
  mem nao da kich hoat), `fa` (nhan dinh PTCB luc do: huong + do
  tin cay, hoac chua co).
- `params_hash`: ma ham cua bo tham so da dung — de nhom cac lenh
  cung 1 bo tham so lai voi nhau khi so sanh truoc/sau tinh chinh.

Ghi day du boi canh la ca vong hoc dung duoc hay khong: khong co
`context` thi sau nay khong biet lenh thang vi RSI, vi ADX, vi soft
rule hay vi PTCB dong thuan.

## 2. Buoc 2 — cham diem ket qua tu nen M15 that (`evaluate-signals`)

```bash
python -m diamondx10 evaluate-signals
python -m diamondx10 evaluate-signals --window 20 --outcomes decisions/signal-outcomes.jsonl --evaluated decisions/signal-outcomes-evaluated.jsonl
```

Lenh doc `decisions/signal-outcomes.jsonl`, lay nen M15 that sau
thoi diem vao lenh TU KHO LICH SU (`HistoryStore`,
`data/history.db` — chay `backfill` truoc de co bar; khong bao
gio goi MT5 live o day, symbol nao chua co bar thi ban ghi do bi
bo qua va dem vao `skipped_no_bars`), cham tung ban ghi trong
cua so `learning.outcome_window_bars` nen (mac dinh 20 nen M15
= 5 gio, xem muc 5; `--window` ghi de config), roi ghi them ket
qua vao `decisions/signal-outcomes-evaluated.jsonl` (file runtime,
da gitignore). File evaluated viet lai toan bo moi lan chay, chi
gom cac ban ghi DA CO outcome (ban ghi da co `outcome` thi giu
nguyen, khong cham lai; ban ghi trung `id` thi dedupe), xep theo
`created_utc` roi `id`. Ban ghi goc khong bi sua — file evaluated
la ban ghi goc + cac truong cham diem (`outcome`, `bars_held`,
`mfe`, `mae`, `ret`, `evaluated_utc`).

Lenh tra 0 neu cham duoc it nhat 1 ban ghi moi (hoac tat ca da
cham truoc do); tra 1 neu khong co file ket qua / file rong, hoac
khong co bar lich su nao cho cac tin hieu can cham (chay
`backfill` truoc roi chay lai).

### Dinh nghia cham diem

- **win (thang):** trong cua so, gia cham TP truoc khi cham SL.
  Tinh theo nen: nen nao co `high >= tp` (lenh BUY) hoac
  `low <= tp` (lenh SELL) truoc nen cham SL thi thang. Neu 1 nen
  cham CA TP VA SL (khong biet thu tu trong nen) thi tinh la
  thua — cach tinh bao thu.
- **loss (thua):** trong cua so, gia cham SL truoc khi cham TP.
- **timeout (het cua so):** het `outcome_window_bars` nen ma
  khong cham TP lan SL. Timeout KHONG phai thang hay thua — no
  duoc cham bang loi/nhuan luc dong cua so (xem `ret` duoi day).
  Neu khong du bar (it hon cua so): van la timeout, `bars_held`
  = so bar co san, `ret` theo close cuoi cung co san.
- **`bars_held`:** so nen da xet den khi ket thuc — nen cham TP/SL
  (doi voi win/loss), hoac tron `outcome_window_bars` nen (doi voi
  timeout).
- **`ret`:** loi/nhuan luc dong cua so, dang phan so (vd 0,003 =
  +0,3%), tinh theo huong lenh (BUY: `(close_cuoi - entry) /
  entry`; SELL: nguoc lai). Doi voi win/loss thi `ret` gan bang
  khoang TP/SL; doi voi timeout thi `ret` la con so that luc het
  cua so — am hay duong tuy gia.
- **`mfe` (maximum favourable excursion):** gia chay co loi xa
  nhat so voi entry trong cua so, theo huong lenh (BUY: `high`
  cao nhat tru entry; SELL: entry tru `low` thap nhat), tinh
  theo DON VI GIA (>= 0, khong phai %). MFE cho biet lenh da tung
  loi bao nhieu truoc khi ket thuc — MFE lon ma ket qua
  timeout/loss thi TP co the dat qua xa.
- **`mae` (maximum adverse excursion):** gia chay nguoc xa nhat
  so voi entry trong cua so, theo huong lenh (BUY: entry tru
  `low` thap nhat; SELL: `high` cao nhat tru entry), tinh theo
  DON VI GIA (>= 0, khong phai %). MAE cho biet lenh da tung lo
  bao nhieu — MAE lon ma ket qua win thi SL co the dat qua chat.

Vi du: lenh BUY EURUSD entry 1,1000, SL 1,0985, TP 1,1030. Nen
sau do high len 1,1035 truoc khi low cham 1,0985 -> **win**,
`bars_held` la so nen den luc cham TP. Neu low xuong 1,0980
truoc -> **loss**. Neu sau 20 nen gia o 1,1010, chua cham cai
nao -> **timeout**, `ret` = (1,1010 - 1,1000) / 1,1000.

## 3. Buoc 3 — doc bai hoc + de xuat (`ta-review`)

```bash
python -m diamondx10 ta-review
```

Lenh doc file evaluated, tong ket theo tung lat cat roi in bao cao
ra console va ghi de xuat vao
`decisions/ta-tuning-proposals-<YYYYMMDD-HHMM>.yaml` (file runtime, da
gitignore; `<YYYYMMDD-HHMM>` la ngay-gio chay review):

- **Theo symbol:** win rate, loi/nhuan trung binh (`ret`), MFE/MAE
  trung binh, so mau `n` — cho moi symbol.
- **Theo chien luoc / bo tham so (`params_hash`):** cung cac chi so
  tren, de so sanh bo tham so cu voi bo moi sau khi tinh chinh.
- **Theo soft rule:** lenh nao co rule mem kich hoat (vd giam size
  vi ADX yeu) thi hieu qua ra sao so voi lenh khong co rule do.
- **Theo PTCB:** lenh co PTCB dong thuan vs mau thuan vs chua co
  PTCB — de biet cong PTCB co dang giu dung lenh xau hay khong.
- **Theo regime / pattern:** win rate khi trending vs ranging,
  khi co engulfing/hammer vs khong.
- **Theo dong thuan HTF:** lenh dong thuan H1 (`agree`) vs nguoc
  xu huong (`against`) vs trung lap (`neutral`) vs khong ap dung
  loc (`not_applied`) — de biet loc HTF co dang giu dung lenh xau
  hay chi lam giam so lenh (xem `docs/multi-timeframe-ta.md` §6).

**Chua du mau thi khong de xuat.** Moi lat cat can it nhat
`learning.min_sample_for_proposal` mau (mac dinh 20) moi duoc de
xuat tinh chinh — it hon thi bao cao ghi ro "chua du mau" cho lat
cat do, khong de xuat gi. Day la cua chan overfitting: 3 lenh
thang lien khong du de doi 1 tham so.

1 de xuat trong file YAML gom: symbol/pham vi ap dung, tham so doi
(`strategy.per_symbol` hoac soft rule), gia tri cu -> gia tri moi,
ly do (lat cat + so lieu: win rate, n, MFE/MAE truoc/sau), va co
`validated: false` + ly do chua kiem dinh — de xuat moi tao ra
CHUA DUOC kiem dinh OOS, chi la goi y can kiem tra (xem muc 4).

## 4. Buoc 4 — duyet tay + ap de xuat (`ta-review --apply`)

```bash
python -m diamondx10 ta-review --apply decisions/ta-tuning-proposals-<YYYYMMDD-HHMM>.yaml
```

Khong co tu dong ap. `--apply` nhan duong dan file de xuat, in
diff (se doi gi trong `config.yaml`), roi hoi Phu go dung chu
`APPLY` 1 lan — go dung thi ap toan bo thay doi hop le trong file
(`strategy.per_symbol` + `soft_rules` moi), go sai thi khong doi
gi. Khong bao gio ap vao `config.example.yaml`.

Truoc khi ap 1 de xuat, Phu kiem dinh no bang walk-forward tren
du lieu that (xem `docs/real-data-backtest.md` + `docs/backtest.md`):

```bash
python -m diamondx10 backtest --walk-forward --source history --desk forex --symbol EURUSD
```

Chi ap de xuat nao thang OOS (doan test, khong phai doan train).
De xuat chi thang tren mau cu (in-sample) ma thua OOS thi bo —
do la overfitting, khong phai cai tien.

## 5. Buoc 5 — chay lai va so sanh

Sau khi ap de xuat, chay live/backtest lai nhu cu (buoc 1). Lenh
moi ghi `params_hash` moi, nen bao cao `ta-review` lan sau so
sanh thang duoc bo tham so moi voi bo cu tren cung lat cat. Neu
bo moi khong tot hon thi revert: sua lai `config.yaml` ve gia
tri cu (file proposals luu ca gia tri cu de revert).

## 6. Cau hinh (`learning:` trong `config.example.yaml`)

```yaml
learning:
  outcome_window_bars: 20    # 20 nen M15 = 5 gio, cua so cham diem
  min_sample_for_proposal: 20 # so mau toi thieu moi lat cat moi duoc de xuat
```

- `outcome_window_bars` (mac dinh 20): cua so cham diem. Cua so
  ngan thi nhieu timeout; cua so dai thi lenh cham TP/SL muon van
  tinh, nhung phai doi lau moi cham xong de review.
- `min_sample_for_proposal` (mac dinh 20): cua chan mau toi thieu.
  Tang len neu muon de xuat chac hon (doi lau hon); giam xuong chi
  khi hieu ro minh dang chap nhan nhieu nhieu hon.

Khong co khoa nao khac trong muc `learning:` — neu evaluator can
them khoa (vd duong dan file evaluated) thi them sau, khong tu
bịa khoa truoc.

## 7. File lien quan

- `src/diamondx10/outcomes.py` — ghi ban ghi khuyen nghi vao
  `decisions/signal-outcomes.jsonl` (hook trong `live.py`).
- `src/diamondx10/evaluator.py` — cham diem (`evaluate-signals`),
  ghi `decisions/signal-outcomes-evaluated.jsonl`.
- `src/diamondx10/ta_review.py` — bao cao bai hoc + de xuat
  (`ta-review`, `ta-review --apply <file>`), ghi
  `decisions/ta-tuning-proposals-<YYYYMMDD-HHMM>.yaml`.
- `src/diamondx10/__main__.py` — lenh `evaluate-signals`,
  `ta-review`.
- `config.example.yaml` (muc `learning:`) — `outcome_window_bars`,
  `min_sample_for_proposal`.
- `docs/trading-principles.md` muc 63 — quy tac vong hoc TA.
- `docs/per-symbol-ta.md` — tham so rieng theo symbol + soft rule
  (noi de xuat tinh chinh ap vao; quy tac 61–62).
- `docs/strategy-engine.md` — registry chien luoc, so sanh /
  sweep, canh bao overfitting.
- `docs/real-data-backtest.md` — walk-forward tren du lieu that
  (kiem dinh OOS truoc khi ap de xuat).
- `docs/live-loop.md` — vong live M15, noi khuyen nghi duoc ghi.
- `docs/analysis-workflow.md` — PTKT + PTCB + tong hop Yuling.

## 8. Mot vong lap day du — lam theo tung buoc (Windows, PowerShell)

Chay tren may Windows co MT5 demo, tai thu muc repo:

```powershell
cd D:\DiamondX\DiamondX10Trading
$env:PYTHONPATH = "src"
```

1. Chay live 1 chu ky (hoac backtest) de co khuyen nghi moi duoc
   ghi lai:

   ```powershell
   python -m diamondx10 live --once --recommend-only --desk forex
   ```

   Kiem tra file `decisions\signal-outcomes.jsonl` co dong moi.
2. Cham diem cac khuyen nghi da ghi bang nen M15 that (can bar
   trong kho truoc — neu chua backfill thi chay
   `python -m diamondx10 backfill --desk forex` truoc):

   ```powershell
   python -m diamondx10 evaluate-signals
   ```

   Kiem tra file `decisions\signal-outcomes-evaluated.jsonl` co
   truong `outcome` (win / loss / timeout) cho tung ban ghi.
3. Xem bai hoc + de xuat:

   ```powershell
   python -m diamondx10 ta-review
   ```

   Doc bao cao: lat cat nao "chua du mau" thi cu chay tiep, dung
   voi doi tham so; lat cat nao du mau thi doc de xuat trong file
   `decisions\ta-tuning-proposals-<YYYYMMDD-HHMM>.yaml` (ten file
   in ra o cuoi lenh `ta-review`).
4. Kiem dinh de xuat bang walk-forward tren du lieu that truoc
   khi ap:

   ```powershell
   python -m diamondx10 backtest --walk-forward --source history --desk forex --symbol EURUSD
   ```

   Chi ap de xuat thang OOS.
5. Ap de xuat da duyet (go dung chu `APPLY` khi lenh hoi, dung
   ten file that lenh `ta-review` o buoc 3 da in ra):

   ```powershell
   python -m diamondx10 ta-review --apply decisions/ta-tuning-proposals-<YYYYMMDD-HHMM>.yaml
   ```

6. Chay lai buoc 1–3 o phien sau, so sanh bo tham so moi voi bo
   cu qua `params_hash` trong bao cao `ta-review`. Khong tot hon
   thi revert gia tri cu trong `config.yaml`.

## 9. Gioi han that — doc truoc khi tin bat ky de xuat nao

- **Day KHONG phai mang neural.** Vong hoc la vong phan hoi co
  he thong — ghi lai, cham diem, quy ve lat cat, de xuat, kiem
  dinh — chu khong phai mo hinh hoc may. No khong tu tim ra tin
  hieu moi, khong tu phat hien quy luat an trong du lieu.
- **Chi hoc tu nhung gi da ghi.** Lenh nao khong ghi vao
  `signal-outcomes.jsonl` thi khong ton tai doi voi vong hoc.
  HOLD khong duoc ghi nen vong hoc khong biet minh da bo lo bao
  nhieu co hoi — no chi biet lenh da vao thi hieu qua ra sao.
- **Mau nho noi doi.** Duoi `min_sample_for_proposal` (mac dinh
  20 mau/lat cat) thi khong co de xuat nao dang tin. Ngay ca 20
  mau van la mau nho: 1 chuoi 5 lenh thang co the chi la may man.
- **Thang truoc khong dam bao thang sau.** Win rate cao trong qua
  khu khong dam bao tuong lai — thi truong doi regime, tin tuc doi,
  thanh khoan doi. De xuat nao cung phai qua walk-forward OOS
  (muc 4) truoc khi ap, va van co the thua sau khi ap.
- **Cham diem bang cua so co dinh la xap xi.** `outcome_window_bars`
  (20 nen M15) cat ket qua o 1 moc co dinh: lenh co the cham TP o
  nen 21 (tinh la timeout) hay bi quet SL roi chay dung huong (tinh
  la loss). Dinh nghia win/loss/timeout chi dung trong cua so do.
- **MFE/MAE khong phai loi nhuan that.** Chung do gia da chay bao
  xa trong cua so, khong tru phi/truot gia, khong tinh den viec
  lenh that co the bi dong som bang trailing stop hay tin hieu
  dao chieu.
- **De xuat chi doi con so, khong doi quy tac.** Vong hoc tinh
  chinh tham so (`strategy.per_symbol`, soft rule) chu khong tu
  viet chien luoc moi, khong tu them dieu kien vao, khong tu bo
  cong nao. Doi quy tac van la viec cua Yuling + LJ/Kel, Phu duyet.
