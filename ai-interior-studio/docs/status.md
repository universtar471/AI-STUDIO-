# Trạng thái

Cập nhật 05/10/2026. Đợt hiện tại: **Đợt 2** — A4, A5, A6 xong và đã merge (213 test Python + 8 test web). **Cổng G2 chưa chạy được**: chờ Đợt 0 (workflow ComfyUI + 5 cảnh + Style Pack) để làm A3 và bộ ảnh chuẩn.

| Agent | Đợt | Trạng thái | Nhánh | Vướng mắc |
| --- | --- | --- | --- | --- |
| A1 Nền tảng | 1 | Xong, 155 test xanh; `docs/contracts.md` đã duyệt 05/10/2026 | main | - |
| A2 API & Job | 1 | Xong, review ĐẠT, đã merge `main` (175 test xanh) | đã xoá `wt/a2-api` | 4 mục NÊN SỬA trong `docs/agent-reviews/a2-api.md` chuyển cho A3/A4 |
| A9 Kiểm thử | 1 | Xong Đợt 1: test tích hợp backend thật + G1 ĐẠT, đã merge (180 test xanh) | đã xoá `wt/a9-g1` | Bộ ảnh chuẩn chặn bởi Đợt 0 |
| A3 ComfyUI | 2 | Phần 1 (adapter, manifest, preflight; test bằng ComfyUI giả) đã giao Codex | `wt/a3-comfyui` | Workflow thật + model chờ Đợt 0 |
| A4 Gemini | 2 | Xong, review ĐẠT, merge (Claude làm) | đã xoá | Chưa gọi Gemini thật lần nào |
| A5 Prompt & Reference | 2 | Xong, review ĐẠT, merge (Claude làm) | đã xoá | Orchestrator chưa dùng A5 (nối cùng A3) |
| A6 Giao diện | 2 | Xong, review ĐẠT, merge (Claude làm); đã chạy tay trong trình duyệt | đã xoá | Chưa có nút Loại (hợp đồng không có) |
| Đợt 0 kiểm chứng tay | 0 | Chưa bắt đầu | - | Cần NGUYEN chạy trên máy có GPU |

## Đề bài đang mở

- A3 phần 1: `docs/agent-tasks/a3-comfyui.md` (Codex).
- A0 nối A5 vào orchestrator + NÊN SỬA A2: `docs/agent-tasks/a0-orchestration-prompts.md` (Claude, song song).
- A9 Đợt 2 (bộ ảnh chuẩn, `run_golden`, cổng G2): chờ Đợt 0 và A3.

Đã đóng: A4, A5, A6 (đề bài, note, review trong `docs/agent-*`). A0 thêm vào API: đăng ký Gemini, `GET /projects/{id}/scenes`, `GET /style-packs/{id}/versions`. A9 đóng (`docs/agent-tasks/a9-g1.md`, `docs/gates/G1.md`). A2 đóng (đề bài `docs/agent-tasks/a2-api.md`, note `docs/agent-notes/a2-api.md`, review `docs/agent-reviews/a2-api.md`).

## Ghi chú A0

- Repo chưa có `.gitignore` ở lần kiểm đầu; đã thêm để chặn `*.egg-info`, `.venv`, cache và dữ liệu chạy thử.
- Nhánh agent dùng quy ước máy `wt/<tên>` (tạo bằng `agent-wt`), thay cho `agent/<tên>` trong kế hoạch; ý nghĩa giữ nguyên: mỗi agent một nhánh.
- A2: Codex viết code nhưng hết hạn mức trước khi commit; A0 commit hộ nguyên văn và tự duyệt. A9 cần kiểm độc lập ở G1.
