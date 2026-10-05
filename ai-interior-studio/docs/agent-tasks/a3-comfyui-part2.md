# Đề bài A3 phần 2: đưa ComfyUI vào API (trước cổng G2)

Giao: A0, 05/10/2026. Người làm: Codex. Nhánh: `wt/a3-part2`.

## Bối cảnh

Đợt 0 đã chạy thật (`docs/gates/G0.md`): workflow `workflows/comfyui/flux2_klein_4b_preview.json` + manifest `workflows/manifests/flux2_klein_4b_preview.json`, ComfyUI ở `http://127.0.0.1:8188`, model ở `D:\ComfyUI\models`. Thời gian đo: lần lạnh (nạp model) 113 s ở 1024, lần nóng 27-31 s ở 1024, 61 s ở 1536. `ComfyUIProvider` đã có (phần 1) nhưng API chưa dùng.

## Việc phải làm

1. **Đăng ký provider** (`services/api/app.py`, mục NÊN SỬA #5 của `docs/agent-reviews/a3-comfyui.md`):
   - Khi `providers is None`, thêm `ComfyUIProvider` **trước** Gemini (ComfyUI là đường preview mặc định; thứ tự danh sách là thứ tự ưu tiên của `select_provider`). Thứ tự cuối: mock, comfyui, gemini — giữ mock ở đầu vì test hiện tại dựa vào nó; nếu thấy thứ tự này sai thì ghi vào note, không tự đổi hành vi mock.
   - Ảnh đầu vào đọc qua `_ManagerImages(app)` giống Gemini.
   - Cấu hình qua `load_config()` (`AI_STUDIO_COMFYUI_CONFIG`). Khi không có file cấu hình: `manifest` mặc định `flux2_klein_4b_preview.json`; `manifest_dir`/`workflow_dir` tính theo **gốc dự án** (thư mục chứa `services/`), không theo thư mục làm việc hiện tại. `models_dir` để trống nếu không cấu hình (preflight tra qua `object_info`).
   - ComfyUI không chạy thì `/providers` báo `unavailable`/`degraded` và app không sập; job vẫn chạy được qua provider khác.
2. **Cache preflight** (NÊN SỬA #2): `health()` cache kết quả 30 s (cấu hình được). Trong thời gian cache không gọi lại `/object_info`. Kết quả lỗi kết nối không cache quá 5 s để bật ComfyUI lên là thấy ngay.
3. **Timeout** (NÊN SỬA #4): `JobManager` đang cắt job ở 120 s, lần chạy lạnh mất 113 s và 1536 lạnh sẽ quá. Cho `create_app` nhận timeout từ biến môi trường `AI_STUDIO_JOB_TIMEOUT_S`, mặc định 600 s; `ComfyUIConfig.timeout_s` mặc định 600 s. Giá trị truyền tường minh vào `create_app(timeout=...)` vẫn thắng.

Không làm: thống nhất bộ cỡ ảnh 1024/1536 với 1K/2K/4K (NÊN SỬA #3, cần đề xuất hợp đồng); SeedVR2 provider (Đợt 3); sửa giao diện.

## Phạm vi file

`services/api/app.py`, `services/providers/comfyui/*`, `tests/unit/comfyui/*`, `tests/unit/api/*` (hoặc nơi test API đang nằm), `docs/agent-notes/a3-comfyui-part2.md`. Không sửa file khác; cần thì ghi vào note.

## Tiêu chí xong

- Test mới (dùng `httpx.MockTransport`/fake, không cần ComfyUI thật):
  - `create_app()` mặc định có provider id `comfyui`, đứng trước `gemini`.
  - ComfyUI không kết nối được → `/providers` trả 200, comfyui không `ok`; job mock vẫn tới REVIEW.
  - Gọi `health()` 2 lần trong 30 s → `object_info` chỉ bị gọi 1 lần; sau khi hết hạn cache thì gọi lại.
  - Lỗi kết nối chỉ cache ≤ 5 s.
  - `AI_STUDIO_JOB_TIMEOUT_S` được đọc; tham số tường minh thắng.
- Toàn bộ test cũ xanh, kể cả `tests/integration` (chạy backend thật bằng `create_app` mặc định). Máy này có ComfyUI thật đang chạy ở 8188: test không được gửi job thật tới đó. Nếu integration cần, cho phép tắt ComfyUI bằng biến môi trường (ví dụ `AI_STUDIO_COMFYUI_CONFIG` trỏ URL không tồn tại) và ghi vào note.
- Note bàn giao ghi rõ đã làm gì, còn nợ gì.

## Lệnh test

```
cd ai-interior-studio
python -m pytest -q
```
