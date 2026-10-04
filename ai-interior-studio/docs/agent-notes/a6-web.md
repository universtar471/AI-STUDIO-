# wt/a6-web

- Agent: claude (thay Codex hết hạn mức)
- Tách từ: main, sau đó merge main có thêm `GET /projects/{id}/scenes` và `GET /style-packs/{id}/versions` (A0 thêm trước để A6 không sửa backend)

## Đã xong (đối chiếu tiêu chí)

- [x] `npm install`, `npm run build`, `npm test` chạy trên Windows (Node 24): build OK, `8 passed`. README ghi lệnh.
- [x] Làm trọn bằng chuột với backend mock, đã chạy trong trình duyệt thật: tạo dự án → thêm 2 cảnh → tạo Style Pack, thả 2 ảnh (Ảnh phong cách chính, Sàn) → v1..v3, mở lại v2 chỉ đọc → Tạo ảnh 2 cảnh cùng lúc → Lịch sử thấy "Chờ chạy → Đang chạy → Chờ duyệt" trực tiếp qua WebSocket → mở job, thanh so sánh với ảnh gốc → Duyệt; job khác → Làm lại → tự chuyển sang job mới r2, r3, so sánh được với r1/r2.
- [x] Kiểu TS sinh từ OpenAPI (`src/api/types.ts`), không viết tay model.
- [x] Provider không hỗ trợ chế độ/tỉ lệ/cỡ/seed/số ảnh tham chiếu bị ẩn; provider tính phí ghi "(tính phí)", provider lỗi bị khóa.
- [x] Bảng Nâng cao mặc định đóng. Ảnh 4K qua provider tính phí hỏi xác nhận trước khi gửi `confirm_high_cost`.

## Chưa làm / cho A0

- **Reject**: state machine không có đường REVIEW → bị loại (chỉ APPROVED hoặc RETRY), nên giao diện chỉ có Duyệt / Làm lại. Muốn nút "Loại" thì cần đề xuất đổi hợp đồng.
- Chưa có URL cho từng dự án: tải lại trang thì về danh sách dự án.
- Thanh so sánh dùng ảnh thật; với MockProvider ảnh kết quả là 1 màu phẳng.
- Kiểm tra bằng tay đã dùng JavaScript để nạp file vào ô chọn file (hộp chọn file của Windows không điều khiển tự động được); kéo thả thì dùng sự kiện drop thật.

## Cạm bẫy

- Máy này có `GEMINI_API_KEY` thật trong môi trường: provider Gemini hiện "ok". Khi thử nghiệm hãy chọn provider `mock` trong Nâng cao để không tốn tiền.
- `vite.config.ts` không nằm trong `tsc` (dùng `process.env`, không muốn thêm `@types/node`).

## Lệnh test

```
cd ai-interior-studio\apps\web
npm install
npm test
npm run build
```
