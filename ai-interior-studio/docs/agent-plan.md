# AI Interior Studio: kế hoạch phát triển và phân việc cho agent

Cập nhật 04/10/2026. Đặc tả gốc: `docs/spec.pdf` (các "mục" nhắc bên dưới là mục của đặc tả).

## 1. Hướng phát triển

Giữ kiến trúc "2 đầu vào, 1 bộ điều phối, nhiều backend" của đặc tả v1.0 và đổi 6 điểm cho hợp với một người dùng, một máy GPU 12 GB, không muốn tốn phí API.

| # | Điểm đổi | Đặc tả v1.0 | Kế hoạch này | Lý do |
| --- | --- | --- | --- | --- |
| 1 | Thứ tự backend | Gemini trước, ComfyUI sau | Mock, rồi ComfyUI + FLUX.2 Klein local làm mặc định; Gemini tùy chọn, có trần chi phí | Preview local không tốn tiền mỗi lần Generate |
| 2 | Kiểm chứng trước khi code | Không có | Đợt 0: chạy tay 2 workflow với 5 cảnh thật, có cổng đi/dừng | Rủi ro lớn nhất là chất lượng ảnh |
| 3 | ComfyUI đóng hộp | Template JSON + bơm biến | 1 template đã khóa cho mỗi việc; chỉ bơm 6 biến: ảnh gốc, ảnh tham chiếu, prompt, cạnh dài, seed, tên file | Dùng hằng ngày không phải chỉnh node |
| 4 | Đồng bộ bộ ảnh | Phase 3 và V2.5 | Kéo lên Đợt 3: duyệt 1 view "neo", các view còn lại bám theo | Giá trị chính của app |
| 5 | Cắt phạm vi | BFL adapter, License Registry, Redis/Celery, Tauri, team sync | Bỏ BFL và hàng đợi ngoài; license còn 1 trường ghi chú trong manifest; đóng gói để sau | Dùng cá nhân, một máy |
| 6 | Bộ ảnh chuẩn | Chỉ test chức năng | 5 cảnh + 1 Style Pack cố định, chạy lại sau mỗi lần đổi prompt hoặc workflow | Biết thay đổi làm ảnh tốt lên hay xấu đi |

Trần chi phí Gemini: mặc định 1K, 4K phải xác nhận, giới hạn số lần gọi mỗi ngày, ghi chi phí từng job.

Câu hỏi còn mở: FLUX.2 Klein 4B có chạy ổn ở cạnh dài 1536 trên 12 GB VRAM không. Đợt 0 trả lời; nếu không thì dùng bản lượng tử hóa hoặc hạ preview xuống 1024.

## 2. Cách tổ chức

Một agent điều phối (A0) giữ kế hoạch và hợp nhất code; 9 agent chuyên trách, mỗi agent sở hữu một nhóm thư mục và không sửa ngoài phạm vi đó. Mỗi agent làm trên nhánh `agent/<tên>`. Các agent chạy song song được vì cùng code theo `docs/contracts.md`.

### Quy tắc chung cho mọi agent

1. Đọc `docs/spec.pdf` và `docs/contracts.md` trước khi code.
2. Chỉ sửa trong thư mục được giao. Cần đổi hợp đồng dùng chung thì ghi đề xuất vào `docs/contract-requests.md`.
3. Làm trên nhánh `agent/<tên>`. Chỉ A0 hợp nhất vào `main`.
4. Trước khi code: nêu kế hoạch và danh sách file sẽ tạo/sửa.
5. Sau khi code: liệt kê file đã đổi, lệnh chạy, kết quả test, việc còn lại.
6. Thiếu file model hoặc workflow thì tạo manifest và báo, không giả vờ đã có.
7. Không ghi đè artifact cũ. API key không được xuất hiện trong log hay thư mục project.
8. Mọi tính năng kèm test; test phải xanh trước khi báo xong.
9. Thêm dependency phải nêu lý do. README chạy được trên Windows.

## 3. Bản đồ agent

| Agent | Thư mục sở hữu | Việc chính | Cần có trước | Đợt |
| --- | --- | --- | --- | --- |
| A0 Điều phối | `docs/`, nhánh `main` | Giao việc, duyệt hợp đồng, chạy cổng, hợp nhất nhánh | Đặc tả | 0-4 |
| A1 Nền tảng | `services/core/domain`, `services/core/storage` | Model dữ liệu, state machine, SQLite, kho artifact | Đặc tả | 1 (đã xong) |
| A2 API & Job | `services/api`, `services/core/orchestration`, `services/providers/mock` | REST + WebSocket, hàng đợi, MockProvider, khôi phục job | A1 | 1 |
| A3 ComfyUI | `services/providers/comfyui`, `services/providers/seedvr2`, `workflows/` | Adapter ComfyUI, template FLUX.2 Klein, preflight, SeedVR2 final | A2, workflow từ Đợt 0 | 0, 2, 3 |
| A4 Gemini | `services/providers/gemini`, `services/core/secrets` | Adapter Gemini đa ảnh, keyring, trần chi phí | A2 | 2, 4 |
| A5 Prompt & Reference | `services/core/prompts`, `services/core/references` | Prompt có cấu trúc, renderer theo provider, xếp ref theo slot, Project Memory, view neo | A1 | 2, 3 |
| A6 Giao diện | `apps/web` | Projects, Style Pack, Generate, tiến độ, History/Compare, Approve, Final | OpenAPI của A2 | 2, 3, 4 |
| A7 SketchUp | `apps/sketchup-plugin` | Plugin Ruby: xuất scene + metadata camera, gửi job | API của A2 | 3 |
| A8 Mặt bằng | `services/core/plan` | Nhập plan, crop phòng, camera hint, `room_meta` | A1, A4 | 4 |
| A9 Kiểm thử | `tests/integration`, `tests/fixtures` | Test tích hợp, bộ ảnh chuẩn, kiểm cổng | Code của đợt đang chạy | 1-4 |

Test đơn vị thuộc agent viết module đó, đặt ở `tests/unit/<module>`. A9 không sửa code của agent khác, chỉ báo lỗi kèm cách tái hiện.

## 4. Các đợt và cổng nghiệm thu

Đợt 1 chạy tuần tự (A1 rồi A2). Từ Đợt 2 các agent trong cùng đợt chạy song song. Không mở đợt sau khi cổng trước chưa đạt. Đợt 0 không chặn Đợt 1.

| Đợt | Nội dung | Agent |
| --- | --- | --- |
| 0 | Kiểm chứng tay 2 workflow trên máy có GPU | Chủ dự án, A3 |
| 1 | Nền tảng | A1, A2, A9 |
| 2 | Provider và giao diện | A3, A4, A5, A6, A9 |
| 3 | Final, bộ ảnh, SketchUp (hoàn thành MVP) | A3, A5, A6, A7, A9 |
| 4 | Concept từ mặt bằng | A8, A4, A6, A9 |

| Cổng | Đạt khi | Ai kiểm |
| --- | --- | --- |
| G0 | Ít nhất 4/5 cảnh chuẩn giữ đúng camera và bố cục (ngưỡng đề xuất); thời gian preview và VRAM chấp nhận được; có 2 file workflow API JSON | Chủ dự án |
| G1 | `docs/contracts.md` đã duyệt; job mock đi hết từ DRAFT đến APPROVED; retry tạo job mới liên kết job cũ; khởi động lại không mất job | A9, chủ dự án duyệt |
| G2 | Từ giao diện: tạo project, Style Pack, preview qua ComfyUI, History, Approve; tắt một provider thì provider kia vẫn chạy; bộ ảnh chuẩn chạy đủ 5 cảnh | A9, chủ dự án xem ảnh |
| G3 | Tiêu chí MVP ở mục 11; view neo giữ được vật liệu ở view thứ hai; không ảnh nào bị ghi đè; API key không có trong log | A9, chủ dự án xem ảnh |
| G4 | Tiêu chí Plan ở mục 11; chi phí cloud nằm trong trần đã đặt | A9, chủ dự án xem ảnh |

## 5. Brief từng agent

### Đợt 0: kiểm chứng tay (chủ dự án làm, A3 hỗ trợ)

Mục tiêu: biết chắc hai workflow cho ảnh dùng được trên máy này.

1. Cài ComfyUI, FLUX.2 Klein 4B distilled, VAE của FLUX.2 và node SeedVR2; ghi lại phiên bản từng thứ.
2. Chọn 5 cảnh SketchUp thật, xuất PNG 16:9, và 1 Style Pack 4-6 ảnh. Đây là bộ ảnh chuẩn.
3. Chạy workflow preview ở cạnh dài 1024 và 1536; ghi thời gian và VRAM đỉnh.
4. Chạy SeedVR2 lên 2048 cho 2 ảnh đạt.
5. Xuất hai workflow ở định dạng API JSON vào `workflows/comfyui/`.

A3 viết `workflows/manifests/` liệt kê model, custom node, phiên bản và 6 điểm bơm biến (id node + tên input). Nếu không đạt G0: đổi đường mặc định sang Gemini, giữ ComfyUI làm tùy chọn.

### A1 Nền tảng (Đợt 1) - ĐÃ XONG

Kết quả ở `services/core/domain`, `services/core/storage`, `tests/unit`, mô tả trong `docs/contracts.md`. Còn lại: chủ dự án duyệt mục 6 của contracts.

### A2 API & Job (Đợt 1, sau khi contracts được duyệt)

Mục tiêu: một job giả chạy trọn vòng đời qua API.

1. FastAPI với các endpoint mục 8 cho projects, style-packs, render/jobs, artifacts, providers, health. Nhóm plans/rooms để Đợt 4.
2. Job manager asyncio: xếp hàng, hủy, timeout; retry dùng `retry_job`; trạng thái lưu qua `Database.jobs`.
3. Chọn provider theo `provider_policy` và capabilities; bỏ qua provider đang lỗi.
4. WebSocket `/ws/jobs` phát `JobProgressEvent`.
5. MockProvider trả ảnh giả sau vài giây, có chế độ giả lỗi hết VRAM và timeout.
6. Khi khởi động lại, job ở `IN_FLIGHT_STATES` được xếp lại hoặc chuyển FAILED kèm lý do.
7. Mỗi job ghi `request.json`, `provider_request.json`, `prompt.txt`, `refs.json`, `metrics.json` qua `JobFiles.write_once`.
8. Xuất `openapi.json` và script sinh kiểu TypeScript cho `apps/web`.

Xong khi: một lệnh khởi động backend; test tích hợp chạy được chuỗi tạo project, Style Pack, job mock, REVIEW, approve, retry.
Không làm: provider thật, Prompt Engine (tạm dùng `PromptSpec.raw_text`).

### A9 Kiểm thử (từ Đợt 1)

1. Test tích hợp đầu-cuối với MockProvider.
2. Dựng `tests/fixtures/golden/` từ 5 cảnh và Style Pack của Đợt 0.
3. Script `run_golden` chạy cả bộ qua một provider, xuất trang HTML so sánh cạnh nhau với lần chạy trước.
4. Trước mỗi cổng, chạy từng tiêu chí và ghi `docs/gates/G<n>.md`.
5. Quét log và thư mục project tìm API key bị lộ.

Không làm: sửa code của agent khác.

### A3 ComfyUI

Mục tiêu: FLUX.2 Klein local là đường preview mặc định, SeedVR2 là bước final.

Đợt 2:
1. `ComfyUIProvider`: gửi `/prompt`, nghe tiến độ qua websocket, đọc `/history`, lấy ảnh qua `/view`, trả `ProviderOutput`.
2. Nạp template JSON và bơm 6 biến theo manifest; không dựng graph bằng code.
3. Preflight: ComfyUI có chạy không, đủ model và custom node theo manifest không; lỗi nêu rõ đường dẫn thiếu.
4. Preset `PREVIEW_FAST` (1024) và `PREVIEW_QUALITY` (1536); steps và CFG đọc từ manifest.
5. Hết VRAM thì tự thử lại một lần ở preset thấp hơn và ghi vào metrics.
6. Snapshot job lưu hash template, hash checkpoint, phiên bản custom node.

Đợt 3:
1. `SeedVR2Provider` cho mode upscale: chỉ nhận job có preview cha ở APPROVED (`ensure_can_finalize`); mặc định 2048, trần 4096, hiệu chỉnh màu LAB, noise 0.
2. Dữ liệu chẩn đoán: GPU, VRAM, thời gian trung bình theo preset.

Xong khi: `run_golden` chạy đủ 5 cảnh qua ComfyUI; tắt ComfyUI thì provider báo degraded và app không sập; SeedVR2 từ chối preview chưa duyệt.
Không làm: ControlNet, Depth, LoRA.

### A4 Gemini

Mục tiêu: đường cloud tùy chọn cho concept nhiều ảnh tham chiếu, có kiểm soát chi phí.

Đợt 2:
1. `GeminiImageProvider` dùng SDK `google-genai` chính thức; model id, số ảnh tối đa và cỡ ảnh đọc từ cấu hình. Kiểm lại với tài liệu Gemini hiện hành trước khi code.
2. API key nằm trong keyring của hệ điều hành hoặc biến môi trường.
3. Trần chi phí: mặc định 1K; 4K cần `confirm_high_cost = true`; giới hạn số lần gọi mỗi ngày; ghi chi phí từng job vào metrics.
4. Timeout thì thử lại theo fingerprint của request để không tạo job trùng.
5. Trả bytes ảnh; không lưu URL.

Đợt 4:
1. Luồng `PLAN_CONCEPT_GEMINI`: nhận crop phòng và ref theo vai trò từ A5, giữ đúng thứ tự.

Xong khi: test với SDK giả xác nhận thứ tự và vai trò của 6 ảnh trong request; vượt trần ngày thì job FAILED với mã lỗi rõ; không có key thì provider báo unavailable và đường ComfyUI vẫn chạy.
Không làm: gọi Gemini qua custom node của ComfyUI.

### A5 Prompt & Reference

Mục tiêu: cùng đầu vào cho ra cùng prompt; mọi view trong một dự án dùng chung style, vật liệu, ánh sáng.

Đợt 2:
1. Điền `PromptSpec` từ scene/room metadata + Style Pack + ràng buộc.
2. Renderer riêng cho FLUX (văn xuôi) và Gemini (chỉ dẫn đa ảnh, nêu vai trò từng ảnh).
3. Lưu `prompt_version` và diff giữa các lần chỉnh.
4. Style Pack: vai trò, checksum, phát hiện ảnh trùng bằng perceptual hash, cảnh báo ảnh nhỏ hoặc mờ.
5. Xếp ref theo số slot: dùng `priority` và `max_reference_images` của provider; ref bị loại được tóm tắt thành chữ trong prompt.

Đợt 3:
1. Project Memory có revision: phiên bản Style Pack, vật liệu, ánh sáng, các khóa, danh sách view đã duyệt.
2. View neo: ảnh đã duyệt thành reference `APPROVED_VIEW` cho các view sau.
3. Chế độ bộ ảnh: từ 1 view neo, tạo hàng loạt job preview cho các scene còn lại với cùng prompt version và memory.

Xong khi: 12 ref với provider 4 slot chọn đúng BASE, STYLE_MASTER, APPROVED_VIEW và vai trò đang chỉnh; đổi 1 ref tạo version mới và history cũ vẫn mở được.
Không làm: phân loại vai trò bằng AI, material fingerprint.

### A6 Giao diện

Mục tiêu: làm trọn luồng bằng chuột, không cần gọi API tay.

Đợt 2 (code trên MockProvider trước):
1. React + TypeScript + Vite; kiểu dữ liệu sinh từ OpenAPI.
2. Các màn: Projects, Style Pack (kéo thả, gán vai trò), Generate, tiến độ thời gian thực, History dạng lưới, Compare bằng thanh trượt, Approve/Reject/Retry.
3. Bảng Advanced mặc định ẩn: model, steps, seed, prompt cuối sửa được.

Đợt 3:
1. Nút Final 4K chỉ bật khi preview đã duyệt.
2. Chế độ bộ ảnh: chọn view neo, chạy các view còn lại.
3. Hộp xác nhận chi phí trước khi gọi 4K cloud; màn chẩn đoán provider.

Đợt 4:
1. Màn Plan: khoanh phòng bằng polygon, đặt mũi tên camera.

Xong khi: toàn bộ tiêu chí cổng của đợt đang chạy làm được trên giao diện; tùy chọn provider không hỗ trợ được ẩn đi.
Không làm: đóng gói Tauri, trau chuốt thẩm mỹ trước cổng G2.

### A7 SketchUp (Đợt 3)

Mục tiêu: từ SketchUp bấm một nút là có job trong app.

1. Extension Ruby cho SketchUp 2025 dùng HTMLDialog, gọi HTTP tới backend localhost.
2. Nút Connect kiểm `/health`.
3. Xuất view hiện tại hoặc các scene đã chọn ra PNG theo tỉ lệ đã chọn.
4. Gửi kèm metadata theo `CameraMeta`: eye/target/up, FOV, tỉ lệ, kích thước viewport, checksum model.
5. Hiện tiến độ và thumbnail; bấm để mở History trong app.

Xong khi: xuất 10 scene tạo 10 job không ghi đè nhau; ảnh và metadata khớp tỉ lệ.
Không làm: pass depth, edge, material ID, mask theo tag.

### A8 Mặt bằng (Đợt 4)

Mục tiêu: từ một bản mặt bằng ra được concept một phòng.

1. Nhập PDF, PNG, JPG; chọn trang, xoay, hiệu chỉnh tỉ lệ.
2. Crop phòng bằng polygon thủ công trước; tự dò biên phòng làm sau và luôn giữ phương án thủ công.
3. Điền `Room`: loại phòng, kích thước, chiều cao trần, cửa và cửa sổ, `camera_hint`.
4. Endpoint nhập plan và tạo room.

Xong khi: nhập 1 plan, crop 1 phòng, gắn 4 ref theo vai trò, tạo concept, retry, approve.
Không làm: DWG, nhận diện chữ nhãn phòng.

## 6. Prompt khởi động cho A0

```text
Bạn là A0, agent điều phối dự án AI Interior Studio.

Đọc CLAUDE.md, docs/agent-plan.md, docs/contracts.md và docs/status.md trước khi làm bất cứ việc gì.

VIỆC CỦA BẠN
1. Không viết code tính năng. Bạn giao việc, duyệt và hợp nhất.
2. Giữ docs/status.md đúng: agent, đợt, trạng thái, nhánh, vướng mắc.
3. Chạy theo từng đợt trong agent-plan.md. Không mở đợt sau khi cổng của đợt trước chưa đạt.
4. Giao việc cho một agent bằng: quy tắc chung + brief của agent đó + phần việc của đợt hiện tại.
5. A1 đã xong. Hỏi tôi duyệt mục 6 của docs/contracts.md rồi mới giao A2.
6. Từ Đợt 2: giao song song các agent của đợt, mỗi agent một nhánh agent/<tên>.
7. Khi agent báo xong: kiểm nó chỉ sửa thư mục của mình và test xanh, rồi mới hợp nhất vào main.
8. Đề xuất đổi hợp đồng trong docs/contract-requests.md do bạn quyết; cập nhật contracts.md và báo các agent bị ảnh hưởng.
9. Cuối mỗi đợt: yêu cầu A9 chạy tiêu chí cổng và ghi docs/gates/G<n>.md. Sau đó dừng, tóm tắt cho tôi và chờ tôi duyệt.
10. Thiếu file model, workflow, API key hay ảnh mẫu thì hỏi tôi, không tự bịa.

BẮT ĐẦU
Xác nhận đã đọc các tài liệu, chạy pytest để kiểm phần A1, rồi hỏi tôi về 6 điểm ở mục 6 của contracts.
```
