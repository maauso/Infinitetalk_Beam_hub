# InfiniteTalk Beam.cloud Deployment

Generate lip-sync videos from images/videos and audio using [InfiniteTalk](https://github.com/Kijai/InfiniteTalk) on Beam.cloud infrastructure. This project deploys a complete ComfyUI-based video generation pipeline with asynchronous task queue processing via RESTful API.

## 🎯 Features

- **Dual video generation modes**:
  - **I2V (Image-to-Video)**: Transform static portraits into talking videos
  - **V2V (Video-to-Video)**: Re-sync lips on existing videos with new audio
- **Asynchronous task queue**: Handle long-running jobs (up to 60 min) without timeouts
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
pip install beam-client

```

### Configure Beam Authentication

```bash
# Login to Beam.cloud
beam configure

# Follow the prompts to authenticate
```

For detailed setup instructions, visit the [Beam Getting Started Guide](https://docs.beam.cloud/v2/getting-started/installation).

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone <your-repo-url>
cd Infinitetalk_Beam_hub
```

### 2. Create Python Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

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

### 5. Preload Models to Beam Volume (One-time, ~1 hour)

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

### 6. Deploy the Task Queue

Deploy the asynchronous task queue (1-hour timeout):
```bash
beam deploy app.py:queue_handler
```

After deployment, Beam will provide a webhook URL like:
```
https://api.beam.cloud/taskqueue/abc123/tasks
```

## 📡 Usage

### Image-to-Video (I2V)

```bash
# Using local files
python client_queue.py \
  --url https://api.beam.cloud/taskqueue/abc123/tasks \
  --mode i2v \
  -i portrait.jpg \
  -a speech.wav \
  -p "A woman speaking calmly" \
  -w 384 -H 384 \
  -o output_i2v.mp4

# Using URLs
python client_queue.py \
  --url https://api.beam.cloud/taskqueue/abc123/tasks \
  --mode i2v \
  -i https://example.com/face.jpg \
  -a https://example.com/audio.wav
```

### Video-to-Video (V2V)

```bash
# Re-sync lips on existing video with new audio
python client_queue.py \
  --url https://api.beam.cloud/taskqueue/abc123/tasks \
  --mode v2v \
  -v input_video.mp4 \
  -a new_audio.wav \
  -p "A person singing" \
  -w 640 -H 640 \
  -o output_v2v.mp4

# Using URLs
python client_queue.py \
  --url https://api.beam.cloud/taskqueue/abc123/tasks \
  --mode v2v \
  -v https://example.com/video.mp4 \
  -a https://example.com/audio.wav
```

### Monitor Task Progress

The client script automatically:
1. Validates inputs based on selected mode
2. Submits the task to Beam queue
3. Polls for completion every 5s with progress bar
4. Downloads the output video from Beam storage
5. Saves to specified filename

```bash
🎬 Mode: I2V (Image-to-Video)
🚀 Submitting task to https://...
✅ Task ID: task_abc123
⏳ Waiting for completion...
Status: RUNNING |█████████████          | 60/100 [01:23]
🎉 Task Completed!
📥 Downloading video from: https://...
✅ Video saved to output.mp4
```
- Support for local files or URLs

## 🎛️ API Parameters

### Common Parameters (I2V & V2V)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input_type` | string | `"image"` | Mode: `"image"` (I2V) or `"video"` (V2V) |
| `wav_path`/`wav_url`/`wav_base64` | string | required | Input audio file (WAV) |
| `prompt` | string | `"A person talking naturally"` | Description text for generation |
| `width` | integer | 384 (I2V), 640 (V2V) | Output video width (pixels) |
| `height` | integer | 384 (I2V), 640 (V2V) | Output video height (pixels) |
| `max_frame` | integer | auto-calculated | Max frames (auto: `audio_duration_sec * 25fps + 81`) |
| `force_offload` | boolean | `true` | Enable GPU offloading (trades speed for VRAM) |

### I2V-Specific Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `image_path`/`image_url`/`image_base64` | string | ✅ Yes | Input portrait image |

### V2V-Specific Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `video_path`/`video_url`/`video_base64` | string | ✅ Yes | Input video file |

## 🗂️ Project Structure

```
├── app.py                 # Beam task queue endpoint
├── handler_logic.py       # Core processing logic (I2V + V2V)
├── preload_models.py      # Model downloader to Volume
├── client_queue.py        # Unified async client (I2V & V2V)
├── retrieve_task.py       # Debug/recovery script
├── I2V_single.json        # ComfyUI workflow for Image-to-Video
├── V2V_single.json        # ComfyUI workflow for Video-to-Video
├── Dockerfile.beam        # Custom Docker image
├── requirements.txt       # Python dependencies
├── .env                   # Local configuration (git-ignored)
└── .env.example           # Configuration template
```

## 🔧 Advanced Configuration

### Modify Video Generation Settings

Edit [handler_logic.py](handler_logic.py) to change ComfyUI workflow parameters:

**For I2V:**
```python
# Line ~420 in process_infinitetalk()
prompt["284"]["inputs"]["image"] = image_path
prompt["245"]["inputs"]["value"] = width
prompt["246"]["inputs"]["value"] = height
prompt["270"]["inputs"]["value"] = max_frame
prompt["128"]["inputs"]["force_offload"] = force_offload
```

**For V2V:**
```python
# Line ~275 in process_v2v()
prompt["228"]["inputs"]["video"] = video_path  # VHS_LoadVideo
prompt["245"]["inputs"]["value"] = width
prompt["246"]["inputs"]["value"] = height
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
