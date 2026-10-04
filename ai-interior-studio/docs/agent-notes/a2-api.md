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

## Da xong

## Con no

## Lenh test

## Cam bay da gap

