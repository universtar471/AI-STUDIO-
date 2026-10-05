# ComfyUI manifest contract

No production manifest or workflow is shipped yet: **chưa có workflow từ Đợt 0**.
`schema.json` is generated from `services.providers.comfyui.manifest.Manifest`.
Synthetic examples live only in `tests/unit/comfyui/fixtures`; they cannot render images.

## Configuration (Windows)

Set `AI_STUDIO_COMFYUI_CONFIG` to a JSON configuration file, or pass `ComfyUIConfig`
to `ComfyUIProvider(images, config=...)`. Fields:

- `url`: defaults to `http://127.0.0.1:8188`; HTTP or HTTPS, no embedded credentials.
- `manifest_dir`: defaults to `workflows/manifests`.
- `workflow_dir`: defaults to `workflows/comfyui`.
- `manifest`: explicit relative manifest filename; unset means unavailable. No auto-selection.
- `models_dir`: optional local ComfyUI `models` directory.
- `timeout_s`: execution deadline including uploads and fallback, default 300 seconds.

Relative configuration directories resolve against the process working directory.
Start the process from `ai-interior-studio`, or supply absolute directories.
The `ImageSource` protocol supplies base and reference bytes; storage stays with the caller.
A0 owns API registration and the storage adapter.

## Manifest fields

`name`, `template` (relative API JSON filename), `models`, `custom_nodes`, `bindings`,
`presets`, `max_reference_images`, `license_note` are required. Extra fields are rejected.
Paths cannot escape configured directories, including Windows absolute paths and symlinks.

Each model has `path` relative to ComfyUI's models directory and optional `sha256`.
For remote preflight, provide `object_info: {class_type, input}` identifying its loader combo.
The combo value is the model path without the first category directory, preserving subdirectories.
Without `models_dir`, preflight verifies advertised filenames only; it cannot verify file hashes.
With `models_dir`, preflight verifies files and declared hashes by streaming the local files.

Custom nodes declare `class_type` and `version`. All graph classes must exist in `/object_info`.
Versions in metrics are the **manifest's pinned versions**, not independently verified installed
versions: standard `/object_info` does not expose a reliable universal node version field.

Bindings specify `{node_id, input}` for the six runtime variables: `source_image`,
`reference_image` (ordered list), `prompt`, `long_edge`, `seed`, `filename_prefix`.
Two additional bindings, `steps` and `cfg`, apply values declared by each preset.
Bindings must be distinct and exist in the template. No nodes or connections are generated.
`max_reference_images` equals the number of reference bindings, excluding the base image.
Unused reference slots receive the uploaded base image again (a template default would be a
stale or missing file in ComfyUI). The adapter never invents filler images.

Both presets are mandatory: `PREVIEW_FAST` has `long_edge=1024`, `PREVIEW_QUALITY` has
`long_edge=1536`; both supply positive `steps` and nonnegative `cfg`.
Request `image_size` accepts `1024` or `1536`; otherwise DRAFT selects FAST and PREVIEW
selects QUALITY. FINAL, UPSCALE and PLAN_CONCEPT are not supported in this adapter stage.
The workflow preserves source aspect ratio; there is no ratio-rewiring binding.

## Execution and snapshots

One execution at a time per provider instance. The socket opens before `/prompt`, uses a unique
client ID per attempt, and filters messages by prompt ID. A deadline bounds stalled sockets.
Binary preview frames are ignored. Only final `output` images from history are returned.
QUALITY OOM retries once at FAST with the same uploaded images, prompt and seed.
Other failures never auto-resubmit a prompt, avoiding duplicate work after ambiguous failures.

`provider_request` records requested preset, prompt, workflow, seed, prefix, template hash,
image roles/IDs/hashes and dropped reference IDs, never image bytes or credentials.
Metrics record actual preset, fallback, attempt count, duration (including local queue wait),
template hash, model path-to-hash map (`checkpoint_sha256`) and pinned custom node versions.

Cancellation closes local monitoring and discards results; it does **not** send a global
ComfyUI `/interrupt`, which could interrupt another user's work. A submitted remote prompt may
finish after local cancellation or timeout. No result file is written by this provider.

Protocol references: [official WebSocket example](https://github.com/comfyanonymous/ComfyUI/blob/master/script_examples/websockets_api_example.py)
and [official server routes](https://github.com/comfyanonymous/ComfyUI/blob/master/server.py).

## Checks

From `ai-interior-studio`:

```powershell
.venv\Scripts\python -m pytest tests/unit/comfyui
.venv\Scripts\python -m pytest
```

Tests use an in-memory HTTP transport and a fake asynchronous socket; no live ComfyUI or external network.
