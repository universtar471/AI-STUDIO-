# AI Interior Studio

App Windows cho một người dùng: render nội thất từ SketchUp (Mode A) và concept từ mặt bằng (Mode B).

## Đọc trước khi làm

1. `docs/agent-plan.md`: kế hoạch, phân việc cho 10 agent, các đợt và cổng nghiệm thu.
2. `docs/contracts.md`: hợp đồng dữ liệu dùng chung. Không tự sửa; đề xuất ghi vào `docs/contract-requests.md`.
3. `docs/status.md`: việc đã xong và việc kế tiếp. Cập nhật sau mỗi lần làm.
4. `docs/spec.pdf`: đặc tả kỹ thuật v1.0 gốc. Khi kế hoạch và đặc tả khác nhau, theo kế hoạch.

## Bối cảnh

- Dùng cá nhân, một máy Windows, GPU NVIDIA 12 GB VRAM trở lên.
- Ưu tiên chạy local (ComfyUI + FLUX.2 Klein) để không tốn phí API. Gemini là tùy chọn và phải có trần chi phí.
- Giá trị chính: bộ ảnh nhiều góc nhìn đồng bộ về vật liệu, phong cách, ánh sáng.
- Chủ dự án là kiến trúc sư, không tự viết code. Trả lời bằng tiếng Việt, ngắn gọn; luôn ghi rõ lệnh cần chạy và việc cần chủ dự án quyết định.

## Trạng thái hiện tại

A1 Nền tảng đã xong (155 test xanh). `docs/contracts.md` đã duyệt 05/10/2026. A2 API & Job đã xong và merge. A9 chạy cổng G1: đề xuất ĐẠT (`docs/gates/G1.md`, 180 test xanh). G1 đã duyệt 05/10/2026. Đợt 2: A4, A5, A6 xong; A3 và cổng G2 chờ Đợt 0. Xem `docs/status.md`.

Giao diện: `apps/web` (`npm run dev`, cần backend `python -m services.api`).
Provider mặc định: ComfyUI (`AI_STUDIO_COMFYUI_CONFIG` trỏ file JSON nếu không dùng `http://127.0.0.1:8188`) và Google Flow (tài khoản Google đã đăng nhập, không tốn tiền). Flow chạy qua driver Node của plugin SketchUp TB Gemini Render (`node run.js <jobDir>`, đường dẫn lấy từ `installation.json` của plugin; profile Chrome `%LOCALAPPDATA%\TBGeminiRender\chrome-profile`, đăng nhập bằng `login.js` của driver). App chỉ ghi thư mục job v3 vào `<data>/flow-jobs/` và đọc kết quả; sửa tự động hoá Flow thì sửa ở driver, không viết lại trong app. Tắt Flow: `AI_STUDIO_DISABLE_FLOW=1` (test đặt sẵn); cấu hình: `AI_STUDIO_FLOW_CONFIG`. Gemini API (tốn tiền) chỉ bật khi `AI_STUDIO_ENABLE_GEMINI_API=1` và có key. Provider mock chỉ bật khi `AI_STUDIO_ENABLE_MOCK=1` (thử giao diện không tốn GPU/tiền). Timeout job: `AI_STUDIO_JOB_TIMEOUT_S` (mặc định 600).

## Lệnh

```
pip install -e ".[dev]"
pytest
```

## Quy tắc

- Mỗi agent chỉ sửa thư mục của mình (bảng trong `docs/agent-plan.md`).
- Không ghi đè artifact. API key không được vào log, repo hay thư mục project.
- Không hard-code tên model, số steps hay custom node vào giao diện hoặc orchestrator.
- Thiếu file model, workflow, key hay ảnh mẫu thì hỏi, không tự bịa.
- Mọi tính năng kèm test; test xanh trước khi báo xong.
