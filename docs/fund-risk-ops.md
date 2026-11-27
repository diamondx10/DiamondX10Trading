# Rủi ro và vận hành cấp quỹ — Phase F

> Tài liệu vận hành cho 3 thứ Phase F thêm vào tool: giới hạn rủi ro
> toàn quỹ, kill switch (nút dừng khẩn cấp) và audit log, cộng báo cáo
> ngày tự động. Trạng thái: **demo-only** (Exness demo + MT5), không
> bao giờ giao dịch tiền thật.
>
> **[CẦN CHỐT]** Các con số giới hạn quỹ mặc định dưới đây **chưa được
> Phu duyệt** — đó là giá trị thận trọng đề xuất, chờ Phu duyệt mới
> thành quy tắc chính thức (xem `docs/trading-principles.md` mục 33).
> Đừng trình bày chúng như quy tắc đã chốt.

---

## 1. Giới hạn rủi ro toàn quỹ

Nằm trong `src/diamondx10/risk.py` (`fund_limits_from_config`,
`check_fund_limits`, `today_pnl_from_log_rows`), cấu hình ở mục `risk:`
trong `config.yaml` (xem `config.example.yaml`). Kiểm tra chạy trong
`live.process_symbol` **trước khi mở lệnh mới** (gate 2c, ngay sau chặn
drawdown và kill switch), theo đúng pattern gate Phase 4: bị chặn thì
ghi log decision + audit, không crash.

| Giới hạn | Mặc định đề xuất | Cấu hình | Khi vượt |
|---|---|---|---|
| Lỗ trong ngày toàn quỹ | **3% vốn quỹ** (300 USD trên vốn 10.000 USD) | `risk.fund_daily_loss_pct` | Chặn mở lệnh mới toàn quỹ đến hết ngày; hôm sau tính lại từ đầu |
| Số vị thế mở toàn quỹ | **10 vị thế** (10 symbol trong danh mục → tối đa 1 vị thế/symbol) | `risk.max_open_positions_fund` | Chặn mở lệnh mới toàn quỹ |
| Số vị thế mở mỗi desk | **2 vị thế/desk** | `risk.max_open_positions_desk` | Chỉ chặn desk đó, desk khác vẫn mở được |

Mã chặn trong decisions log (cột action):

- `BLOCKED-DAILY-LOSS-FUND` — lỗ trong ngày chạm giới hạn.
- `BLOCKED-MAX-POSITIONS-FUND` — đủ số vị thế mở toàn quỹ.
- `BLOCKED-MAX-POSITIONS-DESK` — đủ số vị thế mở của desk đó.

**Lỗ trong ngày tính thế nào.** Cộng P&L đã thực hiện của các lệnh
đóng trong ngày, đọc từ decisions log: mỗi dòng `CLOSE` đều ghi
`P&L {pnl:.2f} USD` trong cột reason (do `positions._close_position`
và `realize_deals` ghi). Lệnh đang mở chưa tính — chỉ tính khi đã
đóng. Giới hạn so sánh theo **giá trị tuyệt đối**: lỗ đúng bằng giới
hạn cũng chặn (chạm mức là chặn). Ví dụ: vốn quỹ 10.000 USD, giới hạn
3% = 300 USD; hôm nay đã lỗ 350 USD → mọi lệnh mới đều bị chặn;
lỗ 250 USD → vẫn mở được.

**Giới hạn này không thay thế drawdown 10%** (mục 12 trong
trading-principles.md — đã chốt): drawdown tính từ đỉnh vốn, còn lỗ
ngày tính từ 0h00 hôm nay. Một ngày có thể chạm giới hạn lỗ ngày mà
chưa chạm drawdown, và ngược lại.

## 2. Kill switch — nút dừng khẩn cấp

Module `src/diamondx10/killswitch.py`, trạng thái lưu file JSON
`decisions/kill-switch.json`:

```json
{"engaged": true, "engaged_at": "2026-11-27T08:32:48+00:00",
 "reason": "su co thi truong", "by": "Phu"}
```

File chưa có = chưa bật. File hỏng (đọc không được) thì coi như chưa
bật — không bao giờ crash vòng live vì file trạng thái.

### Lệnh

```bash
python3 -m diamondx10 kill-switch status
python3 -m diamondx10 kill-switch on --reason "su co thi truong" --by "Phu"
python3 -m diamondx10 kill-switch off --by "Phu"
```

- `on` / `off` ghi audit (`KILL_SWITCH_ON` / `KILL_SWITCH_OFF`) và in
  trạng thái. `--reason` ghi lý do bật (nên ghi rõ để truy vết);
  `--by` ghi tên người bật/tắt (mặc định `operator`).
- `status` chỉ in trạng thái, không ghi gì.

### Khi bật thì chuyện gì xảy ra

- **Không mở lệnh mới nào nữa** — cả vòng `live` lẫn `mt5-trade`
  (dùng chung `process_symbol`): mỗi symbol trả
  `BLOCKED-KILL-SWITCH`, ghi log decision, không gửi lệnh lên MT5.
  `run_live_cycle` kiểm tra ngay đầu chu kỳ, in cảnh báo rõ và ghi
  log `KILL-SWITCH-ENGAGED`.
- **Vị thế đang mở vẫn được đối chiếu và đóng theo SL/TP đã có.**
  Đây là lựa chọn có chủ ý: kill switch dừng việc mở mới, không bỏ
  mặc vị thế đang mở không ai quản — lệnh đang mở vẫn chạm SL/TP thì
  đóng bình thường, vẫn ghi `CLOSE` và P&L vào guard.
- Tắt kill switch là giao dịch trở lại bình thường ngay chu kỳ sau;
  không cần khởi động lại tool.

### Ai được bật

Bất cứ ai chạy được lệnh trên máy live đều bật được — không có phân
quyền riêng. Thực tế chỉ Phu (hoặc người Phu chỉ định) bật/tắt, và
**luôn ghi `--reason` + `--by`** để audit log truy vết được ai dừng
hệ thống vì sao. Bật nhầm thì tắt lại là xong; không mất dữ liệu.

## 3. Audit log

Module `src/diamondx10/audit.py`, file append-only
`decisions/audit-log.jsonl` — mỗi dòng 1 JSON:

```json
{"ts": "2026-11-27T08:32:48+00:00", "actor": "Phu",
 "event": "KILL_SWITCH_ON",
 "details": {"reason": "su co thi truong", "by": "Phu"}}
```

Chỉ ghi thêm, không sửa/xóa dòng cũ. File này là file runtime, đã
gitignore (`decisions/audit-log.jsonl`, cùng với
`decisions/kill-switch.json`).

### Sự kiện nào được ghi

| Sự kiện | Khi nào |
|---|---|
| `KILL_SWITCH_ON` / `KILL_SWITCH_OFF` | Bật/tắt kill switch (CLI hoặc gọi hàm trực tiếp) |
| `FUND_LIMIT_BLOCKED` | Giới hạn quỹ chặn 1 lệnh mới (kèm desk, symbol, mã chặn, lý do) |
| `LIVE_CYCLE_STARTED` | Bắt đầu 1 chu kỳ live (kèm desk, timeframe, kill switch có bật không) |
| `LIVE_CYCLE_STOPPED` | Kết thúc 1 chu kỳ live — **chỉ ghi khi chu kỳ có giao dịch, có lệnh bị chặn, hoặc kill switch đang bật** (tránh spam chu kỳ HOLD) |
| `REPORT_GENERATED` | Chạy `report --save` (kèm đường dẫn file, ngày báo cáo) |

### Đọc audit log

```bash
python3 -m diamondx10 audit --lines 10   # 10 dòng gần nhất, mới nhất lên đầu
python3 -m diamondx10 audit              # mặc định 10 dòng
```

Đọc trực tiếp file cũng được: `decisions/audit-log.jsonl` (mỗi dòng
1 JSON, dòng mới nhất ở cuối file). Audit lỗi (không ghi được file)
không bao giờ crash vòng live — lỗi được bỏ qua lặng lẽ ở
`live.py`.

## 4. Báo cáo ngày tự động

Lệnh `report` đã có từ Phase 5, Phase F thêm 2 thứ:

```bash
python3 -m diamondx10 report
python3 -m diamondx10 report --save decisions/report-2026-11-27.md
```

- `--save PATH`: ghi báo cáo ra file **thay vì** in stdout; tự tạo
  thư mục cha nếu cần; ghi audit `REPORT_GENERATED`.
- Nội dung báo cáo thêm 3 mục: **trạng thái kill switch** (bật/tắt,
  lý do, người bật, lúc bật); **giới hạn quỹ** (giá trị cấu hình +
  trạng thái hiện tại: lỗ hôm nay so với giới hạn, số vị thế mở so
  với giới hạn toàn quỹ và từng desk); **5 dòng audit gần nhất**.

### Chạy tự động mỗi ngày

Báo cáo chạy sau phiên giao dịch (sau giờ đóng phiên Mỹ, khi không
còn chu kỳ live nào chạy nữa). Tool **không tự tạo** lịch chạy —
Phu tạo 1 lần trên máy chạy live:

**Windows Task Scheduler** (máy Windows chạy MT5 — máy live chính):

1. Create Task → Trigger: Daily, sau phiên (vd 05:30 ICT — sau khi
   phiên Mỹ đóng 04:00 ICT mùa đông / 03:00 ICT mùa hè; chọn giờ
   sau khi chu kỳ live cuối đã chạy xong).
2. Action: Start a program → Program: đường dẫn `python.exe` trong
   venv của tool; Arguments:
   ` -m diamondx10 report --save decisions\report-%DATE%.md`
   (chạy trong thư mục repo — đặt "Start in" là thư mục repo);
   vì `%DATE%` của Windows có định dạng tùy locale, nên đặt tên file
   cố định theo ngày bằng tay hoặc dùng script `.bat` nhỏ tự tạo tên
   `report-YYYY-MM-DD.md` từ ngày hiện tại.
3. Điều kiện: chỉ chạy khi máy đang bật; không cần chạy khi máy ngủ.

**cron trên Linux** (nếu máy live là Linux — hiện tại không phải):

```cron
30 22 * * * cd /duong/dan/DiamondX10Trading && /duong/dan/venv/bin/python -m diamondx10 report --save decisions/report-$(date +\%F).md
```

(giờ chạy: sau phiên, điều chỉnh theo múi giờ máy; `$(date +\%F)`
cho tên file `report-YYYY-MM-DD.md`).

File báo cáo lưu trong `decisions/` là file runtime, không commit —
muốn lưu trữ lâu dài thì copy ra ngoài repo hoặc gửi qua Telegram
(tự làm thêm, chưa có trong Phase F).

## 5. File và hàm liên quan

| File | Vai trò Phase F |
|---|---|
| `src/diamondx10/risk.py` | `fund_limits_from_config`, `check_fund_limits`, `today_pnl_from_log_rows`, `today_pnl_from_log` |
| `src/diamondx10/killswitch.py` | `engage`, `disengage`, `is_engaged`, `status` (mới) |
| `src/diamondx10/audit.py` | `log_event`, `read_events` (mới) |
| `src/diamondx10/live.py` | Gate kill switch (2b) + giới hạn quỹ (2c) trong `process_symbol`; kiểm tra kill switch đầu chu kỳ + audit STARTED/STOPPED trong `run_live_cycle` |
| `src/diamondx10/report.py` | `build_report`/`format_report` thêm kill switch + giới hạn quỹ + audit |
| `src/diamondx10/__main__.py` | Lệnh `kill-switch`, `audit`, cờ `report --save` |
| `config.example.yaml` | Mục `risk:` thêm `fund_daily_loss_pct`, `max_open_positions_fund`, `max_open_positions_desk` |
| `tests/test_fund_risk.py`, `tests/test_killswitch.py`, `tests/test_audit.py`, `tests/test_report_save.py` | Test Phase F (33 test) |

## 6. Chưa kiểm chứng live

- Chu kỳ live thật với kill switch bật trên máy Windows có MT5 demo:
  chưa chạy — cần máy Windows + MT5 demo (kill switch chỉ kiểm
  chứng bằng MT5 giả trong test).
- Báo cáo ngày tự động theo lịch Task Scheduler/cron: chưa tạo lịch
  thật — máy này không phải máy chạy live, Phu tạo lịch trên máy
  Windows theo mục 4.
- Giới hạn lỗ ngày trên dữ liệu thật: cách tính dựa vào dòng `CLOSE`
  trong decisions log (đã có sẵn từ Phase 4); chưa có ngày giao dịch
  thật nào lỗ đủ 300 USD để thấy chặn thật.
