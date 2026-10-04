# Trạng thái

Cập nhật 05/10/2026. Đợt hiện tại: **Đợt 2** — G1 đã duyệt 05/10/2026 (`docs/gates/G1.md`).

| Agent | Đợt | Trạng thái | Nhánh | Vướng mắc |
| --- | --- | --- | --- | --- |
| A1 Nền tảng | 1 | Xong, 155 test xanh; `docs/contracts.md` đã duyệt 05/10/2026 | main | - |
| A2 API & Job | 1 | Xong, review ĐẠT, đã merge `main` (175 test xanh) | đã xoá `wt/a2-api` | 4 mục NÊN SỬA trong `docs/agent-reviews/a2-api.md` chuyển cho A3/A4 |
| A9 Kiểm thử | 1 | Xong Đợt 1: test tích hợp backend thật + G1 ĐẠT, đã merge (180 test xanh) | đã xoá `wt/a9-g1` | Bộ ảnh chuẩn chặn bởi Đợt 0 |
| Đợt 0 kiểm chứng tay | 0 | Chưa bắt đầu | - | Cần NGUYEN chạy trên máy có GPU |

## Đề bài đang mở

Không có. A9 đóng (`docs/agent-tasks/a9-g1.md`, `docs/gates/G1.md`). A2 đóng (đề bài `docs/agent-tasks/a2-api.md`, note `docs/agent-notes/a2-api.md`, review `docs/agent-reviews/a2-api.md`).

## Ghi chú A0

- Repo chưa có `.gitignore` ở lần kiểm đầu; đã thêm để chặn `*.egg-info`, `.venv`, cache và dữ liệu chạy thử.
- Nhánh agent dùng quy ước máy `wt/<tên>` (tạo bằng `agent-wt`), thay cho `agent/<tên>` trong kế hoạch; ý nghĩa giữ nguyên: mỗi agent một nhánh.
- A2: Codex viết code nhưng hết hạn mức trước khi commit; A0 commit hộ nguyên văn và tự duyệt. A9 cần kiểm độc lập ở G1.
