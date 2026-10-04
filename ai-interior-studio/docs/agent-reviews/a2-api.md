# Duyệt A2 API & Job (`wt/a2-api`)

Người duyệt: A0 (Claude), 05/10/2026. Commit duyệt: `92031b2`.

Lưu ý: code do Codex viết; Codex hết hạn mức trước khi commit nên A0 commit hộ nguyên văn (`d31c267`) và điền note (`92031b2`). A0 không sửa code, nhưng vừa commit vừa duyệt, nên A9 cần kiểm lại độc lập ở cổng G1.

## Kết luận: ĐẠT

Kiểm đã chạy thật:

- `pytest` trên nhánh: `175 passed, 1 warning` (155 test A1 không bị sửa hay skip).
- `python -m services.api` khởi động, `GET /health` trả 200, mock `ok`.
- `python -m scripts.export_openapi` sinh lại `openapi.json` giống hệt bản đã commit; `scripts.generate_types` sinh TS có `JobProgressEvent`, `RenderJob`.
- `git diff main --stat` chỉ chạm thư mục được giao; `pyproject.toml` chỉ thêm dependency, mỗi dòng có lý do.
- Không sửa `services/core/domain`, `services/core/storage`, `apps/`.

10/10 tiêu chí trong `docs/agent-tasks/a2-api.md` có test hoặc đã chạy tay (đối chiếu trong `docs/agent-notes/a2-api.md`).

## PHẢI SỬA

Không có.

## NÊN SỬA (làm khi có provider thật, không chặn merge)

1. `services/core/orchestration/manager.py:220-223`: mọi exception của provider thành `PROVIDER_ERROR` với thông điệp chung và không ghi ở đâu. Với ComfyUI thật, lỗi thiếu model hay node sẽ không chẩn đoán được. Đề xuất: log tên lớp exception (không ghi message để tránh lộ key) hoặc cho provider ném lỗi có `code` riêng. Giao A3/A4 khi thêm provider.
2. `services/core/orchestration/manager.py:211`: mỗi vòng poll (mặc định 0,1 s) ghi SQLite và phát event WebSocket, kể cả khi tiến độ không đổi. Job ComfyUI 60 s sẽ ghi khoảng 600 lần. Đề xuất: chỉ lưu khi `progress` hoặc `stage` đổi.
3. `tests/unit/orchestration/test_manager.py`: chưa có test 5 file snapshot cho job thành công (chỉ có job lỗi và bị hủy).
4. Finalize: preview cha giữ APPROVED suốt, không đi qua FINALIZING. Đúng tinh thần điểm 3 mục 6 contracts nhưng trạng thái FINALIZING không được dùng; A3 quyết khi làm SeedVR2.
