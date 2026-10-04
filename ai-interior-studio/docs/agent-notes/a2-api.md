# wt/a2-api

- Agent: codex
- Tach tu: main
- Tao luc: 2026-10-05 02:39

## Muc tieu

Hoàn thành A2 API & Job theo đề bài, giữ nguyên domain/storage và apps.

## Kế hoạch trước khi code

1. Đã đọc CLAUDE.md, đề bài, contracts, code domain/storage, agent-plan mục 2 và A2, spec.pdf mục 7–8.
2. Viết test trước cho mock, lựa chọn provider, manager và API; chạy đỏ rồi triển khai.
3. Manager một worker asyncio, timeout toàn lượt chạy, lưu state bằng transition; snapshot write_once.
4. API theo mục 8 (không plans/rooms), OpenAPI và TypeScript, README Windows trong services/api.
5. Chạy toàn bộ test, kiểm phạm vi, commit từng bước nếu sandbox cho phép.

File dự kiến: services/providers/mock/{__init__,provider}.py;
services/core/orchestration/{__init__,manager,selection}.py;
services/api/{__init__,__main__,app,schemas}.py và README.md, openapi.json;
tests/unit/{api,orchestration,providers_mock}/test_*.py;
scripts/{export_openapi,generate_types}.py; pyproject.toml (chỉ dependency); note này.

Baseline: `155 passed in 0.45s` (Python 3.12.13).

## Tiếp quản

Codex (gpt-6-astra) viết toàn bộ code rồi hết hạn mức trước bước commit và trước khi điền note.
Claude (A0, được chủ dự án cho phép làm thay khi Codex hết hạn mức) commit nguyên văn ở `d31c267`,
kiểm lại từng tiêu chí và điền phần dưới. Không sửa dòng code nào của Codex.

## Đã xong (đối chiếu tiêu chí trong đề bài)

- [x] Một lệnh khởi động: `.venv\Scripts\python -m services.api` → `GET /health` 200 (đã chạy thật, mock `ok`).
  Hướng dẫn Windows ở `services/api/README.md`.
- [x] Chuỗi project → scene → Style Pack → job mock → REVIEW → retry (job cũ RETRY, job mới `retry_of`) →
  approve → finalize: `tests/unit/api/test_api.py::test_full_api_lifecycle`.
- [x] FAILED do giả hết VRAM retry được: `test_manager.py::test_failure_retry_and_snapshots[vram]`.
- [x] Khởi động lại: QUEUED được xếp lại và chạy tới REVIEW; RUNNING sang FAILED mã `PROCESS_RESTARTED`
  (provider không resume an toàn được); FINALIZING về APPROVED: `test_restart_reconciles_inflight`,
  `test_worker_survives_provider_exception_and_shutdown`.
- [x] Hủy job đang chạy và job đang xếp hàng → CANCELLED: `test_cancel_running_and_queued`.
  Timeout → FAILED mã `JOB_TIMEOUT`: `test_failure_retry_and_snapshots[timeout]`.
- [x] Đủ 5 file snapshot cho job lỗi và job bị hủy (job REVIEW dùng cùng `_finish_files`, chưa có test riêng); ghi lần hai bị từ chối `SNAPSHOT_EXISTS`.
- [x] WebSocket `/ws/jobs` nhận `JobProgressEvent` của job: `test_full_api_lifecycle`; ngắt kết nối giải phóng subscriber.
- [x] `python -m scripts.export_openapi` sinh `services/api/openapi.json` (chạy lại không đổi file);
  `python -m scripts.generate_types --output <file.ts>` sinh kiểu TS gồm `JobProgressEvent`.
- [x] `pytest`: `175 passed, 1 warning in 2.19s` (155 của A1 giữ nguyên).
- [x] `git diff main --stat` chỉ chạm `services/api`, `services/core/orchestration`, `services/providers/mock`,
  `tests/unit/{api,orchestration,providers_mock}`, `scripts/`, `pyproject.toml` (chỉ dependency), note này.

## Quyết định tự chọn khi mơ hồ

- RUNNING khi khởi động lại → FAILED thay vì chạy lại: provider có thể đã tốn GPU/tiền, chạy lại ngầm dễ trùng job.
  Người dùng bấm Retry.
- `/finalize` tạo job upscale con; preview cha giữ APPROVED suốt (không đi FINALIZING). Đủ cho mock;
  A3 cần xem lại khi làm SeedVR2 (điểm 3 mục 6 contracts).
- Lỗi provider ghi mã `PROVIDER_ERROR` và thông điệp chung, không chép `str(exc)` để tránh lộ token vào DB/log.
- Style Pack không ghi version thì khóa version mới nhất lúc tạo job.

## Còn nợ

- Lỗi `PROVIDER_ERROR` không ghi chi tiết ở đâu cả → khó chẩn đoán khi có provider thật. Nên log lớp exception
  (không kèm message) — để A3/A4 quyết khi thêm provider thật.
- Cảnh báo `StarletteDeprecationWarning` (httpx với TestClient) — chưa ảnh hưởng.
- Test chuỗi đầu-cuối đang ở `tests/unit/api`; bản tích hợp chính thức thuộc A9 (`tests/integration`).

## Lệnh test

```
cd ai-interior-studio
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
```

## Cạm bẫy đã gặp

- Sandbox Codex trên Windows hết hạn mức giữa chừng; commit do Claude làm từ Git Bash.
- `agent-wt` tạo note ở `docs/agent-notes` của gốc repo; dự án nằm trong `ai-interior-studio/`, note đã được chuyển vào đây.

