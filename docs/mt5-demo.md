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

Volume mac dinh duoc tinh tu von desk (500 USD) va
`max_risk_per_trade_pct` (1%) trong config, lam tron xuong buoc 0.01 lot.
Muon tu chon volume: them `--volume 0.01`.

## 5. Gioi han can biet

- **Chi demo:** neu tai khoan dang nhap khong phai demo (trade_mode
  khac DEMO, hoac server chua "Real"), hoac config ghi `demo_only: false`
  hay `provider: live`, tool tu choi gui lenh ngay — co test bao phu.
- **Chung khoan My tren Exness MT5 demo co the thieu symbol:** NVDA, AMD
  thuong co, **CDNS co the khong co** tren server demo. Chay
  `mt5-symbols` de kiem tra; neu thieu thi doi symbol cho desk
  us_securities hoac dung nguon du lieu khac cho desk do.
- **Von desk nho, rui ro 1% rat chat:** von 500 USD/desk, lo toi da
  5 USD/lenh. Voi stop loss 2% va lot toi thieu 0.01, nhieu symbol
  (Forex, XAUUSD) se tinh ra volume < 0.01 lot — luc do tool se khong
  dat lenh va bao volume = 0. De giao dich demo duoc thi can siet stop
  loss lai (vi du 0.2–0.5%), hoac chap nhan rui ro/lenh cao hon 1%,
  hoac doi symbol co bien dong phu hop hon. Day la gioi han that cua
  von nho, khong phai loi code.
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
