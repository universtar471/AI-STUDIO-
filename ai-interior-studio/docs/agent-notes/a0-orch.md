# wt/a0-orch

- Agent: claude (A0), song song với A3 (Codex) trên `wt/a3-comfyui`; không chung file.

## Đã xong (`docs/agent-tasks/a0-orchestration-prompts.md`)

- [x] Job không có prompt và nguồn là scene: orchestrator dựng `PromptSpec` bằng `build_prompt_spec(scene, style_pack@version đã khóa)` lúc submit, lưu vào job → retry và khởi động lại gửi đúng prompt cũ.
- [x] `prompt.txt` = văn bản provider thực sự gửi (`provider_request["prompt"]`); job hỏng trước khi gửi thì ghi `raw_text` hoặc rỗng. `metrics.json` có `prompt_version`.
- [x] MockProvider render bằng `render_flux` (giống provider FLUX thật).
- [x] Lỗi provider: `metrics.json.error_class` + log WARNING chỉ có tên lớp exception và id provider, không có message.
- [x] Chỉ lưu DB/phát WebSocket khi `progress`/`stage` đổi (test: 60 lần poll → ≤ 4 lần lưu ở RUNNING).
- [x] Test đủ 5 snapshot cho job thành công.
- `pytest`: `218 passed, 1 warning`.

## Quy ước cho provider mới (A3)

`provider_request` nên có khoá `"prompt"` là chuỗi văn bản gửi đi; orchestrator ghi nó vào `prompt.txt`.
