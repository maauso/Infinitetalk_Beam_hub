"""
Lógica de procesamiento de InfiniteTalk para Beam.cloud
Adaptado de example/handler.py sin dependencias de RunPod
"""

import os
import websocket
import base64
import json
import uuid
import logging
import urllib.request
import urllib.parse
import binascii
import subprocess
import librosa
import time

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Server address (ComfyUI runs locally)
SERVER_ADDRESS = "127.0.0.1"


def truncate_base64_for_log(base64_str, max_length=50):
    """Truncate base64 string for logging"""
    if not base64_str:
        return "None"
    if len(base64_str) <= max_length:
        return base64_str
    return f"{base64_str[:max_length]}... (total {len(base64_str)} chars)"


def download_file_from_url(url, output_path):
    """Download file from URL"""
    try:
        result = subprocess.run(
            ["wget", "-O", output_path, "--no-verbose", "--timeout=30", url],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            logger.info(f"✅ Downloaded file from URL: {url} -> {output_path}")
            return output_path
        else:
            logger.error(f"❌ wget download failed: {result.stderr}")
            raise Exception(f"URL download failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("❌ Download timeout")
        raise Exception("Download timeout")
    except Exception as e:
        logger.error(f"❌ Download error: {e}")
        raise Exception(f"Download error: {e}")


def save_base64_to_file(base64_data, temp_dir, output_filename):
    """Save base64 data to file"""
    try:
        decoded_data = base64.b64decode(base64_data)
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        with open(file_path, "wb") as f:
            f.write(decoded_data)
        logger.info(f"✅ Saved base64 input to '{file_path}'")
        return file_path
    except (binascii.Error, ValueError) as e:
        logger.error(f"❌ Base64 decode failed: {e}")
        raise Exception(f"Base64 decode failed: {e}")


def process_input(input_data, temp_dir, output_filename, input_type):
    """Process input data and return file path"""
    if input_type == "path":
        logger.info(f"📁 Path input: {input_data}")
        return input_data
    elif input_type == "url":
        logger.info(f"🌐 URL input: {input_data}")
        os.makedirs(temp_dir, exist_ok=True)
        file_path = os.path.abspath(os.path.join(temp_dir, output_filename))
        return download_file_from_url(input_data, file_path)
    elif input_type == "base64":
        logger.info(f"🔢 Base64 input processing")
        return save_base64_to_file(input_data, temp_dir, output_filename)
    else:
        raise Exception(f"Unsupported input type: {input_type}")


def queue_prompt(prompt, client_id):
    """Queue prompt to ComfyUI"""
    url = f"http://{SERVER_ADDRESS}:8188/prompt"
    logger.info(f"Queueing prompt to: {url}")
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode("utf-8")
    
    req = urllib.request.Request(url, data=data)
    req.add_header("Content-Type", "application/json")
    
    try:
        response = urllib.request.urlopen(req)
        result = json.loads(response.read())
        logger.info(f"Prompt sent successfully: {result}")
        return result
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP error: {e.code} - {e.reason}")
        logger.error(f"Response: {e.read().decode('utf-8')}")
        raise
    except Exception as e:
        logger.error(f"Error sending prompt: {e}")
        raise


def get_history(prompt_id):
    """Get history from ComfyUI"""
    url = f"http://{SERVER_ADDRESS}:8188/history/{prompt_id}"
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())


def get_videos(ws, prompt, client_id):
    """Execute workflow and get output videos"""
    prompt_id = queue_prompt(prompt, client_id)["prompt_id"]
    logger.info(f"Workflow started: prompt_id={prompt_id}")
    
    output_videos = {}
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message["type"] == "executing":
                data = message["data"]
                if data["node"] is not None:
                    logger.info(f"Executing node: {data['node']}")
                if data["node"] is None and data["prompt_id"] == prompt_id:
                    logger.info("Workflow completed")
                    break
        else:
            continue
    
    history = get_history(prompt_id)[prompt_id]
    
    for node_id in history["outputs"]:
        node_output = history["outputs"][node_id]
        videos_output = []
        if "gifs" in node_output:
            for video in node_output["gifs"]:
                video_path = video["fullpath"]
                if os.path.exists(video_path):
                    logger.info(f"Video found: {video_path}")
                    videos_output.append(video_path)
        output_videos[node_id] = videos_output
    
    return output_videos


def load_workflow(workflow_path):
    """Load workflow JSON"""
    with open(workflow_path, "r") as file:
        return json.load(file)


def get_audio_duration(audio_path):
    """Get audio duration in seconds"""
    try:
        duration = librosa.get_duration(path=audio_path)
        return duration
    except Exception as e:
        logger.warning(f"Could not get audio duration ({audio_path}): {e}")
        return None


def calculate_max_frames_from_audio(wav_path, fps=25):
    """Calculate max_frames based on audio duration"""
    duration = get_audio_duration(wav_path)
    if duration is None:
        logger.warning("Could not calculate audio duration. Using default 81.")
        return 81
    
    max_frames = int(duration * fps) + 81
    logger.info(f"Audio duration: {duration:.2f}s, calculated max_frames: {max_frames}")
    return max_frames


def process_infinitetalk(inputs: dict) -> dict:
    """
    Process InfiniteTalk request
    
    Compatible with RunPod API format:
    - input_type: "image" (only I2V_single supported)
    - image_url/image_base64/image_path
    - wav_url/wav_base64/wav_path
    - prompt, width, height, max_frame
    """
    client_id = str(uuid.uuid4())
    task_id = f"task_{uuid.uuid4()}"
    
    # Log input (truncate base64)
    log_input = inputs.copy()
    for key in ["image_base64", "wav_base64"]:
        if key in log_input:
            log_input[key] = truncate_base64_for_log(log_input[key])
    logger.info(f"Received input: {log_input}")
    
    # Only I2V_single supported
    input_type = inputs.get("input_type", "image")
    if input_type != "image":
        return {"error": "Only input_type='image' is supported (I2V_single)"}
    
    # Process image input
    image_path = None
    if "image_path" in inputs:
        image_path = process_input(inputs["image_path"], task_id, "input_image.jpg", "path")
    elif "image_url" in inputs:
        image_path = process_input(inputs["image_url"], task_id, "input_image.jpg", "url")
    elif "image_base64" in inputs:
        image_path = process_input(inputs["image_base64"], task_id, "input_image.jpg", "base64")
    else:
        return {"error": "Image input required (image_path, image_url, or image_base64)"}
    
    # Process audio input
    wav_path = None
    if "wav_path" in inputs:
        wav_path = process_input(inputs["wav_path"], task_id, "input_audio.wav", "path")
    elif "wav_url" in inputs:
        wav_path = process_input(inputs["wav_url"], task_id, "input_audio.wav", "url")
    elif "wav_base64" in inputs:
        wav_path = process_input(inputs["wav_base64"], task_id, "input_audio.wav", "base64")
    else:
        return {"error": "Audio input required (wav_path, wav_url, or wav_base64)"}
    
    # Get parameters
    prompt_text = inputs.get("prompt", "A person talking naturally")
    width = inputs.get("width", 512)
    height = inputs.get("height", 512)
    
    # Calculate max_frame from audio if not provided
    max_frame = inputs.get("max_frame")
    if max_frame is None:
        max_frame = calculate_max_frames_from_audio(wav_path)
    
    logger.info(f"Settings: prompt='{prompt_text}', width={width}, height={height}, max_frame={max_frame}")
    
    # Load workflow (Beam syncs files to /mnt/code/)
    workflow_path = "/mnt/code/I2V_single.json"
    prompt = load_workflow(workflow_path)
    
    # ------------------------------------------------------------------
    # Dynamic Force Offload configuration
    # ------------------------------------------------------------------
    # 1. Read force_offload from input (default True: prevent OOM on small GPUs)
    force_offload = inputs.get("force_offload", True)
    logger.info(f"🔧 Settings: force_offload={force_offload}")

    # 2. Inject force_offload parameter into WanVideoSampler node
    sampler_node_id = None
    preferred_id = "128"

    # Check preferred ID (128) first for efficiency
    if preferred_id in prompt and prompt[preferred_id].get("class_type") == "WanVideoSampler":
        sampler_node_id = preferred_id
    else:
        # Fallback: search by class type
        for node_id, node_data in prompt.items():
            if node_data.get("class_type") == "WanVideoSampler":
                sampler_node_id = node_id
                break

    # If sampler node found, inject force_offload parameter
    if sampler_node_id:
        # setdefault creates 'inputs' dict if it doesn't exist
        node_inputs = prompt[sampler_node_id].setdefault("inputs", {})
        node_inputs["force_offload"] = force_offload
        logger.info(f"✅ Node {sampler_node_id} (WanVideoSampler) updated: force_offload={force_offload}")
    else:
        logger.warning("⚠️ Warning: WanVideoSampler node not found. Using workflow defaults.")
    # ------------------------------------------------------------------
    
    # Validate files exist
    if not os.path.exists(image_path):
        return {"error": f"Image file not found: {image_path}"}
    if not os.path.exists(wav_path):
        return {"error": f"Audio file not found: {wav_path}"}
    
    # Configure workflow nodes
    prompt["284"]["inputs"]["image"] = image_path
    prompt["125"]["inputs"]["audio"] = wav_path
    prompt["241"]["inputs"]["positive_prompt"] = prompt_text
    prompt["245"]["inputs"]["value"] = width
    prompt["246"]["inputs"]["value"] = height
    prompt["270"]["inputs"]["value"] = max_frame
    
    # Connect to ComfyUI WebSocket
    ws_url = f"ws://{SERVER_ADDRESS}:8188/ws?clientId={client_id}"
    logger.info(f"Connecting to WebSocket: {ws_url}")
    
    ws = websocket.WebSocket()
    max_attempts = 36  # 3 minutes
    for attempt in range(max_attempts):
        try:
            ws.connect(ws_url)
            logger.info(f"WebSocket connected (attempt {attempt+1})")
            break
        except Exception as e:
            logger.warning(f"WebSocket connection failed (attempt {attempt+1}/{max_attempts}): {e}")
            if attempt == max_attempts - 1:
                return {"error": "WebSocket connection timeout (3 minutes)"}
            time.sleep(5)
    
    # Execute workflow
    videos = get_videos(ws, prompt, client_id)
    ws.close()
    logger.info("WebSocket closed")
    
    # Find output video
    output_video_path = None
    for node_id in videos:
        if videos[node_id]:
            output_video_path = videos[node_id][0]
            break
    
    if not output_video_path:
        return {"error": "No output video found"}
    
    if not os.path.exists(output_video_path):
        return {"error": f"Output video file not found: {output_video_path}"}
    
    # Encode video to base64
    try:
        with open(output_video_path, "rb") as f:
            video_data = base64.b64encode(f.read()).decode("utf-8")
        
        logger.info(f"✅ Video encoded: {len(video_data)} chars")
        return {"video": video_data}
    except Exception as e:
        logger.error(f"❌ Base64 encoding failed: {e}")
        return {"error": f"Base64 encoding failed: {e}"}
