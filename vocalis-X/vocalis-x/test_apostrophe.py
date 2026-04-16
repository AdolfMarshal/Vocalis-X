"""Test that apostrophes work correctly"""
from openutau_ustx import write_ustx

lyrics = "It's my life and it's now or never I ain't gonna live forever 'Cause it's my life"
emotion = {"joy": 0.7, "sadness": 0.2, "tension": 0.3, "energy": 0.8, "darkness": 0.2}

print("Testing lyrics with apostrophes:")
print(f"Lyrics: {lyrics}")

ustx = write_ustx(lyrics=lyrics, bpm=120, emotion=emotion)
print(f"\n✅ Generated: {ustx}")

# Validate YAML
import yaml
with open(ustx, 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f.read())
    
print(f"✅ YAML is VALID!")
print(f"Notes generated: {len(data['voice_parts'][0]['notes'])}")

# Check some lyrics
print("\nFirst 5 note lyrics:")
for note in data['voice_parts'][0]['notes'][:5]:
    print(f"  - {note['lyric']}")
