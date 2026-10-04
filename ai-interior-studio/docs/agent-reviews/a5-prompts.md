# Duyệt A5 Prompt & Reference (`wt/a5-prompts`)

A0 (Claude), 05/10/2026. Claude vừa viết vừa duyệt (Codex hết hạn mức); A9 kiểm lại ở G2.

## Kết luận: ĐẠT

- 5/5 tiêu chí trong `docs/agent-tasks/a5-prompts.md` có test; toàn bộ `pytest`: 198 passed.
- Chỉ chạm `services/core/prompts`, `services/core/references`, test của hai module, `pyproject.toml` (thêm `pillow`, có lý do).

## NÊN SỬA

1. Orchestrator chưa dùng A5 (`services/core/orchestration/manager.py` vẫn chỉ ghi `raw_text` vào `prompt.txt`). Nối khi làm A3/A4: dựng spec, xếp slot theo `max_reference_images`, render theo provider, ghi `prompt_version` vào metrics.
2. Ngưỡng mờ 50 đo trên ảnh tổng hợp; chỉnh lại bằng ảnh Style Pack thật của Đợt 0.
