# tests/fixtures

Chủ sở hữu: A9 Kiểm thử.

## Bộ ảnh chuẩn (`golden/`)

`golden/golden.json` liệt kê 5 cảnh SketchUp + Style Pack, kèm sha256 từng file và danh sách vật thể “phải giữ” để chấm. **Ảnh không nằm trong repo** (repo công khai, ảnh thuộc chủ dự án): đặt chúng ở `data/golden/` (đã gitignore) đúng đường dẫn trong `golden.json`, hoặc truyền `--golden-dir`. File khác sha256 → script dừng, để không so sánh nhầm bộ ảnh.

Chạy (backend đang chạy ở :8000):

```
python -m tests.integration.run_golden --provider comfyui --size 1024
```

Kết quả ở `data/golden-runs/<thời điểm>-<provider>/`: ảnh, `run.json`, `report.html` (SketchUp | lần này | lần trước cùng provider). Thêm hoặc đổi ảnh chuẩn: chép file vào `data/golden/`, sửa `golden.json` (sha256 mới), commit `golden.json`.
