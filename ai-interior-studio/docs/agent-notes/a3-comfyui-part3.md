# Bàn giao A3 ComfyUI phần 3

## Sửa theo review

- Đã đọc review A0 từ `main:ai-interior-studio/docs/agent-reviews/a3-comfyui-part3.md`.
- Viết trước hai ca test: queue rỗng, 2000 MB free + 6000 MB torch → OK; 1000 MB free + 0 MB torch → DEGRADED. Chạy trước sửa: `1 failed, 1 passed, 40 deselected` (tái hiện đúng lỗi ca đầu).
- `_vram_warning` tính khả dụng bằng `vram_free + torch_vram_total` nếu torch là số hữu hạn không âm; thiếu hoặc không hợp lệ thì dùng `vram_free`. So ngưỡng và detail đều dùng dung lượng khả dụng.
- Thêm comment tại `/interrupt` về race giữa snapshot queue và interrupt toàn server vì API không hỗ trợ interrupt theo ID. Giữ nguyên các phần khác.
- Chạy toàn bộ suite bằng Python được chỉ định: **270 passed, 1 warning in 21.04s**. Warning Starlette/httpx có sẵn. `git diff --check` đạt; không gửi job tới ComfyUI thật.

Nhánh: `wt/a3-part3`. Ngày: 05/10/2026.

## Đã làm

- `_Run` lưu `prompt_id` của từng lần chạy; reset khi bắt đầu attempt mới.
- `cancel()` hủy task trong app rồi đọc `/queue`: chỉ interrupt khi ID xuất hiện trong `queue_running`; nếu đang chờ thì gửi `{"delete": [prompt_id]}`. Hủy lặp không gửi thêm request. Không interrupt prompt của người khác.
- Cleanup từ xa giới hạn tối đa 5 giây (hoặc timeout cấu hình nếu ngắn hơn). Lỗi mạng/HTTP/dữ liệu queue không làm mất trạng thái CANCELLED; không ghi exception hay dữ liệu nhạy cảm vào log.
- Xóa cache health khi thực thi gặp `httpx.ConnectError`, `httpx.ConnectTimeout` hoặc lỗi mở websocket.
- Thêm `ComfyUIConfig.min_free_vram_mb`, mặc định 6000, không âm và phải hữu hạn. Preflight đọc `devices[0].vram_free`, đổi byte sang MB theo 1024². Khi thấp hơn ngưỡng và cả queue chạy/chờ đều rỗng, trả DEGRADED, nêu số MB và đề nghị đóng ứng dụng khác dùng GPU. Thiếu endpoint hoặc dữ liệu không hợp lệ thì bỏ qua kiểm tra VRAM.
- Viết test trước code: lượt đỏ `13 failed, 27 passed`; sau sửa toàn bộ suite xanh. Test dùng MockTransport và websocket giả; không submit job tới ComfyUI thật.

## Kiểm chứng

Chạy từ thư mục `ai-interior-studio`:

```powershell
& 'C:\Users\Admin\AppData\Local\Temp\claude\D--my-recorder\0e95023e-8ca4-4d62-bf11-b24cc14cd95a\scratchpad\venv-ais\Scripts\python.exe' -m pytest -q
```

Kết quả: **268 passed, 1 warning in 20.67s**. Warning có sẵn từ Starlette TestClient dùng httpx. `git diff --check` không có lỗi whitespace.

## Còn lại và cạm bẫy

- Đã đọc `selection.py`: chỉ nhận health `ok`, nên DEGRADED bị bỏ qua khi chọn tự động; cả chọn provider tường minh cũng đi qua điều kiện này. Đây là hành vi mong muốn để tránh job treo. Không sửa file đó.
- `/interrupt` là thao tác toàn server: code kiểm tra quyền sở hữu bằng snapshot `/queue` ngay trước POST; API không cung cấp interrupt nguyên tử theo prompt ID, nên không thể loại bỏ hoàn toàn việc queue đổi giữa hai request.
- Nếu mạng hỏng khi hủy, app vẫn CANCELLED nhưng không bảo đảm prompt từ xa đã dừng. Nếu hủy trước khi nhận được prompt ID, không có ID để cleanup.
- Python nền bị sandbox chặn khởi chạy; chạy test thành công qua quyền thực thi ngoài sandbox được cấp.
- Đã thử `git add` và `git commit -m "Cancel owned ComfyUI prompts and refresh health after connection failures"`; cả hai bị chặn: `Unable to create 'D:/AI-STUDIO-/.git/worktrees/a3-part3/index.lock': Permission denied`. **Toàn bộ thay đổi để chưa commit**, nhờ A0 commit khi duyệt. Không merge hoặc push.
- Không sửa giao diện, SeedVR2, cỡ ảnh, hợp đồng hoặc status chung vì ngoài phạm vi đề bài. Không còn việc code trong phạm vi phần 3; chờ A0 review.
