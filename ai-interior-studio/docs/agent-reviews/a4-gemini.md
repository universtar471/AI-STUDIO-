# Duyệt A4 Gemini (`wt/a4-gemini`)

A0 (Claude), 05/10/2026. Claude vừa viết vừa duyệt (Codex hết hạn mức); A9 kiểm lại ở G2.

## Kết luận: ĐẠT

- 5/5 tiêu chí trong `docs/agent-tasks/a4-gemini.md` có test với SDK giả; toàn bộ `pytest`: 210 passed; quét key: 0.
- Chỉ chạm `services/providers/gemini`, `services/core/secrets`, test của hai module, `pyproject.toml` (thêm `google-genai`, `keyring`, có lý do).

## NÊN SỬA

1. Chưa gọi Gemini thật lần nào (chưa có key). Khi có key: chạy 1 ảnh 1K bằng tay, so định dạng phản hồi với `_images_from` trong `services/providers/gemini/provider.py`.
2. Chưa đăng ký trong `services/api/app.py` (A0 làm ở bước tích hợp).
3. Giá trong `GeminiConfig` là ước tính theo bảng giá 10/2026; số thật xem trên hoá đơn Google.
