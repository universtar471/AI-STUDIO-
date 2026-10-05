# Bàn giao A3 ComfyUI phần 2

Nhánh: `wt/a3-part2`. Chỉ làm trong worktree `D:\worktrees\AI-STUDIO-\a3-part2`, thư mục `ai-interior-studio/`.

## Đã làm

- Đăng ký provider mặc định theo thứ tự `mock`, `comfyui`, `gemini`; danh sách provider truyền tường minh vẫn được giữ nguyên. ComfyUI đọc ảnh qua `_ManagerImages(app)` và cấu hình qua `load_config()` / `AI_STUDIO_COMFYUI_CONFIG`.
- Mặc định dùng manifest `flux2_klein_4b_preview.json`, đường dẫn manifest/workflow theo gốc dự án, không phụ thuộc thư mục chạy. Không mặc định `models_dir`; preflight kiểm model qua `object_info`.
- Cache preflight trong từng provider, TTL mặc định 30 giây, cấu hình JSON bằng `health_cache_ttl_s` (0 để tắt). Kết quả unavailable được cache tối đa 5 giây. Dùng đồng hồ monotonic và khóa async để tránh preflight trùng khi gọi đồng thời.
- Timeout mặc định của ComfyUI và API là 600 giây. API đọc `AI_STUDIO_JOB_TIMEOUT_S`; `create_app(timeout=...)` được ưu tiên.
- Viết test trước code: lần đỏ `9 failed, 20 passed`; sau sửa nhóm liên quan đạt `29 passed`. Test kiểm cache hết hạn, TTL tùy chỉnh/tắt cache, hồi phục sau lỗi kết nối, cấu hình không phụ thuộc CWD, thứ tự provider, đọc ảnh từ storage và mock tới REVIEW khi ComfyUI offline.
- Cập nhật hai test wiring cũ vốn giả định chỉ có mock/Gemini hoặc Gemini ở index 1; dùng MockTransport để không gọi ComfyUI thật.

## Kiểm thử

Kết quả toàn bộ suite, gồm integration: **247 passed, 1 warning in 24.69s**. Warning là Starlette deprecation về httpx, không phải lỗi test.

Chạy từ `ai-interior-studio/` bằng PowerShell, tạo cấu hình tạm ngoài repo để cả backend integration kế thừa URL ComfyUI không có dịch vụ:

```powershell
$testConfig = Join-Path $env:TEMP 'a3-part2-comfyui-offline.json'
[System.IO.File]::WriteAllText($testConfig, '{"url":"http://127.0.0.1:1"}')
$env:AI_STUDIO_COMFYUI_CONFIG = $testConfig
& 'C:\Users\Admin\AppData\Local\Temp\claude\D--my-recorder\0e95023e-8ca4-4d62-bf11-b24cc14cd95a\scratchpad\venv-ais\Scripts\python.exe' -m pytest -q
```

Không gửi job tới ComfyUI thật ở 8188. Các test provider dùng fake/MockTransport. Biến môi trường trong lệnh trên chỉ phục vụ test; bỏ nó trong shell trước khi chạy app thật.

## Còn lại và cạm bẫy

- Giữ mock đầu danh sách đúng đề bài: request tự chọn provider vẫn ưu tiên mock nếu phù hợp. Muốn render thật cần chọn `provider_id='comfyui'`; thay hành vi mặc định cần A0 quyết định riêng.
- Chưa thống nhất kích cỡ 1024/1536 với 1K/2K/4K, chưa làm SeedVR2, giao diện hay kiểm ảnh thật/G2; ngoài phạm vi phần 2.
- Không sửa `docs/status.md` vì đề bài giới hạn phạm vi; A0 cập nhật khi duyệt.
- Test checksum model thay đổi liên tiếp đã đặt `health_cache_ttl_s=0` để tiếp tục kiểm tra file thực ở mỗi bước.
- Sandbox không khởi chạy được Python gốc của venv; test được chạy với quyền thực thi mở rộng bằng đúng Python đã chỉ định.
- Đã thử `git add` và commit bước test với message `Test ComfyUI API registration, health caching, and timeout defaults`, nhưng cả hai bị lỗi `Unable to create 'D:/AI-STUDIO-/.git/worktrees/a3-part2/index.lock': Permission denied`. Theo yêu cầu, để toàn bộ thay đổi chưa commit; không merge vào main.
