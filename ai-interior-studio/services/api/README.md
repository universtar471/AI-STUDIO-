# Backend A2 (Windows PowerShell)

Chạy từ thư mục `ai-interior-studio` với Python 3.12:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m services.api
```

Backend: `http://127.0.0.1:8000`; Swagger: `/docs`; health: `/health`.
Chỉ chạy **một process/worker** cho mỗi data root. Dữ liệu mặc định ở
`%LOCALAPPDATA%\AIInteriorStudio`, ngoài repo. Có thể đặt trước khi chạy:

```powershell
$env:AI_STUDIO_DATA_ROOT = 'D:\AIInteriorStudioData'
```

## Test và hợp đồng giao diện

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\python -m scripts.export_openapi
.venv\Scripts\python -m scripts.generate_types --output "$env:TEMP\a2-api-types.ts"
```

Nếu pytest không có quyền đọc thư mục tạm chung, đặt thư mục riêng rồi chạy lại:

```powershell
$env:PYTEST_DEBUG_TEMPROOT = Join-Path $env:TEMP 'a2-tests'
New-Item -ItemType Directory -Force $env:PYTEST_DEBUG_TEMPROOT | Out-Null
.venv\Scripts\python -m pytest
```

OpenAPI được ghi vào `services/api/openapi.json`. Script TypeScript sinh các kiểu
component, gồm `JobProgressEvent`, không sinh HTTP client và không tự ghi vào apps/web.
A6 có thể chỉ định `--output` đến vị trí mong muốn khi tích hợp.

## Luồng API

1. `POST /projects` JSON `{ "name": "Apartment" }`.
2. `POST /projects/{id}/scenes/import`: multipart `file` (PNG/JPEG/WebP),
   `name`, tùy chọn `camera` (JSON CameraMeta), `model_checksum`.
3. `POST /style-packs`: JSON `name`, `project_id`, tùy chọn `palette`.
4. `POST /style-packs/{id}/references`: multipart `file`, `role`, tùy chọn
   `source_note`, `usage_rights_note`. Mỗi lần tạo version mới.
5. `POST /render/jobs`: RenderRequest trong Swagger; dùng `source.scene_id`
   hoặc `source.artifact_id`, `mode=sketchup_render`, `prompt.raw_text`.
   Nếu chọn Style Pack mà không ghi version thì khóa version mới nhất ngay lúc tạo job.
   Nếu references rỗng thì lấy references của version đó; không có Prompt Engine.
6. `GET /render/jobs/{id}` hoặc WS `/ws/jobs` để theo dõi. WS phát các event mới;
   kết nối lại dùng GET để lấy trạng thái hiện tại. Hàng đợi mỗi subscriber giữ tối đa
   128 event, bỏ event cũ nhất nếu client chậm.
7. `POST /render/jobs/{id}/approve`, `/retry`, `/cancel`.
8. `/finalize` nhận JSON tùy chọn `{ "image_size": "2K" }`, chỉ nhận preview APPROVED,
   tạo job upscale con qua provider contract. A2 chỉ trả ảnh mock; job con tới REVIEW
   để duyệt, preview cha giữ APPROVED. Không có SeedVR2 thật hoặc export final ở A2.
9. `GET /artifacts/{id}` lấy metadata, `/file` đọc bytes sau khi kiểm checksum.

Các GET `/projects`, `/style-packs`, `/render/jobs` hỗ trợ màn hình danh sách;
hai endpoint sau nhận `project_id`. `/style-packs/{id}?version=1` đọc version cũ.
`GET /providers` và `/health` có capabilities và health từng provider.
Upload giới hạn 20 MiB, kiểm media type; chưa giải mã/đánh giá chất lượng ảnh.

## Scheduler và mock

FIFO một worker; timeout mặc định 120 giây tính từ RUNNING, bao gồm health,
validate, submit, poll và fetch. Auto ưu tiên local; explicit provider vẫn phải
thỏa policy và capabilities. Provider health không OK hoặc ném lỗi bị bỏ qua.
Paid 4K phải có `confirm_high_cost=true`.

Ứng dụng/test có thể inject `create_app(path, providers=[MockProvider(delay=0,
failure='vram')], timeout=1, poll_interval=0.01)`. Failure hỗ trợ `vram`, `timeout`,
hoặc `None`; mặc định trễ 2 giây. PNG mock 1×1 chỉ dùng kiểm tra pipeline.

Restart: QUEUED xếp lại; RUNNING thành FAILED/PROCESS_RESTARTED và retry thủ công;
FINALIZING trở lại APPROVED với lý do, theo state machine đã duyệt.
Không tự gửi lại RUNNING để tránh lặp tác vụ tính phí. Shutdown yêu cầu provider cancel,
giữ RUNNING để reconcile khi mở lại. Snapshot cũ không ghi đè.
Ba snapshot đầu vào ghi khi enqueue; provider_request ghi sau submit;
metrics ghi khi kết thúc chạy. Job hủy trước submit vẫn đủ năm file, với
`provider_request.json` ghi `submitted=false`. Prompt trống tạo file prompt.txt rỗng.

Adapter tương lai phải trả provider_request/JobError không chứa credential.
Exception bất ngờ được đổi thành thông báo chung, không đưa exception thô ra API.
JobError.code là chuỗi theo contract; mã bổ sung nằm trong note bàn giao để A0 duyệt.
