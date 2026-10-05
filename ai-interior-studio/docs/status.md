# Trạng thái

Cập nhật 05/10/2026. Đợt hiện tại: **Đợt 2, kiểm cổng G2** (`docs/gates/G2.md`): phần chức năng ĐẠT (giao diện → ComfyUI thật → duyệt; tắt ComfyUI app vẫn chạy). **G0 và G2 chờ 3 cảnh SketchUp nữa (đang 2/5) và chủ dự án chấm ảnh.** 273 test Python xanh. Đã sửa các ghi nhận G2: huỷ job gửi `/interrupt` sang ComfyUI, health kiểm lại khi mất kết nối, cảnh báo VRAM thấp (DEGRADED), mock chỉ bật bằng `AI_STUDIO_ENABLE_MOCK=1`.

| Agent | Đợt | Trạng thái | Nhánh | Vướng mắc |
| --- | --- | --- | --- | --- |
| A1 Nền tảng | 1 | Xong, 155 test xanh; `docs/contracts.md` đã duyệt 05/10/2026 | main | - |
| A2 API & Job | 1 | Xong, review ĐẠT, đã merge `main` (175 test xanh) | đã xoá `wt/a2-api` | 4 mục NÊN SỬA trong `docs/agent-reviews/a2-api.md` chuyển cho A3/A4 |
| A9 Kiểm thử | 1-2 | G1 ĐẠT. Đợt 2: `golden.json` + `run_golden` (báo cáo HTML so lần trước), G2 đã kiểm (Claude làm) | đã xoá | Ảnh chuẩn để ở `data/golden/` (repo công khai, không commit ảnh); mới 2/5 cảnh |
| A3 ComfyUI | 2 | Phần 1-3 xong (Codex viết, review ĐẠT, merge): đăng ký trong API, cache preflight, timeout 600 s, huỷ thật, cảnh báo VRAM | đã xoá | NÊN SỬA còn lại: `docs/agent-reviews/a3-comfyui-part2.md`, `docs/gates/G2.md` mục Ghi nhận |
| A4 Gemini | 2 | Xong, review ĐẠT, merge (Claude làm) | đã xoá | Chưa gọi Gemini thật lần nào |
| A5 Prompt & Reference | 2 | Xong, review ĐẠT, merge (Claude làm) | đã xoá | Orchestrator chưa dùng A5 (nối cùng A3) |
| A6 Giao diện | 2 | Xong, review ĐẠT, merge (Claude làm); đã chạy tay trong trình duyệt; thêm URL dự án `#/projects/<id>` | đã xoá | Chưa có nút Loại (hợp đồng không có) |
| Đợt 0 kiểm chứng tay | 0 | Kỹ thuật xong (A0): 2 workflow API JSON + manifest thật, preview 1024 ~30 s, 1536 ~60 s, SeedVR2 2048 ~30-50 s, VRAM < 10 GB; vá A3 NÊN SỬA #1 (ô tham chiếu trống dùng ảnh base) | `wt/wave0` | Còn 3/5 cảnh chuẩn; 1 lần lỗi driver GPU chưa rõ nguyên nhân (xem G0.md) |

## Đề bài đang mở

- A0 nối A5 vào orchestrator + NÊN SỬA A2: xong, merge (218 test).
- G2: chạy lại `run_golden --provider comfyui` khi đủ 5 cảnh, chủ dự án chấm `report.html`.
- Còn mở trước Đợt 3: thống nhất cỡ ảnh 1024/1536 với 1K/2K/4K (cần đề xuất hợp đồng); gọi Gemini thật một lần (tốn phí, cần chủ dự án đồng ý).

Đã đóng: A4, A5, A6 (đề bài, note, review trong `docs/agent-*`). A0 thêm vào API: đăng ký Gemini, `GET /projects/{id}/scenes`, `GET /style-packs/{id}/versions`. A9 đóng (`docs/agent-tasks/a9-g1.md`, `docs/gates/G1.md`). A2 đóng (đề bài `docs/agent-tasks/a2-api.md`, note `docs/agent-notes/a2-api.md`, review `docs/agent-reviews/a2-api.md`).

## Ghi chú A0

- Repo chưa có `.gitignore` ở lần kiểm đầu; đã thêm để chặn `*.egg-info`, `.venv`, cache và dữ liệu chạy thử.
- Nhánh agent dùng quy ước máy `wt/<tên>` (tạo bằng `agent-wt`), thay cho `agent/<tên>` trong kế hoạch; ý nghĩa giữ nguyên: mỗi agent một nhánh.
- A2: Codex viết code nhưng hết hạn mức trước khi commit; A0 commit hộ nguyên văn và tự duyệt. A9 cần kiểm độc lập ở G1.
