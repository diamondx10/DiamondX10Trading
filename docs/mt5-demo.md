# MT5 Demo — Exness demo + MetaTrader 5

> **CHI DEMO.** Connector nay chi chay voi tai khoan DEMO Exness.
> Khong bao gio dat lenh that. Xem chan DEMO-ONLY trong
> `src/diamondx10/execution.py` (co test trong `tests/test_mt5.py`).

## Hien trang

Tool co 2 che do du lieu:

| Provider | Du lieu | Can gi |
|---|---|---|
| `simulated` (mac dinh) | Gia mo phong, sinh ngau nhien | Khong can gi them, chay duoc o dau cung duoc |
| `mt5` | Gia that theo thoi gian thuc tu MT5 terminal | MT5 terminal + tai khoan demo Exness, chay cung may voi tool |

Ban demo / backtest / signals cu van chay voi `simulated` nhu truoc,
khong anh huong gi.

## 0. Chay nhanh — quickstart.bat / quickstart.py (khuyen dung)

Tren may Windows co MT5 terminal, chi can **nhap doi vao `quickstart.bat`**
— khong can Python hay pip san. File `.bat` se tu tim Python 3.10+,
neu chua co thi tu cai Python 3.12 (qua winget; neu khong co winget thi
tai bo cai chinh thuc tu python.org va cai lang, khong can quyen admin),
roi chay `quickstart.py`. Neu may da co Python thi chay thang:

```bash
python quickstart.py
```

Script chay theo thu tu: **chuan bi xong moi hoi dang nhap**.
0. Kiem tra Python >= 3.10. 1. Tu dong cai `requirements.txt` +
`MetaTrader5` (cai loi thi dung ngay). 2. **Tu dong quet tim MT5
terminal roi kiem tra noi duoc khong** (`mt5.initialize(path=...)`);
terminal chua cai / chua mo thi dung ngay va huong dan cai/mo — chua
hoi gi ve tai khoan. Thu tu tim terminal: (1) bien moi truong
`MT5_TERMINAL_PATH` (neu dat va file ton tai); (2)
`mt5.terminal_path` trong `config.yaml` cu (neu dat va file ton tai);
(3) cac duong dan da biet — truoc het vi tri chinh
`C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe`, roi
`C:\Program Files\MetaTrader 5\terminal64.exe` va cac bien the o
`Program Files (x86)`; (4) quet 1 cap trong `Program Files` /
`Program Files (x86)` / `ProgramW6432` / `LOCALAPPDATA` tim
`*/terminal64.exe`, uu tien thu muc co ten chua "Exness", roi
"MetaTrader", roi "MT5". Duong dan tim thay duoc ghi vao
`mt5.terminal_path` trong `config.yaml` local o buoc 4 (ghi bang dau
`/`, vd `C:/Program Files/MetaTrader 5 EXNESS/terminal64.exe`); de
trong thi moi lan chay lai tu quet. Neu duong dan da chon ma
`initialize(path=...)` that bai thi tool BAO LOI chu khong tu doi
sang terminal mac dinh (co the nham broker khac) — xoa dong
`terminal_path` trong `config.yaml` local hoac chay lai
`quickstart.py` de quet lai. 3. Hoi server demo,
so login demo va mat khau demo luc chay (mat khau nhap an, chi giu trong
bo nho luc chay, KHONG ghi vao file). 4. Ghi `config.yaml` local.
5. Dang nhap MT5, kiem tra chac chan la tai khoan DEMO, kiem tra symbol.
6. Dry-run tin hieu cho ca 4 desk. 7. Cai dat Telegram (hoi token bot +
chat_id, ghi `config.yaml` local) roi **chay bo kiem tra `test_run.py`**
— co buoc LOI thi hoi co tiep tuc khong, khong tiep tuc thi dung lai
truoc khi dat lenh/chay live. 8. Tuy chon: `--trade` / `--live-once` /
`--live`. Mac dinh KHONG dat lenh.

Cac che do them:

```bash
python quickstart.py --check-only   # chi buoc 0-2: cai goi + kiem tra
                                    # terminal, khong hoi dang nhap
python quickstart.py --skip-install # bo qua buoc cai goi pip
python quickstart.py --trade        # sau dry-run, go ro "dat lenh"
                                    # moi dat lenh DEMO
python quickstart.py --live-once    # sau dry-run, go ro "chay live"
                                    # moi chay 1 chu ky live M15,
                                    # ca 4 desk (co the dat lenh DEMO)
python quickstart.py --live         # nhu tren nhung chay vong lap live
                                    # M15 lien tuc cho 1 desk
                                    # (chon desk luc chay, Ctrl+C de dung)
```

Khi chay `--live` / `--live-once`, script hoi them Telegram bot token
(Enter de bo qua) de gui canh bao trong vong live; token chi giu trong
bo nho luc chay, khong ghi vao file. Muon chay live tu dong moi 15 phut
tren Windows, dung Task Scheduler (1 tac vu / desk), vd:

```powershell
schtasks /create /tn "DiamondX10-live-forex" /tr "python -m diamondx10 live --once --desk forex" /sc minute /mo 15
```

Xem them `docs/live-loop.md` (vong live, canh bao, kill switch) va
`docs/fund-risk-ops.md` (gioi han quy, audit log).

## 0b. Kiem tra truoc khi chay that — test_run.py

`quickstart.py` **tu chay bo kiem tra nay o buoc 7** (sau khi setup
xong, truoc khi dat lenh/chay live); dung `--skip-tests` de bo qua.
Chay rieng tren may Windows (sau khi `quickstart.py` chay xong) cung
duoc — no tu kiem tra moi truong, cau hinh, ket noi MT5, symbol,
nen + tin hieu, kho lich su, Telegram (gui 1 tin thu) va bao cao ngay,
roi dump tat ca ra 1 file log. Buoc [2] cung tu quet tim terminal
(cung thu tu uu tien nhu quickstart buoc 2) roi noi bang
`mt5.initialize(path=...)`, va buoc [4] mo feed bang chinh duong dan
do.

```bash
python test_run.py                  # chi kiem tra, KHONG dat lenh
python test_run.py --with-tests     # them bo test pytest
python test_run.py --live-once      # them 1 chu ky live M15, ca 4 desk
                                    # (CO THE dat lenh DEMO — phai go ro
                                    # "chay live" moi chay)
```

Log ghi ra `logs/test-run-YYYYMMDD-HHMMSS.log` (da gitignore qua `*.log`),
cuoi log co bang TONG KET (PASS/FAIL/SKIP) va danh sach buoc loi. Log
**khong bao gio chua token Telegram hay mat khau MT5** (tu dong che
truoc khi ghi). Gui file log do cho Muse de debug — khong can che them
gi. Neu buoc nao FAIL, sua theo huong dan trong log truoc khi chay live
that (vd thieu token thi dat bien moi truong `DIAMONDX10_TELEGRAM_TOKEN`,
chua co kho thi chay `backfill`).

## 1. Tao tai khoan Exness demo

1. Vao trang Exness, tao tai khoan demo (khong nap tien that).
2. Chon nen tang **MT5**, ghi lai 3 thong tin: **so login**, **mat khau**,
   **ten server demo** (vd `Exness-MT5Trial7` — ten that xem trong
   email Exness gui hoac trong MT5 terminal).
3. Tai MT5 terminal ve may se chay tool (Windows), dang nhap bang
   3 thong tin tren, doi MT5 tai xong du lieu lich su cho cac symbol.

## 2. May nao chay tool?

**MT5 terminal va tool Python phai chay tren CUNG 1 may** (thuong la
may Windows, hoac VPS Windows). Ly do: goi Python `MetaTrader5` chi
noi duoc voi terminal dang chay local, khong noi qua mang duoc.

May Linux / VM khong co MT5 terminal thi chi chay duoc che do
`simulated` — khong test duoc ket noi MT5 that o do. Code MT5 o day
duoc test bang MT5 gia (`tests/test_mt5.py`), khong can terminal that.

## 3. Cai dat tren may Windows chay MT5

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install MetaTrader5
copy config.example.yaml config.yaml
```

Mo `config.yaml` (file local, **khong commit**) va dien:

```yaml
data:
  provider: mt5          # doi tu simulated sang mt5
mt5:
  demo_only: true        # giu nguyen true — chi demo
  login: 12345678        # so tai khoan DEMO Exness cua ban
  server: "Exness-MT5Trial7"   # ten server demo that cua ban
  timeframe: M15
```

Mat khau demo — **khong ghi vao file, khong gui trong chat**:

```powershell
setx MT5_PASSWORD "mat-khau-demo-cua-ban"
```

(Dong terminal mo lai de bien moi truong co hieu luc.)
Neu muon, co the them dong `password: ...` vao `config.yaml` local,
nhung bien moi truong van la cach khuyen dung.

## 4. Chay thu — dry-run truoc, dat lenh sau

```powershell
# 1. Kiem tra symbol nao co tren server demo (CDNS co the khong co)
python -m diamondx10 mt5-symbols

# 2. Dry-run: lay gia that, in tin hieu, KHONG dat lenh
python -m diamondx10 mt5-dry-run --desk forex --symbol EURUSD
python -m diamondx10 mt5-dry-run --desk xauusd
python -m diamondx10 mt5-dry-run --desk crypto --symbol BTCUSD
python -m diamondx10 mt5-dry-run --desk us_securities --symbol NVDA

# 3. Dat lenh DEMO (chi khi dry-run dung): tin hieu BUY/SELL moi dat lenh,
#    HOLD thi khong dat. Len nao cung co stop loss, ghi vao decisions log.
python -m diamondx10 mt5-trade --desk forex --symbol EURUSD
```

Volume mac dinh duoc tinh tu von desk (2.500 USD, chia deu cho cac
symbol cua desk) va `max_risk_per_trade_pct` (1%) trong config, lam tron
xuong buoc 0.01 lot. Muon tu chon volume: them `--volume 0.01`.

## 5. Gioi han can biet

- **Chua kiem chung ten symbol that tren server demo:** viec kiem tra
  cac symbol BNBUSD / SNPS / INTC / CDNS co that tren server demo
  Exness hay khong van can chay `mt5-symbols` tren may Windows co
  MT5 terminal — chua lam o day (VM Linux nay khong co MT5 terminal),
  va test chi dung MT5 gia. Xem them muc "pending" o cuoi file.
- **Chi demo:** neu tai khoan dang nhap khong phai demo (trade_mode
  khac DEMO, hoac server chua "Real"), hoac config ghi `demo_only: false`
  hay `provider: live`, tool tu choi gui lenh ngay — co test bao phu.
- **Chung khoan My tren Exness MT5 demo co the thieu symbol:** NVDA, AMD
  thuong co, **CDNS co the khong co** tren server demo. Chay
  `mt5-symbols` de kiem tra; neu thieu thi doi symbol cho desk
  us_securities hoac dung nguon du lieu khac cho desk do.
- **Rủi ro theo từng symbol — mọi symbol đặt được ít nhất 0,01 lot,
  mức chung vẫn là 1%/lệnh:** EURUSD 3% (0,01 lot, lỗ tối đa 75 USD),
  XAUUSD 10% (0,01 lot, 250 USD), BTCUSD 8% (0,01 lot, 67 USD),
  ETH 0,05 lot, BNB 0,18 lot, nhóm chứng khoán 0,22–2,50 lot — tất cả
  tính ở stop 5%, đã kiểm chứng bằng code. Trước đó nhóm đã thử một con
  số chung 10% cho mọi lệnh rồi bỏ, vì nó bắt cả những mã không cần phải
  chịu rủi ro cao. **Còn một điểm nhóm cần biết:** một lệnh vàng thua là
  lỗ 250 USD = 10% vốn desk = đúng giới hạn drawdown tối đa, nên desk
  vàng coi như chỉ được phép thua 1 lệnh trước khi chạm giới hạn.
- **Kiểm soát rủi ro lúc chạy (Phase 4):** trước khi đặt lệnh mới, tool
  đối chiếu vị thế mở theo nến mới (chạm SL/TP, trailing SL, đảo chiều —
  log `CLOSE` kèm P&L), rồi chặn lệnh mới khi drawdown chạm giới hạn quỹ
  10% / cảnh báo desk 5% (`BLOCKED-DRAWDOWN-FUND` / `BLOCKED-DRAWDOWN-DESK`),
  khi trong cửa sổ cấm giao dịch (`BLOCKED-NO-TRADE-WINDOW`, danh sách
  `no_trade_events` trong config, mặc định rỗng), hoặc khi đã đặt 1 lệnh
  cho symbol đó trong ngày (`BLOCKED-DAILY-LIMIT`). Trước khi gửi lệnh,
  tool kiểm tra ký quỹ bằng `mt5.order_check` (`BLOCKED-MARGIN` khi
  không đủ; ở chế độ mô phỏng thì bỏ qua và ghi rõ). Vị thế mở và đường
  cong vốn lưu ở `decisions/equity-state.json` (file runtime, không commit).
- **MT5 terminal phai mo trong suot luc chay tool.** Tat terminal la
  mat ket noi du lieu va khong dat lenh duoc.
- **Khong co gia that / lenh that trong repo:** repo chi co code va
  du lieu mo phong. Gia that chi xuat hien luc chay tren may cua ban,
  voi tai khoan demo cua ban.

## 6. Quy trinh lam viec (LJ / Kel)

- **LJ (data scientist):** model / chien luoc trong `strategies/`,
  tin hieu trong `signals.py` — khong doi khi them MT5.
- **Kel (data analysis):** du lieu trong `data/` (`MT5Feed`,
  kiem tra symbol) va khop lenh trong `execution.py`.
- **Yuling:** nghien cuu ly thuyet, duyet chien luoc truoc khi cho
  chay `mt5-trade` tren demo.
- Quyet dinh mua/ban nao cung ghi vao `decisions/decisions-log.csv`
  va thong bao nhu cu.

## 7. Pending — can chay tren may Windows co MT5

- **Kiem chung ten symbol that tren server demo Exness:** cac symbol
  BNBUSD / SNPS / INTC / CDNS co that tren server demo hay khong van
  chua duoc kiem tra. Can chay `python -m diamondx10 mt5-symbols`
  tren may Windows co MT5 terminal dang nhap tai khoan demo Exness.
  **Khong lam o day** — VM Linux nay khong co MT5 terminal nen khong
  ket noi that duoc; test trong repo chi dung MT5 gia (FakeMT5).
