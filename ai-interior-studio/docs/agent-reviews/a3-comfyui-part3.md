# Review A3 phần 3 (`wt/a3-part3`)

Người duyệt: A0 (Claude), 05/10/2026. Bản duyệt: thay đổi chưa commit của Codex (268 test xanh theo note).

## Kết luận: PHẢI SỬA 1 mục rồi merge

Huỷ từ xa theo đúng `prompt_id`, timeout huỷ 5 s, xoá cache health khi lỗi kết nối: đúng đề bài, test đủ.

## PHẢI SỬA

1. `services/providers/comfyui/provider.py` `_vram_warning`: đang so `devices[0].vram_free` với ngưỡng. `vram_free` đã trừ phần **chính ComfyUI đang giữ** (model để lại sau job). Đo trên máy này lúc ComfyUI rảnh sau một job Klein: `vram_free` = 7130 MB, `torch_vram_total` = 4064 MB. Chỉ cần ComfyUI còn giữ thêm text encoder (7.6 GB) là `vram_free` < 6000 → DEGRADED → `select_provider` bỏ ComfyUI dù không có ứng dụng nào khác dùng GPU. ComfyUI tự giải phóng được phần nó giữ, nên phải tính:
   `available = vram_free + torch_vram_total` (khi `torch_vram_total` là số hợp lệ; thiếu thì dùng `vram_free`), so `available` với `min_free_vram_mb`, và `detail` báo `available`.
   Test: `vram_free` = 2000 MB, `torch_vram_total` = 6000 MB, hàng đợi rỗng → OK; `vram_free` = 1000 MB, `torch_vram_total` = 0 → DEGRADED.

## NÊN SỬA

1. `_cancel_prompt`: giữa `GET /queue` và `POST /interrupt` prompt của mình có thể vừa xong và prompt khác bắt đầu → ngắt nhầm. ComfyUI không có interrupt theo id ở bản này; chấp nhận, ghi chú trong code.
2. `detail` cảnh báo VRAM viết tiếng Việt trong khi các `detail` khác tiếng Anh; giao diện hiện nguyên chuỗi. Giữ một ngôn ngữ (tiếng Việt cho người dùng là được, nhưng thống nhất về sau).
