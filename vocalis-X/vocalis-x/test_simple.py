"""
test_simple.py - Quick Test of Enhanced Singing

Simple script to quickly test if the enhanced singing works.
"""

print("🎤 Quick Test: Enhanced Singing\n")

# Test 1: Import check
print("1. Checking if enhanced module loads...")
try:
    from openutau_ustx_enhanced import write_ustx
    print("   ✅ Enhanced module imported successfully!\n")
except ImportError as e:
    print(f"   ❌ Failed to import: {e}\n")
    exit(1)

# Test 2: Generate simple USTX
print("2. Generating test USTX...")
try:
    test_lyrics = "Hello world this is a test"
    test_emotion = {
        "joy": 0.6,
        "sadness": 0.2,
        "tension": 0.3,
        "energy": 0.7,
        "darkness": 0.3
    }
    
    ustx_path = write_ustx(
        lyrics=test_lyrics,
        bpm=120,
        emotion=test_emotion
    )
    
    print(f"   ✅ Generated: {ustx_path}\n")
    
except Exception as e:
    print(f"   ❌ Generation failed: {e}\n")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 3: Check file contents
print("3. Analyzing generated file...")
try:
    with open(ustx_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check for key features
    checks = {
        "Notes generated": '- position:' in content,
        "Vibrato present": 'vibrato:' in content,
        "Smart vibrato (no vibrato on some notes)": 'length: 0' in content,
        "Pitch curves": 'pitch:' in content,
        "Voice colors": 'color_index:' in content,
        "Phoneme expressions": '- abbr:' in content,
        "Tension expression": 'abbr: tenc' in content,
        "Breathiness expression": 'abbr: brec' in content,
        "Gender expression": 'abbr: genc' in content,
    }
    
    print("   Feature Checklist:")
    all_passed = True
    for check_name, check_result in checks.items():
        status = "✅" if check_result else "❌"
        print(f"      {status} {check_name}")
        if not check_result:
            all_passed = False
    
    print()
    
    if all_passed:
        print("   ✅ ALL CHECKS PASSED! Enhanced singing is working!\n")
    else:
        print("   ⚠️  Some features missing. Check openutau_ustx_enhanced.py\n")
    
except Exception as e:
    print(f"   ❌ Analysis failed: {e}\n")

# Test 4: File size comparison
print("4. File statistics...")
import os
file_size = os.path.getsize(ustx_path)
note_count = content.count('- position:')
print(f"   • File size: {file_size:,} bytes")
print(f"   • Note count: {note_count}")
print(f"   • Avg bytes per note: {file_size // note_count if note_count > 0 else 0}\n")

# Success message
print("=" * 60)
print("✅ QUICK TEST COMPLETE!")
print("=" * 60)
print(f"\nGenerated file: {ustx_path}")
print("\nNext steps:")
print("1. Open this file in OpenUtau")
print("2. Listen to the result")
print("3. Compare with original if you have it")
print("4. Run 'python test_enhanced_singing.py' for full test suite")
print()
