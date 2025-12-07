import requests
import sys
import json
import time
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

TASK_ID = "ffa96469-869e-4e77-ac44-e3917970cff4"
BEAM_TOKEN = os.getenv("BEAM_TOKEN")
if not BEAM_TOKEN:
    print("❌ Error: BEAM_TOKEN environment variable not set")
    print("Configure it in .env file or set: export BEAM_TOKEN='your-token-here'")
    sys.exit(1)

OUTPUT_FILE = "rescued_video_queue.mp4"

def check_task():
    # Correct URL according to docs: https://api.beam.cloud/v2/task/{TASK_ID}/
    url = f"https://api.beam.cloud/v2/task/{TASK_ID}/"
    headers = {"Authorization": f"Bearer {BEAM_TOKEN}"}

    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Error checking status: {e}")
        return None

print(f"🕵️  Checking task {TASK_ID}...")

while True:
    info = check_task()
    if not info:
        time.sleep(5)
        continue

    status = info.get("status")
    print(f"Status: {status}")

    if status in ["COMPLETED", "COMPLETE"]:
        outputs = info.get("outputs", [])
        if outputs:
            url = outputs[0].get("url")
            print(f"📥 Downloading video from: {url}")
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(OUTPUT_FILE, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            print(f"✅ Video saved to {OUTPUT_FILE}")
        else:
            print("❌ No outputs found (as expected if handler returned dict).")
            print("🔍 Inspecting full response for base64 data...")
            # Save full JSON to file to avoid console spam
            with open("task_debug.json", "w") as f:
                json.dump(info, f, indent=2)
            print("📄 Saved full response to task_debug.json")

            # Try to find base64 in common places
            # Beam might put return value in a specific field?
            # Or maybe we can't retrieve return values from Task Queue like this?
            # Let's hope it is in there.
        break

    if status in ["FAILED", "CANCELED"]:
        print("❌ Task failed!")
        break

    time.sleep(10)
