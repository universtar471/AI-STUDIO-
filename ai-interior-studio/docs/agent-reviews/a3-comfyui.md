# Duyệt A3 ComfyUI phần 1 (`wt/a3-comfyui`)

A0 (Claude), 05/10/2026. Code do Codex viết; sandbox chặn git nên A0 commit hộ nguyên văn (`3df7189`).

## Kết luận: ĐẠT

- 5/5 tiêu chí trong `docs/agent-tasks/a3-comfyui.md` có test (`tests/unit/comfyui/test_provider.py`, 19 test, ComfyUI giả).
- A0 tự chạy sau khi merge `main` vào nhánh: `237 passed`; quét key: 0.
- Chỉ chạm `services/providers/comfyui`, `workflows/manifests` (schema + README, không có manifest thật), `tests/unit/comfyui`, `pyproject.toml` (`httpx` thành dependency chính, có lý do).
- `provider_request` có khoá `"prompt"` nên khớp với việc orchestrator ghi `prompt.txt`.

## PHẢI SỬA

Không có.

## NÊN SỬA (làm khi ráp workflow thật của Đợt 0, trước cổng G2)

1. `services/providers/comfyui/manifest.py:140`: khi ít ảnh tham chiếu hơn số slot, slot thừa giữ nguyên tên file có sẵn trong template. Với workflow thật, ComfyUI sẽ báo thiếu file hoặc dùng nhầm ảnh cũ. Cần quy ước trong manifest: slot trống thì dùng ảnh base, hoặc workflow có nhánh bỏ qua.
2. `services/providers/comfyui/provider.py:70-76`: `health()` tải `/object_info` mỗi lần gọi, trong khi `select_provider` chỉ cho health 2 giây. ComfyUI nhiều custom node trả `object_info` vài MB, có thể quá 2 giây → bị coi là unavailable. Nên cache kết quả preflight 30–60 giây.
3. `services/providers/comfyui/provider.py:58`: cỡ ảnh dùng `"1024"`/`"1536"`, Gemini dùng `"1K"`/`"2K"`/`"4K"`; giao diện đang gộp hai bộ. Nên thống nhất một bộ từ (ví dụ preset `fast`/`quality`), cần đề xuất hợp đồng.
4. Timeout ComfyUI mặc định 300 s nhưng `JobManager` cắt ở 120 s. Khi biết thời gian thật ở Đợt 0, chỉnh cả hai.
5. Chưa đăng ký `ComfyUIProvider` trong `services/api/app.py` (A0 làm khi có manifest thật).
