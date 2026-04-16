"""
Quick manual test of enhanced singing
"""


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
