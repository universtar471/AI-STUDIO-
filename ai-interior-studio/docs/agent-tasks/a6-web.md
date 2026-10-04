# Đề bài A6: Giao diện (Đợt 2)

Giao 05/10/2026 bởi A0. Nhánh `wt/a6-web`. Người làm: Claude (Codex hết hạn mức).

## Phạm vi file

Được sửa: `apps/web/`, `docs/agent-notes/a6-web.md`. Kiểu dữ liệu sinh từ `services/api/openapi.json` bằng `scripts/generate_types.py`, ghi vào `apps/web/src/api/types.ts`. Thiếu endpoint thì ghi vào note cho A0, không sửa backend.

## Việc (brief A6, Đợt 2, chạy trên MockProvider)

1. React + TypeScript + Vite.
2. Màn: Projects; Style Pack (kéo thả ảnh, gán vai trò); Generate; tiến độ thời gian thực qua `/ws/jobs`; History dạng lưới; Compare thanh trượt; Approve / Reject / Retry.
3. Bảng Advanced mặc định ẩn: provider, seed, prompt cuối sửa được.
4. Tùy chọn provider không hỗ trợ (theo `capabilities`) bị ẩn.

Không làm: đóng gói Tauri, trau chuốt thẩm mỹ.

## Tiêu chí xong

- [ ] `npm install`, `npm run build`, `npm test` chạy được trên Windows; README ghi lệnh.
- [ ] Làm trọn bằng chuột với backend mock: tạo project → import scene → Style Pack + ảnh → Generate → thấy tiến độ → History → Compare → Approve / Retry.
- [ ] Kiểu TS lấy từ OpenAPI, không viết tay lại model.
