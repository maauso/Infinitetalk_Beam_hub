"""
InfiniteTalk Beam.cloud Endpoint
Lip-sync video generation from image and audio

IMPORTANT: First run preload_models.py to load models into the Volume
"""

from beam import endpoint, task_queue, Output, Image, Volume
import subprocess
import time
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Volume for models (persistent across executions)
MODEL_VOLUME = Volume(name="infinitetalk-models", mount_path="/models")

# Image from Dockerfile
image = (
    Image.from_dockerfile("./Dockerfile.beam")
    .add_python_packages(["websocket-client", "librosa"])
    .with_envs({
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "PYTHONUNBUFFERED": "1"
    })
)

# Model mapping: Volume path -> ComfyUI path
MODEL_SYMLINKS = [
    # OLD GGUF models (kept temporarily for rollback)
    ("/models/diffusion_models/Wan2_1-InfiniteTalk_Single_Q8.gguf",
     "/ComfyUI/models/diffusion_models/Wan2_1-InfiniteTalk_Single_Q8.gguf"),
    ("/models/diffusion_models/wan2.1-i2v-14b-480p-Q8_0.gguf",
     "/ComfyUI/models/diffusion_models/wan2.1-i2v-14b-480p-Q8_0.gguf"),

    # NEW fp8 models (active)
    ("/models/diffusion_models/Wan2_1-InfiniteTalk-Single_fp8_e4m3fn_scaled_KJ.safetensors",
     "/ComfyUI/models/diffusion_models/Wan2_1-InfiniteTalk-Single_fp8_e4m3fn_scaled_KJ.safetensors"),
    ("/models/diffusion_models/Wan2_1-InfiniteTalk-Multi_fp8_e4m3fn_scaled_KJ.safetensors",
     "/ComfyUI/models/diffusion_models/Wan2_1-InfiniteTalk-Multi_fp8_e4m3fn_scaled_KJ.safetensors"),
    ("/models/diffusion_models/Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors",
     "/ComfyUI/models/diffusion_models/Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors"),

    # Common models (unchanged)
    ("/models/loras/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
     "/ComfyUI/models/loras/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"),
    ("/models/vae/Wan2_1_VAE_bf16.safetensors",
     "/ComfyUI/models/vae/Wan2_1_VAE_bf16.safetensors"),
    ("/models/text_encoders/umt5-xxl-enc-bf16.safetensors",
     "/ComfyUI/models/text_encoders/umt5-xxl-enc-bf16.safetensors"),
    ("/models/clip_vision/clip_vision_h.safetensors",
     "/ComfyUI/models/clip_vision/clip_vision_h.safetensors"),
    ("/models/diffusion_models/MelBandRoformer_fp16.safetensors",
     "/ComfyUI/models/diffusion_models/MelBandRoformer_fp16.safetensors"),
]


def setup_model_symlinks():
    """Create symlinks from Volume to ComfyUI model directories"""
    missing = []

    for volume_path, comfyui_path in MODEL_SYMLINKS:
        # Check if model exists in Volume
        if not os.path.exists(volume_path):
            logger.warning(f"⚠️ Model not found in Volume: {volume_path}")
            missing.append(volume_path)
            continue

        # Create parent directory
        os.makedirs(os.path.dirname(comfyui_path), exist_ok=True)

        # Remove existing file/symlink if exists
        if os.path.exists(comfyui_path) or os.path.islink(comfyui_path):
            os.remove(comfyui_path)

        # Create symlink
        os.symlink(volume_path, comfyui_path)
        logger.info(f"✅ Symlink: {comfyui_path} -> {volume_path}")

    if missing:
        raise Exception(f"Missing models in Volume. Run preload_models.py first! Missing: {missing}")


def on_start():
    """Initialize ComfyUI before processing requests"""
    logger.info("🚀 Starting initialization...")

    # Setup symlinks from Volume to ComfyUI
    logger.info("🔗 Setting up model symlinks...")
    setup_model_symlinks()

    # Start ComfyUI in background (without sage-attention - requires nvcc to compile)
    logger.info("🖥️ Starting ComfyUI...")
    subprocess.Popen([
        "python", "/ComfyUI/main.py",
        "--listen"
    ])

    # Wait for ComfyUI to be ready
    import urllib.request
    max_wait = 180  # 3 minutes
    for i in range(max_wait):
        try:
            urllib.request.urlopen("http://127.0.0.1:8188/", timeout=5)
            logger.info(f"✅ ComfyUI ready after {i} seconds")
            return {"comfyui_ready": True, "startup_time": i}
        except:
            time.sleep(1)

    raise Exception("ComfyUI failed to start within 3 minutes")


@endpoint(
    name="infinitetalk",
    cpu=2,
    memory="42Gi",
    gpu="RTX4090",
    image=image,
    volumes=[MODEL_VOLUME],
    on_start=on_start,
    keep_warm_seconds=900,  # 15 minutos warm para evitar colas
    timeout=1800,  # 30 minutes for long videos
)
def handler(context, **inputs):
    """
    InfiniteTalk endpoint - Generate lip-sync video from image + audio

    API compatible with RunPod format:

    Args:
        image_url/image_base64/image_path: Input portrait image
        wav_url/wav_base64/wav_path: Input audio file
        prompt: Description text (default: "A person talking naturally")
        width: Output width (default: 512)
        height: Output height (default: 512)
        max_frame: Max frames (auto-calculated from audio if not provided)
        force_offload: Enable GPU offloading to save VRAM (default: True)

    Returns:
        {"video": "base64_encoded_video"} on success
        {"error": "message"} on failure
    """
    from handler_logic import process_infinitetalk

    logger.info(f"📥 Received request with {len(inputs)} parameters")

    result = process_infinitetalk(inputs)

    if "error" in result:
        logger.error(f"❌ Error: {result['error']}")
    else:
        logger.info("✅ Video generated successfully")

    return result


# -----------------------------------------------------------------------------
# Task Queue (Asynchronous)
# Recommended for long running jobs to avoid timeouts
# -----------------------------------------------------------------------------
@task_queue(
    name="infinitetalk-queue",
    cpu=2,
    memory="48Gi",
    gpu="RTX4090",
    image=image,
    volumes=[MODEL_VOLUME],
    on_start=on_start,
    keep_warm_seconds=60,  # 1 minute wait before scaling down
    timeout=3600,           # 1 hour max execution time
)
def queue_handler(**inputs):
    """
    Async Task Queue for InfiniteTalk
    """
    from handler_logic import process_infinitetalk
    import base64

    logger.info(f"📥 Received ASYNC task with {len(inputs)} parameters")

    # Process normally which returns base64 video in 'video' key
    result = process_infinitetalk(inputs)

    if "error" in result:
        logger.error(f"❌ Error: {result['error']}")
        raise Exception(result['error'])

    # Decode base64 to file for Output()
    video_b64 = result.get("video")
    if video_b64:
        output_path = "output.mp4"
        with open(output_path, "wb") as f:
            f.write(base64.b64decode(video_b64))

        logger.info(f"💾 Saving Output: {output_path}")
        Output(path=output_path).save()

        # We don't need to return the base64 content now
        return {"status": "success", "message": "Video generated and uploaded"}

    return result


# For local testing (will not run on Beam.cloud)
if __name__ == "__main__":
    print("1. First run: beam run preload_models.py:preload_models")
    print("2. Then deploy: beam deploy app.py:handler")
