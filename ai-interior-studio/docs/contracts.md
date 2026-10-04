# Hợp đồng dùng chung

Trạng thái: **chờ A0 và NGUYEN duyệt**. Sau khi duyệt, không agent nào tự sửa các file trong `services/core/domain` và `services/core/storage`; đề xuất thay đổi ghi vào `docs/contract-requests.md`.

Mọi module khác import từ hai gói:

```python
from services.core.domain import RenderRequest, RenderJob, JobState, transition, ImageProvider, DomainError
from services.core.storage import DataRoot, Database, ArtifactStore, JobFiles
```

## 1. Model dữ liệu (`services/core/domain/models.py`)

Tất cả là Pydantic, `frozen` và từ chối trường lạ. Muốn đổi thì dùng `model_copy(update=...)`.

| Model | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `Project` | Dự án | `type`: apartment, house, office, retail |
| `Artifact` | Bản ghi trỏ tới một file bất biến | `id` là uuid; file định danh bằng `sha256` |
| `ReferenceSlot` | Ảnh tham chiếu trong một request | `artifact_id`, `role`, `priority` (mặc định theo role) |
| `Reference` | Ảnh tham chiếu lưu trong Style Pack | thêm `room_id`, `tags`, ghi chú nguồn và quyền dùng |
| `StylePack` | Bộ ảnh tham chiếu có phiên bản | khóa là `(id, version)`; `next_version()` tạo bản mới |
| `Scene`, `CameraMeta` | Cảnh SketchUp và metadata camera | `pass_artifact_ids` dành cho depth/edge ở V2 |
| `Room`, `Opening`, `CameraHint` | Phòng crop từ mặt bằng | dùng ở Đợt 4 |
| `PromptSpec` | Prompt có cấu trúc, 8 khối của mục 1.2 | `raw_text` là bản người dùng sửa tay |
| `RenderRequest` | Yêu cầu render chuẩn, mục 7.1 | xem mục 6 về các trường thêm |
| `RenderJob`, `RenderResult`, `JobError`, `StateChange` | Job và lịch sử trạng thái | |

Vai trò tham chiếu và ưu tiên mặc định (`ROLE_DEFAULT_PRIORITY`): BASE_PLAN, STYLE_MASTER, APPROVED_VIEW = 100; CEILING, WALL, FLOOR, CABINET = 75; FURNITURE, LIGHTING = 50; DECOR = 25.

## 2. State machine (`services/core/domain/job_state.py`)

| Từ | Được sang |
| --- | --- |
| DRAFT | QUEUED, CANCELLED |
| QUEUED | RUNNING, CANCELLED |
| RUNNING | REVIEW, FAILED, CANCELLED |
| REVIEW | APPROVED, RETRY |
| FAILED | RETRY |
| APPROVED | FINALIZING, DONE |
| FINALIZING | DONE, APPROVED |
| RETRY, DONE, CANCELLED | trạng thái kết |

- `transition(job, to_state, reason=, result=, error=)` trả về bản sao mới; job đầu vào không đổi. Sai thì ném `DomainError` mã `JOB_INVALID_TRANSITION`.
- Sang REVIEW phải có ít nhất 1 artifact (`JOB_MISSING_RESULT`). Sang FAILED phải có `error` (`JOB_MISSING_ERROR`).
- `retry_job(job)` chỉ nhận job ở REVIEW hoặc FAILED. Trả về `(job_cũ_ở_RETRY, job_mới_ở_DRAFT)`; job mới có `retry_of = id job cũ` và `revision + 1`.
- `ensure_can_finalize(preview_job)` ném `FINALIZE_REQUIRES_APPROVED` nếu preview chưa duyệt.
- `IN_FLIGHT_STATES` = QUEUED, RUNNING, FINALIZING: các job A2 phải đối chiếu khi khởi động lại.

## 3. Provider (`services/core/domain/provider.py`)

`ImageProvider` có `id`, `capabilities` và 6 hàm async: `health`, `validate`, `submit`, `poll`, `cancel`, `fetch_result`.

- `ProviderCapabilities`: `supported_modes`, `supports_multi_reference`, `max_reference_images`, `supported_ratios`, `supported_sizes`, `supports_seed`, `supports_negative_prompt`, `supports_local`, `has_usage_cost`, `license_class`.
- `fetch_result` trả `list[ProviderOutput]` (bytes ảnh). Provider không ghi file; orchestrator lưu qua `ArtifactStore`.
- `ProviderJob.provider_request` là nội dung để ghi `provider_request.json`.

## 4. Sự kiện WebSocket (`services/core/domain/events.py`)

`JobProgressEvent`: `type = "job.progress"`, `job_id`, `state`, `progress` (0 đến 1), `stage`, `message`, `metrics`.

## 5. Lưu trữ (`services/core/storage`)

```
<data_root>/
  studio.sqlite3
  projects/<project_id>/
    artifacts/<2 ký tự đầu sha>/<sha256><đuôi>   # ghi một lần, chỉ đọc
    jobs/<job_id>/request.json | provider_request.json | prompt.txt | refs.json | metrics.json
    sources/sketchup/  sources/plans/  cache/  logs/
```

- `ArtifactStore.put_bytes / put_file` trả về `Artifact`; cùng nội dung dùng chung một file; không có hàm nào sửa file đã ghi. `verify()` phát hiện file bị đổi (`ARTIFACT_CORRUPT`).
- `JobFiles.write_once` chỉ nhận 5 tên file ở trên và từ chối ghi lần hai (`SNAPSHOT_EXISTS`).
- `Database`: `projects`, `scenes`, `rooms`, `jobs` có `add / get / find / list / save`; `artifacts` chỉ có `add` (không sửa); `style_packs` có `add_version / get(id, version=None) / versions / list_latest`.
- `JobRepo` thêm `list_by_state`, `retries_of`, `children_of`.

## 6. Điểm khác đặc tả v1.0, cần bạn duyệt

1. **FAILED được sang RETRY.** Đặc tả không có đường nào ra khỏi FAILED.
2. **RETRY là trạng thái kết của job cũ.** Retry luôn tạo job mới (`retry_of`), đúng tiêu chí "new job links parent, old artifact immutable" ở mục 11. `parent_job_id` chỉ dùng cho quan hệ đầu vào: job edit hoặc upscale trỏ về job gốc.
3. **Final hỏng thì preview quay về APPROVED**, không sang FAILED. Lỗi nằm ở job upscale; preview đã duyệt không bị mất trạng thái.
4. **`fetch_result` trả bytes thay vì `Artifact`**, thêm `health()`, thêm `supported_modes` và `has_usage_cost` vào capabilities.
5. **File ảnh nằm trong `artifacts/` theo checksum**, không theo tên như `scenes/<id>/rgb.png`. Scene và Room trỏ tới artifact bằng id.
6. **`RenderRequest` thêm 6 trường**: `image_size`, `provider_id`, `seed`, `style_pack_id`, `style_pack_version`, `confirm_high_cost` (bắt buộc `true` cho lệnh 4K có phí).

## 7. Mã lỗi (`ErrorCode`)

NOT_FOUND, ALREADY_EXISTS, JOB_INVALID_TRANSITION, JOB_MISSING_RESULT, JOB_MISSING_ERROR, JOB_NOT_RETRYABLE, FINALIZE_REQUIRES_APPROVED, ARTIFACT_NOT_FOUND, ARTIFACT_CORRUPT, SNAPSHOT_EXISTS, SNAPSHOT_NAME_INVALID. Agent khác cần mã mới thì ghi đề xuất, A1 thêm vào.
