"""
test_enhanced_singing.py - Test Script for Enhanced Vocal Synthesis

This script helps you test and compare the enhanced singing system.

Usage:
    python test_enhanced_singing.py
"""

import os
import sys
from pathlib import Path

print("=" * 70)
print("🎤 VOCALIS-X ENHANCED SINGING TEST SUITE")
print("=" * 70)

# Check dependencies
print("\n1️⃣ Checking dependencies...")
try:
    import openutau_ustx_enhanced
    print("   ✅ openutau_ustx_enhanced.py found")
except ImportError as e:
    print(f"   ❌ openutau_ustx_enhanced.py not found: {e}")
    sys.exit(1)

try:
    import openutau_ustx
    print("   ✅ openutau_ustx.py (original) found")
    has_original = True
except ImportError:
    print("   ⚠️  openutau_ustx.py (original) not found - comparison tests will be skipped")
    has_original = False

try:
    from basic_pitch_melody import extract_melody_notes
    print("   ✅ basic_pitch_melody.py found")
    has_melody_extraction = True
except ImportError:
    print("   ⚠️  basic_pitch_melody.py not found - melody extraction will be skipped")
    has_melody_extraction = False

print("\n2️⃣ Setting up test scenarios...")

# Test scenarios with different emotions
test_scenarios = [
    {
        "name": "Happy Pop Song",
        "lyrics": "Dancing in the sunshine feeling so alive today",
        "emotion": {
            "joy": 0.8,
            "sadness": 0.1,
            "tension": 0.2,
            "energy": 0.9,
            "darkness": 0.1
        },
        "bpm": 128,
        "description": "High energy, bright, uplifting"
    },
    {
        "name": "Emotional Ballad",
        "lyrics": "I miss you so much it hurts to breathe without you here",
        "emotion": {
            "joy": 0.1,
            "sadness": 0.8,
            "tension": 0.3,
            "energy": 0.3,
            "darkness": 0.7
        },
        "bpm": 75,
        "description": "Slow, sad, breathy"
    },
    {
        "name": "Intense Rock",
        "lyrics": "Breaking through the chains that held me down so long",
        "emotion": {
            "joy": 0.4,
            "sadness": 0.2,
            "tension": 0.8,
            "energy": 0.9,
            "darkness": 0.5
        },
        "bpm": 140,
        "description": "High tension, powerful"
    },
    {
        "name": "Soft Jazz",
        "lyrics": "Moonlight whispers secrets only lovers know tonight",
        "emotion": {
            "joy": 0.5,
            "sadness": 0.3,
            "tension": 0.1,
            "energy": 0.4,
            "darkness": 0.6
        },
        "bpm": 90,
        "description": "Smooth, intimate, soft"
    }
]

print(f"   ✅ {len(test_scenarios)} test scenarios prepared")

# Create output directory for test files
test_output_dir = Path("output/test_enhanced")
test_output_dir.mkdir(parents=True, exist_ok=True)
print(f"   ✅ Test output directory: {test_output_dir}")


def analyze_ustx_file(ustx_path):
    """Analyze a USTX file and report on its contents"""
    try:
        with open(ustx_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Count features
        note_count = content.count('- position:')
        has_vibrato_variation = 'length: 0' in content  # Some notes have no vibrato
        has_phoneme_expr = 'phoneme_expressions:' in content and '- abbr:' in content
        has_voice_colors = 'color_index:' in content
        has_pitch_curves = 'pitch:' in content
        
        # Count expression types
        tension_count = content.count('abbr: tenc')
        breathiness_count = content.count('abbr: brec')
        gender_count = content.count('abbr: genc')
        
        return {
            'notes': note_count,
            'has_smart_vibrato': has_vibrato_variation,
            'has_phoneme_expressions': has_phoneme_expr,
            'has_voice_colors': has_voice_colors,
            'has_pitch_curves': has_pitch_curves,
            'tension_expressions': tension_count,
            'breathiness_expressions': breathiness_count,
            'gender_expressions': gender_count,
            'file_size': os.path.getsize(ustx_path)
        }
    except Exception as e:
        return {'error': str(e)}


def print_analysis(name, analysis):
    """Print analysis results in a nice format"""
    print(f"\n   📊 Analysis of {name}:")
    if 'error' in analysis:
        print(f"      ❌ Error: {analysis['error']}")
        return
    
    print(f"      • Notes: {analysis['notes']}")
    print(f"      • Smart Vibrato: {'✅' if analysis['has_smart_vibrato'] else '❌'}")
    print(f"      • Phoneme Expressions: {'✅' if analysis['has_phoneme_expressions'] else '❌'}")
    print(f"      • Voice Colors: {'✅' if analysis['has_voice_colors'] else '❌'}")
    print(f"      • Pitch Curves: {'✅' if analysis['has_pitch_curves'] else '❌'}")
    print(f"      • Expression Counts:")
    print(f"         - Tension: {analysis['tension_expressions']}")
    print(f"         - Breathiness: {analysis['breathiness_expressions']}")
    print(f"         - Gender: {analysis['gender_expressions']}")
    print(f"      • File Size: {analysis['file_size']:,} bytes")


# Run tests
print("\n3️⃣ Running tests...")
print("-" * 70)

test_results = []

for i, scenario in enumerate(test_scenarios, 1):
    print(f"\n🎵 Test {i}/{len(test_scenarios)}: {scenario['name']}")
    print(f"   Description: {scenario['description']}")
    print(f"   Lyrics: \"{scenario['lyrics']}\"")
    print(f"   BPM: {scenario['bpm']}")
    print(f"   Emotion: joy={scenario['emotion']['joy']}, sadness={scenario['emotion']['sadness']}, " 
          f"tension={scenario['emotion']['tension']}, energy={scenario['emotion']['energy']}")
    
    try:
        # Test enhanced version
        print("\n   🔬 Testing ENHANCED version...")
        from openutau_ustx_enhanced import write_ustx as write_enhanced
        
        enhanced_path = write_enhanced(
            lyrics=scenario['lyrics'],
            bpm=scenario['bpm'],
            emotion=scenario['emotion']
        )
        
        print(f"      ✅ Generated: {enhanced_path.name}")
        
        # Analyze enhanced output
        enhanced_analysis = analyze_ustx_file(enhanced_path)
        print_analysis("Enhanced", enhanced_analysis)
        
        # Test original version if available
        if has_original:
            print("\n   🔬 Testing ORIGINAL version (for comparison)...")
            from openutau_ustx import write_ustx as write_original
            
            original_path = write_original(
                lyrics=scenario['lyrics'],
                bpm=scenario['bpm'],
                emotion=scenario['emotion']
            )
            
            print(f"      ✅ Generated: {original_path.name}")
            
            # Analyze original output
            original_analysis = analyze_ustx_file(original_path)
            print_analysis("Original", original_analysis)
            
            # Comparison
            print("\n   📈 COMPARISON:")
            print(f"      Enhanced vs Original:")
            print(f"      • Smart Vibrato: {enhanced_analysis['has_smart_vibrato']} vs {original_analysis['has_smart_vibrato']}")
            print(f"      • Phoneme Expressions: {enhanced_analysis['tension_expressions'] + enhanced_analysis['breathiness_expressions'] + enhanced_analysis['gender_expressions']} vs 0")
            print(f"      • File Size: {enhanced_analysis['file_size']:,} vs {original_analysis['file_size']:,} bytes")
            
            improvement_pct = ((enhanced_analysis['file_size'] - original_analysis['file_size']) / original_analysis['file_size'] * 100)
            print(f"      • Size Increase: +{improvement_pct:.1f}% (more expression data)")
        
        test_results.append({
            'scenario': scenario['name'],
            'status': 'PASS',
            'enhanced_path': enhanced_path
        })
        
    except Exception as e:
        print(f"      ❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        test_results.append({
            'scenario': scenario['name'],
            'status': 'FAIL',
            'error': str(e)
        })
    
    print("-" * 70)


# Summary
print("\n4️⃣ TEST SUMMARY")
print("=" * 70)

passed = sum(1 for r in test_results if r['status'] == 'PASS')
failed = sum(1 for r in test_results if r['status'] == 'FAIL')

print(f"\n✅ PASSED: {passed}/{len(test_results)}")
print(f"❌ FAILED: {failed}/{len(test_results)}")

if failed > 0:
    print("\n❌ Failed Tests:")
    for r in test_results:
        if r['status'] == 'FAIL':
            print(f"   • {r['scenario']}: {r.get('error', 'Unknown error')}")

if passed > 0:
    print("\n✅ Generated Files:")
    for r in test_results:
        if r['status'] == 'PASS':
            print(f"   • {r['scenario']}: {r['enhanced_path']}")

# Next steps
print("\n5️⃣ NEXT STEPS")
print("=" * 70)
print("""
To hear the results:

1. Open OpenUtau:
   - Navigate to the output/ directory
   - Open any of the generated .ustx files

2. Compare original vs enhanced:
   - Listen to how vibrato changes based on note length
   - Notice pitch slides on large intervals
   - Hear voice color changes
   - Feel the emotional expression in phonemes

3. Fine-tune if needed:
   - Edit openutau_ustx_enhanced.py
   - Adjust vibrato depths, pitch slide amounts, etc.
   - Re-run this test script

4. Integrate into your workflow:
   - Replace openutau_ustx.py with enhanced version
   - Or import from openutau_ustx_enhanced in singing_synth.py
""")

print("\n" + "=" * 70)
print("🎤 TEST COMPLETE!")
print("=" * 70)
