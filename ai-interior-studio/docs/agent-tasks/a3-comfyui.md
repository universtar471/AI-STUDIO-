# Đề bài A3: ComfyUI adapter (Đợt 2, phần 1 — chưa có workflow thật)

Giao 05/10/2026 bởi A0. Nhánh `wt/a3-comfyui`. Người làm: Codex.

Workflow thật (API JSON) và danh sách model sẽ có sau Đợt 0. Phần này dựng toàn bộ adapter và kiểm bằng **ComfyUI giả** + **template mẫu chỉ dùng cho test**. Không được tạo workflow "thật" giả vờ chạy được FLUX.2 Klein.

## Đọc trước

`CLAUDE.md`, `docs/agent-plan.md` (mục 2, brief A3), `docs/contracts.md` mục 3 (`ImageProvider`), `services/providers/gemini/provider.py` (mẫu provider đã duyệt: hàng đợi nội bộ, `ImageSource`, `provider_request` không chứa bytes/key), `services/core/prompts` (`render_flux`), `services/core/references` (`select_references`).

## Phạm vi file

Được sửa: `services/providers/comfyui/`, `workflows/manifests/` (schema + README, KHÔNG tạo manifest thật), `tests/unit/comfyui/` (kể cả `tests/unit/comfyui/fixtures/` cho template mẫu), `pyproject.toml` (chỉ thêm dependency, có lý do), `docs/agent-notes/a3-comfyui.md`.

Không sửa: `services/core/*`, `services/api`, `services/providers/gemini|mock`, `apps/`, `workflows/comfyui/` (chỗ của workflow thật).

## Việc

1. **Manifest** (`workflows/manifests/<tên>.json`, mô tả bằng Pydantic trong `services/providers/comfyui/manifest.py`): tên file template, model files (đường dẫn tương đối trong thư mục models của ComfyUI + sha256 tuỳ chọn), custom nodes (class_type + phiên bản), 6 điểm bơm biến (node id + tên input): `source_image`, `reference_image` (có thể nhiều slot), `prompt`, `long_edge`, `seed`, `filename_prefix`; presets `PREVIEW_FAST` (1024) và `PREVIEW_QUALITY` (1536) với steps/cfg; `max_reference_images`; `license_note`.
2. **Bơm biến**: nạp template JSON, deep-copy, chỉ sửa đúng các input khai trong manifest; không dựng graph bằng code. Sai node id/input → lỗi rõ.
3. **`ComfyUIProvider`** (implements `ImageProvider`): upload ảnh base + ref qua `POST /upload/image`, gửi `POST /prompt` với `client_id`, theo dõi tiến độ qua websocket `/ws?clientId=` (`progress`, `executing`, `execution_error`), đọc `GET /history/{prompt_id}`, lấy ảnh qua `GET /view`. Trả `ProviderOutput` bytes. Prompt dùng `render_flux` của A5 (`raw_text` thắng); ref xếp bằng `select_references(max_reference_images)`. `provider_request` phải có khoá `"prompt"` (văn bản gửi đi), `"workflow"` (tên), `"preset"`, `"template_sha256"`, danh sách ảnh (role, artifact_id, sha256) — không chứa bytes.
4. **Preflight / health**: ComfyUI không chạy → `unavailable` (không ném lỗi); đủ custom node theo `GET /object_info`; đủ file model (kiểm trên đĩa nếu cấu hình `models_dir`, hoặc qua `object_info`). Lỗi nêu rõ đường dẫn/node thiếu. Không có manifest/template → `unavailable` với thông điệp "chưa có workflow từ Đợt 0".
5. **Preset & hết VRAM**: `PREVIEW_QUALITY` hết VRAM (lỗi thực thi có `OutOfMemory`/`CUDA out of memory`) → tự thử lại một lần ở `PREVIEW_FAST`; ghi `metrics.extra.vram_fallback = true`.
6. **Snapshot**: `metrics.extra` có `template_sha256`, `checkpoint_sha256` (nếu manifest có), phiên bản custom node, preset, thời gian.
7. Cấu hình: URL ComfyUI (mặc định `http://127.0.0.1:8188`), đường dẫn thư mục manifest/workflow, `models_dir` tuỳ chọn — đọc từ cấu hình/biến môi trường như `services/providers/gemini/config.py`; không hard-code tên model/steps.

Không làm: SeedVR2 (Đợt 3), ControlNet/Depth/LoRA, đăng ký provider vào `services/api` (A0 làm), sửa orchestrator.

## Tiêu chí xong

- [ ] ComfyUI giả (aiohttp/`httpx.MockTransport`/server asyncio cục bộ trong test) chạy trọn: upload → prompt → progress → history → view → `ProviderOutput`; kiểm đúng giá trị 6 biến đã bơm vào graph gửi đi.
- [ ] ComfyUI tắt → `health()` unavailable, không exception; thiếu node/model → thông điệp nêu đúng tên.
- [ ] Hết VRAM ở QUALITY → chạy lại FAST một lần, metrics ghi `vram_fallback`; hết VRAM ở FAST → FAILED mã `COMFYUI_OUT_OF_MEMORY`.
- [ ] Đổi steps/cfg trong manifest đổi graph gửi đi mà không sửa code.
- [ ] Không test nào cần ComfyUI thật hay mạng ngoài. `pytest` toàn bộ xanh.

## Lệnh test

```
cd ai-interior-studio
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest
```

## Bàn giao

Ghi `docs/agent-notes/a3-comfyui.md` (đối chiếu từng ô tiêu chí, lệnh, dòng tổng kết pytest, việc chờ Đợt 0, cạm bẫy). Commit từng bước; nếu git bị sandbox chặn thì để file lại và ghi "chưa commit được". Không merge vào `main`.
