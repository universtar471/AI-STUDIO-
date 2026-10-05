# Review A3 phần 2 (`wt/a3-part2`)

Người duyệt: A0 (Claude), 05/10/2026. Code: Codex (sandbox không ghi được `index.lock`, A0 commit hộ nguyên văn).

## Kết luận: ĐẠT

Đúng đề bài `docs/agent-tasks/a3-comfyui-part2.md`; 247 test xanh (Codex chạy, A0 chạy lại trên `main` sau merge).

- `services/api/app.py`: thứ tự mặc định mock → comfyui → gemini; ComfyUI đọc ảnh qua `_ManagerImages`; timeout lấy `AI_STUDIO_JOB_TIMEOUT_S`, mặc định 600 s, tham số tường minh thắng.
- `services/providers/comfyui/config.py`: `manifest_dir`/`workflow_dir` theo gốc dự án (`parents[3]` = `ai-interior-studio/`, đúng), manifest mặc định Klein, `timeout_s` 600.
- `services/providers/comfyui/provider.py`: cache preflight 30 s có khoá async, kết quả không `ok` chỉ cache ≤ 5 s.

## PHẢI SỬA

Không có.

## NÊN SỬA

1. `provider.py` `health()`: sau khi đã cache `ok`, nếu ComfyUI tắt thì trong tối đa 30 s `select_provider` vẫn chọn ComfyUI và job FAILED (`COMFYUI_ERROR`) thay vì chuyển provider. Nên xoá cache khi `_execute` gặp lỗi kết nối (`httpx.ConnectError`).
2. `tests/unit/api/test_comfyui_registration.py:10`: `from test_api import wait_state` dựa vào cách pytest chèn `sys.path`; nên chuyển `wait_state` vào `conftest.py` hoặc module helper.
3. Mock vẫn đứng đầu danh sách mặc định nên chế độ AUTO luôn chọn mock. Đúng đề bài (giữ test cũ), nhưng trước khi phát hành phải bỏ mock khỏi danh sách mặc định hoặc chỉ bật bằng cờ. A0 ghi vào status.
