# InfiniteTalk Beam.cloud Deployment

Generate lip-sync videos from static images and audio using InfiniteTalk on Beam.cloud infrastructure. This project deploys a complete ComfyUI-based video generation pipeline with both synchronous and asynchronous processing modes.

## 🎯 Features

- **Lip-sync video generation**: Transform static portraits into talking videos
- **Dual deployment modes**: Synchronous endpoint for quick jobs, async task queue for long videos
- **Flexible input formats**: Support for file paths, URLs, and base64-encoded data
- **Persistent model storage**: 20GB+ models stored in Beam Volume for fast cold starts
- **Auto frame calculation**: Automatically determines video length from audio duration
- **GPU optimization**: Configurable force_offload for VRAM management on RTX4090

## 📋 Prerequisites

- **Python 3.10+**
- **Beam.cloud account**: Sign up at [beam.cloud](https://www.beam.cloud)
- **Beam CLI installed**: See [Installation Guide](https://docs.beam.cloud/v2/getting-started/installation)

### Install Beam CLI

```bash
# Using pip
pip install beam-sdk

# Or using homebrew (macOS)
brew tap slai-labs/homebrew-tap
brew install beam
```

### Configure Beam Authentication

```bash
# Login to Beam.cloud
beam configure

# Follow the prompts to authenticate
```

For detailed setup instructions, visit the [Beam Getting Started Guide](https://docs.beam.cloud/v2/getting-started/installation).

## 🚀 Quick Start

### 1. Clone and Install Dependencies

```bash
git clone <your-repo-url>
cd Infinitetalk_Beam_hub
pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your Beam token
nano .env
```

Your `.env` file should contain:
```bash
BEAM_TOKEN=your-beam-token-here
```

You can find your Beam token at: https://www.beam.cloud/account

### 3. Preload Models to Beam Volume (One-time, ~1 hour)

This downloads ~20GB of models (quantized GGUF, VAE, LoRA) to persistent storage:

```bash
beam run preload_models.py:preload_models
```

**Models downloaded:**
- Wan2.1-InfiniteTalk (Q8 GGUF) - 7.2GB
- Wan2.1-I2V-14B (Q8 GGUF) - 8.5GB
- Lightx2v LoRA - 450MB
- VAE (bf16) - 320MB
- UMT5-XXL text encoder - 4.8GB
- CLIP Vision - 3.7GB
- MelBandRoFormer - 320MB

### 4. Deploy the Endpoints

**Synchronous Endpoint** (30-min timeout):
```bash
beam deploy app.py:handler
```

**Async Task Queue** (1-hour timeout, recommended):
```bash
beam deploy app.py:queue_handler
```

After deployment, Beam will provide webhook URLs for your endpoints.

## 📡 API Usage

### Synchronous Endpoint

```python
import requests
import base64

# Encode your files
with open("portrait.jpg", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()
with open("audio.wav", "rb") as f:
    audio_b64 = base64.b64encode(f.read()).decode()

# Make request
response = requests.post(
    "https://api.beam.cloud/your-endpoint-url",
    json={
        "image_base64": image_b64,
        "wav_base64": audio_b64,
        "prompt": "A person talking naturally",
        "width": 512,
        "height": 512,
        "force_offload": True
    },
    headers={"Authorization": "Bearer YOUR_BEAM_TOKEN"}
)

# Get video
video_data = response.json()["video"]
with open("output.mp4", "wb") as f:
    f.write(base64.b64decode(video_data))
```

### Async Task Queue (Recommended for Long Videos)

Use the provided client script:

```bash
python client_queue.py \
  --url https://api.beam.cloud/v1/task_queue/YOUR_QUEUE_ID/tasks \
  -i portrait.jpg \
  -a audio.wav \
  -p "A person talking naturally" \
  -w 512 \
  -H 512 \
  -o output.mp4
```

**Client features:**
- Automatic task submission and polling
- Progress bar with status updates
- Automatic video download on completion
- Support for local files or URLs

## 🎛️ API Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image_path`/`image_url`/`image_base64` | string | required | Input portrait image |
| `wav_path`/`wav_url`/`wav_base64` | string | required | Input audio file (WAV) |
| `prompt` | string | `"A person talking naturally"` | Description text for generation |
| `width` | integer | `512` | Output video width (pixels) |
| `height` | integer | `512` | Output video height (pixels) |
| `max_frame` | integer | auto-calculated | Max frames (auto: `audio_duration_sec * 25fps + 81`) |
| `force_offload` | boolean | `true` | Enable GPU offloading (trades speed for VRAM) |

## 🗂️ Project Structure

```
├── app.py                 # Beam endpoints (sync + async)
├── handler_logic.py       # Core processing logic
├── preload_models.py      # Model downloader to Volume
├── client_queue.py        # Async queue client script
├── retrieve_task.py       # Debug/recovery script
├── I2V_single.json        # ComfyUI workflow (423 lines)
├── Dockerfile.beam        # Custom Docker image
├── requirements.txt       # Python dependencies
├── .env                   # Local configuration (git-ignored)
└── .env.example           # Configuration template
```

## 🔧 Advanced Configuration

### Modify Video Generation Settings

Edit `handler_logic.py` to change ComfyUI workflow parameters:

```python
# Line ~285-290 in process_infinitetalk()
prompt["245"]["inputs"]["value"] = width   # Node 245 = width
prompt["246"]["inputs"]["value"] = height  # Node 246 = height
prompt["270"]["inputs"]["value"] = max_frame
prompt["128"]["inputs"]["force_offload"] = force_offload
```

### Add New Models

1. Add download URL to `preload_models.py:MODEL_DOWNLOADS`
2. Add symlink mapping to `app.py:MODEL_SYMLINKS`
3. Re-run: `beam run preload_models.py:preload_models`

### Debug ComfyUI Workflow

Check startup logs to ensure ComfyUI initializes properly:
```bash
beam logs --app infinitetalk
```

ComfyUI runs on `localhost:8188` within the container and is initialized in `app.py:on_start()`.

## 🐛 Troubleshooting

### "Missing models in Volume" Error
Run `beam run preload_models.py:preload_models` to download models first.

### WebSocket Connection Timeout
ComfyUI takes ~30-60s to start. The handler waits up to 3 minutes. Check logs if it fails consistently.

### Out of Memory (OOM) Errors
Set `force_offload: true` in your API request to enable GPU memory offloading.

### Task Stuck in PENDING
Check Beam quotas and GPU availability in your dashboard.

## 📚 Additional Resources

- **Beam.cloud Documentation**: https://docs.beam.cloud
- **ComfyUI**: https://github.com/comfyanonymous/ComfyUI
- **InfiniteTalk Model**: https://huggingface.co/Kijai/WanVideo_comfy_GGUF

## 📝 License

This project uses multiple open-source models and frameworks. Check individual model licenses on HuggingFace.

## 🤝 Contributing

Contributions welcome! Please open issues for bugs or feature requests.
