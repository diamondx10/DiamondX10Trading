# Quy trinh phan tich DiamondX10 — PTKT + PTCB + tong hop Yuling

De xac dinh diem mua/ban, tool chay 2 nhanh phan tich roi tong hop lai:

```
PTKT (offline, trong tool)          PTCB (tin tuc -> Muse phan tich)
  chi bao + mau hinh                 briefing md+json
  SMA5/20, RSI, ATR, ADX             -> Phu gui file cho Muse trong chat
  regime, ho tro/khang cu            -> Muse (vai Kathy/Yumi/Rich/Yuling)
  engulfing, hammer, doji...            tra verdict JSON
        \                                  /
         \                                /
          Yuling tong hop (synthesize)
                 |
          khuyen nghi MUA/BAN/CHO
          + he so size (1.0 / 0.5 / 0)
                 |
          vong live: chan neu mau thuan manh
          (BLOCKED-FA-CONFLICT)
```

Quy tac goc (xem `docs/trading-principles.md` muc 37-40): PTKT chay
offline trong tool; PTCB can AI phan tich tin; Yuling tong hop cuoi;
PTCB mot minh KHONG bao gio tao lenh vao.

## 1. PTKT — phan tich ky thuat (offline, trong tool)

`generate_signals(desk, bars, ...)` tra tin hieu BUY/SELL/HOLD kem
`levels` (entry/SL/TP theo ATR) tu chien luoc cua desk (SMA5/SMA20 +
loc RSI + ATR stop, xem `docs/phase0-desk-rules.md`).

Boi canh kem theo tin hieu (CHI de tham khao, KHONG doi action):

- **Regime** (`models/quant.py`, muc 21): ADX + ATR percentile +
  huong SMA — trending / transitional / ranging, chi de doc them.
- **Mau hinh nen** (`patterns.py` `detect_patterns`, muc 37):
  engulfing tang/giam, hammer, shooting star, doji, morning star,
  evening star; pivot swing (N=5 nen moi ben) -> muc ho tro/khang cu;
  double top/bottom (2 pivot cach nhau >= 5 nen, gia chenh <= 1%);
  breakout len tren swing high / xuong duoi swing low gan nhat.
  Ket qua nam trong key `"patterns"` cua tin hieu (moi mau hinh:
  `{name, direction, strength 0..1, bar_index, time, detail}`) va
  `"pattern_score"` tu `pattern_summary` (diem rong -1..1, tang duong).
  It hon 6 nen thi khong co mau hinh.

## 2. PTCB — phan tich co ban (tin tuc -> briefing -> verdict)

### 2a. Tao briefing

```bash
python -m diamondx10 briefing --desk forex [--days 3]
python -m diamondx10 briefing --all   # ca 4 desk
```

Moi desk co 1 nha phan tich phu trach:

| Desk | Analyst | Thi truong |
|---|---|---|
| forex | Yuling Pan | Forex + vi mo |
| xauusd | Yumi | Vang + chau A |
| crypto | Rich | Crypto |
| us_securities | Kathy | Chung khoan My |

`briefing` gom cho moi symbol cua desk: gia moi nhat + tin hieu TA
(action, ly do, regime, patterns) + tin thi truong (`run_news`,
xem `docs/market-news.md`) + macro (neu config co muc `macro:`).
Tin duoc nhom theo tang do tin cay: tang 1 CHINH THONG, tang 2 BAO
CHI, tang 3 RO RI — CHUA XAC MINH (tang 3 luon kem canh bao, khong
duoc viet nhu su that da xac minh, khong dung lam can cu duy nhat).

File ghi ra `briefings/briefing-<desk>-<YYYYMMDD-HHMM>.md` (de doc,
gui cho nha phan tich) + file `.json` cung ten (cung noi dung dang
co cau truc). Thu muc `briefings/` la file runtime, da gitignore.

Can co muc `news:` trong config (copy tu `config.example.yaml`);
thieu thi lenh bao loi sach: `chua co news: trong config — copy tu
config.example.yaml`. Tren may Linux khong co MT5, briefing dung
`provider: simulated`; tren Windows thi lay gia that tu MT5 demo.

### 2b. Muse phan tich — BAN GIAO BANG FILE (khong co API)

**Noi thang: tool KHONG goi duoc Muse qua API.** Khong co API nao
cho tool goi Muse. Vong PTCB chay bang ban giao file:

1. Phu chay `briefing` truoc phien, lay file md trong `briefings/`.
2. Phu gui file do cho Muse trong chat (kem cau hoi: phan tich va
   tra verdict theo mau trong file).
3. Muse doc briefing, dong vai nha phan tich cua desk do (Kathy /
   Yumi / Rich / Yuling tuy desk), tra ve **verdict JSON** theo dung
   mau trong briefing.
4. Phu luu verdict JSON do thanh file (vd `verdict-forex.json`).
5. Phu chay lenh `verdict` de nap vao tool (muc 2c).

### 2c. Nap verdict vao tool

```bash
python -m diamondx10 verdict --file verdict-forex.json
```

Verdict JSON (1 nhan dinh, hoac `{"verdicts": [...]}` neu nhieu desk):

```json
{
  "desk": "forex",
  "analyst": "Yuling Pan",
  "direction": "buy",
  "confidence": 0.8,
  "drivers": ["Fed cat lai suat, USD yeu di"],
  "risks": ["ECB co the cung ran lai"],
  "note": "Dong thuan voi PTKT: xu huong tang, RSI 59",
  "created_utc": "2026-11-27T09:00:00+00:00"
}
```

- `direction`: chi `"buy"` | `"sell"` | `"neutral"`.
- `confidence`: so 0..1 (0 = khong chac, 1 = chac chan).
- `created_utc`: thoi gian ISO UTC luc dua ra nhan dinh; thieu thi
  tool tu dien thoi gian hien tai.

Luu y: chu trong `"direction"`/`"confidence"` la tieng Anh (de code
xu ly), con `drivers`/`risks`/`note` viet tieng Viet khong dau cung
duoc, co dau cung duoc — tool khong kiem tra chinh ta o do.

`verdict` kiem tra chat: sai desk, sai direction, confidence ngoai
0..1, thieu truong -> bao loi sach, exit 1, khong luu gi. Luu duoc
thi gop theo desk (giu ban moi nhat moi desk) vao
`decisions/fundamental-verdicts.json` (file runtime, da gitignore).

## 3. Tong hop Yuling — PTKT + PTCB

```bash
python -m diamondx10 synthesize --desk forex [--symbol EURUSD]
```

`synthesize` tinh TA cho tung symbol cua desk, doc verdict moi nhat
cua desk, ap ma tran tong hop (Yuling), in khuyen nghi moi symbol va
luu JSON vao `decisions/synthesis-<YYYYMMDD>.json`.

### Ma tran (mac dinh — CAN CHOT, xem muc 39)

| PTKT | PTCB | Khuyen nghi | Size |
|---|---|---|---|
| BUY | buy, tin cay >= 0.6 | MUA | 1.0 |
| BUY | buy, tin cay < 0.6 | MUA | 0.5 |
| BUY | neutral | MUA | 0.5 |
| BUY | sell, tin cay >= 0.6 | KHONG MUA (chan) | 0 |
| BUY | sell, tin cay < 0.6 | MUA (canh bao) | 0.5 |
| SELL | doi xung voi BUY | BAN / KHONG MUA | 1.0 / 0.5 / 0 |
| HOLD | bat ky | CHO | 0 |

- **PTCB thieu hoac cu** (qua `verdict_max_age_hours`, mac dinh 24
  gio): coi nhu chua co PTCB moi — size 0.5 theo PTKT, kem canh bao
  "chua co PTCB moi". Neu `require_fa: true` thi chan (size 0).
- **PTCB mot minh khong tao lenh:** PTKT HOLD thi luon CHO.

Cau hinh trong `config.example.yaml` (muc `synthesis:`):

```yaml
synthesis:
  verdict_max_age_hours: 24   # verdict cu hon so gio nay thi coi nhu het han
  require_fa: false           # true = thieu/cu verdict thi CHAN khong vao lenh
  fa_high_confidence: 0.6     # nguong tin cay cao (dong thuan manh / mau thuan manh)
```

## 4. Cong PTCB trong vong live

Sau khi tinh xong tin hieu + volume, truoc khi dat lenh DEMO,
`process_symbol` (buoc 6b) doc verdict moi nhat cua desk va ap ma
tran muc 3 (xem `docs/live-loop.md` §5):

- Mau thuan manh -> `BLOCKED-FA-CONFLICT`: khong dat lenh, ghi log,
  gui canh bao chan Telegram.
- Dong thuan/trung lap -> dat lenh nhu thuong, ket qua ghi them
  `fa_note` (vd `FA: buy 0.8`).
- Thieu/cu verdict -> van chay nhu cu, ket qua ghi `FA: chua co` /
  `FA: cu` (tru khi `require_fa: true` thi chan).
- Kho nhan dinh loi -> coi nhu chua co PTCB, in canh bao, khong
  crash vong live.

## 5. Lenh tom tat

```bash
python -m diamondx10 briefing --desk forex     # briefing truoc phien
python -m diamondx10 verdict --file verdict-forex.json
python -m diamondx10 synthesize --desk forex   # xem tong hop Yuling
python -m diamondx10 live --once --desk forex  # vong live (co cong PTCB)
python -m diamondx10 live --once --recommend-only --desk forex  # chi gui khuyen nghi
python -m diamondx10 telegram-listen   # nhan nut "Dat lenh" tren Telegram
```

## 6. File lien quan

- `src/diamondx10/patterns.py` — `detect_patterns`, `pattern_summary`.
- `src/diamondx10/signals.py` — `generate_signals` (key `"patterns"`,
  `"pattern_score"`, `"regime"`).
- `src/diamondx10/briefing.py` — `build_briefing`, `cmd_briefing`.
- `src/diamondx10/synthesis.py` — `validate_verdict`,
  `load_verdict(s)`, `save_verdict`, `synthesize`, `cmd_verdict`,
  `cmd_synthesize`.
- `src/diamondx10/live.py` — `_apply_fa_gate`, buoc 6b trong
  `process_symbol`; buoc 7 che do khuyen nghi (RECOMMENDED).
- `src/diamondx10/pending.py` — `PendingOrderStore` (lenh cho xac nhan).
- `src/diamondx10/listener.py` — `run_listener` (long-poll nut bam
  Telegram, dat lenh DEMO theo lenh cho).
- `src/diamondx10/telegram.py` — `order_keyboard`, `get_updates`,
  `answer_callback_query`, `edit_message_text`.
- `tests/test_patterns.py`, `tests/test_briefing.py`,
  `tests/test_synthesis.py`, `tests/test_live_fa.py`,
  `tests/test_pending.py`, `tests/test_telegram_keyboard.py`,
  `tests/test_recommend.py`, `tests/test_listener.py`.
- `docs/trading-principles.md` muc 37-40 — quy tac [DA CO]/[CAN CHOT].
- `docs/trading-principles.md` muc 41-43 — che do khuyen nghi + nut
  dat lenh [DA CO]/[DA CHOT]/[CAN CHOT].
- `docs/live-loop.md` §6 — che do khuyen nghi + listener.
- `docs/market-news.md` — nguon tin + phan tang tin cay.
- `docs/live-loop.md` §5 — cong PTCB trong vong live.
