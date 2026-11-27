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

Ngon ngu briefing theo lua chon cua user (quy tac 51): noi dung
briefing viet bang ngon ngu trong `language:` cua `config.yaml`
(mac dinh tieng Viet); doi bang nut toggle tren web UI
(`POST /api/language`, xem `docs/web-ui.md` §7). Noi dung bai bao
goc trong briefing giu nguyen ngon ngu goc, khong dich.

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

### 2d. Nhan dinh tac dong tung tin (per-item impact verdict)

Ngoai nhan dinh chung cua desk, Muse danh gia them TUNG TIN trong
briefing: tin do tac dong the nao den 1 symbol cu the. Moi tin trong
briefing deu co id rieng (`news_id`, MD5 cua title+link — cung id
voi the tin tren feed tin), in kem tung tin o muc tin tuc cua file
`.md` (dong `news_id: <id>`) va trong file `.json` (truong `"id"`
cua moi tin). Muse nhac lai id do trong verdict:

```json
{
  "desk": "forex",
  "analyst": "Yuling Pan",
  "direction": "buy",
  "confidence": 0.8,
  "drivers": ["Fed cat lai suat, USD yeu di"],
  "risks": ["ECB co the cung ran lai"],
  "note": "Dong thuan voi PTKT: xu huong tang, RSI 59",
  "created_utc": "2026-11-27T09:00:00+00:00",
  "news_impacts": [
    {
      "news_id": "9f2c...a1",
      "impact": "positive",
      "direction": "buy",
      "confidence": 0.7,
      "summary": "Fed dovish day EUR len.",
      "affected_symbol": "EURUSD",
      "verdict_created_utc": "2026-11-27T09:00:00+00:00"
    }
  ]
}
```

- `"news_impacts"` la truong TUY CHON (vang mat -> `[]`); moi muc:
  `news_id` (chuoi khong rong, id tin trong briefing), `impact`
  (`"positive"` | `"negative"` | `"neutral"`), `direction`
  (`"buy"` | `"sell"` | `"neutral"`), `confidence` (so 0..1),
  `summary` (chuoi, duoc rong), `affected_symbol` (chuoi hoac
  `null`), `verdict_created_utc` (ISO, tuy chon — vang mat thi lay
  `created_utc` cua verdict).
- Kiem tra chat nhu verdict desk: muc nao sai (direction la,
  confidence ngoai 0..1, thieu `news_id`, sai kieu) thi CA verdict
  bi loai, exit 1, khong luu gi. `news_id` la van CHAP NHAN (verdict
  co the nhac tin chua co tren feed).
- Luu verdict (`verdict --file`, hoac `muse-auto` doi duoc verdict)
  thi nhan dinh tung tin duoc gan len the tin tuong ung trong kho
  `decisions/news-cards.json` (`newsfeed.py` `NewsCardStore`,
  `attach_impacts`) — CHI hien thi tren feed tin, KHONG gui
  Telegram o buoc nay. `save_verdict` khong co side effect nao
  (chi luu verdict); gan the nam o lenh `verdict` / chu ky
  `muse-auto` / `muse-send`.

Feed tin (`src/diamondx10/newsfeed.py`, kho
`decisions/news-cards.json` — file runtime, da gitignore): moi the
tin la 1 bai bao da lay ve (`briefing` va lenh `news` dang the khi
lay tin, dedupe theo id — 1 bai chi co 1 the, desk dau tien thang):

```json
{
  "id": "9f2c...a1",
  "title": "Federal Reserve holds rates steady",
  "link": "https://example.com/fed-1",
  "source": "Fake Forex",
  "summary": "ECB and Fed signal no change...",
  "tier": 2,
  "desk": "forex",
  "analyst": "Yuling Pan",
  "published_utc": "2026-11-27T09:00:00+00:00",
  "created_utc": "2026-11-27T10:00:00+00:00",
  "impact": null
}
```

`impact` la `null` khi tin moi lay ve ("dang cho phan tich"), sau
gan verdict thi co dang `{impact, direction, confidence, summary,
affected_symbol, verdict_created_utc}` nhu tren. Kho the hong /
chua co thi doc nhu kho rong, khong bao gio crash.

Chuan kich hoat Telegram cho 1 tin (da chot — `news_qualifies`):
tin duoc dua vao khuyen nghi Telegram khi va chi khi verdict tac
dong cua no la **buy/sell voi do tin cay >= 0.6**, tin thuoc
**tier 1 hoac 2**, VA **tong hop Yuling dong thuan** (PTKT BUY voi
buy, SELL voi sell — rule 40: PTCB mot minh khong tao lenh). Tin
**tier 3 (ro ri) KHONG BAO GIO** kich hoat Telegram mot minh, du
tin cay co cao den dau. Telegram CHI gui qua duong dang bai hien
co (`synthesize --publish`, xem muc 3) — khong co them lenh gui
Telegram nao cho tin: bai BUY/SELL du chuan thi kem tom tat tac
dong vao drivers + tom tat va ghi `"news_id"` len bai, roi tom tat
bai gui qua Telegram nhu thuong; tin khong du chuan thi impact cua
no chi hien tren the tin.

Chu ky `muse-auto` mang impact di suot: `briefing` dang the tin
-> gui Muse -> doi verdict (`wait_for_verdict` validate + luu,
gom ca `news_impacts`) -> gan impact len the tin -> `synthesize
--publish` moi xet kich hoat Telegram.

### Che do TEST (`news.test_mode`)

De kiem tra duong tin -> khuyen nghi ma khong can doi tin dat
chuan 0.6, Phu bat che do TEST: co `news.test_mode: true` trong
`config.yaml` (mac dinh `false`, xem `config.example.yaml`), hoac
bat tam 1 lan bang co `synthesize --publish --test-mode` (chi co
tac dung cho lan chay do, khong ghi vao config). O che do test,
MOI impact buy/sell deu du chuan (`news_qualifies(..., test_mode=True)`
bo qua nguong 0.6, dong thuan tong hop va loai tier — ke ca tier 3);
direction neutral thi KHONG BAO GIO du (khong co khuyen nghi de
gui), bai NEUTRAL cung khong gui Telegram. Phan tich tac dong van
la verdict THAT cua Muse — che do test chi bo cua kich hoat, khong
tao phan tich gia. Moi bai test deu danh dau ro de khong nham voi
khuyen nghi that: truong `"test_mode": true` tren bai dang (hien
qua `GET /api/posts` de web UI gan nhan [TEST]) va tien to
`"[TEST] "` o dau chinh tin Telegram gui di.

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

### Dang bai phan tich len feed trang chu (`synthesize --publish`)

Ket luan tong hop khong chi in ra console — no duoc **dang len
feed trang chu** nhu bai dang Facebook (quy tac 53–54, xem
`docs/web-ui.md` §8):

```bash
python -m diamondx10 synthesize --desk forex --publish
```

Voi `--publish`, moi symbol cua desk duoc dang them 1 bai
(`posts.py` `publish_synthesis_post`, luu vao kho
`decisions/analysis-posts.json` — file runtime, da gitignore):

- Ket luan bai dang: PTKT BUY/SELL ma khong bi chan -> **BUY/SELL**;
  PTKT HOLD hoac bi chan (BLOCKED) -> **NEUTRAL**, khong co
  entry/SL/TP.
- Tom tat bai gom 1–3 cau: cau PTKT (huong + ly do) + cau PTCB
  (huong + do tin cay, kem drivers/risks neu co) + cau muc gia
  (entry/SL/TP, chi khi BUY/SELL) hoac cau chan lenh (khi bi chan).
- Confidence/drivers/risks lay tu verdict (neu co); entry/SL/TP
  lay tu levels TA (chi khi BUY/SELL).
- **Telegram:** bai BUY/SELL moi thi gui 1 tin tom tat qua
  Telegram (`telegram.py` `format_post_summary`, chi khi
  `telegram.enabled: true`); bai NEUTRAL khong gui. Tin chi la
  thong tin — khong nut dat lenh, khong tao lenh cho. Gui loi chi
  in canh bao, khong lam hong viec dang bai. Bai BUY/SELL co tin
  du chuan kich hoat (muc 2d) thi kem tom tat tac dong cua tin do
  vao drivers + tom tat va ghi `"news_id"` len bai — cung 1 tin
  Telegram do, khong gui them tin nao cho tin do.
- **Dedupe:** cung symbol + cung ket luan + cung
  `verdict_created_utc` thi tra lai bai cu, khong tao bai moi,
  khong gui Telegram lai. Loi dang bai chi in canh bao, khong lam
  hong ket qua tong hop (exit code van theo tong hop).

Hai duong dang bai khac (cung kho, cung quy tac Telegram):

- **Dang tay qua CLI** — `publish-post` (luon tao bai moi, khong
  dedupe):

  ```bash
  python -m diamondx10 publish-post --desk xauusd --symbol XAUUSD \
    --action BUY --summary "PTKT BUY, RSI 59, PTCB buy 0.8." \
    --confidence 0.8 --entry 3650 --sl 3600 --tp 3750 \
    --drivers "Fed cat lai suat;USD yeu di" --risks "ECB ran lai"
  ```

  `--desk` / `--symbol` / `--action` / `--summary` bat buoc;
  `--confidence` (0..1, mac dinh 0.0), `--entry` / `--sl` /
  `--tp`, `--drivers` / `--risks` (1 chuoi, cac muc cach nhau
  bang `;`) tuy chon. Sai thi bao loi sach, exit 1, khong dang gi.
- **Dang tay qua web UI** — composer tren feed trang chu
  (`POST /api/posts`, xem `docs/web-ui.md` §8) hoac nut
  **"Dang tu tong hop"** (`POST /api/publish`, chay lai tong hop
  Yuling roi dang bai moi — giong `synthesize --publish` nhung goi
  tu trinh duyet; tra chi bai MOI tao).

Vong live **khong** dang bai: `live.py` khong goi `PostStore`
(xem `docs/live-loop.md` §4) — tom tat bai phan tich va khuyen
nghi live la 2 duong Telegram rieng, khong double-send.

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
python -m diamondx10 synthesize --desk forex --publish  # tong hop + dang bai len feed
python -m diamondx10 publish-post --desk forex --symbol EURUSD --action BUY --summary "..."  # dang bai tay
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
- `src/diamondx10/posts.py` — `PostStore` (kho
  `decisions/analysis-posts.json`), `publish_synthesis_post`,
  `cmd_publish_post` (lenh `publish-post`); dedupe bai tong hop,
  Telegram chi cho BUY/SELL.
- `src/diamondx10/newsfeed.py` — `NewsCardStore` (kho the tin
  `decisions/news-cards.json`), `news_qualifies`,
  `impacts_for_symbol`; chuan kich hoat Telegram cho tin (muc 2d).
- `tests/test_newsfeed.py`, `tests/test_verdict_impact.py` — the
  tin (tao/dedupe/list/gan impact), chuan `news_qualifies`,
  validate `news_impacts`, gan impact khi luu verdict / muse-auto,
  kich hoat Telegram qua duong dang bai.
- `src/diamondx10/telegram.py` — `format_post_summary` (tom tat bai
  dang, chi thong tin, khong nut dat lenh); `order_keyboard`,
  `get_updates`, `answer_callback_query`, `edit_message_text`
  (khuyen nghi live + nut dat lenh).
- `src/diamondx10/webapi.py` — `GET /api/posts`, `POST /api/posts`,
  `POST /api/publish` (xem `docs/web-ui.md` §8).
- `tests/test_posts.py`, `tests/test_posts_api.py` — kho bai dang,
  dedupe, Telegram chi BUY/SELL, 3 endpoint posts.
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
