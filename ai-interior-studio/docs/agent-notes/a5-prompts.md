# wt/a5-prompts

- Agent: claude (thay Codex hết hạn mức)
- Tách từ: main `bec92ea`

## Đã xong (đối chiếu tiêu chí)

- [x] 12 ref / 4 slot → BASE_PLAN, STYLE_MASTER, APPROVED_VIEW, vai trò đang chỉnh (FLOOR); 8 ref còn lại vào câu tóm tắt: `test_twelve_refs_four_slots_keeps_anchors_and_focus`.
- [x] Đổi 1 ref → version mới; version cũ đọc được bằng `Database.style_packs.get(id, version=1)`: `test_replacing_one_reference_creates_version_and_keeps_history`.
- [x] Cùng đầu vào → cùng `PromptSpec`, cùng văn bản, cùng `prompt_version`: `test_scene_spec_and_flux_text_are_deterministic`.
- [x] Phát hiện ảnh gần trùng (kể cả resize + JPEG 70), cảnh báo ảnh < 512 px, ảnh mờ, ảnh hỏng.
- [x] `pytest`: `198 passed, 1 warning`.

## Module

- `services/core/prompts`: `build_prompt_spec(scene=|room=, style_pack, constraints, lighting, materials)`; `render_flux`, `render_gemini(spec, slots)`; `prompt_version`, `text_diff`, `spec_diff`.
- `services/core/references`: `select_references(refs, max_slots, focus_roles)` → `SlotSelection(selected, dropped, summary)`; `check_style_pack`, `check_image`, `replace_reference`.
- Dependency mới: `pillow` (đọc kích thước, đo độ nét, dHash).

## Quyết định tự chọn

- Thứ tự neo cố định BASE_PLAN → STYLE_MASTER → APPROVED_VIEW; hòa nhau giữ thứ tự đầu vào (tất định).
- `prompt_version` = `pv_` + 16 ký tự sha256 của (spec + văn bản gửi đi), nên sửa tay `raw_text` cũng ra version mới.
- Độ mờ: phương sai Laplacian trên bản xám 512 px, ngưỡng 50 (đo: ảnh nét ~487, mờ bán kính 2 ~62, bán kính 3 ~39). Chỉ là cảnh báo.
- BASE_PLAN nằm trong Style Pack bị cảnh báo: ảnh gốc thuộc scene/room, không thuộc pack.

## Cho A0 (ngoài phạm vi A5)

- Orchestrator (A2) chưa gọi A5: khi `prompt.raw_text` trống thì nên dựng spec bằng `build_prompt_spec`, xếp ref bằng `select_references(max_reference_images)`, render theo provider, ghi văn bản vào `prompt.txt` và `prompt_version` vào `metrics.json`. Nên làm cùng A3/A4 khi có provider thật.
- Lưu lịch sử `prompt_version` hiện dựa vào snapshot từng job (mỗi job một `prompt.txt`); chưa cần bảng mới.

## Lệnh test

```
cd ai-interior-studio
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest tests/unit/prompts tests/unit/references
```
