# flow-provider — Google Flow thay Gemini API

## Mục tiêu
Render qua Google Flow (tài khoản PRO đã đăng nhập, Nano Banana 2, 0 credit) thay cho Gemini API trả tiền,
tái dùng driver Flow đã chạy ổn của plugin SketchUp TB Gemini Render thay vì tự viết tự động hoá trình duyệt.

## Đã xong
- `services/providers/flow/`:
  - `driver.py` — `NodeFlowDriver`: ghi job v3 (request.json, source.png cắt đúng tỷ lệ Flow, prompt.txt, 1 STYLE_REF),
    chạy `node run.js <jobDir>`, theo dõi `status.json`, đọc `results.json`, nhớ `flow_project_url` để dùng lại một project.
  - `provider.py` — `FlowProvider` (id `flow`): 1 ảnh tham chiếu (slot STYLE_REF), không seed, không tốn tiền, chạy tuần tự.
  - `config.py` — đường dẫn node/run.js từ `installation.json` của plugin, ghi đè bằng `AI_STUDIO_FLOW_CONFIG`.
- `services/api/app.py`: thứ tự comfyui → flow (tắt bằng `AI_STUDIO_DISABLE_FLOW=1`) → gemini (chỉ khi
  `AI_STUDIO_ENABLE_GEMINI_API=1`) → mock (`AI_STUDIO_ENABLE_MOCK=1`).
- `tests/integration/run_golden.py`: chỉ gửi seed khi provider hỗ trợ.
- Bản tự viết bằng Playwright Python đã bỏ (lỗi upload ảnh thứ 2); không thêm dependency Python nào.

## Kiểm chứng
- `python -m pytest -q` — 284 passed. Test Flow dùng run.js giả, không bao giờ chạm tài khoản thật.
- Chạy thật 1 cảnh (bedroom_2 + material board): 85 s, ảnh 2752×1536, giữ bố cục.

## Còn nợ / cạm bẫy
- Phụ thuộc plugin TB Gemini Render đã cài (driver + Node 24). Không có → health `unavailable`.
- Hết phiên đăng nhập → job lỗi `FLOW_NEEDS_ATTENTION`; đăng nhập lại bằng `node login.js` trong thư mục driver.
- Profile Chrome dùng chung với plugin: plugin đang render thì job app báo bận (driver tự khoá).
- Flow chỉ nhận tỷ lệ 16:9/4:3/1:1/3:4/9:16; ảnh gốc bị cắt giữa về tỷ lệ gần nhất.
