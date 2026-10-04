# Việc A0: nối A5 vào orchestrator + 3 mục NÊN SỬA của A2

05/10/2026. Nhánh `wt/a0-orch`. Người làm: Claude (A0), song song với A3 (Codex). Không đụng file của A3.

## Phạm vi file

`services/core/orchestration/`, `services/providers/mock/`, `tests/unit/orchestration/`, `tests/unit/providers_mock/`, `docs/agent-notes/a0-orch.md`.

## Việc

1. Job không có prompt (spec rỗng, không `raw_text`): orchestrator dựng `PromptSpec` bằng `build_prompt_spec(scene=…, style_pack=…)` trước khi lưu job; job lưu spec đã dựng.
2. `prompt.txt` ghi văn bản provider thực sự gửi đi (`provider_request["prompt"]`); `metrics.json` có `prompt_version`.
3. MockProvider render prompt bằng `render_flux` như provider thật.
4. NÊN SỬA A2 #1: lỗi provider ghi tên lớp exception (không kèm message) vào `metrics.json` và log.
5. NÊN SỬA A2 #2: chỉ lưu DB/phát event khi `progress` hoặc `stage` đổi.
6. NÊN SỬA A2 #3: test 5 file snapshot cho job thành công.

## Tiêu chí xong

- [ ] Test cho từng mục trên; `pytest` toàn bộ xanh.
