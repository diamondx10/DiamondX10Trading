# Mo hinh AI outcome offline — chinh tham so TA tu log (muc 65)

> Trang thai 2026-11-28: code da co (`src/diamondx10/ai/`,
> lenh `ai-setup` / `ai-train` / `ai-tune`, tich hop live o
> `src/diamondx10/ai/live_hook.py` + `live.py`); kiem chung bang
> `tests/test_ai_live.py` (mo hinh gia + 1 test mo hinh torch that)
> — CHUA kiem chung tren may Windows co MT5 demo (train that,
> verdict that, lenh demo that qua vong live).

Quy tac goc: xem `docs/trading-principles.md` muc 65.

## 1. Vai tro: chinh tham so, KHONG phai tao tin hieu

Mo hinh nay hoc anh xa **(context thi truong + tham so TA) ->
ket qua lenh**, de tra loi mot cau duy nhat: *"voi bo tham so nay,
trong context nay, xac suat thang la bao nhieu?"* Dau ra la
**P(tp_first) / P(sl_first) / P(timeout)** cua lenh sap dat —
tuc la xac suat TP cham truoc / SL cham truoc / het cua so 20 bar
M15 ma khong cham cai nao (theo huong cua tin hieu).

**Khong co head du doan huong rieng** (`ai_direction` /
`ai_confidence` da bo): huong mua/ban do quy tac TA quyet; mo hinh
chi danh gia chat luong cua tin hieu do duoi tham so hien tai.
Viec chinh la **chinh tham so TA tu log** (per-symbol params +
nguong soft rule), di qua duong de xuat ta-review (§5) — mo hinh
khong bao gio thay the mo hinh TA quy tac hay cac gate cung.

```
MT5 bars (M15) + outcomes log            ai-tune
  (context + params -> ket qua)   ---->   xep hang ung vien
        |                                     |
        v                                     v
  ai-train (offline, theo lich)       kiem dinh OOS walk-forward
        |                                     |
        v                                     v
  data/ai-models/<SYMBOL>.pt+.json    de xuat ta-review (YAML)
  (chi ghi file khi thang gate §6)            |
                                        ta-review --apply (go APPLY,
                                        Phu duyet tay) -> config.yaml
```

## 2. Vi sao chon GRU PyTorch thuan (khong vendor thu vien)

Tieu chi chon: (a) bai toan la **phan loai ket qua** (TP/SL/timeout)
chu khong phai du bao gia; (b) input la **48 cot tu che** (35
context + 13 tham so) — thu vien phai an duoc feature tuy chinh,
khong ep kieu du lieu rieng; (c) chay **offline, CPU-only, tren
may Windows cua Phu**, khong them phu thuoc nang; (d) luu/tai
**weights-only + sidecar JSON** de live nap an toan; (e) giay
phep mo cho phep dung thuong mai.

| Thu vien | Giay phep | Vi sao loai |
|---|---|---|
| NeuralForecast (Nixtla) | Apache-2.0 | Du bao gia / chuoi thoi gian, khong phai phan loai ket qua lenh theo tham so; API fit/predict cua no khong an feature 48 cot tu che + vector tham so. |
| Darts (Unit8) | Apache-2.0 | Cung la thu vien du bao (forecasting/anomaly detection) voi kieu `TimeSeries` rieng; qua nang cho 1 head phan loai 3 lop, khong can TimeSeries container. |
| FinRL (AI4Finance) | MIT | Hoc tang cuong (RL agent hoc chinh sach giao dich) — thay ca bo ra quyet dinh, nguoc voi vai tro "co van chinh tham so"; can moi truong gym + du lieu lon hon nhieu. |
| Qlib (Microsoft) | MIT | Nen tang nghien cuu quant toan dien (factor library Alpha158/360, tap trung co phieu ngay) — qua nang, khong thiet ke cho M15 FX/vang/crypto + tham so TA rieng cua dx10. |
| tsai (timeseriesAI) | Apache-2.0 | Gan nhat (phan loai chuoi thoi gian, co LSTM-FCN/InceptionTime san) — nhung keo theo fastai + training loop rieng, kho giu co che luu/tai weights-only + sidecar + scaler cua dx10; loi ich khong bu duoc phu thuoc them. |
| pytorch-forecasting | MIT | Du bao voi N-BEATS/TFT/DeepAR tren PyTorch Lightning — lai la bai toan du bao gia, khong phai phan loai ket qua; Lightning la phu thuoc nang khong can thiet. |
| **GRU PyTorch thuan (chon)** | PyTorch: BSD-3-Clause | Chi them torch CPU (~250 MB, opt-in qua `ai-setup`); toan quyen kiem soat input 48 cot, scaler, sidecar, weights-only save/load; kien truc nho, train/inference CPU duoc. |

Kien truc tham chieu (khong vendor code): GRU — Cho et al.
2014 ("Learning Phrase Representations using RNN
Encoder-Decoder"); LSTM-FCN / MLSTM-FCN — Karim et al. 2017,
2019 (duong nang cap neu GRU underfit); InceptionTime — Fawaz
et al. 2019 (duong nang cap thu hai). Bat dau bang GRU don gian;
chi nang cap khi OOS chung minh GRU thieu suc.

## 3. Kien truc + du lieu

**Input — 48 cot, cua so 32 bar (`seq_len=32`):**

| Nhom | So cot | Noi dung |
|---|---|---|
| Context thi truong (`ai/features.py`, `FEATURE_VERSION = 1`) | 35 | log-return (1/3/5/10/20 bar), bien dong, volume tuong doi, SMA/RSI/ATR/ADX (tinh theo tham so da resolve), regime, diem + 13 mau hinh, cot huong lenh (`direction_long`: BUY +1 / SELL -1). |
| Tham so TA (`ai/params.py`, `PARAM_FEATURE_VERSION = 1`) | 13 | SMA fast/slow, 6 nguong RSI, `atr_sl_mult`, `tp_mult`, `trail_mult`, `adx_min`, `min_atr_pct` — chuan hoa ve [0, 1]. Tham so vao mo hinh theo 2 duong: gian tiep qua cac cot chi bao (tinh theo tham so ung vien) va truc tiep qua vector tham so — nho vay mo hinh moi hoc duoc anh huong rieng cua tham so. |

**Mo hinh (`ai/model.py` — `DirectionGRU`):** GRU 2 lop,
hidden 64, dropout 0.2, lay hidden state buoc cuoi -> Linear
head -> **3 logits** `[sl_first, timeout, tp_first]`. Khong co
head huong rieng.

**Nhan (`ai/dataset.py`):** TP/SL-first tren 20 bar M15 sau
diem vao (`learning.outcome_window_bars` mac dinh 20 = 5 gio):
TP cham truoc = thang, SL cham truoc = thua, het cua so = timeout.
Mau chi ton tai o diem quy tac kich hoat (khong phai moi bar).

**Train (`ai/train.py`):** tach chronological 70/15/15
(train/val/test — khong tron lan thoi gian); scaler (mean/std
theo cot) chi fit tren train fold; class weights cap 3x; early
stopping patience 5; walk-forward 3 folds truoc khi train mo
hinh chinh. Bao cao OOS so voi 2 baseline: naive + quy tac
(rule-based).

**Luu / tai (weights-only, khong bao gio pickle ca object):**
`<SYMBOL>.pt` (state_dict) + `<SYMBOL>.json` (sidecar: symbol,
label_mode, classes, feature/param version + ten cot, mean/std,
seq_len, trained_at, bars_used, walkforward_metrics, oos_metrics,
torch_version). Load kiem tra feature version truoc, roi
`load_state_dict(weights_only=True, map_location="cpu")`; file
thieu/hong/khong khop -> `ModelLoadError` ghi ro ten file.
Torch la phu thuoc tuy chon (khong co trong `requirements.txt`,
quickstart khong tu cai); thieu torch thi bao loi sach ten
`ai-setup`.

## 4. Vong chinh tham so (tuning loop)

```
ai-tune --symbol EURUSD --days 90
  1. counterfactual sampling (ai/tune.py): chay quy tac tren bar
     gan nhat voi bo tham so hien tai + tung bien doi mot tham so
     mot luc (candidate_param_sets — coordinate variations, khong
     phai luoi day du; tuong tac cap 2 khong lay mau o v1);
     khoa cung (HARD_RULE_KEYS) bi loai ngay.
  2. Xep hang ung vien theo win rate DU DOAN (trung binh
     P(tp_first) cua mo hinh tren cac cua so kich hoat; mac dinh
     top 3, toi thieu 5 lenh du doan moi xep hang).
  3. Kiem dinh OOS walk-forward THAT (run_walk_forward): ung vien
     chi duoc de xuat khi return OOS thang tham so hien tai tren
     cung bar, voi du so lenh OOS (mac dinh >=
     learning.min_sample_for_proposal, 20).
  4. De xuat ghi ra file YAML dang strategy.per_symbol /
     soft_rules — DUNG HAM write_proposals CUA ta_review
     (1 dinh dang de xuat duy nhat), kem validated + ly do OOS.
  5. Phu duyet tay: `ta-review --apply <file>` (go chu APPLY).
     KHONG BAO GIO tu ap.
```

## 5. Tich hop live — tac dong chinh xac

File: `src/diamondx10/ai/live_hook.py`, moc trong
`live.process_symbol` (buoc 5b, ngay sau khi co tin hieu).

**Mac dinh — chi la boi canh, khong doi hanh vi:**

- Co file mo hinh cho symbol (`data/ai-models/<SYMBOL>.pt` +
  `.json`, theo `ai.models_dir`) thi live nap 1 lan / process /
  symbol (cache theo fingerprint mtime + kich thuoc file — file
  thay doi thi chu ky sau nap lai) va gan du doan vao dict tin
  hieu: `ai_win_prob` (P(tp_first) duoi tham so HIEN TAI),
  `ai_probs` = `[P(sl_first), P(timeout), P(tp_first)]`,
  `ai_model_version` (trained_at + feature/param version tu
  sidecar). Ket qua TRADED/RECOMMENDED mang theo 3 khoa nay;
  outcome log ghi vao `context.ai_win_prob` /
  `context.ai_probs` / `context.ai_model_version`
  (`outcomes.py` — ban ghi khong co AI giu nguyen nhu cu).
- Du doan can 81 bar M15 (50 cua so feature + 32 chuoi - 1);
  live chi lay 81 bar khi co file mo hinh, khong thi 60 bar nhu cu.
- AI **khong bao gio**: vuot gate cung, dat lenh, doi size/risk,
  ghi de ma tran tong hop TA+FA (muc 39-40, 61-63). Tin hieu HOLD
  khong duoc du doan (khong co huong).

**Chan opt-in (mac dinh TAT):** chi khi
`ai.block_on_low_win_prob: true` trong config thi tin hieu vuot
MOI gate (ke ca PTCB) ma `ai_win_prob < ai.min_win_prob` (mac
dinh 0.30) moi bi chan thanh `BLOCKED-AI-LOW-WIN-PROB`, truoc
khi dat lenh / tao khuyen nghi. Chan nay nam sau moi gate cung
nen no chi chan them — khong bao gio mo duong cho lenh nao.
Day la cau hinh YAML (theo quy tac "rule moi bang YAML" —
xem `docs/trading-principles.md` muc 65), khong phai luat cung
trong code.

**Suy giam an toan:** thieu file / model het han
(`trained_at` cu hon `ai.max_age_days`, mac dinh 90 ngay) /
file hong / khong tai duoc / chua cai torch / khong du bar —
vong live chay tiep KHONG CO AI, chi in 1 dong canh bao (moi ly
do 1 lan / process / symbol), khong bao gio crash, khong
traceback.

## 6. Lenh + lich chay

```powershell
# 1 lan duy nhat (may Windows): cai torch CPU + numpy + pandas (~250 MB)
python -m diamondx10 ai-setup

# Train 1 symbol / tat ca (mac dinh 90 ngay lich su, toi da 50 epoch,
# nguon history = kho SQLite — can backfill truoc; simulated = demo/test)
python -m diamondx10 ai-train --symbol EURUSD --days 90
python -m diamondx10 ai-train --all --days 90
python -m diamondx10 ai-train --symbol EURUSD --days 90 --no-promote  # chi train, khong ghi file

# Tune: xep hang ung vien -> kiem dinh OOS -> ghi de xuat (khong tu ap)
python -m diamondx10 ai-tune --symbol EURUSD --days 90
python -m diamondx10 ai-tune --all --days 90 --top 3 --rank-bars 2000 --min-trades 5
```

**Gate promotion file mo hinh** (`train.evaluate_model_promotion`):
mo hinh moi chi thay file live (`.pt`/`.json`) khi win rate OOS
cua no thang CA baseline quy tac VA mo hinh live hien co (neu
co); khong thang thi giu file cu, bao cao ghi ro ly do.
`--no-promote` thi chi train + bao cao, khong ghi file du gate
thang.

**Lich dinh ky (Windows Task Scheduler, chay tay 1 tac vu hang
tuan):** train + tune la viec offline, khong chay trong vong
live. De xuat: tac vu tuan, Chu nhat 22:00 ICT (sau khi dong
tuan), chay bang cung user Windows, Start in = thu muc repo:

1. Action 1: `python.exe` + doi so
   `-m diamondx10 ai-train --all --days 90`
2. Action 2 (chay sau khi train xong): `python.exe` + doi so
   `-m diamondx10 ai-tune --all --days 90`
3. Sau do Phu xem file de xuat `decisions/ta-tuning-proposals-*.yaml`
   va duyet tay bang `ta-review --apply` (xem §4). De xuat khong
   thang OOS thi khong co file de xuat nao — do la ket qua binh
   thuong, khong phai loi.

## 7. "Train theo thoi gian thuc" co nghia la gi

- **Du lieu** den theo thoi gian thuc: moi nen M15 tu MT5 chay
  vao kho lich su (`data/history.db`), moi khuyen nghi TRADED /
  RECOMMENDED chay vao outcome log — do la "thoi gian thuc" cua
  he thong nay.
- **Train lai KHONG phai theo tung nen:** train la tac vu offline
  theo lich (hang tuan, §6) hoac chay tay khi Phu muon. Mo hinh
  live chi doc file `.pt` da train; vong live M15 khong bao gio
  train, khong bao gio cap nhat weights.
- File mo hinh moi (train xong + thang gate) duoc live nap o chu
  ky sau (cache theo fingerprint file, §5) — khong can khoi dong
  lai live.

## 8. Khung thoi gian

- **v1 chi M15:** dataset mang `"timeframe": "M15"`; train/tune/
  du doan live deu an bar M15. HTF (H1 trend, muc 64) chua phai
  feature cua mo hinh — chi la boi canh `htf` trong outcome log.
- Them khung khac sau nay: cot HTF phai dat ten co tien to
  (`htf_h1_*`), kem tang `FEATURE_VERSION` (mo hinh cu tu choi
  tai vi version khong khop) — khong tron lan cot M15 voi cot HTF.

## 9. Gioi han trung thuc — doc truoc khi tin mo hinh

- **Mang neural khong dam bao khuyen nghi tot hon.** No hoc tu
  log + lich su — du lieu nhieu, mau thua, thi truong doi che do
  thi mo hinh sai nhu bat ky mo hinh nao. OOS la bang chung duy
  nhat: mo hinh khong thang baseline quy tac tren OOS thi khong
  duoc promote file, ung vien khong thang OOS thi khong duoc de
  xuat.
- **Mau nho thi overfit:** moi symbol can du lich su (mac dinh
  it nhat 10 mau train, toi thieu 20 lenh OOS moi de xuat); duoi
  nguong thi bao "chua du mau", khong de xuat gi.
- **Mo hinh la co van trong cac gate san co, khong bao gio la
  nguoi ra quyet dinh:** no khong tao tin hieu, khong vuot gate
  cung, khong dat lenh, khong doi size/risk. AI chinh mo hinh TA
  tu du lieu log — no khong thay the mo hinh TA hay cac gate cung.
- **Chua kiem chung that:** train that / du doan that / de xuat
  that / lenh demo that qua vong live — tat ca can may Windows co
  MT5 demo + lich su that (history.db hien trong tren may Linux
  dang trong; test chi dung nen gia).

## 10. File + tai lieu lien quan

- `src/diamondx10/ai/features.py` — 35 feature context (v1)
- `src/diamondx10/ai/dataset.py` — nhan TP/SL-first, build_dataset
- `src/diamondx10/ai/model.py` — DirectionGRU + luu/tai weights-only
- `src/diamondx10/ai/params.py` — 13 feature tham so + ung vien
- `src/diamondx10/ai/train.py` — train / walk-forward / gate promotion
- `src/diamondx10/ai/tune.py` — counterfactual + xep hang + OOS
- `src/diamondx10/ai/live_hook.py` — du doan trong vong live (muc 65)
- `src/diamondx10/live.py` — moc 5b (boi canh) + 6c (chan opt-in)
- `src/diamondx10/outcomes.py` — `context.ai_*` trong outcome log
- `config.example.yaml` — muc `ai:` (models_dir / seq_len /
  rank_bars / block_on_low_win_prob / min_win_prob / max_age_days)
- `docs/ta-learning-loop.md` — vong hoc TA goc (muc 63): ghi log,
  cham diem, review, de xuat, kiem dinh OOS — AI dung chung duong
  de xuat nay
- `docs/per-symbol-ta.md` — tham so TA rieng theo symbol + mo hinh
  quy tac cung/mem (muc 61–62): cai ma AI de xuat chinh
- `docs/multi-timeframe-ta.md` — HTF H1 + entry M15 (muc 64)
- `docs/trading-principles.md` — muc 65
