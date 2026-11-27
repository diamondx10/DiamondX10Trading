# Flow van hanh dx10 (DiamondX10 Trading) — 24/7

`dx10` = DiamondX10 Trading (ten gon tu 2026-11-27). Day la flow DA
CHINH theo thuc te code hien tai — nhung cho nao mo ta cu chua dung
thi ghi ro o duoi.

## 0. Khoi dong (1 lan, tren may Windows)

1. Mo MT5 terminal Exness, dang nhap tai khoan DEMO (giữ terminal mở).
2. Chay `quickstart.bat` (nhap doi) hoac `python quickstart.py`:
   quet terminal -> cai goi -> kiem tra demo -> dry-run -> chay bo
   kiem tra `test_run.py` (buoc 7).
3. Chay vong live che do de xuat + trinh nghe Telegram (2 cua so):
   ```
   python quickstart.py --live --recommend-only
   set PYTHONPATH=src
   python -m diamondx10 telegram-listen
   ```
   (`quickstart.py` tu them src/ vao duong dan nen khong can
   PYTHONPATH; moi lenh `python -m diamondx10 ...` chay truc tiep
   deu can `set PYTHONPATH=src` truoc — PowerShell:
   `$env:PYTHONPATH = "src"`.)
   Muon 24/7 that thi may phai luon bat; dung Task Scheduler de tu
   chay lai khi khoi dong may (xem cong thuc trong `docs/mt5-demo.md`).

**3 thu chay song song tren CUNG 1 may Windows:** (1) MT5 terminal
Exness (demo), (2) dx10 live recommend mode, (3) dx10 telegram-listen.
`quickstart` / `test_run.py` chi chay 1 lan luc khoi dong, khong chay
24/7.

## 1. PTKT — lay chart live tu MT5, phan tich offline (tu dong)

Moi nen M15, vong live lay nen truc tiep tu MT5 terminal (MT5Feed)
cho tung symbol cua tung desk, tinh offline trong tool: SMA5/20, RSI,
ATR, ADX regime, mau hinh nen (engulfing, hammer, doji...), ho
tro/khang cu -> tin hieu BUY / SELL / HOLD. Khong can mang ngoai, khong
can AI.

## 2. PTCB — tin tuc -> Muse phan tich (BAN tu dong qua trinh duyet — xem ky)

**Diem can sua so voi mo ta cu:** khau nay truoc day hoan toan
thu cong vi khong co API de tool goi Muse. Nay da co cach **ban
tu dong**: dx10 dieu khien cua so Chromium (Playwright) de gui
file briefing vao chat Muse va doi verdict tra ve (xem
`docs/muse-browser.md`). Van **KHONG co API** — gui can cua so
trinh duyet headed + phien dang nhap Muse cua user (dang nhap
tay 1 lan, phien luu local o `data/muse-profile`), va luong tra
ve (doc verdict tu chat) chi la best-effort: neu hong thi quay
ve nap tay bang `verdict --file`.

1. Truoc phien (hoac dinh ky), chay lenh lay tin + briefing,
   gui luon cho Muse — chay tay 1 lan:
   ```
   python -m diamondx10 briefing --all --send   # hoac --desk forex --send
   ```
   hoac chay **tu dong theo lich** bang lenh moi `muse-auto`
   (Task Scheduler 2–3 lan/ngay, truoc phien A + truoc phien My —
   cong thuc day du xem `docs/muse-browser.md` §8):
   ```
   python -m diamondx10 muse-auto --all --wait-min 10
   ```
   File ra o `briefings/briefing-<desk>-<gio>.md` (+ `.json`).
   Khong muon gui tu dong thi bo `--send`, gui tay nhu cu.
2. Tool gui file briefing vao chat Muse (cua so Chromium mo
   len, user nhin thay duoc — `muse-auto` chay headless mac
   dinh, dung lai phien dang nhap da luu san).
3. Muse phan tich voi vai Kathy / Yumi / Rich tuy desk, tra ve
   **verdict JSON** (huong mua/ban/trung lap, do tin cay, ly do, rui ro).
4. Tool doi verdict trong chat (mac dinh toi da 10 phut), lay
   khoi ```json cuoi cung, kiem tra bang `validate_verdict`
   roi nap vao `decisions/fundamental-verdicts.json`.
   **Fallback:** het gio doi, doc khong duoc verdict, hay
   verdict khong hop le thi lenh thoat 1 (`muse-send`) — Phu copy
   verdict JSON tu chat roi nap tay:
   ```
   python -m diamondx10 verdict --file verdict-forex.json
   ```
   Rieng `muse-auto` (chay dinh ky): het gio doi verdict chi la
   CANH BAO, lenh thoat 0 vi briefing da gui — vong live van dung
   verdict cu, khong bao gio bi chan vi thieu verdict moi. Trang
   thai moi lan chay ghi vao `decisions/fa-cycle-state.json`
   (de web UI hien thi). Phien Muse het han thi `muse-auto` gui
   canh bao Telegram (tieng Anh) de Phu dang nhap lai bang tay.
   Verdict co han 24 gio (quy tac 39). Vong live chi DOC verdict da
   nap — no khong tu di lay tin, khong tu nap verdict chua kiem tra.

Nhip thuc te de xuat: briefing + verdict moi buoi truoc phien (dau
phien My / dau phien A), hoac moi 24h; co tin dot xuat thi briefing
them 1 desk. Voi `muse-auto` + Task Scheduler thi nhip nay chay tu
dong (vd 06:30 ICT truoc phien A, 21:00 ICT mua dong / 20:00 ICT
mua he truoc phien My — xem `docs/muse-browser.md` §8).

## 3. Tong hop — Muse + tool, moi ben 1 nua (can sua mo ta cu)

- **Muse tong hop PTCB tung desk** (Kathy / Yumi / Rich) tu briefing.
- **Tong hop CUOI (TA + PTCB -> khuyen nghi) la TOOL lam**, theo ma
  tran cua Yuling (quy tac 39, muc `synthesis:` trong config): trong
  vong live (cong FA, buoc 6b) hoac lenh `synthesize`. Muse trong chat
  co the tong hop bang loi them, nhung quyet dinh vao lenh cua tool
  dua tren code, khong dua tren chat.

## 4. Khuyen nghi qua Telegram (chi o che do recommend)

Tin hieu BUY/SELL qua du 7 cong (kill switch, drawdown, margin, gioi
han ngay, cua so cam, cong FA, tin hieu) thi o che do recommend
(`live --recommend-only` hoac `trading.require_confirmation: true`):
tool KHONG dat lenh ngay — no tao lenh cho (het han 15 phut) roi gui
khuyen nghi Telegram kem nut **Place order / Ignore** (tieng Anh).

O che do auto mac dinh thi nguoc lai: tool tu dat lenh roi moi bao
Telegram (tin chi la thong bao, khong co nut).

## 5. Vao lenh — bam nut, dx10 vao lenh tren MT5 demo

1. Phu bam **Place order** tren Telegram.
2. `telegram-listen` (dang chay) nhan callback, kiem tra lai: kill
   switch TAT, tai khoan DEMO, du margin, gia thi truong lech khoi
   gia khuyen nghi <= 1%.
3. Dat duoc thi dx10 vao lenh tren MT5 demo **theo gia thi truong
   luc bam** (khong phai dung gia entry da bao — co chan lech 1%),
   ghi log `ORDER-PLACED-VIA-TELEGRAM`, sua tin thanh
   `ORDER PLACED — ticket #X`, go nut.
4. Bam **Ignore** thi lenh cho bi huy. Bam sau 15 phut thi het han.

## Tu dong vs thu cong (tom tat)

| Buoc | Tu dong? |
|---|---|
| Quet terminal, dry-run, test | 1 lan luc khoi dong (`quickstart`) |
| Lay chart MT5 + PTKT moi nen M15 | Tu dong (vong live) |
| Lay tin + tao briefing | Tu dong (`muse-auto` theo lich Task Scheduler) hoac thu cong (`briefing`, truoc phien) |
| Gui briefing cho Muse, nhan verdict | Tu dong (`muse-auto` / `briefing --send` / `muse-send`, luong tra ve best-effort; hong thi nap tay `verdict --file`) |
| Nap verdict vao tool | Tu dong khi `muse-send` / `muse-auto` doi duoc verdict hop le; thu cong (`verdict --file`) khi doi that bai |
| Tong hop TA+PTCB | Tu dong (tool, ma tran Yuling) |
| Gui khuyen nghi Telegram | Tu dong (che do recommend) |
| Vao lenh | Nguoi bam nut (listener dat lenh) |

## Nhung gi chua co (noi thang)

- Khong co cach nao de tool goi Muse qua API — chi co tu dong hoa
  trinh duyet (mo muse.ai, gui file, doc verdict tu chat). Gui can
  cua so headed + phien dang nhap cua user; luong tra ve la
  best-effort, neu muse.ai doi giao dien thi hong va phai nap tay
  bang `verdict --file` (xem `docs/muse-browser.md`). Muon PTCB chay
  lien tuc thi lap lai buoc 2 theo nhip phien (muc 2) — nay da co
  `muse-auto` + Task Scheduler de lap lich tu dong, nhung ban chat
  van la tu dong hoa trinh duyet, khong phai API.
- Tool khong tu khoi dong lai khi may tat / mat dien — can may luon
  bat + Task Scheduler.
