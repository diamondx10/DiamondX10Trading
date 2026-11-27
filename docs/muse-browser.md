# Gui briefing cho Muse bang trinh duyet tu dong (Playwright + Chromium)

Khau PTCB truoc day chay hoan toan bang tay: Phu chay `briefing`,
gui file cho Muse trong chat, doi verdict JSON, roi nap bang
`verdict --file` (xem `docs/analysis-workflow.md` §2). Tu nay khau
gui + doi verdict co the chay **ban tu dong**: dx10 mo cua so
trinh duyet Chromium, gui file briefing vao chat Muse, doi Muse
tra verdict JSON, kiem tra roi nap vao tool.

**Noi thang: van KHONG co API nao de tool goi Muse.** Cach nay
dieu khien trinh duyet nhu nguoi dung (mo trang muse.ai, dang
file len chat, doc tin nhan tra ve). No chi tu dong hoa thao tac
tay, khong phai tich hop API.

dx10 la CLI, KHONG co cua so GUI rieng. "Mo trinh duyet" o day
nghia la dx10 khoi dong va dieu khien 1 cua so Chromium rieng
(che do headed de user nhin thay), khong phai nhung trinh duyet
vao trong dx10.

## 1. Cai dat 1 lan (`muse-setup`)

Playwright la phu thuoc **tu chon (opt-in)**, khong nam trong
luong cai dat mac dinh cua `quickstart.py` va khong can thiet
neu van muon gui briefing bang tay.

```bash
python -m diamondx10 muse-setup
```

Lenh nay lam 2 viec:

1. `pip install playwright`
2. `playwright install chromium` (tai ban Chromium rieng cua
   Playwright, khong dung trinh duyet san co cua may)

## 2. Dang nhap thu cong lan dau (chi 1 lan)

Chay 1 lenh gui o che do headed (mac dinh `muse.headless: false`):

```bash
python -m diamondx10 muse-send --file briefings/briefing-forex-20261127-0900.md --no-wait
```

Cua so Chromium mo len o trang `muse.chat_url` (mac dinh
`https://muse.ai`). **Phu dang nhap Muse bang tay trong cua so
do, mo chat chinh 1 lan.** Phien dang nhap duoc luu local vao
`muse.profile_dir` (mac dinh `data/muse-profile`) — lan sau
trinh duyet mo len da dang nhap san, khong can dang nhap lai.

Khong co mat khau nao duoc ghi vao config hay dua cho tool:
dang nhap la viec cua user trong trinh duyet, tool chi giu
nguyen phien da dang nhap do.

## 3. Lenh gui briefing

### `muse-send` — gui 1 file briefing co san

```bash
python -m diamondx10 muse-send --file briefings/briefing-forex-20261127-0900.md
python -m diamondx10 muse-send --file briefings/briefing-xauusd-20261127-0900.md --prompt "Phan tich voi vai Yumi, tra verdict JSON theo mau trong file."
python -m diamondx10 muse-send --file briefings/briefing-crypto-20261127-0900.md --wait-min 15
python -m diamondx10 muse-send --file briefings/briefing-forex-20261127-0900.md --no-wait
python -m diamondx10 muse-send --file briefings/briefing-forex-20261127-0900.md --headless
```

- `--file`: file briefing `.md` (bat buoc).
- `--prompt`: cau nhan gui kem file (tuy chon; mac dinh tool dung
  cau nhan chuan: phan tich voi vai nha phan tich cua desk va tra
  verdict JSON theo mau trong file).
- `--wait-min N`: so phut toi da doi verdict (mac dinh lay
  `muse.wait_min` trong config, mac dinh 10).
- `--no-wait`: chi gui file roi thoat ngay, khong doi verdict.
- `--headless`: chay trinh duyet ngam (chi dung khi phien dang
  nhap da luu san; lan dau phai chay headed de dang nhap).

### `briefing --send` — tao briefing roi gui luon

```bash
python -m diamondx10 briefing --desk forex --send
python -m diamondx10 briefing --all --send --wait-min 15
```

Tao briefing nhu binh thuong (`briefings/briefing-<desk>-<gio>.md`)
roi gui ngay file vua tao cho Muse, khong can chay 2 lenh rieng.

### Ma thoat (exit code)

- **0** chi khi: verdict da duoc kiem tra + luu vao tool,
  hoac `--no-wait` va file da gui thanh cong.
- **1** trong moi truong hop con lai: gui that bai, het gio doi
  ma chua co verdict, verdict tra ve khong hop le, hoac
  Playwright/Chromium chua cai (chay `muse-setup` truoc).

## 4. Luong tra ve (return leg): doi verdict nhu the nao

Sau khi gui file, tool doi trong cua so chat (`wait_for_verdict`):

1. Dinh ky doc tin nhan moi cua tro ly trong chat
   (mac dinh moi 10 giay, toi da `wait_min` phut).
2. Lay khoi ```json cuoi cung trong tin nhan moi nhat.
3. Kiem tra verdict bang `synthesis.validate_verdict` — cung
   ham kiem tra nhu lenh `verdict --file` (desk phai co,
   direction chi buy/sell/neutral, confidence 0..1, du truong).
4. Hop le thi luu vao `decisions/fundamental-verdicts.json`
   (gop theo desk, giu ban moi nhat moi desk) — xong thi lenh
   thoat 0.

### Mong manh o dau (doc ky)

- **Doc DOM la best-effort.** Tool doc tin nhan bang cach doc
  cau truc trang muse.ai. Neu muse.ai doi giao dien (doi ten
  lop, doi cach hien thi tin nhan, doi cach upload file) thi
  viec gui hoac doc co the hong ma khong bao truoc. Day la rui
  ro co huu cua tu dong hoa trinh duyet, khong phai loi cau hinh.
- **Verdict khong bao gio duoc luu khi chua kiem tra.**
  Khoi JSON doc duoc ma sai dinh dang, sai desk, sai direction
  hay confidence ngoai 0..1 thi bi loai, khong ghi vao file
  verdict — giong nhu `verdict --file` tu choi file loi.
- **Fallback luon co: `verdict --file`.** Gui that bai, het gio
  doi, hay doc khong duoc verdict thi quay ve luong tay:
  Phu copy verdict JSON tu chat Muse roi chay
  `python -m diamondx10 verdict --file verdict-forex.json`
  (xem `docs/analysis-workflow.md` §2c). Khong co verdict moi
  thi vong live van chay nhu cu, chi ghi `FA: chua co` /
  `FA: cu` (quy tac 39–40).

## 5. Bao mat

- **Phien dang nhap o local, khong bao gio commit.**
  `data/muse-profile/` chua cookie/phien dang nhap Muse cua
  user, da co trong `.gitignore`. Khong commit, khong gui,
  khong copy thu muc nay di dau.
- **Tool khong doc, khong copy phien dang nhap.**
  Tool chi bao trinh duyet dung profile do; no khong mo file
  profile de doc cookie hay token, khong gui session di dau.
- **Khong xu ly mat khau.** Tool khong hoi, khong nhan, khong
  luu mat khau Muse. Dang nhap lan dau la Phu lam bang tay
  trong cua so trinh duyet.
- **Khong co token hay chat ID trong config.**
  `config.example.yaml` (muc `muse:`) chi co URL chat, duong
  dan profile, co headed va so phut doi — khong co thong tin
  dinh danh hay bi mat nao.
- **Opt-in, khong ep buoc.** Chua chay `muse-setup` thi lenh
  `muse-send` / `briefing --send` bao loi sach (huong dan cai
  dat) thay vi crash; luong PTCB bang tay van dung nhu cu.

## 6. Cau hinh (`config.example.yaml`, muc `muse:`)

```yaml
muse:
  chat_url: https://muse.ai        # URL chat Muse mo trong trinh duyet
  profile_dir: data/muse-profile  # thu muc profile giu phien dang nhap (da gitignore)
  headless: false                 # false = mo cua so that de dang nhap/nhin thay
  wait_min: 10                    # so phut toi da doi verdict JSON sau khi gui
```

## 7. File lien quan

- `src/diamondx10/muse_browser.py` — `send_briefing`,
  `wait_for_verdict`.
- `src/diamondx10/muse_auto.py` — `cmd_muse_auto` (chu ky tu dong,
  xem §8).
- `src/diamondx10/synthesis.py` — `validate_verdict`,
  `save_verdict` (kiem tra + luu verdict).
- `docs/analysis-workflow.md` §2 — quy trinh PTCB day du
  (briefing -> verdict -> tong hop Yuling).
- `docs/dx10-flow.md` §2 — khau PTCB trong flow van hanh 24/7.
- `docs/trading-principles.md` muc 45–46, 49 — quy tac [DA CO] /
  [DA CHOT] cho tu dong hoa trinh duyet.

## 8. Chu ky tu dong (`muse-auto`) + Task Scheduler

`muse-send` / `briefing --send` gui 1 lan khi Phu chay tay.
`muse-auto` lap lai toan bo chu ky PTCB — tao briefing, gui,
doi verdict — cho 1 desk hoac tat ca 4 desk, de chay dinh ky
ma khong can ai ngoi canh:

```bash
python -m diamondx10 muse-auto --all --wait-min 10
python -m diamondx10 muse-auto --desk forex --wait-min 10
python -m diamondx10 muse-auto --all --headed   # mo cua so de nhin thay
```

- `--desk`: chi chay 1 desk (mac dinh: tat ca 4 desk, nhu `--all`).
- `--all`: chay tat ca 4 desk.
- `--wait-min N`: so phut doi verdict toi da moi desk (mac dinh lay
  `muse.wait_min` trong config, mac dinh 10).
- `--headless` / `--headed`: mac dinh `muse-auto` chay **headless**
  (trinh duyet an) — tac vu dinh ky khong co desktop tuong tac.
  `--headed` mo cua so that (dung khi dang nhap lan dau hoac muon
  nhin thay). **Cung 1 profile luu san (`muse.profile_dir`) chay
  duoc ca headed lan headless**: dang nhap headed 1 lan (§2) roi
  cac lan chay headless sau do dung lai phien do, khong can dang
  nhap lai — tru khi phien het han (xem duoi).

### Ma thoat

- **0** khi tat ca briefing da GUI duoc. Het gio doi verdict hay
  chua co verdict moi chi la **CANH BAO**, khong phai loi: vong live
  van chay voi verdict cu (quy tac 39–40), khong bao gio bi chan vi
  thieu verdict moi.
- **1** khi bat ky lenh gui nao that bai: loi trinh duyet, chua dang
  nhap, khong tim thay composer, hoac khong tao duoc briefing.

### Het phien dang nhap -> canh bao Telegram

Neu gui that bai vi phien Muse da het han (khong tim thay o nhap
tin nhan — co the dang o trang dang nhap), `muse-auto` gui them 1
canh bao Telegram (tieng Anh, theo quy tac 44): phien trinh duyet
Muse da het han, can dang nhap lai bang tay (chay `muse-send`
headed 1 lan, dang nhap vao muse.ai trong cua so trinh duyet).
Canh bao la best-effort: Telegram chua cau hinh thi lenh chi in ro
ra; loi Telegram khong bao gio che mat loi gui goc. Ma thoat van la 1.

### File trang thai chu ky

Sau moi lan chay, `muse-auto` ghi `decisions/fa-cycle-state.json`
(file runtime, da gitignore) de web UI hien thi trang thai lan
chay cuoi:

```json
{
  "started_utc": "2026-11-27T13:00:00+00:00",
  "desks": {
    "forex": {"sent": true, "verdict_stored": true,
              "reason": "verdict da luu — desk forex — direction buy (tin cay 0.8)"},
    "crypto": {"sent": true, "verdict_stored": false,
               "reason": "da gui briefing, het 10 phut cho verdict — chua co verdict moi..."}
  }
}
```

File nay chi co trang thai gui/nhan — **khong chua token, mat khau
hay du lieu phien** nao.

### Chay dinh ky bang Windows Task Scheduler

May Windows chay dx10 24/7 thi dat 1 tac vu chay `muse-auto`
2–3 lan/ngay, truoc moi phien (verdict co han 24 gio nen khong
can chay day hon):

| Trigger (vi du) | Gio ICT | Ly do |
|---|---|---|
| Truoc phien A | 06:30 hang ngay | Truoc mo cua Tokyo 9:00 JST = 7:00 ICT |
| Truoc phien My (mua dong, EST) | 21:00 hang ngay | Truoc mo cua My 9:30 ET = 21:30 ICT (EST: 1 Nov 2026 – 14 Mar 2027) |
| Truoc phien My (mua he, EDT) | 20:00 hang ngay | Truoc mo cua My 9:30 ET = 20:30 ICT (EDT: tu 14 Mar 2027) |

Them trigger **At log on** nua de may khoi dong lai / dang nhap
lai thi co ngay 1 chu ky. Cach tao (Task Scheduler -> Create
Task, khong phai Basic Task):

1. **General:** ten `DiamondX10 muse-auto`; chon **Run only when
   user is logged on**; chay bang **cung user Windows** da dang
   nhap Muse headed (§2) — vi profile trinh duyet (`data/muse-profile`)
   nam trong thu muc user do.
2. **Triggers:** nhu bang tren (Daily 06:30 + Daily 21:00 mua dong /
   20:00 mua he — sua gio khi My doi gio DST; + At log on).
3. **Actions:** Start a program — Program: duong dan day du toi
   `python.exe` (vd `C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe`);
   Arguments: `-m diamondx10 muse-auto --all --wait-min 10`;
   Start in: thu muc repo (vd `C:\Users\<user>\DiamondX10Trading`).
4. **Conditions:** may phai dang bat + user dang dang nhap (tac vu
   chi chay khi user session con ton tai — giu don gian, khong dung
   "Run whether user is logged on or not"). Neu la desktop/server
   luon bat thi bo tick "Start the task only if the computer is on
   AC power".

**Khong hua hon thuc te:** luong tra ve (doc verdict tu chat) van
la best-effort nhu §4 — neu muse.ai doi giao dien, het gio doi,
hay Muse tra verdict khong hop le thi chu ky do khong co verdict
moi, lenh thoat 0 (da gui) kem CANH BAO, vong live van dung verdict
cu; fallback luon la nap tay bang `verdict --file`. Chi can kiem
tra log / file `decisions/fa-cycle-state.json` sau vai lan chay
dau de chac tac vu chay dung.
