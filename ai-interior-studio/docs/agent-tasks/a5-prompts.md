# Đề bài A5: Prompt & Reference (Đợt 2)

Giao 05/10/2026 bởi A0. Nhánh `wt/a5-prompts`. Người làm: Claude (Codex hết hạn mức).

## Phạm vi file

Được sửa: `services/core/prompts/`, `services/core/references/`, `tests/unit/prompts/`, `tests/unit/references/`, `pyproject.toml` (chỉ thêm dependency, có lý do), `docs/agent-notes/a5-prompts.md`.
Không sửa: domain, storage, orchestration, api, providers. Cần nối vào orchestrator thì ghi vào note cho A0.

## Việc (brief A5, Đợt 2)

1. `build_prompt_spec(...)`: điền `PromptSpec` từ `Scene`/`Room` + `StylePack` + ràng buộc. Cùng đầu vào → cùng `PromptSpec` (tất định).
2. Renderer: `render_flux(spec)` văn xuôi; `render_gemini(spec, slots)` chỉ dẫn đa ảnh, nêu vai trò từng ảnh theo đúng thứ tự slot. `raw_text` có thì dùng nguyên văn.
3. `prompt_version`: mã tất định theo nội dung; `diff(old, new)` giữa hai lần chỉnh.
4. Style Pack: kiểm vai trò, checksum, ảnh trùng bằng perceptual hash, cảnh báo ảnh nhỏ hoặc mờ.
5. Xếp ref theo slot: giữ BASE_PLAN, STYLE_MASTER, APPROVED_VIEW, rồi vai trò đang chỉnh, rồi theo `priority`; tôn trọng `max_reference_images`; ref bị loại tóm tắt thành chữ trong prompt.

Không làm: phân loại vai trò bằng AI, material fingerprint.

## Tiêu chí xong

- [ ] 12 ref, provider 4 slot: chọn đúng BASE_PLAN, STYLE_MASTER, APPROVED_VIEW và vai trò đang chỉnh; 8 ref còn lại có trong phần tóm tắt.
- [ ] Đổi 1 ref trong Style Pack tạo version mới; version cũ vẫn đọc được qua `Database.style_packs.get(id, version)`.
- [ ] Cùng đầu vào chạy hai lần ra cùng prompt và cùng `prompt_version`.
- [ ] Phát hiện 2 ảnh gần trùng; cảnh báo ảnh < 512 px và ảnh mờ.
- [ ] `pytest` toàn bộ xanh.
