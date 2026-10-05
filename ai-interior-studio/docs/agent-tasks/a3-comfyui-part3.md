# Đề bài A3 phần 3: huỷ thật, health theo thực tế, cảnh báo VRAM

Giao: A0, 05/10/2026. Người làm: Codex. Nhánh: `wt/a3-part3`.

## Bối cảnh

Kiểm cổng G2 (`docs/gates/G2.md`, mục Ghi nhận 1, 2, 4) với ComfyUI thật:

- Huỷ job (người dùng bấm, hoặc `JobManager` cắt vì quá timeout) chỉ huỷ task asyncio phía app. ComfyUI vẫn chạy tiếp prompt đó và giữ GPU; job sau phải xếp hàng sau một prompt không ai cần.
- Khi D5 Render đang mở, VRAM trống còn ~1 GB, Klein tràn sang RAM chung, job treo tới timeout 600 s. Preflight vẫn báo `ok`.
- Health đã cache `ok` 30 s; ComfyUI tắt giữa chừng thì `select_provider` vẫn chọn ComfyUI trong thời gian đó (review A3 phần 2, NÊN SỬA #1).

## Việc phải làm (`services/providers/comfyui/`)

1. **Huỷ thật**: `_attempt` nhớ `prompt_id` của run (lưu trên `_Run`). `cancel()`:
   - prompt đang chờ trong hàng → `POST /queue` với `{"delete": [prompt_id]}`;
   - prompt đang chạy → `POST /interrupt` **chỉ khi** prompt đang chạy của ComfyUI đúng là `prompt_id` này (đọc `GET /queue`, `queue_running[i][1]`), để không ngắt job của người khác;
   - lỗi mạng khi huỷ không được làm hỏng việc huỷ phía app (vẫn CANCELLED); không log chi tiết exception ngoài tên lớp.
2. **Health theo thực tế**: khi `_execute` gặp lỗi kết nối (`httpx.ConnectError`, `httpx.ConnectTimeout`, lỗi mở websocket) thì xoá cache health để lần chọn provider kế tiếp kiểm lại ngay.
3. **Cảnh báo VRAM**: preflight đọc `GET /system_stats` (`devices[0].vram_free`, byte). Nếu nhỏ hơn `min_free_vram_mb` (cấu hình trong `ComfyUIConfig`, mặc định 6000) và ComfyUI **không** đang chạy prompt nào (`/queue` rỗng), trả `HealthStatus.DEGRADED` với `detail` nói rõ VRAM trống bao nhiêu MB và gợi ý đóng ứng dụng khác dùng GPU. Lúc ComfyUI đang chạy prompt thì VRAM thấp là bình thường, không hạ trạng thái. Thiếu `/system_stats` hoặc dữ liệu lạ → bỏ qua kiểm tra này, không lỗi.
   - Kiểm tra `select_provider` hiện chỉ nhận `ok`; ghi vào note hệ quả: DEGRADED sẽ bị bỏ qua khi chọn tự động (đúng ý: tránh job treo). Không sửa `selection.py`.

Không làm: sửa giao diện, SeedVR2, đổi bộ cỡ ảnh.

## Phạm vi file

`services/providers/comfyui/*`, `tests/unit/comfyui/*`, `docs/agent-notes/a3-comfyui-part3.md`.

## Tiêu chí xong

Test mới (fake HTTP/websocket như phần 1, không gọi ComfyUI thật ở 8188):

- Huỷ khi prompt đang chạy → có đúng 1 `POST /interrupt`; huỷ khi prompt đang chờ → `POST /queue` delete đúng id, không interrupt; prompt đang chạy là của người khác → không interrupt.
- Huỷ mà ComfyUI không trả lời → trạng thái vẫn CANCELLED, không ném lỗi.
- ConnectError trong `_execute` → lần `health()` kế tiếp gọi lại `/object_info` dù còn trong 30 s.
- `vram_free` thấp + hàng đợi rỗng → DEGRADED, `detail` có số MB; thấp nhưng đang chạy prompt → OK; thiếu `/system_stats` → OK.
- Toàn bộ test cũ xanh.

## Lệnh test

```
cd ai-interior-studio
python -m pytest -q
```
