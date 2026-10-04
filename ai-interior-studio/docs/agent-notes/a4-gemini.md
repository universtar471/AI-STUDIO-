# wt/a4-gemini

- Agent: claude (thay Codex hết hạn mức)
- Tách từ: main `0137315` (đã có A5)

## Đã kiểm tài liệu Gemini (05/10/2026)

`ai.google.dev`: `gemini-3.1-flash-image` (Nano Banana 2) là model đa dụng; tối đa 14 ảnh tham chiếu; cỡ 1K/2K/4K; giá khoảng USD 0,067 / 0,101 / 0,151 mỗi ảnh. SDK `google-genai` 2.28: `client.aio.models.generate_content(model, contents, config=GenerateContentConfig(response_modalities=['IMAGE'], image_config=ImageConfig(image_size, aspect_ratio)))`. Tất cả nằm trong `GeminiConfig`, đổi bằng file JSON trỏ qua `AI_STUDIO_GEMINI_CONFIG`.

## Đã xong (đối chiếu tiêu chí)

- [x] SDK giả: 6 ảnh gửi đúng thứ tự base → STYLE_MASTER → APPROVED_VIEW → FLOOR → WALL → DECOR, prompt nêu đúng vai trò "Image 1..6": `test_six_images_keep_order_and_roles`.
- [x] Vượt trần ngày → job FAILED mã `GEMINI_DAILY_LIMIT` (`retryable=false`), chạy qua `JobManager` thật: `test_daily_limit_fails_job_with_clear_code`. 4K thiếu xác nhận → `HIGH_COST_NOT_CONFIRMED` ở `validate` và `submit`.
- [x] Không key → `health()` unavailable; orchestrator chọn MockProvider, Gemini không bị gọi.
- [x] Không test nào gọi mạng. Key giả không có trong `provider_request` hay lỗi; lỗi SDK chỉ giữ tên lớp exception.
- [x] Timeout thử lại tối đa `max_attempts`; gửi lại cùng request (cùng fingerprint) dùng lại lượt đang chạy, không trả tiền hai lần.
- [x] `pytest`: `210 passed, 1 warning`; quét key toàn repo: 0.

## Module

- `services/core/secrets`: `get_secret('gemini')` (env `GEMINI_API_KEY`, `GOOGLE_API_KEY`, rồi keyring dịch vụ `ai-interior-studio`), `set_secret`, `redact`.
- `services/providers/gemini`: `GeminiImageProvider(images, config, usage_path, api_key, client_factory)`, `StorageImageSource(db, store)`, `DailyUsage`, `GeminiConfig`/`load_config`.
- Dùng A5: `select_references` (slot = `max_reference_images` − 1 cho ảnh base) và `render_gemini`.
- Dependency mới: `google-genai`, `keyring`.

## Quyết định tự chọn

- Trần ngày đếm theo **lượt gọi API** (kể cả lần thử lại vì có thể bị tính tiền), theo ngày giờ máy. Mặc định 30/ngày.
- Đạt trần thì health vẫn OK (ghi số lượt còn lại) để job chọn Gemini rõ ràng thất bại với mã riêng, thay vì lỗi chung `NO_ELIGIBLE_PROVIDER`.
- `health()` không gọi mạng để không tốn quota.

## Cho A0 (ngoài phạm vi A4)

- `services/api/app.py` mới đăng ký `MockProvider`. Cần thêm Gemini: `GeminiImageProvider(StorageImageSource(db, store), usage_path=<data_root>/cache/gemini_usage.json)`.
- Lưu key một lần (PowerShell): `.venv\Scripts\python -c "from services.core.secrets import set_secret; set_secret('gemini', input('Key: '))"`.

## Lệnh test

```
cd ai-interior-studio
.venv\Scripts\python -m pytest tests/unit/gemini tests/unit/secrets
```
