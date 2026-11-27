# Web UI dx10 — giao dien web quan ly giao dich

Giao dien web cho dx10: xem trang thai quy, vi the, tin hieu, tong hop
TA+PTCB, duyet / bo lenh cho, bat tat kill switch, tao briefing, gui
cho Muse, nap verdict, xem tin + backtest + bieu do nen — tat ca tu
trinh duyet, khong can go lenh CLI.

> Da doi chieu 2026-11-27: danh sach endpoint o muc 4 khop 1-1 voi route
> table trong `src/diamondx10/webapi.py` (31 route).

## 1. Chay

Cai phu thuoc web UI 1 lan (them vao `requirements.txt`):

```
pip install -r requirements.txt
```

Chay server (mo 1 cua so terminal trong thu muc repo):

```
set PYTHONPATH=src
python -m diamondx10.webapi [--port 8000] [--host 127.0.0.1]
```

(PowerShell: `$env:PYTHONPATH = "src"` thay cho dong `set`.)
`PYTHONPATH=src` la bat buoc — khong co no se loi `No module named
'diamondx10'` (repo dung bo cuc src/, chua co goi cai dat).
Nhanh hon: nhap doi **`start-webui.bat`** (tu set PYTHONPATH roi
chay server).

Mo trinh duyet: http://127.0.0.1:8000

- Mac dinh host `127.0.0.1`, port `8000`. Chi mo tren may dang chay
  server — muon xem du lieu live day du thi chay tren CUNG may
  Windows co MT5 terminal + vong live (xem `docs/dx10-flow.md`).
- Chay tren Linux khong co MT5 thi UI van mo duoc, nhung muc live /
  vi the / tin hieu se trong hoac bao loi do khong doc duoc MT5 —
  dung de xem giao dien, khong dung de giao dich.

## 2. Build lai frontend — chi khi code frontend doi

Frontend la React + Vite + TypeScript trong `webui/`. Ban build san
nam o `src/diamondx10/static/` va duoc FastAPI phuc vu truc tiep, nen
**chay UI khong can Node**. Chi can Node khi sua code frontend:

```
cd webui && npm install && npm run build
```

- `npm run build` bien dich TypeScript roi build ra
  `src/diamondx10/static/` (cau hinh `outDir` trong
  `webui/vite.config.ts`); build xong thi khoi dong lai server
  webapi de nhan ban moi.
- Phat trien frontend: `npm run dev` chay Vite o port 5173, tu proxy
  `/api` ve `http://127.0.0.1:8000` (cau hinh san trong
  `vite.config.ts`) — can chay `python -m diamondx10.webapi` song
  song.

## 3. Kien truc

```
trinh duyet  ->  FastAPI (webapi.py, 127.0.0.1:8000)
                   |-- /            : file tinh React build
                   |                  (src/diamondx10/static/)
                   |-- /api/*       : JSON (xem muc 4)
                   |-- quan ly vong live + telegram-listen
                   |   duoi dang tien trinh con (subprocess),
                   |   bat/tat duoc tu UI
                   |-- doc/ghi cung file voi CLI:
                       decisions/*, briefings/*, config.yaml
```

- UI khong co database rieng, khong co logic giao dich rieng: no doc
  cung file quyet dinh / lenh cho / verdict nhu CLI, va goi cung ham
  backend nhu CLI (quy tac 47–48 trong
  `docs/trading-principles.md`).
- Vong live (`live --recommend-only`) va `telegram-listen` van la 2
  tien trinh rieng; web UI chi bat/tat va theo doi chung, khong thay
  the flow o `docs/dx10-flow.md`.

## 4. Endpoint API

Goc: `http://127.0.0.1:8000`. Tat ca tra JSON. Tru 3 route
`/api/auth/request-otp`, `/api/auth/verify-otp`,
`/api/auth/status`, moi `/api/*` khac doi cookie phien
`dx10_session` hop le, khong thi tra 401 (xem muc 9).

| Phuong thuc | Duong dan | Dung de lam gi |
|---|---|---|
| GET | `/api/status` | Trang thai quy: von, drawdown, kill switch, MT5, Telegram, live/listener co dang chay khong |
| POST | `/api/auth/request-otp` | Gui ma OTP 6 so qua Telegram (hoac fallback terminal); tra `{"sent": true}` hoac `{"sent": false, "fallback": "terminal", ...}`; yeu cau qua nhanh → 429 `{"retry_after": N}` (xem muc 9) |
| POST | `/api/auth/verify-otp` | Nhap ma OTP; dung thi set cookie `dx10_session` (httpOnly), sai → 401 `{"reason": ...}` (xem muc 9) |
| POST | `/api/auth/sign-out` | Dang xuat (huy phien server + xoa cookie) |
| GET | `/api/auth/status` | Da dang nhap chua (`{"authenticated": bool}`) |
| GET | `/api/logs?process=&after=` | Log terminal cua tien trinh duoc quan ly (`live` / `listener` / `diagnostics`); tra `{"process","running","started_utc","exit_code","lines","total"}` (xem muc 9) |
| POST | `/api/diagnostics` | Chay `test_run.py` che do an toan (khong dat lenh) nhu tien trinh "diagnostics" (xem muc 9) |
| POST | `/api/telegram-test` | Gui 1 tin nhan thu qua Telegram bot; tra `{"ok","reason"}` |
| GET | `/api/positions` | Vi the dang mo |
| GET | `/api/signals?desk=` | Tin hieu TA moi nhat theo desk (`forex` / `xauusd` / `crypto` / `us_securities`) |
| GET | `/api/synthesis?desk=` | Tong hop TA+PTCB theo desk (ma tran Yuling, quy tac 39) |
| GET | `/api/pending` | Danh sach lenh cho |
| POST | `/api/pending/{id}/place` | Dat lenh cho (duyet) |
| POST | `/api/pending/{id}/ignore` | Huy lenh cho |
| POST | `/api/kill-switch` | Bat/tat kill switch |
| GET | `/api/decisions` | Lich su quyet dinh (decisions log) |
| GET | `/api/briefings` | Danh sach briefing da tao |
| POST | `/api/briefing` | Tao briefing moi (theo desk) |
| POST | `/api/muse-send` | Gui briefing cho Muse qua trinh duyet (xem `docs/muse-browser.md`) |
| GET | `/api/muse-send/{job_id}` | Trang thai job gui Muse / verdict da ve chua |
| GET | `/api/verdicts` | Danh sach verdict PTCB da nap |
| POST | `/api/verdicts` | Nap verdict (paste JSON tu chat Muse) |
| GET | `/api/news?desk=` | Tin tuc theo desk |
| GET | `/api/backtest` | Ket qua backtest |
| GET | `/api/bars?symbol=&n=` | Nen gia de ve bieu do |
| GET | `/api/live` | Trang thai vong live |
| POST | `/api/live/start` | Bat vong live |
| POST | `/api/live/stop` | Tat vong live |
| GET | `/api/listener` | Trang thai telegram-listen |
| POST | `/api/listener/start` | Bat telegram-listen |
| POST | `/api/listener/stop` | Tat telegram-listen |
| GET | `/api/language` | Ngon ngu giao dien hien tai (`vi` \| `en`) |
| POST | `/api/language` | Doi ngon ngu (`{"language": "vi" \| "en"}`) |
| GET | `/api/team-news` | Tin doi da phan tich trang chu (xem muc 7) |
| GET | `/api/posts?limit=&desk=` | Feed bai dang phan tich, moi nhat len dau; `limit` mac dinh 20, kep 1–200; `desk` tuy chon (`forex` / `xauusd` / `crypto` / `us_securities`); tra `{"posts": [...]}` (xem muc 8) |
| POST | `/api/posts` | Dang 1 bai phan tich thu cong (composer); body `{desk, symbol, action, summary, confidence?, entry?, sl?, tp?, drivers?, risks?}`; 201 tra `{"post": {...}}`; thieu/sai truong → 400 (xem muc 8) |
| POST | `/api/publish` | Chay tong hop Yuling + dang 1 bai / symbol; body `{desk?, symbol?}` (mac dinh `desk=forex`, tat ca symbol cua desk); tra `{"posts": [...]}` chi bai MOI tao (bai da co do dedupe khong nam trong danh sach); desk sai → 400; tong hop loi → 500 (xem muc 8) |

## 5. Lam duoc / khong lam duoc

Lam duoc:

- Xem trang thai, vi the, tin hieu, tong hop, tin tuc, backtest,
  bieu do nen, lich su quyet dinh.
- Xem + dang bai phan tich tren feed trang chu (muc 8): moi bai deu
  co ket luan BUY/SELL/NEUTRAL; bai BUY/SELL thi gui tom tat qua
  Telegram, bai NEUTRAL thi khong gui.
- Doi ngon ngu giao dien Anh/Viet (muc 7) va xem tin doi da phan
  tich o trang chu (muc 7).
- Duyet / bo lenh cho; bat tat kill switch; bat tat vong live va
  telegram-listen.
- Tao briefing, gui briefing cho Muse, nap verdict paste tu chat.

Khong lam duoc (va khong bao gio lam):

- **Khong lam gi hon CLI.** Dat lenh tu UI chay dung phep kiem tra
  nhu nut Telegram: kill switch TAT, tai khoan DEMO, du ky quy, gia
  thi truong lech khoi gia khuyen nghi <= 1,0% (quy tac 43, 48).
  Khong co duong tat, khong bo qua cong nao.
- **Khong giao dich tien that — chi demo.** Cung gioi han demo-only
  nhu CLI (quy tac 19): tai khoan khong phai demo thi bi chan.
- **Khong thay viec dang nhap Muse bang tay.** Lan dau dang nhap
  muse.ai van lam bang tay trong cua so trinh duyet (phien luu local
  o `data/muse-profile`); UI chi bam nut gui, khong hoi / khong luu
  mat khau Muse (xem `docs/muse-browser.md`).

## 6. Bao mat — localhost-only + dang nhap OTP (quy tac 55)

- Server mac dinh chi bind `127.0.0.1` (localhost). Ai mo duoc port
  8000 tren may do thi van can dang nhap OTP moi dung duoc API —
  moi `/api/*` (tru 3 route auth) doi cookie phien `dx10_session`
  hop le, khong thi tra 401. Trang tinh (`/` va `/assets/*`) van
  mo duoc de hien man hinh dang nhap.
- **Khong mo port ra ngoai, khong bind `0.0.0.0`**, khong mo
  firewall cho port nay, khong chay tren may dung chung ma khong
  khoa man hinh. Can xem tu xa thi dung remote desktop vao may
  Windows do, khong phoi API ra internet.
- OTP va token phien chi nam trong bo nho server, khong ghi file,
  khong ghi log, khong tra ve trong response API. Tat server la
  mat het phien (xem muc 9).
- Khong co token, mat khau hay du lieu phien dang nhap trong doc
  nay hay trong code frontend — token Telegram va mat khau MT5 van
  chi qua bien moi truong luc chay nhu cu.

## 7. Ngon ngu giao dien + tin doi trang chu (quy tac 51–52)

### Chon ngon ngu (Anh / Viet)

- Web UI co **nut doi ngon ngu** (toggle VI/EN). Bam nut goi
  `POST /api/language` voi `{"language": "vi" | "en"}`; gia tri khac
  bi tra 400. Server ghi khoa `language:` o cap cao nhat cua
  `config.yaml` local bang cach thay dong (giu nguyen moi khoa va
  comment khac; chua co khoa thi them o cuoi file) — khong ghi de
  toan bo file. Neu `config.yaml` chua co thi tra loi ro rang, khong
  tu tao config nua voi. `GET /api/language` tra
  `{"language": "vi" | "en"}`; thieu/sai thi mac dinh `"vi"`.
- **Lua chon chay theo ca 3 noi:** web UI (nhan, tab) + **Telegram**
  (tin khuyen nghi/chan/thu, nut bam, cau tra loi callback — xem
  `docs/live-loop.md` §4/§6, quy tac 44) + **briefing** (noi dung
  briefing tao ra bang ngon ngu da chon — xem
  `docs/analysis-workflow.md` §2a). Backend doc lai config moi
  request nen doi ngon ngu co hieu luc ngay, khong can khoi dong lai
  server; tab Muse (`POST /api/briefing`, `POST /api/muse-send`)
  doc config luc goi nen luon dung ngon ngu hien tai.
- **Khong dich:** noi dung bai bao goc trong kho tin giu nguyen ngon
  ngu goc. Nhan tieng Viet tren web UI co dau day du (xem
  `webui/src/i18n.tsx`); **CLI/console/log van tieng Viet khong dau.**

### Tin doi da phan tich o trang chu

Trang chu hien muc tin cua doi qua 1 endpoint gop
`GET /api/team-news` tra `{"items", "verdicts", "briefings"}`:

- `items`: bai tin **moi nhat moi desk** tu kho tin (`NewsStore`):
  `title`, `source`, `tier` (1 chinh thong / 2 bao chi / 3 ro ri —
  chua xac minh), `desk`, `analyst` (Yuling Pan / Yumi / Rich /
  Kathy), `time`, `briefing_url` (duong dan tuong doi
  `briefings/<file briefing moi nhat cua desk>`; null neu chua co
  briefing — mo file tu tab Muse / danh sach briefing).
- `verdicts`: nhan dinh PTCB moi nhat **moi desk**
  (`{direction: buy|sell|neutral, confidence}` hoac `null` neu
  chua co verdict) — doc tu `decisions/fundamental-verdicts.json`.
- `briefings`: file briefing moi nhat moi desk
  (`{desk, file, time}`).
- Thieu du lieu (chua chay `news`, chua co verdict/briefing) thi tra
  list rong / `null`, khong bao gio loi — muc tin chi hien "chua co
  du lieu".

## 8. Feed bai dang phan tich o trang chu (quy tac 53–54)

Trang chu (tab Overview) la **feed kieu Facebook**: ket qua phan
tich cua doi dang len nhu bai dang, moi nhat len dau, moi bai deu
mang 1 ket luan. Code: `webui/src/components/Feed.tsx`
(`AnalysisFeed`: composer + post card + feed), `Overview.tsx` dat
feed vao trang chu, `webui/src/api.ts` (`Post` / `PostCreate`,
`fetchPosts` / `createPost` / `publishPosts`), `webui/src/i18n.tsx`
(30 khoa `feed.*`, ca `vi` + `en`), `webui/src/styles.css` (style
feed). Backend: `src/diamondx10/posts.py` (`PostStore`),
`src/diamondx10/telegram.py` (`format_post_summary`),
`src/diamondx10/webapi.py` (3 endpoint muc 4).

### Bo cuc trang chu (feed-first)

Thu tu tu tren xuong trong `Overview.tsx`:

1. Day thong tin quy (4 the: Equity + von, drawdown + gauge, so vi
   the dang mo, trang thai MT5 / Telegram / Live / Listener).
2. **Feed** — cot giua toi da **680px** (`.feed-column`:
   `max-width: 680px; margin: 0 auto`), composer o tren cung, duoi
   la danh sach bai dang.
3. Muc "Tin team da phan tich" (`TeamNewsSection`, muc 7).
4. Kill switch, dieu khien live/listener, von theo desk.

### Composer — dang bai thu cong

Thanh composer luc dau chi la 1 dong mo (`feed.composerPlaceholder`,
avatar "DX"); bam vao thi mo form day du:

- **Desk** (select, mac dinh `forex`), **symbol** (text, tu viet
  hoa khi gui), **ket luan** (3 nut chon: MUA / BAN / CHO — mac dinh
  CHO/NEUTRAL), **tom tat** (1–3 cau ve ket luan).
- Tuy chon: **do tin cay %** (0–100, doi sang 0..1 khi gui, kep
  trong 0..100), **entry / SL / TP** (so, tuy chon), **drivers /
  risks** (moi dong 1 muc).
- Kiem tra (validation): thieu **symbol hoac tom tat** thi bao loi
  ngay tren form (`feed.validation`), khong goi API. Gui len
  `POST /api/posts`; backend thieu/sai truong (desk la, action la,
  confidence ngoai 0..1, drivers/risks khong phai list chuoi) thi
  tra 400 va form hien loi do. Dang xong thi bai moi chen len dau
  feed, form dong + reset, hien `feed.posted`.

### Bai dang (post card) — giai phau 1 bai

- **Dau bai:** avatar tron (2 chu cai dau ten analyst, nen mau theo
  desk) + ten analyst + desk + thoi gian tuong doi (`Vua xong` /
  `{n} phut truoc` / `{n} gio truoc` / `{n} ngay truoc`) + **badge
  ket luan** ben phai (MUA xanh / BAN do / CHO xam; tieng Anh:
  BUY / SELL / WAIT).
- **Than bai:** dong symbol (vd `EURUSD`), tom tat ket luan.
- **Hang so chinh** (chi hien khi co it nhat 1 so): entry / SL / TP
  / do tin cay %. Bai NEUTRAL hoac bi chan thi khong co entry/SL/TP.
- **Chi tiet mo rong:** neu co drivers/risks thi co nut `Xem them`
  / `Thu gon` mo list drivers + risks.
- **Chan bai:** desk + nguon (`Tong hop TA+FA` neu `source` la
  `synthesis`, `Dang tay` neu `manual`) + thoi gian verdict neu co
  (`Verdict: {thoi gian tuong doi}`).

Truong bai dang (backend `PostStore`, luu o
`decisions/analysis-posts.json` — file runtime, da gitignore):

`id` (8 ky hex) | `created_utc` | `desk` | `analyst` | `symbol` |
`action` (`BUY` | `SELL` | `NEUTRAL`) | `confidence` (0..1) |
`summary` | `drivers` / `risks` (list chuoi) | `entry` / `sl` /
`tp` (so hoac null) | `source` (`synthesis` | `manual`) |
`verdict_created_utc` (null neu khong tu verdict).

Feed co **nut loc theo desk** (Tat ca + 4 desk), nut **Refresh**,
va nut **"Dang tu tong hop"** goi `POST /api/publish` voi desk
dang loc (loc Tat ca thi khong gui desk, backend mac dinh
`desk=forex`); thong bao tra ve cho biet da dang bao nhieu bai MOI
(`feed.publishDone`). **Khong co** like / comment / reaction /
stories — feed chi de doc + dang ket luan phan tich.

### Quy tac Telegram — BUY/SELL gui tom tat, NEUTRAL khong gui

Moi bai dang co ket luan (quy tac 53). Khi bai **BUY hoac SELL**
duoc dang, backend gui **1 tin tom tat qua Telegram**
(`telegram.py` `format_post_summary`, qua `PostStore._notify`,
chi khi `telegram.enabled: true`): tieu de phan tich + symbol +
ket luan, desk + analyst, entry / SL / TP (neu co), do tin cay,
tom tat. Bai **NEUTRAL khong gui gi**. Tin chi la **thong tin**:
khong kem nut dat lenh, khong tao lenh cho — muon dat lenh thi
dung duong khuyen nghi live / nut Telegram o `docs/live-loop.md`
§6, khong phai tu bai dang. Gui loi thi chi in canh bao, khong bao
gio lam hong viec dang bai. Ngon ngu tin theo lua chon cua user
(quy tac 44, 51); luu y cac chuoi `tg.*` tieng Viet trong
`src/diamondx10/i18n.py` **co dau** (theo thoi quen cu cua tin
Telegram), khac voi CLI/console/log tieng Viet khong dau.

**Dedupe (quy tac 54):** bai tu tong hop (`source: synthesis`)
duoc dedupe theo symbol + action + `verdict_created_utc` — neu bai
moi nhat cua cung symbol co cung ket luan VA cung thoi gian verdict
thi tra lai bai cu, khong tao bai moi, khong gui Telegram lai.
Bai dang tay (`publish-post` / composer / `POST /api/posts`)
luon tao bai moi, khong dedupe.

**Khong trung lap voi vong live:** vong live **khong** dang bai
phan tich va **khong** gui tom tat bai dang — 2 duong Telegram
(khuyen nghi live dat lenh DEMO, tom tat bai phan tich) tach biet,
khong co double-send (xem `docs/live-loop.md` §4).

### Tham chieu thiet ke — Kinfolk

Bo cuc feed (composer o tren, cot giua la cac post card: avatar +
ten + thoi gian, than bai, hang so, chi tiet mo rong, chan bai)
tham khao **Kinfolk** — ban Facebook clone ma nguon mo cua
suhasbhairav (github.com/suhasbhairav/facebook-clone, **giay phep
MIT**). Chi lay y tuong bo cuc; **khong copy code, khong them
dependency** — feed dx10 viet bang React + token thiet ke Apple-style
san co cua dx10, khong dung Next.js/Tailwind cua Kinfolk.

## 9. Dang nhap OTP + tab Quan ly + xem log terminal (quy tac 55–56)

**Dang nhap (quy tac 55).** Mo web UI len thi gap man hinh dang
nhap truoc, khong vao thang giao dien. Bam "Gui ma OTP qua
Telegram" — bot gui 1 ma 6 so ve chat Telegram da cau hinh
(`telegram.chat_id`). Ma chi song **60 giay**, dung **1 lan**;
nhap sai toi da **5 lan** thi ma bi huy. Gui ma qua nhanh thi bi
chan ~15 giay (429 + `retry_after`). Neu Telegram chua cau hinh
hoac gui loi: server **in ma ra cua so terminal dang chay server**
(de doc truc tiep) va man hinh dang nhap bao user doc ma o
terminal — giao dien khong bao gio bi khoa vi thieu Telegram.
Ma OTP va token phien **chi nam trong bo nho server** (khong ghi
file, khong ghi log, khong tra ve trong response API); phien la
cookie httpOnly `dx10_session`. **Tat server/host la dang xuat**
(khoi dong lai server thi het phien, phai dang nhap lai) — ngoai
ra co nut **Dang xuat** o header luc nao cung thay. Nut chon
ngon ngu VI | EN van hien tren man hinh dang nhap va o header.
Moi `/api/*` (tru 3 route auth) doi cookie phien hop le, khong
thi tra 401 JSON, khong traceback.

**Tab Quan ly (quy tac 56).** Sau khi dang nhap, tab **Quan ly**
la trang chinh: the trang thai (MT5, Live, Listener, Telegram,
kill switch, von quy) + cac nut bat dau chay: **Bat/Tat Live**
che do recommend (`POST /api/live/start {"mode":"recommend"}` —
mac dinh recommend, lenh chi dat qua nut Telegram), **Bat/Tat
Telegram listener**, **Chay kiem tra he thong** (`POST
/api/diagnostics` — chay `test_run.py` che do an toan, khong dat
lenh), **Gui tin Telegram thu** (`POST /api/telegram-test`),
**bat/tat kill switch**. Moi nut hien lai ly do (`reason`) tra ve
tu backend.

**Xem log terminal (quy tac 56).** Trong tab Quan ly co khung
terminal: chon tien trinh (Live / Telegram / Kiem tra he thong),
poll `GET /api/logs?process=...&after=...` moi ~2 giay, hien ~200
dong moi nhat (nen toi, chu monospace, tu cuon xuong co nut tam
dung). Tren khung co dong trang thai: dang chay / da dung, gio
bat dau, ma thoat — de biet dang chay o buoc nao, ket qua ra sao
(`test_run.py` in buoc `[n/8]`; vong live in tung vong). Log chi
luu trong bo nho server (vong dem ~500 dong / tien trinh, khong
ghi file); chi gom log cua tien trinh duoc quan ly (live,
listener, diagnostics) — dong khoi dong cua chinh server webapi
van chi o cua so console.

## Tai lieu lien quan

- `docs/trading-principles.md` quy tac 47–48 (web UI, UI dung
  lai kiem tra cua backend), quy tac 51–52 (song ngu + tin doi),
  quy tac 53–54 (feed bai dang phan tich + dedupe + Telegram),
  quy tac 55–56 (dang nhap OTP + tab Quan ly + log terminal).
- `docs/dx10-flow.md` — flow van hanh 24/7 (live + listener).
- `docs/live-loop.md` §6 — che do khuyen nghi + nut dat lenh.
- `docs/muse-browser.md` — gui briefing cho Muse qua trinh duyet.
- `docs/analysis-workflow.md` — workflow PTKT + PTCB + tong hop.
