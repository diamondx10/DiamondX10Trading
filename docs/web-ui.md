# Web UI dx10 — giao dien web quan ly giao dich

Giao dien web cho dx10: xem trang thai quy, vi the, tin hieu, tong hop
TA+PTCB, duyet / bo lenh cho, bat tat kill switch, tao briefing, gui
cho Muse, nap verdict, xem tin + backtest + bieu do nen — tat ca tu
trinh duyet, khong can go lenh CLI.

> Da doi chieu 2026-11-27: danh sach endpoint o muc 4 khop 1-1 voi route
> table trong `src/diamondx10/webapi.py` (25 route).

## 1. Chay

Cai phu thuoc web UI 1 lan (them vao `requirements.txt`):

```
pip install -r requirements.txt
```

Chay server:

```
python -m diamondx10.webapi [--port 8000] [--host 127.0.0.1]
```

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

Goc: `http://127.0.0.1:8000`. Tat ca tra JSON.

| Phuong thuc | Duong dan | Dung de lam gi |
|---|---|---|
| GET | `/api/status` | Trang thai quy: von, drawdown, kill switch, MT5, Telegram, live/listener co dang chay khong |
| GET | `/api/positions` | Vi the dang mo |
| GET | `/api/signals?desk=` | Tin hieu TA moi nhat theo desk (`forex` / `gold` / `crypto` / `securities`) |
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

## 5. Lam duoc / khong lam duoc

Lam duoc:

- Xem trang thai, vi the, tin hieu, tong hop, tin tuc, backtest,
  bieu do nen, lich su quyet dinh.
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

## 6. Bao mat — localhost-only, khong co auth

- Server mac dinh chi bind `127.0.0.1` (localhost), **khong co
  dang nhap**. Ai mo duoc port 8000 tren may do thi bam nut dat
  lenh duoc nhu Phu — cung ranh gioi nhu dashboard chi doc
  (`dashboard.py`).
- **Khong mo port ra ngoai, khong bind `0.0.0.0`**, khong mo
  firewall cho port nay, khong chay tren may dung chung ma khong
  khoa man hinh. Can xem tu xa thi dung remote desktop vao may
  Windows do, khong phoi API ra internet.
- Khong co token, mat khau hay du lieu phien dang nhap trong doc
  nay hay trong code frontend — token Telegram va mat khau MT5 van
  chi qua bien moi truong luc chay nhu cu.

## Tai lieu lien quan

- `docs/trading-principles.md` quy tac 47–48 (web UI, UI dung
  lai kiem tra cua backend).
- `docs/dx10-flow.md` — flow van hanh 24/7 (live + listener).
- `docs/live-loop.md` §6 — che do khuyen nghi + nut dat lenh.
- `docs/muse-browser.md` — gui briefing cho Muse qua trinh duyet.
- `docs/analysis-workflow.md` — workflow PTKT + PTCB + tong hop.
