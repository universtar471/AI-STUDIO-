# wt/a3-comfyui

- Agent: codex
- Tach tu: main
- Tao luc: 2026-10-05 04:13

## Mục tiêu và kế hoạch

A3 phần 1 Đợt 2, hoàn tất ngày 05/10/2026 bằng ComfyUI giả. Làm một mình.
Không merge main. **chưa commit được**, A0 cần commit hộ và duyệt.

1. Đọc đề bài, CLAUDE.md, agent-plan/status, contracts mục 3, Gemini provider/config,
   render_flux và select_references; tạo venv Python 3.12, xác nhận 213 test nền.
2. Viết test/fixture trước; chạy đỏ vì chưa có module comfyui.config.
3. Triển khai config, manifest/bơm biến, provider/preflight; chạy test ComfyUI.
4. Kiểm hash/model/preset/progress, xuất schema/README, chạy toàn bộ pytest.

## File tạo/sửa

Đường dẫn tính từ ai-interior-studio:

- `services/providers/comfyui/config.py`: JSON config qua AI_STUDIO_COMFYUI_CONFIG.
- `services/providers/comfyui/manifest.py`: Pydantic, path/bindings/preset validation, deep-copy template.
- `services/providers/comfyui/provider.py`: ImageSource, hàng đợi nội bộ, upload/WS/history/view,
  bytes output, preflight, timeout/cancel, VRAM fallback và snapshot.
- `tests/unit/comfyui/test_provider.py`: 19 test/case; HTTP MockTransport và socket async giả.
- `tests/unit/comfyui/fixtures/{manifest,template}.json`: fixture tổng hợp, không chạy render thật.
- `workflows/manifests/{README.md,schema.json}`: schema, cấu hình, giới hạn và hướng dẫn.
- `pyproject.toml`: thêm httpx>=0.27 dependency runtime vì adapter import trực tiếp.
  Giữ entry dev cũ theo phạm vi chỉ thêm dependency; websockets đã có sẵn.
- `docs/agent-notes/a3-comfyui.md`: bàn giao.

Không sửa core/API/provider khác/apps, không tạo workflow hoặc manifest production.

## Đối chiếu tiêu chí

- [x] Luồng giả upload → prompt → progress → history → view → ProviderOutput.
  test_complete_flow_and_snapshot kiểm đủ sáu biến graph gửi đi, base/style theo thứ tự,
  raw_text thắng, SHA ảnh/template, JSON không chứa bytes, output bytes.
  test_progress_is_visible_and_other_jobs_are_ignored kiểm progress và lọc prompt_id.
- [x] Tắt server → unavailable không exception; node/model thiếu nêu tên.
  test_health_unavailable có offline/node/model/workflow; test_missing_template_and_node
  có thiếu template/sai node; test_injection_isolated_and_manifest_drives_presets có sai input.
- [x] QUALITY OOM retry FAST đúng một lần, metrics vram_fallback; FAST OOM thất bại
  COMFYUI_OUT_OF_MEMORY. test_fallback gồm 4 case, cả lỗi thường không retry.
- [x] Đổi steps/cfg manifest đổi graph gửi đi, không sửa code:
  test_disk_models_hash_snapshot_and_changed_preset; test injection kiểm template không đổi.
- [x] Không test nào cần ComfyUI thật hoặc mạng ngoài. Full suite 232 passed.

Bổ sung: cấu hình môi trường; model/checksum trên đĩa; từ chối traversal, binding chồng nhau,
slot count/preset sai; timeout/cancel và fetch_result trước thành công.

## Lệnh test và kết quả thật

Phiên không có python/py trong PATH. Dùng uv có sẵn tải CPython 3.12.13 vào
$env:TEMP\a3-python rồi tạo .venv. Không đổi PATH/cấu hình hệ thống. uv thử tạo executable
link/registry mặc định nhưng sandbox từ chối; interpreter trong temp vẫn dùng được.

```powershell
& "$env:TEMP\a3-python\cpython-3.12.13-windows-x86_64-none\python.exe" -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
# Temp mới mỗi lần, ngoài repo; tránh pytest-of-Admin cũ bị chặn quyền.
$env:PYTEST_ADDOPTS = '--basetemp=' + ((Join-Path $env:TEMP ('a3-test-' + [guid]::NewGuid().ToString('N'))).Replace('\','/'))
.venv\Scripts\python -m pytest tests/unit/comfyui -q
.venv\Scripts\python -m pytest
git diff --check
```

- Baseline trước code: `213 passed, 1 warning in 16.43s`.
- Test-first đỏ: `ModuleNotFoundError: No module named 'services.providers.comfyui.config'`.
- ComfyUI: `19 passed in 0.25s`.
- **Dòng tổng kết pytest cuối cùng: `232 passed, 1 warning in 16.46s`.**
- Warning đã có ở baseline: Starlette deprecate httpx TestClient; không sửa ngoài phạm vi.
- git diff --check không lỗi whitespace, chỉ cảnh báo LF/CRLF.

## Quyết định và giới hạn

- Manifest chọn bằng filename cấu hình, không tự đoán; không có manifest/template trả
  unavailable với chuỗi `chưa có workflow từ Đợt 0`.
- Thêm binding steps/cfg ngoài sáu biến runtime để áp preset không hard-code node.
- image_size 1024/1536 → FAST/QUALITY. Không chỉ định: DRAFT → FAST, PREVIEW → QUALITY.
  FINAL/UPSCALE/PLAN_CONCEPT chưa hỗ trợ. Không có binding thay ratio; workflow giữ ratio nguồn.
- Reference slot chưa dùng giữ default template. Đợt 0 cần bảo đảm default hợp lệ/trung tính
  cho 0/ít refs; adapter không chế filler hoặc đổi topology.
- Model remote kiểm đúng loader/input khai trong manifest, bỏ category đầu khỏi path để so combo.
  Không có models_dir thì chỉ xác minh filename công bố, không xác minh hash trên server.
- checkpoint_sha256 là map path → hash đã khai; không tự đoán model nào là checkpoint.
  Custom node versions trong metrics là bản khóa manifest, không phải version server đo được.
- provider_request ghi preset yêu cầu; metrics ghi preset thực tế, fallback, số lần và thời gian
  gồm cả chờ hàng đợi. Seed chưa chỉ định được sinh và ghi lại.
- Cancel/timeout đóng theo dõi và không lấy kết quả, không gọi global /interrupt vì có thể hủy
  job khác trên server dùng chung. Prompt đã gửi có thể tiếp tục chạy ở ComfyUI.
- Không tự retry lỗi mạng/timeout vì không biết server đã nhận prompt chưa.
- Protocol đã đối chiếu mã nguồn chính thức:
  https://github.com/comfyanonymous/ComfyUI/blob/master/script_examples/websockets_api_example.py
  và https://github.com/comfyanonymous/ComfyUI/blob/master/server.py.

## Chờ Đợt 0 / A0

- API workflow thật kiểm chứng trên GPU, model path/hash, node versions, license note.
- Xác minh workflow chạy với 0/ít/đủ refs, ratio nguồn, output, preset 1024/1536.
- Chạy 5 cảnh thật + Style Pack, đo chất lượng/VRAM/thời gian, kiểm cổng G2.
- A0 đăng ký provider trong API, nối ImageSource với storage và cấu hình manifest cụ thể.
- SeedVR2/final/ControlNet/Depth/LoRA ngoài phạm vi phần này.

## Cạm bẫy và commit

- PowerShell 5.1; PYTEST_ADDOPTS dùng slash / vì pytest/shlex bỏ backslash không quote.
- Temp pytest mặc định PermissionError; temp UUID riêng giải quyết, không sửa test nền.
- .venv dùng Python trong temp; nếu dọn temp cần tạo lại bằng Python 3.12 của máy.
- Đã thử commit nhỏ sau test-first: `Add ComfyUI adapter contract tests with synthetic workflows`.
  Git add và commit đều bị `Unable to create D:/AI-STUDIO-/.git/worktrees/a3-comfyui/index.lock: Permission denied`.
  Dừng thử commit, không lách sandbox, không sửa .git hay đổi quyền bằng lệnh hệ thống.
  **chưa commit được**; để toàn bộ file trên wt/a3-comfyui cho A0 commit hộ.

