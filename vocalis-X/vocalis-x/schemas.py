from pydantic import BaseModel, Field
from typing import List, Optional


# ---------- EMOTION ----------
class Emotion(BaseModel):
    joy: float
    sadness: float
    tension: float




# ---------- MUSIC CONFIG ----------
class MusicConfig(BaseModel):
    genre: str
   

# ---------- PROMPT CONFIG ----------
class PromptConfig(BaseModel):
    genre_lock: Optional[bool] = None


# ---------- GENERATION CONFIG ----------
class GenerationConfig(BaseModel):
    chunk_duration: Optional[float] = None
    overlap_sec: Optional[float] = None
    keep_sec: Optional[float] = None
    temperature: Optional[float] = None
    top_k: Optional[int] = None
    model_name: Optional[str] = None
    duration_sec: Optional[int] = None
    musicgen_cloud_enabled: Optional[bool] = None
    musicgen_kaggle_kernel: Optional[str] = None
    musicgen_kaggle_template_dir: Optional[str] = None
    musicgen_kaggle_poll_interval_sec: Optional[int] = None


# ---------- SINGING CONFIG ----------
class SingingConfig(BaseModel):
    enabled: Optional[bool] = None
    backend: Optional[str] = None  # mini_engine | diffsinger | external
    language: Optional[str] = None  # en | ja
    voicebank_path: Optional[str] = None
    diffsinger_root: Optional[str] = None
    manual_emotion_override: bool = False
    groove_template: str = None # <--- ADD THIS LINE
    vocoder_path: Optional[str] = None
    melody_midi_path: Optional[str] = None
    mt3_midi_path: Optional[str] = None
    mt3_fallback_enabled: Optional[bool] = None
    mt3_force_enabled: Optional[bool] = None
    mt3_compare_enabled: Optional[bool] = None
    mt3_input_source: Optional[str] = None  # guide_vocals | instrumental
    mt3_command: Optional[str] = None       # may contain {input_wav} and {output_mid}
    openutau_aah_primary_enabled: Optional[bool] = None
    vocals_path: Optional[str] = None
    vocals_gain: Optional[float] = None
    instrumental_gain: Optional[float] = None
    engine_url: Optional[str] = None
    model_name: Optional[str] = None
    target_duration: Optional[float] = None
    max_wait_sec: Optional[int] = None
    syllables_per_second: Optional[float] = None
    min_phoneme_duration: Optional[float] = None
    max_phoneme_duration: Optional[float] = None
    pause_multiplier: Optional[float] = None
    debug_phonemes: Optional[bool] = None
    debug_durations: Optional[bool] = None
    repeat_lyrics_until_target: Optional[bool] = None
    vowel_multiplier: Optional[float] = None
    consonant_multiplier: Optional[float] = None
    speedup: Optional[int] = None
    debug_lexicon: Optional[bool] = None
    openutau_exe_path: Optional[str] = None
    openutau_autostart: Optional[bool] = None
    openutau_wait_sec: Optional[int] = None
    openutau_open_key: Optional[str] = None
    openutau_export_key: Optional[str] = None
    openutau_export_menu_down: Optional[int] = None
    openutau_export_submenu_down: Optional[int] = None
    openutau_export_timeout_sec: Optional[int] = None
    autotune_enabled: Optional[bool] = None
    autotune_strength: Optional[float] = None
    autotune_max_shift: Optional[float] = None
    autotune_scale_mode: Optional[str] = None  # auto | major | minor | off
    autotune_key_pc: Optional[int] = None      # 0..11
    autotune_rubberband_exe: Optional[str] = None
    timemap_align_enabled: Optional[bool] = None
    timemap_anchor_hop_sec: Optional[float] = None
    timemap_max_warp_ratio: Optional[float] = None
    openutau_bpm: Optional[int] = None
    openutau_base_tone: Optional[int] = None
    openutau_export_dir: Optional[str] = None
    instrumental_path: Optional[str] = None 
    # DiffRhythm-first pipeline fields
    pipeline_mode: Optional[str] = None  # default | diffrhythm
    diffrhythm_command: Optional[str] = None
    diffrhythm_cwd: Optional[str] = None
    diffrhythm_song_path: Optional[str] = None
    # Cloud-first orchestration knobs
    cloud_first_enabled: Optional[bool] = None
    cloud_command: Optional[str] = None
    cloud_cwd: Optional[str] = None
    cloud_timeout_sec: Optional[int] = None
    kaggle_kernel: Optional[str] = None
    kaggle_template_dir: Optional[str] = None
    kaggle_poll_interval_sec: Optional[int] = None
    # Optional pre-generated stems (e.g. from Kaggle/Colab) to skip local DiffRhythm/Demucs load.
    diffrhythm_instrumental_path: Optional[str] = None
    diffrhythm_vocals_path: Optional[str] = None
    # Local fallback chunk settings (used when cloud attempt fails).
    local_chunk_fallback_enabled: Optional[bool] = None
    local_chunk_audio_length_sec: Optional[int] = None
    local_chunk_crossfade_sec: Optional[float] = None
    demucs_model: Optional[str] = None
    lead_vocals_path: Optional[str] = None
    backing_vocals_path: Optional[str] = None
    openutau_transcribed_ustx_path: Optional[str] = None
    mfa_command: Optional[str] = None
    mfa_textgrid_path: Optional[str] = None
    # Optional emotion hints for OpenUtau melody shaping
    joy: Optional[float] = None
    sadness: Optional[float] = None
    tension: Optional[float] = None
    energy: Optional[float] = None
    darkness: Optional[float] = None


# ---------- MAIN REQUEST ----------
class SemanticVector(BaseModel):
    # Suno-style prompting
    song_name: Optional[str] = None
    creative_prompt: Optional[str] = None
    music_config: Optional[MusicConfig] = None
    prompt_config: Optional[PromptConfig] = None
    generation_config: Optional[GenerationConfig] = None
    singing_config: Optional[SingingConfig] = None
    lyrics: Optional[str] = None
    instrumental_path: Optional[str] = None
    reuse_last_instrumental: Optional[bool] = None

    # Semantic innovation
    tempo: float
    energy: float
    darkness: float
    emotion: Emotion

    # Legacy / compatibility
    instrumentation: List[str]
    genre_hint: Optional[str] = None


class LyricsGenerationRequest(BaseModel):
    song_type: str = Field(..., min_length=2, max_length=40)
    time_signature: str = Field(..., min_length=3, max_length=12)
    bpm: int = Field(..., ge=40, le=240)
    description: str = Field(..., min_length=20, max_length=2000)


class LyricsGenerationResponse(BaseModel):
    title: str
    song_type: str
    time_signature: str
    bpm: int
    structure: List[str]
    lyrics: str
    notes: List[str]
