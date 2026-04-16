"""
Integration of learned timing patterns with openutau_ustx.py
This replaces the random duration calculation with learned patterns
"""

from pathlib import Path
import json
from syllable_timing import count_syllables


class LearnedTimingEngine:
    """Uses learned USTX patterns to generate natural timing"""
    
    def __init__(self, model_path: str = "ustx_timing_model.json"):
        self.model = self.load_model(model_path)
    
    def load_model(self, path: str):
        """Load the learned timing model"""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Timing model not found at {path}, using defaults")
            return self.get_default_model()
    
    def get_default_model(self):
        """Default model if no learned patterns available"""
        return {
            'syllable_duration': {'mean': 480, 'median': 480, 'std': 100},
            'phrase_start_duration': {'mean': 400, 'median': 400},
            'phrase_end_duration': {'mean': 960, 'median': 960},
            'duration_by_word_length': {
                '1': {'median': 360},
                '2': {'median': 400},
                '3': {'median': 480},
                '4': {'median': 540},
                '5': {'median': 600},
            }
        }
    
    def calculate_note_duration(
        self,
        word: str,
        is_phrase_start: bool = False,
        is_phrase_end: bool = False,
        is_climax: bool = False,
        emotion: dict = None,
        bpm: int = 120
    ) -> int:
        """
        Calculate natural duration for a word using learned patterns
        """
        
        if emotion is None:
            emotion = {}
        
        # Base duration from learned patterns
        word_len = str(len(word))
        
        if is_phrase_start:
            base_duration = self.model['phrase_start_duration']['median']
        elif is_phrase_end:
            base_duration = self.model['phrase_end_duration']['median']
        elif word_len in self.model.get('duration_by_word_length', {}):
            base_duration = self.model['duration_by_word_length'][word_len]['median']
        else:
            base_duration = self.model['syllable_duration']['median']
        
        # Adjust for syllable count
        num_syllables = count_syllables(word)
        if num_syllables > 1:
            base_duration = base_duration * (0.7 + num_syllables * 0.3)
        
        # Climax gets longer
        if is_climax:
            base_duration *= 1.3
        
        # Emotion adjustments
        joy = emotion.get('joy', 0.3)
        sadness = emotion.get('sadness', 0.2)
        
        if joy > 0.6:
            base_duration *= 0.9  # Faster
        elif sadness > 0.6:
            base_duration *= 1.15  # Slower
        
        # BPM adjustment (relative to 120 BPM base)
        if bpm != 120:
            base_duration *= (120 / bpm)
        
        return int(base_duration)


# Global instance
_timing_engine = None

def get_timing_engine():
    """Get or create the global timing engine"""
    global _timing_engine
    if _timing_engine is None:
        _timing_engine = LearnedTimingEngine()
    return _timing_engine


if __name__ == "__main__":
    # Test the timing engine
    engine = LearnedTimingEngine()
    
    print("🎵 Testing Learned Timing Engine\n")
    
    test_cases = [
        ("I", True, False, False),
        ("love", False, False, False),
        ("you", False, False, True),
        ("forever", False, True, False),
    ]
    
    emotion = {"joy": 0.7, "sadness": 0.2}
    
    for word, start, end, climax in test_cases:
        duration = engine.calculate_note_duration(
            word, start, end, climax, emotion, bpm=120
        )
        position = "start" if start else "end" if end else "climax" if climax else "middle"
        print(f"  '{word}' ({position}): {duration} ticks ({duration/480:.2f} beats)")
