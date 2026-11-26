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

## 0. Chay nhanh — quickstart.py (khuyen dung)

Tren may Windows co MT5 terminal, chi can:

```bash
python quickstart.py
```

Script se tu: cai `requirements.txt` + `MetaTrader5`; hoi server demo,
so login demo va mat khau demo luc chay (mat khau nhap an, chi giu trong
bo nho luc chay, KHONG ghi vao file); ghi `config.yaml` local; dang nhap
MT5 va kiem tra chac chan la tai khoan DEMO; kiem tra symbol; roi dry-run
tin hieu cho ca 4 desk. Mac dinh KHONG dat lenh. Muon dat lenh demo thi
chay `python quickstart.py --trade` roi go ro `dat lenh` de xac nhan.

```bash
python quickstart.py --skip-install   # bo qua buoc cai goi pip
```

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
