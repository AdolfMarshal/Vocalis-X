"""
Improved schemas with validation for Vocalis-X
This is a drop-in replacement for schemas.py with better validation
"""
from pydantic import BaseModel, Field, validator, field_validator
from typing import List, Optional


# ---------- EMOTION ----------
class Emotion(BaseModel):
    joy: float = Field(ge=0.0, le=1.0, description="Joy level (0-1)")
    sadness: float = Field(ge=0.0, le=1.0, description="Sadness level (0-1)")
    tension: float = Field(ge=0.0, le=1.0, description="Tension level (0-1)")


# ---------- MUSIC CONFIG ----------
class MusicConfig(BaseModel):
    genre: str = Field(min_length=1, max_length=100, description="Music genre")


# ---------- PROMPT CONFIG ----------
class PromptConfig(BaseModel):
    genre_lock: Optional[bool] = Field(default=None, description="Lock genre in prompt")


# ---------- GENERATION CONFIG ----------
class GenerationConfig(BaseModel):
    chunk_duration: Optional[float] = Field(default=None, gt=0, le=60, description="Chunk duration in seconds")
    overlap_sec: Optional[float] = Field(default=None, ge=0, le=10, description="Overlap between chunks")
    keep_sec: Optional[float] = Field(default=None, ge=0, le=30, description="Seconds to keep from each chunk")
    temperature: Optional[float] = Field(default=None, gt=0, le=2.0, description="Sampling temperature")
    top_k: Optional[int] = Field(default=None, gt=0, le=1000, description="Top-k sampling")
    model_name: Optional[str] = Field(default=None, description="Model name to use")


# ---------- SINGING CONFIG ----------
class SingingConfig(BaseModel):
    enabled: Optional[bool] = Field(default=None, description="Enable vocal synthesis")
    backend: Optional[str] = Field(default=None, pattern="^(mini_engine|diffsinger|external|openutau)$", description="Synthesis backend")
    language: Optional[str] = Field(default=None, pattern="^(en|ja)$", description="Language code")
    voicebank_path: Optional[str] = None
    diffsinger_root: Optional[str] = None
    manual_emotion_override: bool = Field(default=False, description="Override joy-pad lock")
    groove_template: Optional[str] = None
    vocoder_path: Optional[str] = None
    melody_midi_path: Optional[str] = None
    vocals_path: Optional[str] = None
    vocals_gain: Optional[float] = Field(default=None, ge=0.0, le=5.0, description="Vocals volume multiplier")
    instrumental_gain: Optional[float] = Field(default=None, ge=0.0, le=5.0, description="Instrumental volume multiplier")
    engine_url: Optional[str] = None
    model_name: Optional[str] = None
    target_duration: Optional[float] = Field(default=None, gt=0, description="Target duration in seconds")
    max_wait_sec: Optional[int] = Field(default=None, gt=0, le=3600, description="Max wait time for synthesis")
    syllables_per_second: Optional[float] = Field(default=None, gt=0, le=10, description="Syllables per second")
    min_phoneme_duration: Optional[float] = Field(default=None, ge=0.01, le=2.0)
    max_phoneme_duration: Optional[float] = Field(default=None, ge=0.01, le=5.0)
    pause_multiplier: Optional[float] = Field(default=None, ge=0.1, le=10.0)
    debug_phonemes: Optional[bool] = None
    debug_durations: Optional[bool] = None
    repeat_lyrics_until_target: Optional[bool] = None
    vowel_multiplier: Optional[float] = Field(default=None, ge=0.1, le=5.0)
    consonant_multiplier: Optional[float] = Field(default=None, ge=0.1, le=5.0)
    speedup: Optional[int] = Field(default=None, ge=1, le=100)
    debug_lexicon: Optional[bool] = None
    openutau_exe_path: Optional[str] = None
    openutau_autostart: Optional[bool] = None
    openutau_wait_sec: Optional[int] = Field(default=None, gt=0, le=300)
    openutau_open_key: Optional[str] = None
    openutau_export_key: Optional[str] = None
    openutau_export_menu_down: Optional[int] = Field(default=None, ge=1, le=50)
    openutau_export_submenu_down: Optional[int] = Field(default=None, ge=1, le=50)
    openutau_export_timeout_sec: Optional[int] = Field(default=None, gt=0, le=3600)
    openutau_bpm: Optional[int] = Field(default=None, ge=30, le=300, description="BPM for OpenUtau")
    openutau_base_tone: Optional[int] = Field(default=None, ge=36, le=96, description="Base MIDI tone")
    openutau_export_dir: Optional[str] = None
    
    # Optional emotion hints for OpenUtau melody shaping
    joy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    sadness: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    tension: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    energy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    darkness: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    
    @field_validator('min_phoneme_duration', 'max_phoneme_duration')
    def validate_phoneme_durations(cls, v, info):
        """Ensure min <= max for phoneme durations"""
        if info.field_name == 'max_phoneme_duration':
            min_dur = info.data.get('min_phoneme_duration')
            if min_dur is not None and v is not None and v < min_dur:
                raise ValueError('max_phoneme_duration must be >= min_phoneme_duration')
        return v


# ---------- MAIN REQUEST ----------
class SemanticVector(BaseModel):
    # Suno-style prompting
    song_name: Optional[str] = Field(default=None, max_length=200)
    creative_prompt: Optional[str] = Field(default=None, max_length=2000, description="Text prompt for generation")
    music_config: Optional[MusicConfig] = None
    prompt_config: Optional[PromptConfig] = None
    generation_config: Optional[GenerationConfig] = None
    singing_config: Optional[SingingConfig] = None
    lyrics: Optional[str] = Field(default=None, max_length=10000, description="Lyrics for vocal synthesis")
    instrumental_path: Optional[str] = None
    reuse_last_instrumental: Optional[bool] = Field(default=None, description="Reuse last generated instrumental")
    
    # Session management
    session_id: Optional[str] = Field(default=None, description="Session ID for tracking")

    # Semantic innovation
    tempo: float = Field(gt=0.0, le=2.0, description="Tempo multiplier (0-2)")
    energy: float = Field(ge=0.0, le=1.0, description="Energy level (0-1)")
    darkness: float = Field(ge=0.0, le=1.0, description="Darkness level (0-1)")
    emotion: Emotion

    # Legacy / compatibility
    instrumentation: List[str] = Field(default_factory=list, max_length=20)
    genre_hint: Optional[str] = Field(default=None, max_length=100)
    
    @field_validator('lyrics')
    def validate_lyrics_when_vocals_enabled(cls, v, info):
        """Ensure lyrics are provided when vocals are enabled"""
        singing_config = info.data.get('singing_config')
        if singing_config and singing_config.enabled and not v:
            raise ValueError('lyrics are required when singing_config.enabled is True')
        return v
    
    @field_validator('instrumentation')
    def validate_instrumentation_items(cls, v):
        """Validate instrumentation list items"""
        if v:
            for item in v:
                if not isinstance(item, str) or len(item) > 50:
                    raise ValueError('Each instrumentation item must be a string with max 50 characters')
        return v


# ---------- RESPONSE MODELS ----------
class GenerationResponse(BaseModel):
    """Response from generation endpoints"""
    song_name: Optional[str] = None
    prompt_used: str
    audio_url: str
    instrumental_url: Optional[str] = None
    vocals_url: Optional[str] = None
    vocals_enabled: bool = False
    session_id: Optional[str] = None
    generation_time_sec: Optional[float] = None


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    message: str
    details: dict = Field(default_factory=dict)
