"""
USTX Pattern Learner - Learn timing patterns from professional USTX files
This analyzes real Vocaloid/OpenUtau projects to extract natural singing patterns
"""

import yaml
import json
import statistics
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict


class USTXPatternLearner:
    """Learn timing patterns from professional USTX files"""
    
    def __init__(self):
        self.patterns = {
            'syllable_durations': [],
            'phrase_end_durations': [],
            'phrase_start_durations': [],
            'vibrato_patterns': [],
            'note_durations_by_position': defaultdict(list),
            'duration_by_word_length': defaultdict(list),
            'bpm_distribution': [],
        }
        
        self.learned_stats = None
    
    def parse_ustx_file(self, file_path: str) -> Dict:
        """Parse a USTX file and extract timing information"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not data or 'voice_parts' not in data:
                return None
            
            bpm = data.get('bpm', 120)
            resolution = data.get('resolution', 480)
            
            voice_parts = data.get('voice_parts', [])
            if not voice_parts:
                return None
            
            notes = voice_parts[0].get('notes', [])
            
            return {
                'bpm': bpm,
                'resolution': resolution,
                'notes': notes,
                'file_path': file_path
            }
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            return None
    
    def analyze_note_sequence(self, notes: List[Dict], bpm: int):
        """Analyze a sequence of notes for patterns"""
        
        for i, note in enumerate(notes):
            duration = note.get('duration', 480)
            lyric = note.get('lyric', '')
            
            # Skip if no lyric
            if not lyric or lyric == '':
                continue
            
            # Determine position in phrase
            is_phrase_start = (i == 0)
            is_phrase_end = (i == len(notes) - 1)
            
            # Check for phrase boundaries (large gap before/after)
            if i > 0:
                prev_note = notes[i-1]
                gap = note['position'] - (prev_note['position'] + prev_note['duration'])
                if gap > 240:  # More than eighth note gap
                    is_phrase_start = True
            
            if i < len(notes) - 1:
                next_note = notes[i+1]
                gap = next_note['position'] - (note['position'] + duration)
                if gap > 240:
                    is_phrase_end = True
            
            # Collect duration data
            self.patterns['syllable_durations'].append(duration)
            
            if is_phrase_start:
                self.patterns['phrase_start_durations'].append(duration)
            elif is_phrase_end:
                self.patterns['phrase_end_durations'].append(duration)
            
            # Word length estimation (rough)
            word_len = len(lyric)
            self.patterns['duration_by_word_length'][word_len].append(duration)
            
            # Position in sequence
            position_bucket = min(i // 5, 10)  # Group into buckets
            self.patterns['note_durations_by_position'][position_bucket].append(duration)
            
            # Vibrato patterns
            if 'vibrato' in note:
                vib = note['vibrato']
                if isinstance(vib, dict):
                    self.patterns['vibrato_patterns'].append({
                        'duration': duration,
                        'vibrato_length': vib.get('length', 0),
                        'vibrato_depth': vib.get('depth', 0)
                    })
        
        self.patterns['bpm_distribution'].append(bpm)
    
    def learn_from_directory(self, directory: str):
        """Learn patterns from all USTX files in a directory"""
        
        directory = Path(directory)
        ustx_files = list(directory.glob('**/*.ustx'))
        
        print(f"Found {len(ustx_files)} USTX files to analyze...")
        
        analyzed = 0
        for file_path in ustx_files:
            data = self.parse_ustx_file(str(file_path))
            if data:
                self.analyze_note_sequence(data['notes'], data['bpm'])
                analyzed += 1
                if analyzed % 10 == 0:
                    print(f"  Analyzed {analyzed}/{len(ustx_files)} files...")
        
        print(f"✅ Analysis complete! Analyzed {analyzed} files.")
        
        # Calculate statistics
        self.calculate_statistics()
    
    def calculate_statistics(self):
        """Calculate statistical summaries of learned patterns"""
        
        def safe_stats(data_list):
            if not data_list:
                return {'mean': 480, 'median': 480, 'std': 0, 'min': 480, 'max': 480}
            return {
                'mean': statistics.mean(data_list),
                'median': statistics.median(data_list),
                'std': statistics.stdev(data_list) if len(data_list) > 1 else 0,
                'min': min(data_list),
                'max': max(data_list)
            }
        
        self.learned_stats = {
            'syllable_duration': safe_stats(self.patterns['syllable_durations']),
            'phrase_start_duration': safe_stats(self.patterns['phrase_start_durations']),
            'phrase_end_duration': safe_stats(self.patterns['phrase_end_durations']),
            'bpm': safe_stats(self.patterns['bpm_distribution']),
            'duration_by_word_length': {
                length: safe_stats(durations)
                for length, durations in self.patterns['duration_by_word_length'].items()
            },
            'vibrato_usage': {
                'total_notes': len(self.patterns['syllable_durations']),
                'notes_with_vibrato': sum(1 for v in self.patterns['vibrato_patterns'] if v['vibrato_length'] > 0),
                'vibrato_percentage': (sum(1 for v in self.patterns['vibrato_patterns'] if v['vibrato_length'] > 0) / 
                                     len(self.patterns['vibrato_patterns'])) * 100 if self.patterns['vibrato_patterns'] else 0
            }
        }
        
        print("\n📊 Learned Statistics:")
        print(f"  Average syllable duration: {self.learned_stats['syllable_duration']['mean']:.0f} ticks")
        print(f"  Average phrase start: {self.learned_stats['phrase_start_duration']['mean']:.0f} ticks")
        print(f"  Average phrase end: {self.learned_stats['phrase_end_duration']['mean']:.0f} ticks")
        print(f"  Vibrato usage: {self.learned_stats['vibrato_usage']['vibrato_percentage']:.1f}% of notes")
    
    def save_model(self, output_path: str = "ustx_timing_model.json"):
        """Save learned patterns to file"""
        
        if not self.learned_stats:
            print("No statistics to save. Run learn_from_directory first.")
            return
        
        with open(output_path, 'w') as f:
            json.dump(self.learned_stats, f, indent=2)
        
        print(f"✅ Saved timing model to: {output_path}")
    
    def load_model(self, model_path: str = "ustx_timing_model.json"):
        """Load pre-trained model"""
        
        try:
            with open(model_path, 'r') as f:
                self.learned_stats = json.load(f)
            print(f"✅ Loaded timing model from: {model_path}")
            return True
        except FileNotFoundError:
            print(f"Model not found: {model_path}")
            return False
    
    def suggest_duration(self, word: str, position: str = "middle", word_index: int = 0) -> int:
        """
        Suggest natural duration for a word based on learned patterns
        
        position: "start", "middle", "end"
        """
        
        if not self.learned_stats:
            return 480  # Default quarter note
        
        word_len = len(word)
        
        # Get base duration from word length patterns
        if word_len in self.learned_stats['duration_by_word_length']:
            base_duration = self.learned_stats['duration_by_word_length'][word_len]['median']
        else:
            base_duration = self.learned_stats['syllable_duration']['median']
        
        # Adjust based on position
        if position == "start":
            return int(self.learned_stats['phrase_start_duration']['median'])
        elif position == "end":
            return int(self.learned_stats['phrase_end_duration']['median'])
        else:
            return int(base_duration)


# Create sample USTX files for initial training
def create_sample_ustx_database():
    """Create a few sample USTX files with realistic timing patterns"""
    
    sample_dir = Path("sample_ustx_database")
    sample_dir.mkdir(exist_ok=True)
    
    # Sample 1: Pop song pattern
    sample1 = """name: Sample Pop Song
bpm: 120
resolution: 480
voice_parts:
- notes:
  - position: 0
    duration: 360
    tone: 64
    lyric: I
  - position: 360
    duration: 360
    tone: 65
    lyric: love
  - position: 720
    duration: 480
    tone: 67
    lyric: you
  - position: 1200
    duration: 720
    tone: 69
    lyric: so
  - position: 1920
    duration: 960
    tone: 67
    lyric: much
"""
    
    # Sample 2: Ballad pattern
    sample2 = """name: Sample Ballad
bpm: 75
resolution: 480
voice_parts:
- notes:
  - position: 0
    duration: 600
    tone: 62
    lyric: When
  - position: 600
    duration: 480
    tone: 64
    lyric: I
  - position: 1080
    duration: 720
    tone: 65
    lyric: see
  - position: 1800
    duration: 960
    tone: 67
    lyric: you
  - position: 2760
    duration: 1440
    tone: 69
    lyric: smile
"""
    
    # Sample 3: Upbeat pattern
    sample3 = """name: Sample Upbeat
bpm: 140
resolution: 480
voice_parts:
- notes:
  - position: 0
    duration: 240
    tone: 65
    lyric: Let's
  - position: 240
    duration: 240
    tone: 67
    lyric: go
  - position: 480
    duration: 480
    tone: 69
    lyric: dancing
  - position: 960
    duration: 240
    tone: 70
    lyric: all
  - position: 1200
    duration: 720
    tone: 72
    lyric: night
"""
    
    samples = [
        ('sample_pop.ustx', sample1),
        ('sample_ballad.ustx', sample2),
        ('sample_upbeat.ustx', sample3)
    ]
    
    for filename, content in samples:
        filepath = sample_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    print(f"✅ Created {len(samples)} sample USTX files in {sample_dir}")
    return sample_dir


if __name__ == "__main__":
    print("🎵 USTX Pattern Learner\n")
    
    # Learn from professional samples
    pro_sample_dir = Path("professional_ustx_samples")
    
    if pro_sample_dir.exists():
        print("📚 Learning from professional-style samples...")
        learner = USTXPatternLearner()
        learner.learn_from_directory(str(pro_sample_dir))
    else:
        print("⚠️ Professional samples not found, creating basic samples...")
        sample_dir = create_sample_ustx_database()
        learner = USTXPatternLearner()
        learner.learn_from_directory(str(sample_dir))
    
    # Save model
    learner.save_model("ustx_timing_model.json")
    
    # Test suggestions
    print("\n🎯 Duration Suggestions:")
    test_words = [("I", "start"), ("love", "middle"), ("you", "end"), ("forever", "end")]
    for word, pos in test_words:
        duration = learner.suggest_duration(word, pos)
        print(f"  '{word}' at {pos}: {duration} ticks ({duration/480:.2f} beats)")
