# Nhận định Forex — Yuling Pan (mô phỏng)

- Tác giả: Yuling Pan — CEO, chuyên môn Forex. Ngày: 2026-11-26.
- **Đây là bài mẫu mô phỏng, không có giá thật, không phải khuyến nghị đầu tư.**

## Lý thuyết áp dụng
Xu hướng + động lượng: chỉ khi SMA ngắn hạn vượt SMA dài hạn và RSI
không quá mua thì mới xem xét tín hiệu mua (xem `src/diamondx10/models/quant.py`).

## Nhận định mẫu
Theo khung lý thuyết này, desk Forex theo dõi các cặp chính, ưu tiên
giao dịch thuận xu hướng, cắt lỗ theo ATR. Quyết định cụ thể xem
`decisions/decisions-log.csv`.
