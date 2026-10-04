# AI Interior Studio

Render từ SketchUp và concept từ mặt bằng. Kế hoạch và phân việc: `docs/agent-plan.md`. Đặc tả: `docs/spec.pdf`. Hợp đồng dùng chung: `docs/contracts.md`.

## Chạy trên Windows (PowerShell)

Cần Python 3.11 trở lên.

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

## Hiện có

- `services/core/domain`: model dữ liệu, state machine của job, hợp đồng provider, sự kiện WebSocket.
- `services/core/storage`: kho artifact bất biến, file snapshot theo job, SQLite.
- `tests/unit`: 155 test cho hai gói trên.

Các thư mục còn lại là chỗ trống cho agent kế tiếp; xem `docs/status.md`.

## Tiếp tục trong Claude Code

Mở repo này trong Claude Code và dán prompt ở mục 6 của `docs/agent-plan.md`. `CLAUDE.md` chứa bối cảnh dự án.

## Dữ liệu

App ghi mọi thứ vào một thư mục dữ liệu (`DataRoot`), nằm ngoài repo. Thư mục `data/` đã có trong `.gitignore`.
