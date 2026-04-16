"""
Test YAML format validation for OpenUtau
"""

import yaml

print("🔍 Testing YAML Format Validation\n")

# Test the latest generated file
test_file = "output/vocalisx_20260226_150200_cd731d.ustx"

print(f"Testing file: {test_file}\n")

try:
    with open(test_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Try to parse as YAML
    data = yaml.safe_load(content)
    
    print("✅ YAML is VALID!")
    print(f"   Voice Parts: {len(data.get('voice_parts', []))}")
    
    if data.get('voice_parts'):
        notes = data['voice_parts'][0].get('notes', [])
        print(f"   Notes: {len(notes)}")
        
        # Check first note
        if notes:
            first_note = notes[0]
            print(f"\n📝 First Note:")
            print(f"   Lyric: {first_note.get('lyric')}")
            print(f"   Tone: {first_note.get('tone')}")
            print(f"   Color: {first_note.get('color_index')}")
            print(f"   Phoneme Expressions: {first_note.get('phoneme_expressions')}")
    
    print("\n✅ File should open in OpenUtau!")
    
except yaml.YAMLError as e:
    print(f"❌ YAML ERROR: {e}")
    print("\nThis means OpenUtau will reject the file.")
    
except Exception as e:
    print(f"❌ ERROR: {e}")

print("\n" + "="*60)
print("Now try opening this file in OpenUtau:")
print(f"  {test_file}")
print("="*60)
