"""
Script to pre-load models into the Beam.cloud Volume
Run: python preload_models.py
"""

from beam import function, Image, Volume
import subprocess
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Same volume as the endpoint
MODEL_VOLUME = Volume(name="infinitetalk-models", mount_path="/models")

# Minimum image to download
image = (
    Image(python_version="python3.10")
    .add_commands(["apt-get update && apt-get install -y wget"])
)

# Model URLs
MODEL_DOWNLOADS = [
    # OLD GGUF models (kept temporarily for rollback, can remove after testing)
    ("https://huggingface.co/Kijai/WanVideo_comfy_GGUF/resolve/main/InfiniteTalk/Wan2_1-InfiniteTalk_Single_Q8.gguf",
     "diffusion_models/Wan2_1-InfiniteTalk_Single_Q8.gguf"),
    ("https://huggingface.co/city96/Wan2.1-I2V-14B-480P-gguf/resolve/main/wan2.1-i2v-14b-480p-Q8_0.gguf",
     "diffusion_models/wan2.1-i2v-14b-480p-Q8_0.gguf"),

    # NEW fp8 models (active)
    ("https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/InfiniteTalk/Wan2_1-InfiniteTalk-Single_fp8_e4m3fn_scaled_KJ.safetensors",
     "diffusion_models/Wan2_1-InfiniteTalk-Single_fp8_e4m3fn_scaled_KJ.safetensors"),
    ("https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/InfiniteTalk/Wan2_1-InfiniteTalk-Multi_fp8_e4m3fn_scaled_KJ.safetensors",
     "diffusion_models/Wan2_1-InfiniteTalk-Multi_fp8_e4m3fn_scaled_KJ.safetensors"),
    ("https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors",
     "diffusion_models/Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors"),

    # Common models (unchanged)
    ("https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
     "loras/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"),
    ("https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1_VAE_bf16.safetensors",
     "vae/Wan2_1_VAE_bf16.safetensors"),
    ("https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/umt5-xxl-enc-bf16.safetensors",
     "text_encoders/umt5-xxl-enc-bf16.safetensors"),
    ("https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors",
     "clip_vision/clip_vision_h.safetensors"),
    ("https://huggingface.co/Kijai/MelBandRoFormer_comfy/resolve/main/MelBandRoformer_fp16.safetensors",
     "diffusion_models/MelBandRoformer_fp16.safetensors"),
]


@function(
    name="preload-models",
    cpu=2,
    memory="4Gi",
    image=image,
    volumes=[MODEL_VOLUME],
    timeout=3600,  # 1 hour to download everything
)
def preload_models():
    """Downloads all models to the Volume"""

    results = []

    for url, relative_path in MODEL_DOWNLOADS:
        dest_path = f"/models/{relative_path}"

        if os.path.exists(dest_path):
            size_mb = os.path.getsize(dest_path) / (1024 * 1024)
            logger.info(f"✅ Already exists: {relative_path} ({size_mb:.1f} MB)")
            results.append({"file": relative_path, "status": "exists", "size_mb": size_mb})
            continue

        # Create directory
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        logger.info(f"📥 Downloading: {url}")
        try:
            result = subprocess.run(
                ["wget", "-O", dest_path, "--progress=dot:giga", url],
                capture_output=True,
                text=True,
                timeout=1800  # 30 min per model
            )
            if result.returncode == 0:
                size_mb = os.path.getsize(dest_path) / (1024 * 1024)
                logger.info(f"✅ Downloaded: {relative_path} ({size_mb:.1f} MB)")
                results.append({"file": relative_path, "status": "downloaded", "size_mb": size_mb})
            else:
                logger.error(f"❌ Failed: {result.stderr}")
                results.append({"file": relative_path, "status": "failed", "error": result.stderr})
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            results.append({"file": relative_path, "status": "error", "error": str(e)})

    # List all files in volume
    total_size = 0
    for root, dirs, files in os.walk("/models"):
        for f in files:
            path = os.path.join(root, f)
            total_size += os.path.getsize(path)

    return {
        "results": results,
        "total_size_gb": total_size / (1024 * 1024 * 1024)
    }


if __name__ == "__main__":
    # Executes the function on Beam.cloud
    print("🚀 Starting model preload on Beam.cloud...")
    result = preload_models.remote()
    print(f"✅ Result: {result}")
