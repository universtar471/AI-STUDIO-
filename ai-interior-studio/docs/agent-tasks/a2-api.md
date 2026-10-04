# Đề bài A2: API & Job (Đợt 1)

Giao ngày 05/10/2026 bởi A0. Nhánh: `agent/a2-api`. Hợp đồng `docs/contracts.md` đã duyệt.

## Đọc trước

1. `CLAUDE.md`, `docs/agent-plan.md` (mục 2 quy tắc chung, mục 5 brief A2).
2. `docs/contracts.md`: chỉ dùng qua `services.core.domain` và `services.core.storage`, không sửa hai gói này.
3. `docs/spec.pdf` mục 7 (RenderRequest) và mục 8 (API).

## Quy tắc chung (tóm tắt mục 2 của kế hoạch)

- Chỉ sửa thư mục được giao (bên dưới). Cần đổi hợp đồng thì ghi `docs/contract-requests.md`, không tự sửa domain/storage.
- Trước khi code: nêu kế hoạch và danh sách file sẽ tạo/sửa (ghi vào note bàn giao).
- Không ghi đè artifact. API key không vào log hay thư mục project.
- Mọi tính năng kèm test; test xanh trước khi báo xong. Thêm dependency phải nêu lý do (ghi cạnh dòng trong `pyproject.toml`, như mẫu đang có).
- README chạy được trên Windows.

## Phạm vi file

Được sửa:

- `services/api/`
- `services/core/orchestration/`
- `services/providers/mock/`
- `tests/unit/api/`, `tests/unit/orchestration/`, `tests/unit/providers_mock/`
- `pyproject.toml`: chỉ thêm dependency (fastapi, uvicorn, httpx cho test...), có ghi lý do
- `scripts/` (mới): script xuất `openapi.json` và sinh kiểu TypeScript
- `docs/agent-notes/a2-api.md` (note bàn giao)

Không được sửa: `services/core/domain`, `services/core/storage`, `tests/unit/domain`, `tests/unit/storage`, `apps/`, `docs/` khác.

## Việc cần làm

1. FastAPI với endpoint mục 8 của đặc tả cho: projects, style-packs, render/jobs, artifacts, providers, health. Bỏ plans/rooms (Đợt 4).
2. Job manager asyncio: xếp hàng, hủy, timeout. Retry dùng `retry_job`. Trạng thái lưu qua `Database.jobs`; mọi chuyển trạng thái đi qua `transition`.
3. Chọn provider theo `provider_policy` và `ProviderCapabilities`; bỏ qua provider có `health()` lỗi.
4. WebSocket `/ws/jobs` phát `JobProgressEvent`.
5. `MockProvider` (implements `ImageProvider`): trả ảnh PNG giả sau vài giây (độ trễ cấu hình được để test chạy nhanh); có chế độ giả lỗi hết VRAM và giả timeout.
6. Khởi động lại: job ở `IN_FLIGHT_STATES` được xếp lại hoặc chuyển FAILED kèm lý do (ghi rõ quy tắc chọn trong note).
7. Mỗi job ghi `request.json`, `provider_request.json`, `prompt.txt`, `refs.json`, `metrics.json` qua `JobFiles.write_once`.
8. Xuất `openapi.json` và script sinh kiểu TypeScript cho `apps/web` (script chỉ cần chạy được; không tạo code trong `apps/web`).
9. Prompt: tạm dùng `PromptSpec.raw_text`, không làm Prompt Engine.

Không làm: provider thật (ComfyUI, Gemini, SeedVR2), Prompt Engine, plans/rooms.

## Tiêu chí xong

- [ ] Một lệnh khởi động backend, ghi trong README (ví dụ `python -m services.api`), chạy được trên Windows; `GET /health` trả 200.
- [ ] Test tích hợp đi hết chuỗi: tạo project → Style Pack → job mock → REVIEW → approve; và nhánh: job → REVIEW → retry tạo job mới có `retry_of` = job cũ, job cũ ở RETRY.
- [ ] Job FAILED (MockProvider giả hết VRAM) retry được.
- [ ] Test khởi động lại: tạo DB có job ở QUEUED/RUNNING, khởi động manager mới, job không bị mất (được xếp lại hoặc FAILED có lý do).
- [ ] Test hủy job đang chạy → CANCELLED; test timeout → FAILED với `error`.
- [ ] Test: 5 file snapshot của job tồn tại; ghi lần hai bị từ chối.
- [ ] Test WebSocket nhận được ít nhất một `JobProgressEvent` cho job mock.
- [ ] `openapi.json` sinh được bằng lệnh ghi trong README.
- [ ] Toàn bộ `pytest` xanh, gồm 155 test cũ của A1 (không test nào bị sửa hoặc skip).
- [ ] `git diff main --stat` chỉ chạm các đường dẫn trong "Được sửa".

## Lệnh test

```
pip install -e ".[dev]"
pytest
```

## Bàn giao

Ghi `docs/agent-notes/a2-api.md`: kế hoạch, file đã đổi, lệnh chạy, kết quả test (dán dòng tổng kết pytest), việc còn lại, cạm bẫy. Commit trên `agent/a2-api` rồi báo tên nhánh. Không tự merge vào `main`; A0 duyệt rồi hợp nhất.
