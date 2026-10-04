# Trạng thái

Cập nhật 05/10/2026. Đợt hiện tại: **Đợt 1** (A2 đang được giao).

| Agent | Đợt | Trạng thái | Nhánh | Vướng mắc |
| --- | --- | --- | --- | --- |
| A1 Nền tảng | 1 | Xong, 155 test xanh; `docs/contracts.md` đã duyệt 05/10/2026 | main | - |
| A2 API & Job | 1 | Đã giao cho Codex, đang làm | `wt/a2-api` | Codex hết hạn mức thì Claude làm tiếp |
| A9 Kiểm thử | 1 | Chưa bắt đầu; nhận việc khi A2 có API chạy được | - | - |
| Đợt 0 kiểm chứng tay | 0 | Chưa bắt đầu | - | Cần NGUYEN chạy trên máy có GPU |

## Đề bài đang mở

- A2: `docs/agent-tasks/a2-api.md`

## Ghi chú A0

- Repo chưa có `.gitignore` ở lần kiểm đầu; đã thêm để chặn `*.egg-info`, `.venv`, cache và dữ liệu chạy thử.
- Nhánh agent dùng quy ước máy `wt/<tên>` (tạo bằng `agent-wt`), thay cho `agent/<tên>` trong kế hoạch; ý nghĩa giữ nguyên: mỗi agent một nhánh.
