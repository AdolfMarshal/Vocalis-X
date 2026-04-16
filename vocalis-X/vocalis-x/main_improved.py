"""
Improved main.py with:
- Thread-safe session management
- Better error handling
- Configuration management
- Caching support
- Structured logging

This is a drop-in replacement for main.py
"""
import time
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import structlog

from schemas_improved import SemanticVector, GenerationResponse, ErrorResponse
from config import settings
from errors import (
    VocalisXError, MusicGenerationError, VocalSynthesisError,
    ValidationError, ConfigurationError
)
from session_manager import get_session_manager
from cache_manager import get_cache_manager
from prompt_builder import build_prompt
from musicgen_ai import generate_audio, get_audio_duration
from singing_synth import generate_vocals, mix_audio


# Setup structured logging
logger = structlog.get_logger()

# Initialize FastAPI app
app = FastAPI(
    title="Vocalis-X API",
    description="AI-powered music generation with vocal synthesis",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get managers
session_manager = get_session_manager()
cache_manager = get_cache_manager()
OUTPUT_ROOT = settings.output_dir.resolve()


def _audio_url_for_path(path: str) -> Optional[str]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        rel = p.resolve().relative_to(OUTPUT_ROOT)
    except ValueError:
        return f"/audio/{p.name}"
    return f"/audio/{str(rel).replace(os.sep, '/')}"


def _resolve_audio_file(file_path: str) -> Optional[Path]:
    normalized = os.path.normpath((file_path or "").replace("/", os.sep))
    if not normalized or normalized in {".", ""}:
        return None
    if os.path.isabs(normalized):
        return None
    candidate = (OUTPUT_ROOT / normalized).resolve()
    try:
        candidate.relative_to(OUTPUT_ROOT)
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info("vocalisx_starting", 
                port=settings.api_port,
                musicgen_model=settings.musicgen_model)
    settings.ensure_directories()


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("vocalisx_shutting_down")


@app.exception_handler(VocalisXError)
async def vocalisx_error_handler(request, exc: VocalisXError):
    """Handle custom Vocalis-X errors"""
    logger.error("vocalisx_error",
                 error_type=exc.__class__.__name__,
                 message=exc.message,
                 details=exc.details)
    
    return HTTPException(
        status_code=422,
        detail=exc.to_dict()
    )


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "sessions_active": len(session_manager.get_all_sessions()),
        "cache_size_mb": round(cache_manager.get_cache_size_mb(), 2)
    }


@app.post("/generate")
def generate_music(semantic: SemanticVector):
    """Generate instrumental music only (legacy endpoint)"""
    start_time = time.time()
    
    try:
        prompt = build_prompt(semantic)
        audio_path = generate_audio(prompt, semantic.generation_config)
        logger.info("generation_complete",
                    duration=time.time() - start_time,
                    prompt=prompt,
                    output=os.path.basename(audio_path))
        
        return {
            "song_name": semantic.song_name,
            "prompt_used": prompt,
            "audio_url": _audio_url_for_path(audio_path),
            "generation_time_sec": round(time.time() - start_time, 2)
        }
        
    except Exception as exc:
        logger.error("generation_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/generate_with_vocals", response_model=GenerationResponse)
def generate_with_vocals(
    semantic: SemanticVector,
    x_session_id: Optional[str] = Header(None)
):
    """Generate music with vocals (main endpoint)"""
    start_time = time.time()
    
    # Session management
    session_id = semantic.session_id or x_session_id
    if not session_id:
        session_id = session_manager.create_session()
    else:
        session_manager.get_session(session_id)  # Ensure exists and touch
    
    logger.info("generation_started",
                session_id=session_id,
                has_lyrics=bool(semantic.lyrics),
                vocals_enabled=semantic.singing_config and semantic.singing_config.enabled)
    
    try:
        # ====================================================
        # 1. JOY-PAD LOCK
        # ====================================================
        if semantic.singing_config and not semantic.singing_config.manual_emotion_override:
            if settings.joy_pad_lock_enabled:
                logger.debug("joy_pad_locked", session_id=session_id)
                semantic.emotion.joy = 0.0
                semantic.emotion.sadness = 0.0
                semantic.emotion.tension = 0.0
        else:
            # Apply throttle
            throttle = settings.emotion_throttle_max
            logger.debug("joy_pad_unlocked", 
                        session_id=session_id,
                        throttle=throttle)
            semantic.emotion.joy *= throttle
            semantic.emotion.sadness *= throttle
            semantic.emotion.tension *= throttle

        # Build prompt with protected emotions
        prompt = build_prompt(semantic)
        
        # ====================================================
        # 2. TEACHER TRACK REFERENCE
        # ====================================================
        teacher_track_name = session_manager.get_metadata(
            session_id, 
            "teacher_track", 
            default=settings.default_teacher_track
        )
        teacher_track = settings.get_teacher_track_path(teacher_track_name)
        
        if not teacher_track.exists():
            logger.warning("teacher_track_not_found",
                          path=str(teacher_track),
                          using_fallback=True)
            # Try fallback
            teacher_track = settings.get_teacher_track_path("ref1")
            if not teacher_track.exists():
                raise ConfigurationError(
                    "No teacher track found",
                    {"searched_paths": [str(teacher_track)]}
                )
        
        song_folder_name = teacher_track.parent.name
        
        # ====================================================
        # 3. INSTRUMENTAL GENERATION
        # ====================================================
        instrumental_path = None
        
        if semantic.instrumental_path:
            if not os.path.exists(semantic.instrumental_path):
                raise ValidationError(
                    "instrumental_path does not exist",
                    {"path": semantic.instrumental_path}
                )
            instrumental_path = semantic.instrumental_path
            
        elif semantic.reuse_last_instrumental:
            last_path = session_manager.get_last_instrumental(session_id)
            if last_path and os.path.exists(last_path):
                instrumental_path = last_path
                logger.info("reusing_instrumental", 
                           session_id=session_id,
                           path=instrumental_path)
            else:
                raise ValidationError("No previous instrumental to reuse")

        if not instrumental_path:
            logger.info("generating_instrumental",
                       session_id=session_id,
                       teacher_track=song_folder_name)
            
            instrumental_path = generate_audio(
                prompt=prompt,
                generation_config=semantic.generation_config,
                melody_ref_path=str(teacher_track)
            )
            
            # Store in session
            session_manager.set_last_instrumental(session_id, instrumental_path)

        response = GenerationResponse(
            song_name=semantic.song_name,
            prompt_used=prompt,
            instrumental_url=_audio_url_for_path(instrumental_path),
            audio_url=_audio_url_for_path(instrumental_path),
            vocals_enabled=False,
            session_id=session_id
        )

        # ====================================================
        # 4. VOCAL SYNTHESIS (if enabled)
        # ====================================================
        if not (semantic.singing_config and semantic.singing_config.enabled):
            response.generation_time_sec = round(time.time() - start_time, 2)
            logger.info("generation_complete",
                       session_id=session_id,
                       duration=response.generation_time_sec,
                       vocals_enabled=False)
            return response

        if not semantic.lyrics:
            raise ValidationError("lyrics is required for singing synthesis")

        try:
            logger.info("generating_vocals", session_id=session_id)
            
            # Pass emotion context to singing config
            if semantic.singing_config:
                semantic.singing_config.joy = semantic.emotion.joy
                semantic.singing_config.sadness = semantic.emotion.sadness
                semantic.singing_config.tension = semantic.emotion.tension
                semantic.singing_config.energy = semantic.energy
                semantic.singing_config.darkness = semantic.darkness
                semantic.singing_config.groove_template = f"{song_folder_name}_groove.json"
                semantic.singing_config.target_duration = get_audio_duration(instrumental_path)
            
            semantic.singing_config.instrumental_path = instrumental_path
            vocals_path = generate_vocals(
                lyrics=semantic.lyrics,
                language=semantic.singing_config.language or "en",
                singing_config=semantic.singing_config,
            )
            
            logger.info("mixing_audio", session_id=session_id)
            
            mixed_path = mix_audio(
                instrumental_path,
                vocals_path,
                vocals_gain=semantic.singing_config.vocals_gain or settings.default_vocals_gain,
                instrumental_gain=semantic.singing_config.instrumental_gain or settings.default_instrumental_gain,
            )
            
            response.vocals_enabled = True
            response.vocals_url = _audio_url_for_path(vocals_path)
            response.audio_url = _audio_url_for_path(mixed_path)
            
        except Exception as exc:
            logger.error("vocal_synthesis_failed",
                        session_id=session_id,
                        error=str(exc))
            raise VocalSynthesisError(str(exc), {"session_id": session_id})

        response.generation_time_sec = round(time.time() - start_time, 2)
        
        logger.info("generation_complete",
                   session_id=session_id,
                   duration=response.generation_time_sec,
                   vocals_enabled=True)
        
        return response
        
    except VocalisXError:
        raise
    except Exception as exc:
        logger.error("unexpected_error",
                    session_id=session_id,
                    error=str(exc),
                    error_type=type(exc).__name__)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/audio/{file_path:path}")
def get_audio(file_path: str):
    """Serve generated audio files"""
    file_path = _resolve_audio_file(file_path)
    
    if not file_path:
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    return FileResponse(
        file_path,
        media_type="audio/wav",
        headers={"Content-Disposition": "inline"}
    )


@app.post("/session/cleanup")
def cleanup_sessions():
    """Cleanup expired sessions"""
    removed = session_manager.cleanup_expired_sessions()
    return {"sessions_removed": removed}


@app.post("/cache/clear")
def clear_cache(prefix: Optional[str] = None):
    """Clear cache (optionally by prefix)"""
    cache_manager.clear(prefix)
    return {"status": "cache_cleared", "prefix": prefix}


@app.get("/cache/stats")
def cache_stats():
    """Get cache statistics"""
    return {
        "cache_size_mb": round(cache_manager.get_cache_size_mb(), 2),
        "cache_dir": str(cache_manager.cache_dir),
        "max_size_mb": cache_manager.max_size_mb
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug_mode
    )
