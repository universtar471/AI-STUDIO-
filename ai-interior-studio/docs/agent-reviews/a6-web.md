# Duyệt A6 Giao diện (`wt/a6-web`)

A0 (Claude), 05/10/2026. Claude vừa viết vừa duyệt (Codex hết hạn mức); A9 kiểm lại ở G2.

## Kết luận: ĐẠT

- 3/3 tiêu chí trong `docs/agent-tasks/a6-web.md`: build và `npm test` (8 passed) chạy trên Windows; luồng chuột đầy đủ đã chạy tay trong trình duyệt với backend mock; kiểu TS sinh từ OpenAPI.
- Chỉ chạm `apps/web/` và note. Hai endpoint thiếu do A0 thêm riêng (`wt/a0-lists`) trước khi làm.

## NÊN SỬA

1. Không có nút "Loại" vì hợp đồng không có REVIEW → bị loại. Nếu chủ dự án cần, ghi đề xuất vào `docs/contract-requests.md`.
2. Chưa có địa chỉ riêng cho từng dự án (tải lại trang về danh sách dự án).
3. `apps/web/src/components/ProjectView.tsx`: gọi `refetch` bên trong hàm cập nhật state; StrictMode chạy hai lần nên có thể gọi API hai lần. Không sai dữ liệu, chỉ thừa một request.
