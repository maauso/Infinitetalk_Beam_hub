# InfiniteTalk Beam.cloud Hub - AI Coding Agent Instructions

## Project Overview
This is a **Beam.cloud deployment** for InfiniteTalk (lip-sync video generation from image + audio) using ComfyUI. The architecture centers around:
- **Volume-based model storage** (persistent across executions)
- **Two deployment modes**: synchronous endpoint + asynchronous task queue
- **ComfyUI workflow orchestration** via WebSocket API

## Critical Architecture Patterns

### Model Management (Volume + Symlinks)
Models are stored in a persistent Beam Volume (`/models`) and symlinked to ComfyUI directories at startup:
- **First-time setup**: Run `beam run preload_models.py:preload_models` to download ~20GB of models to Volume
- **Runtime**: `app.py:setup_model_symlinks()` creates symlinks from `/models/*` → `/ComfyUI/models/*`
- **Key pattern**: Volume paths are absolute (`/models/diffusion_models/...`), ComfyUI paths follow standard structure
- See `MODEL_SYMLINKS` list in `app.py` for exact mappings

### Deployment Workflow (Critical Order)
```bash
# 1. Load models to Volume (one-time, ~1 hour)
beam run preload_models.py:preload_models

# 2. Deploy synchronous endpoint
beam deploy app.py:handler

# 3. Deploy async task queue
beam deploy app.py:queue_handler
```

### Dual API Modes
**Synchronous Endpoint** (`@endpoint`):
- Returns base64-encoded video in response JSON: `{"video": "base64_string"}`
- 30-min timeout, RTX4090 GPU, 15-min keep_warm
- Use for quick jobs or testing

**Async Task Queue** (`@task_queue`):
- Saves video to Beam storage via `Output().save()`
- Returns metadata: `{"status": "success", ...}`
- Client retrieves video from Beam's S3-like storage (see `client_queue.py`)
- 1-hour timeout, better for long videos

### ComfyUI Integration Pattern
1. **Startup**: `on_start()` launches ComfyUI server (`python /ComfyUI/main.py --listen`), waits for port 8188
2. **Runtime**: `handler_logic.py` communicates via:
   - HTTP POST to `/prompt` (submit workflow JSON)
   - WebSocket to `/ws` (monitor execution progress)
   - HTTP GET to `/history/{prompt_id}` (retrieve output paths)
3. **Workflow JSON**: `I2V_single.json` is the ComfyUI workflow template
   - Modified dynamically: inject image/audio paths, prompt text, dimensions
   - Node IDs are hardcoded (e.g., `"128"` = WanVideoSampler, `"284"` = image input)

### Input Flexibility Pattern
All handlers accept 3 input formats (see `handler_logic.py:process_input()`):
- `image_path`/`wav_path`: Absolute filesystem path
- `image_url`/`wav_url`: HTTP URL (downloaded via `wget`)
- `image_base64`/`wav_base64`: Base64-encoded data

Example API call:
```python
{
  "image_url": "https://example.com/face.jpg",
  "wav_base64": "UklGRi4...",
  "prompt": "A person talking naturally",
  "width": 512,
  "height": 512,
  "force_offload": true  # GPU memory optimization
}
```

### Frame Calculation
When `max_frame` is omitted, it's auto-calculated from audio duration:
```python
max_frame = int(audio_duration_seconds * 25_fps) + 81
```
See `handler_logic.py:calculate_max_frames_from_audio()` using `librosa`.

## Key Files & Responsibilities

| File | Purpose |
|------|---------|
| `app.py` | Beam entry points (endpoint + task queue), model symlink setup |
| `handler_logic.py` | Core processing logic, ComfyUI API client, input handling |
| `preload_models.py` | One-time model downloader to Volume |
| `client_queue.py` | Example client for submitting async tasks |
| `retrieve_task.py` | Debug script for polling/downloading completed tasks |
| `I2V_single.json` | ComfyUI workflow (423 lines, node graph for InfiniteTalk) |
| `Dockerfile.beam` | Custom Docker image (based on `wlsdml1114/multitalk-base:1.7`) |

## Common Development Tasks

### Modify Video Generation Parameters
Edit `handler_logic.py:process_infinitetalk()` where workflow nodes are configured:
```python
prompt["245"]["inputs"]["value"] = width   # Node 245 = width
prompt["246"]["inputs"]["value"] = height  # Node 246 = height
prompt["270"]["inputs"]["value"] = max_frame
```

### Add New Model to Volume
1. Add URL to `preload_models.py:MODEL_DOWNLOADS`
2. Add symlink mapping to `app.py:MODEL_SYMLINKS`
3. Re-run `beam run preload_models.py:preload_models`

### Debug ComfyUI Issues
- Check startup logs: `on_start()` waits up to 180s for ComfyUI readiness
- Inspect workflow errors: `handler_logic.py` logs node execution progress
- Manual testing: Add `logger.info()` in `get_videos()` WebSocket loop

### Test Locally (Limitations)
- Cannot run full deployment locally (requires Beam infrastructure)
- Test workflow modifications by loading `I2V_single.json` in standalone ComfyUI
- Validate input processing with `handler_logic.py` functions independently

## Critical Conventions

### Error Handling
All handlers return `{"error": "message"}` on failure (never raise exceptions to user)
```python
if not os.path.exists(image_path):
    return {"error": f"Image file not found: {image_path}"}
```

### Logging Style
Uses emoji prefixes for visibility: `✅`, `❌`, `⚠️`, `📥`, `🚀`
```python
logger.info("✅ ComfyUI ready after {i} seconds")
logger.error(f"❌ Base64 encoding failed: {e}")
```

### Base64 Truncation
For logging, truncate base64 to 50 chars (see `truncate_base64_for_log()`) to avoid log spam.

## External Dependencies
- **ComfyUI**: Running on `localhost:8188` (started by `on_start()`)
- **Beam SDK**: `beam-sdk` package, special decorators `@endpoint`, `@task_queue`, `Volume`, `Output`
- **HuggingFace**: Models downloaded from `huggingface.co` (Kijai, city96, Comfy-Org repos)
- **Custom ComfyUI Nodes**: 7 extensions cloned in `Dockerfile.beam` (GGUF, VideoHelper, MelBandRoFormer, etc.)

## Performance Notes
- `force_offload=true` trades speed for VRAM (enables larger videos on RTX4090)
- Keep-warm settings prevent cold starts: 900s for endpoint, 60s for queue
- Workflow uses quantized models (Q8 GGUF) for memory efficiency
