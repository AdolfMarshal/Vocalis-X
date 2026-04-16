"""
Configuration management for Vocalis-X
Supports environment variables and .env files
"""
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Optional


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # ========== PATHS ==========
    # Base directories
    base_dir: Path = Path(__file__).parent
    output_dir: Path = base_dir / "output"
    cache_dir: Path = base_dir / "cache"
    
    # Teacher tracks (reference instrumentals)
    teacher_track_dir: Path = base_dir / "separated" / "htdemucs"
    default_teacher_track: str = "ref1"  # Which ref track to use by default
    
    # OpenUtau
    openutau_cache_dir: Optional[Path] = None  # Auto-detected if None
    openutau_exe_path: Optional[Path] = None
    openutau_export_dir: Path = output_dir / "openutau"
    
    # DiffSinger
    diffsinger_root: Optional[Path] = None
    diffsinger_mini_engine_url: str = "http://127.0.0.1:9266"
    
    # ========== AUDIO SETTINGS ==========
    # Mixing
    default_vocals_gain: float = 0.25
    default_instrumental_gain: float = 2.0
    
    # Sample rates
    target_sample_rate: int = 44100
    musicgen_sample_rate: int = 32000
    
    # ========== MODEL SETTINGS ==========
    # MusicGen
    musicgen_model: str = "facebook/musicgen-medium"
    musicgen_fallback_model: str = "facebook/musicgen-small"
    musicgen_chunk_duration: float = 30.0
    musicgen_temperature: float = 1.0
    musicgen_top_k: int = 250
    
    # ========== GENERATION DEFAULTS ==========
    max_audio_duration: float = 180.0  # 3 minutes max
    min_audio_duration: float = 5.0    # 5 seconds min
    
    # ========== API SETTINGS ==========
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list = ["http://localhost:3000"]
    
    # ========== OPENUTAU AUTOMATION ==========
    openutau_autostart: bool = True
    openutau_wait_sec: int = 20
    openutau_open_key: str = "^o"
    openutau_export_key: str = "^e"
    openutau_export_menu_down: int = 11
    openutau_export_submenu_down: int = 2
    openutau_export_timeout_sec: int = 600
    openutau_default_bpm: int = 120
    openutau_default_base_tone: int = 72
    
    # ========== SESSION SETTINGS ==========
    session_timeout_minutes: int = 60
    max_cache_size_mb: int = 1000
    auto_cleanup_enabled: bool = True
    cleanup_interval_hours: int = 24
    
    # ========== EMOTION SETTINGS ==========
    joy_pad_lock_enabled: bool = True
    emotion_throttle_max: float = 0.25  # Max 25% emotion influence
    
    # ========== DEBUG SETTINGS ==========
    debug_mode: bool = False
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
    def get_teacher_track_path(self, track_name: Optional[str] = None) -> Path:
        """Get full path to a teacher track"""
        track = track_name or self.default_teacher_track
        return self.teacher_track_dir / track / "no_vocals.wav"
    
    def get_openutau_cache_dir(self) -> Path:
        """Get OpenUtau cache directory (auto-detect if not set)"""
        if self.openutau_cache_dir:
            return self.openutau_cache_dir
        
        # Try to auto-detect
        import os
        user_home = Path.home()
        possible_paths = [
            user_home / "Documents" / "OpenUtau" / "Cache",
            user_home / "AppData" / "Roaming" / "OpenUtau" / "Cache",
        ]
        
        for path in possible_paths:
            if path.exists():
                return path
        
        # Fallback
        return user_home / "Documents" / "OpenUtau" / "Cache"
    
    def ensure_directories(self):
        """Create necessary directories if they don't exist"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.openutau_export_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()

# Ensure directories exist on import
settings.ensure_directories()
