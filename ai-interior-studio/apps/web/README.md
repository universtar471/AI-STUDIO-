# apps/web

Giao diện AI Interior Studio (React + TypeScript + Vite). Chủ sở hữu: A6.

## Chạy (Windows PowerShell)

Cần Node 20 trở lên. Mở hai cửa sổ:

```powershell
# 1. Backend (từ thư mục ai-interior-studio)
.venv\Scripts\python -m services.api

# 2. Giao diện (từ thư mục ai-interior-studio\apps\web)
npm install
npm run dev
```

Mở http://localhost:5173. Vite chuyển các lời gọi API và WebSocket `/ws/jobs` sang backend `http://127.0.0.1:8000` (đổi bằng biến môi trường `AI_STUDIO_API`).

## Lệnh khác

```powershell
npm test          # vitest
npm run build     # kiểm kiểu TypeScript + build vào dist/
npm run gen:types # xuất lại openapi.json và sinh src/api/types.ts (cần Python của backend)
```

`src/api/types.ts` sinh tự động từ OpenAPI, không sửa tay.

## Luồng dùng

Dự án → Cảnh (thêm PNG xuất từ SketchUp) → Style Pack (kéo thả ảnh, chọn vai trò; mỗi lần thêm tạo phiên bản mới, bản cũ xem được) → Tạo ảnh (chọn nhiều cảnh, Style Pack; mục Nâng cao: nguồn chạy, provider, cỡ ảnh, seed, prompt cuối) → Lịch sử (tiến độ trực tiếp) → mở job: so sánh bằng thanh trượt với ảnh gốc hoặc lần chạy khác, Duyệt / Làm lại / Hủy.
