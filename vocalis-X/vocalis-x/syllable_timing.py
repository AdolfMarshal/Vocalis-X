"""
Syllable-based timing system for natural singing
Based on how professional Vocaloid/OpenUtau users structure timing
"""

import re
from typing import List, Tuple


# Vowel sounds that form syllable nuclei
VOWELS = set('aeiouy')

def count_syllables(word: str) -> int:
    """
    Count syllables in a word using vowel-group method
    
    Examples:
        love -> 1 (one vowel group)
        beautiful -> 3 (eau, ti, ul)
        never -> 2 (e, er)
    """
    word = word.lower().strip()
    
    # Remove non-letters
    word = re.sub(r'[^a-z]', '', word)
    
    if not word:
        return 1
    
    # Count vowel groups
    vowel_groups = 0
    previous_was_vowel = False
    
    for char in word:
        is_vowel = char in VOWELS
        if is_vowel and not previous_was_vowel:
            vowel_groups += 1
        previous_was_vowel = is_vowel
    
    # Handle silent e
    if word.endswith('e') and vowel_groups > 1:
        vowel_groups -= 1
    
    # Handle special cases
    if word.endswith('le') and len(word) > 2 and word[-3] not in VOWELS:
        vowel_groups += 1
    
    return max(1, vowel_groups)


def is_stressed_syllable(word: str, syllable_index: int, total_syllables: int) -> bool:
    """
    Determine if a syllable is stressed
    
    Simple heuristic:
    - 1 syllable: always stressed
    - 2 syllables: first is stressed (HAPpy, LOVing)
    - 3+ syllables: stress varies, but typically on first or second
    """
    if total_syllables == 1:
        return True
    elif total_syllables == 2:
        return syllable_index == 0
    else:
        # For longer words, typically first or second syllable
        return syllable_index in [0, 1]


def calculate_syllable_durations(
    word: str,
    base_duration: int = 480,  # Quarter note in ticks
    is_phrase_end: bool = False,
    is_climax: bool = False,
    emotion: dict = None
) -> List[int]:
    """
    Calculate natural durations for each syllable in a word
    
    Returns list of durations (in ticks) for each syllable
    """
    if emotion is None:
        emotion = {}
    
    num_syllables = count_syllables(word)
    
    # Total time budget for this word
    total_duration = base_duration
    
    if is_phrase_end:
        total_duration = int(total_duration * 1.8)
    elif is_climax:
        total_duration = int(total_duration * 1.4)
    
    # Emotion affects overall tempo
    joy = emotion.get('joy', 0.3)
    sadness = emotion.get('sadness', 0.2)
    
    if joy > 0.6:
        total_duration = int(total_duration * 0.9)  # Faster
    elif sadness > 0.6:
        total_duration = int(total_duration * 1.2)  # Slower
    
    # Distribute duration across syllables
    if num_syllables == 1:
        return [total_duration]
    
    durations = []
    remaining_duration = total_duration
    
    for i in range(num_syllables):
        is_stressed = is_stressed_syllable(word, i, num_syllables)
        is_last = (i == num_syllables - 1)
        
        if is_last:
            # Last syllable gets whatever's left
            duration = remaining_duration
        else:
            # Stressed syllables get 60% of average
            # Unstressed get 40% of average
            avg_duration = total_duration // num_syllables
            
            if is_stressed:
                duration = int(avg_duration * 1.3)
            else:
                duration = int(avg_duration * 0.7)
            
            remaining_duration -= duration
        
        durations.append(max(120, duration))  # Minimum duration
    
    return durations


def split_word_into_syllables(word: str) -> List[str]:
    """
    Simple syllable splitting
    
    Note: This is approximate! Real syllabification is complex.
    For singing, we just need reasonable splits.
    """
    word = word.lower()
    syllables = []
    current = ""
    
    for i, char in enumerate(word):
        current += char
        
        # If we hit a vowel followed by consonant(s) then vowel, split
        if i < len(word) - 1:
            if char in VOWELS and word[i+1] not in VOWELS:
                # Check if next vowel is coming
                for j in range(i+1, len(word)):
                    if word[j] in VOWELS:
                        syllables.append(current)
                        current = ""
                        break
    
    if current:
        syllables.append(current)
    
    if not syllables:
        return [word]
    
    return syllables


# Professional timing templates based on common singing patterns
TIMING_TEMPLATES = {
    # Quarter note patterns (480 ticks = 1 beat at 120 BPM)
    "short": 240,      # Eighth note
    "normal": 480,     # Quarter note
    "long": 720,       # Dotted quarter
    "sustained": 960,  # Half note
    
    # Common syllable patterns
    "one_syllable": [480],
    "two_syllables_equal": [240, 240],
    "two_syllables_stressed": [320, 160],  # Stressed first
    "three_syllables": [200, 160, 120],     # Descending
    "four_syllables": [120, 120, 120, 120], # Equal
}


def get_natural_timing_for_phrase(
    words: List[str],
    phrase_position: str = "middle",  # "start", "middle", "end"
    tempo_factor: float = 1.0,
    emotion: dict = None
) -> List[Tuple[str, int]]:
    """
    Get natural timing for a list of words in a phrase
    
    Returns: List of (word, duration_in_ticks)
    """
    result = []
    
    for i, word in enumerate(words):
        is_phrase_start = (i == 0 and phrase_position == "start")
        is_phrase_end = (i == len(words) - 1 and phrase_position == "end")
        is_climax = (i == len(words) // 2)  # Middle word
        
        # Get syllable durations for this word
        syllable_durations = calculate_syllable_durations(
            word,
            base_duration=int(480 * tempo_factor),
            is_phrase_end=is_phrase_end,
            is_climax=is_climax,
            emotion=emotion
        )
        
        # Sum up syllable durations for total word duration
        total_word_duration = sum(syllable_durations)
        
        result.append((word, total_word_duration))
    
    return result


if __name__ == "__main__":
    # Test the system
    test_words = ["love", "beautiful", "forever", "it's", "life"]
    
    print("Syllable Counting:")
    for word in test_words:
        count = count_syllables(word)
        syllables = split_word_into_syllables(word)
        print(f"  {word}: {count} syllables -> {syllables}")
    
    print("\nDuration Calculation:")
    for word in test_words:
        durations = calculate_syllable_durations(word, is_phrase_end=(word=="life"))
        print(f"  {word}: {durations} ticks (total: {sum(durations)})")
    
    print("\nPhrase Timing:")
    phrase = ["It's", "my", "life"]
    emotion = {"joy": 0.7, "sadness": 0.1, "tension": 0.3}
    timing = get_natural_timing_for_phrase(phrase, "end", emotion=emotion)
    for word, duration in timing:
        print(f"  {word}: {duration} ticks ({duration/480:.2f} beats)")
