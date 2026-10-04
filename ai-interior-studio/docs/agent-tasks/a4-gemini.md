# Đề bài A4: Gemini (Đợt 2)

Giao 05/10/2026 bởi A0. Nhánh `wt/a4-gemini`. Người làm: Claude (Codex hết hạn mức).

## Phạm vi file

Được sửa: `services/providers/gemini/`, `services/core/secrets/`, `tests/unit/gemini/`, `tests/unit/secrets/`, `pyproject.toml` (chỉ dependency, có lý do), `docs/agent-notes/a4-gemini.md`.

## Việc (brief A4, Đợt 2)

1. `GeminiImageProvider` (implements `ImageProvider`) dùng SDK chính thức `google-genai`; model id, số ảnh tối đa, cỡ ảnh đọc từ cấu hình, không hard-code trong code gọi. Kiểm lại tài liệu Gemini hiện hành trước khi code.
2. API key: keyring hệ điều hành hoặc biến môi trường; không bao giờ ghi vào log, `provider_request.json`, lỗi hay repo.
3. Trần chi phí: mặc định 1K; 4K cần `confirm_high_cost = true`; giới hạn số lần gọi mỗi ngày; ghi chi phí ước tính từng job vào metrics.
4. Timeout thì thử lại theo fingerprint request, không tạo job trùng.
5. Trả bytes ảnh, không lưu URL.

Không làm: gọi Gemini qua custom node ComfyUI; luồng plan (Đợt 4).

## Tiêu chí xong

- [ ] Test với SDK giả xác nhận thứ tự và vai trò của 6 ảnh trong request.
- [ ] Vượt trần ngày → job FAILED với mã lỗi rõ; 4K thiếu xác nhận → bị từ chối ở `validate`.
- [ ] Không có key → `health()` trả unavailable; orchestrator vẫn chọn được provider khác.
- [ ] Không test nào gọi mạng thật. Key giả không xuất hiện trong `provider_request` hay thông điệp lỗi.
- [ ] `pytest` toàn bộ xanh.
