"""
Full Server Test - Run the FastAPI server and test with frontend

This script helps you test the full pipeline:
1. Start the FastAPI server
2. Use existing instrumental file
3. Generate vocals with enhanced expressions
4. Get the mixed output
"""

print("=" * 70)
print("🚀 VOCALIS-X SERVER TEST SETUP")
print("=" * 70)

print("""
This will help you test the FULL pipeline:

Step 1: Start the FastAPI server
--------------------------------
Open a NEW terminal and run:
  cd vocalis-x
  .venv\\Scripts\\Activate.ps1
  uvicorn main:app --reload

Step 2: Start the frontend (if using UI)
--------------------------------
Open ANOTHER terminal and run:
  cd vocalis-x-ui
  npm run dev

Step 3: Test with API (or use frontend)
--------------------------------
Option A - Using Python requests:
""")

test_request = """
import requests
import json

# API endpoint
url = "http://localhost:8000/generate_with_vocals"

# Your request payload
payload = {
    "song_name": "Test Song",
    "creative_prompt": "A happy upbeat pop song",
    "lyrics": "Love is a beautiful thing that makes my heart sing",
    "tempo": 1.2,
    "energy": 0.8,
    "darkness": 0.2,
    "emotion": {
        "joy": 0.8,
        "sadness": 0.1,
        "tension": 0.2
    },
    "singing_config": {
        "enabled": True,
        "backend": "openutau",
        "language": "en",
        "manual_emotion_override": True,
        "joy": 0.8,
        "sadness": 0.1,
        "tension": 0.2,
        "energy": 0.8,
        "darkness": 0.2
    },
    "instrumental_path": "C:/Users/adolf/vocalis-x/separated/htdemucs/ref1/no_vocals.wav",
    "reuse_last_instrumental": False
}

# Send request
response = requests.post(url, json=payload)

# Check response
if response.status_code == 200:
    result = response.json()
    print("✅ SUCCESS!")
    print(f"Vocals URL: {result.get('vocals_url')}")
    print(f"Mixed URL: {result.get('audio_url')}")
    print(f"Session ID: {result.get('session_id')}")
else:
    print(f"❌ ERROR: {response.status_code}")
    print(response.text)
"""

print(test_request)

print("""
Option B - Using frontend:
1. Open http://localhost:3000
2. Fill in:
   - Prompt: "A happy upbeat pop song"
   - Lyrics: "Love is a beautiful thing that makes my heart sing"
   - Adjust emotion sliders
3. Click Generate
4. Wait for Rena to sing!

Step 4: What to expect
--------------------------------
✅ Server generates instrumental (or uses provided file)
✅ Creates USTX with ENHANCED expressions
✅ Opens OpenUtau (if configured)
✅ Exports vocals
✅ Mixes vocals + instrumental
✅ Returns final audio with HUMAN-LIKE singing!

""")

print("=" * 70)
print("🎯 QUICK TEST WITHOUT SERVER")
print("=" * 70)

print("""
If you want to test just the USTX generation + OpenUtau:

1. Use existing instrumental file
2. Generate USTX with enhanced expressions
3. OpenUtau renders vocals
4. Mix manually

Here's a script to do that:
""")

quick_test = """
from openutau_ustx import write_ustx
from openutau_automation import render_ustx_to_wav
from pathlib import Path

# Your inputs
lyrics = "Love is a beautiful thing that makes my heart sing"
emotion = {
    "joy": 0.8,
    "sadness": 0.1,
    "tension": 0.2,
    "energy": 0.8,
    "darkness": 0.2
}

# Generate USTX with enhanced expressions
ustx_path = write_ustx(
    lyrics=lyrics,
    bpm=120,
    emotion=emotion
)

print(f"✅ USTX created: {ustx_path}")

# Render with OpenUtau
vocals_path = render_ustx_to_wav(
    ustx_path=str(ustx_path),
    export_dir="output/openutau",
    autostart=True
)

print(f"✅ Vocals rendered: {vocals_path}")
print("🎧 Open this file to hear Rena sing with enhanced expressions!")
"""

print(quick_test)

print("\n" + "=" * 70)
print("📝 SAVE THIS AS test_manual.py AND RUN IT")
print("=" * 70)

# Save the quick test script
with open("test_manual.py", "w", encoding="utf-8") as f:
    f.write('"""\nQuick manual test of enhanced singing\n"""\n\n')
    f.write(quick_test)

print("\n✅ Created: test_manual.py")
print("\nRun it with:")
print("  python test_manual.py")
print("\nThis will:")
print("  1. Generate USTX with enhanced expressions")
print("  2. Open OpenUtau and render vocals")
print("  3. Give you the vocals file")
print("\n" + "=" * 70)
