# Phan tich ky thuat da khung thoi gian (MTF) — xu huong H1 + entry M15

> Quy tac goc: xem `docs/trading-principles.md` muc 64.
> Trang thai: **[ĐÃ CÓ — 2026-11-27]** (code: `multitimeframe.py`,
> `data/multitimeframe.py`, loc trong `signals.py`, boi canh htf
> trong `outcomes.py`, backtest MTF trong `backtest.py`).
>
> Quy uoc ngon ngu trong file nay: van viet tieng Viet co dau;
> ten khoa config / ten ham / ten khung thoi gian viet **khong dau**,
> dung nhu trong code va file YAML.

## 1. Stack v1 — moi khung mot viec

| Khung | Vai tro v1 | Ly do |
|---|---|---|
| **H1** | Xu huong (trend) — dat huong cho phep | Du dai de loc nhieu M15, du ngan de van phan anh phien hien tai |
| **M15** | Entry — tin hieu mua/ban nhu cu (muc 4) | Khung chinh cua vong live tu dau; moi gate rui ro van chay tren M15 |
| **M5** | Timing — NGOAI v1 | Tinh chinh diem vao la buoc toi uu sau; v1 chi can dung huong + dung entry |
| **H4** | NGOAI v1 | Cham hon H1 mot bac nhung them do tre va them du lieu can backfill; chi xem xet khi H1 da chung minh hieu qua |

Nguyen tac: **khung cao hon dat huong, khung thap hon cho diem vao**.
H1 khong bao gio tu tao tin hieu mua/ban; M15 khong bao gio duoc
di nguoc H1 khi H1 dang co xu huong manh.

## 2. Quy tac loc — khung cao hon dat huong cho phep

`compute_htf_trend(bars_h1)` tra ve:

```python
{"timeframe": "H1", "direction": "up" | "down" | "neutral" | "unknown",
 "adx": <ADX(14) cua H1>, "sma_fast": <SMA5>, "sma_slow": <SMA20>,
 "trusted": <adx >= htf_adx_min>, "bars": <so nen dung>,
 "reason": <giai thich>, "htf_adx_min": <nguong>}
```

- Huong: SMA nhanh > SMA cham → `up`; nguoc lai → `down`;
  bang nhau → `neutral`. SMA lay do dai tu tham so per-symbol da
  resolve khi co `cfg` + `desk` + `symbol`, khong thi 5/20.
- `trusted = adx >= htf_adx_min` (mac dinh 20). ADX tinh theo
  Wilder, chu ky 14 — cung ham nhu regime M15 (`models/quant.py`).
- Qua it nen (chua du tinh SMA/ADX) → `direction = "unknown"`,
  `trusted = False`.

`htf_filter(action, trend)` — bang cho phep / chan day du:

| Trend H1 | BUY | SELL | Ghi chu ghep vao reason |
|---|---|---|---|
| (khong co trend) | cho phep | cho phep | (khong ghi chu) |
| `unknown` | cho phep | cho phep | `[HTF H1: thieu du lieu — khong ap dung loc]` |
| khong `trusted` (ADX thap) | cho phep | cho phep | `[HTF H1: ADX thap ({adx:.1f} < {min}) — khong ap dung loc]` |
| `up` | cho phep | **chan** | BUY: `[HTF H1: trend UP, ADX {adx:.1f} — dong thuan]`; SELL: `[HTF H1: trend UP — khong SELL]` |
| `down` | **chan** | cho phep | SELL: `[HTF H1: trend DOWN, ADX {adx:.1f} — dong thuan]`; BUY: `[HTF H1: trend DOWN — khong BUY]` |
| `neutral` | cho phep | cho phep | `[HTF H1: trend trung lap — cho phep]` |
| (action la HOLD) | — | — | loc khong ap dung, `(True, "")` |

Hieu ung trong `generate_signals(..., htf_trend=trend)`:

- Tin hieu M15 BUY/SELL bi chan → thanh **HOLD**, `levels = None`,
  ghi chu HTF ghep vao `reason`. HOLD khong duoc ghi vao outcome
  log (nhu moi HOLD khac) — vong hoc khong biet minh da bo lo bao
  nhieu co hoi, chi biet lenh da vao thi hieu qua ra sao.
- Tin hieu dong thuan giu nguyen action, kem ghi chu dong thuan.
- Ket qua them khoa `"htf_trend"` (dict trend nguyen ven).

Ba truong hop loc KHONG chan — chi abstain (khong ap dung):

1. **ADX H1 yeu** (`adx < htf_adx_min`): xu huong khong du manh
   de tin; loc dung ngoai thay vi doan huong.
2. **Thieu du lieu H1**: xuong muc 5.
3. **Trend trung lap** (`neutral`): khong co huong de chan.

Ly do abstain thay vi chan: chan khi khong chac chan se bien loc
thanh cam giao dich trong thi truong di ngang — dung truong hop
M15 van kiem duoc tien. Loc chi chan khi co bang chung manh rang
huong M15 dang di nguoc xu huong lon.

## 3. Config — muc `timeframes:`

```yaml
timeframes:
  entry: M15          # khung entry — khong doi, vong live chay tren nay
  trend: H1           # khung xu huong
  timing: M5          # khung timing — NGOAI v1, chi de san cho sau
  trend_enabled: true # bat loc HTF
  timing_enabled: false
  htf_adx_min: 20     # ADX H1 toi thieu de trend duoc tin
  trend_bars: 60      # so nen H1 lay de tinh trend
```

- Thieu ca muc `timeframes:` → M15-only nhu cu, loc tat
  (`resolve_timeframes({})` tra `trend_enabled: False`).
- `trend_enabled: false` → tat loc ma khong can xoa muc config.
- `timing_enabled` luon `false` o v1; bat len khong co tac dung
  cho den khi logic timing M5 duoc viet.

## 4. Moi khung de lam gi — tom tat van hanh

- **H1 — dat huong.** Moi chu ky live, lay `trend_bars` nen H1,
  tinh trend mot lan cho moi symbol. Chi co 4 gia tri huong
  (`up` / `down` / `neutral` / `unknown`) + do tin cay ADX.
- **M15 — quyet dinh.** Tin hieu, gate ADX/ATR%, soft rule,
  tong hop FA, size, SL/TP — tat ca van chay tren M15 nhu cu.
  HTF chi la mot buoc loc truoc khi tin hieu di tiep.
- **M5 — chua dung.** Ghi san trong config de sau nay them buoc
  tinh chinh diem vao (vi du: cho pullback M5 truoc khi vao lenh
  M15) ma khong doi schema.
- **H4 — chua dung.** Chi xem xet neu walk-forward cho thay H1
  chua du (muc 8).

## 5. Override HTF theo symbol — dung co che `strategy.per_symbol` co san

Khong co bang HTF rieng. Do dai SMA va nguong ADX cua trend H1
lay tu tham so per-symbol da resolve cho symbol do
(`resolve_strategy_params`, thu tu mac dinh < chung < desk <
symbol — xem `docs/per-symbol-ta.md` §1–§2). Vi du: EURUSD dung
SMA 8/21 thi trend H1 cua EURUSD cung dung 8/21; BTCUSD giu
5/20. `htf_adx_min` la nguong chung trong muc `timeframes:`;
muon nang nguong cho mot symbol thi dung gate `adx_min` cua
symbol do (muc 61) thay vi them khoa HTF rieng.

## 6. Ghi log + hoc — boi canh htf trong outcome, lat cat trong ta-review

Moi khuyen nghi TRADED/RECOMMENDED duoc ghi kem boi canh htf
(`outcomes.py`, `build_record`):

```python
"context": {
    ...
    "htf": {"timeframe": "H1", "direction": "up" | "down"
            | "neutral" | "unknown",
            "adx": <ADX H1>, "trusted": True | False,
            "agreement": "agree" | "against" | "neutral"
                         | "not_applied"},
}
```

- `agreement`: `agree` — tin hieu cung huong trend H1;
  `against` — tin hieu nguoc trend (chi xay ra khi loc khong ap
  dung: ADX thap / thieu du lieu / trend tat); `neutral` — trend
  trung lap; `not_applied` — khong co trend H1 (loc tat hoac
  chay M15-only).
- `ta-review` chia them lat cat **theo dong thuan HTF**
  (`breakdowns["htf_agreement"]`): win rate / profit factor /
  expectancy cua nhom `agree` so voi `against` / `neutral` /
  `not_applied`, moi con so kem `n`; lat cat `n <
  min_sample_for_proposal` (mac dinh 20) thi "chua du mau",
  khong de xuat. Lat cat nay tra loi cau hoi: loc HTF co dang
  giu lai nhung lenh tot va loai lenh xau khong — hay chi lam
  giam so lenh mot cach mu quang. **Trang thai 2026-11-27: lat
  cat nay duoc dinh nghia o day, phan `ta_review.py` chua ha
  canh — `outcomes.py` da ghi `context["htf"]` nen du lieu de
  chia lat cat da co san.**

## 7. Quy trinh Windows — backfill roi moi live

Tren may Windows (MT5 Exness demo mo san, xem
`docs/dx10-flow.md`):

1. Backfill ca hai khung truoc khi bat live:
   `backfill --timeframes M15,H1` (mac dinh chi M15; them H1
   de co du `trend_bars` nen cho trend — 60 nen H1 ≈ 2,5 ngay).
2. Chay live nhu cu: `live --recommend-only` (+ `telegram-listen`).
   Vong live tu lay nen H1 qua `fetch_bars_for_timeframes`
   (xem muc 5 — thieu H1 thi chay tiep M15-only, khong dung vong).
3. Kiem tra bang `ta-review` sau khi du mau (≥ 20 lenh moi lat
   cat) truoc khi ket luan loc co ich hay khong.

## 8. Gioi han that — doc truoc khi tin loc HTF

- **Loc lam giam so lenh.** Chan tin hieu nguoc xu huong dong
  nghia voi viec bo lo cac dao chieu that: day la cai gia cua
  loc. Neu H1 doi huong cham, M15 co the cho tin hieu dao chieu
  dung trong khi loc van chan — do la truong hop loc thua.
- **Loc khong phai bao dam.** Trend H1 manh khong dam bao M15
  di cung huong; ADX cao chi noi xu huong H1 dang manh, khong
  noi no se tiep tuc. Tin hieu dong thuan van thua nhu thuong.
- **Chua kiem chung tren thi truong that.** Muc 61–63 da noi:
  moi con so deu la diem xuat phat. Loc HTF can walk-forward
  theo tung symbol (so sanh co loc / khong loc, OOS) truoc khi
  tin — neu walk-forward noi loc khong cai thien expectancy
  thi tat loc (`trend_enabled: false`), khong co gang giu.
- **Chi hoc tu lenh da vao.** HOLD do HTF chan khong duoc ghi
  log, nen `ta-review` khong do duoc "lenh bi chan thi ra sao".
  Muon biet loc co bo lo co hoi tot khong thi phai chay backtest
  MTF so sanh (`backtest.py`, che do MTF) chu khong chi doc
  bao cao review.

## 9. File lien quan

- `src/diamondx10/multitimeframe.py` — `resolve_timeframes`,
  `compute_htf_trend`, `htf_filter`.
- `src/diamondx10/data/multitimeframe.py` —
  `fetch_bars_for_timeframes`.
- `src/diamondx10/signals.py` — `generate_signals(htf_trend=...)`.
- `src/diamondx10/outcomes.py` — `build_record`, context `"htf"`.
- `src/diamondx10/backtest.py` — che do backtest MTF.
- `src/diamondx10/ta_review.py` — lat cat `htf_agreement`.
- `config.example.yaml` — muc `timeframes:`.
- `docs/trading-principles.md` muc 64.
- `docs/per-symbol-ta.md` — tham so per-symbol ma HTF tai su dung.
- `docs/ta-learning-loop.md` — vong hoc doc boi canh htf.
- `tests/test_multitimeframe_integration.py` — test tich hop
  end-to-end (dong thuan / nguoc xu huong / thieu nen H1).
