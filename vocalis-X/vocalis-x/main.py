from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from schemas import SemanticVector, LyricsGenerationRequest, LyricsGenerationResponse
from prompt_builder import build_prompt
from musicgen_ai import generate_audio, get_audio_duration
from singing_synth import generate_vocals, mix_audio, SingingNotConfiguredError
from diffrhythm_pipeline import run_diffrhythm_pipeline, DiffRhythmPipelineError
from lyrics_generator import generate_lyrics
from lyrics_llm import generate_lyrics_with_llm, LyricsLLMError
from musicgen_kaggle import run_musicgen_kaggle_generation, MusicGenKaggleError

from fastapi.responses import FileResponse
import os
import traceback
from pathlib import Path


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_LAST_INSTRUMENTAL_PATH = None
_OUTPUT_ROOT = os.path.abspath("output")


def _default_musicgen_kaggle_kernel() -> str | None:
    explicit = os.environ.get("VOCALIS_MUSICGEN_KAGGLE_KERNEL")
    if explicit:
        return explicit
    diffrhythm_kernel = os.environ.get("VOCALIS_KAGGLE_KERNEL")
    if not diffrhythm_kernel or "/" not in diffrhythm_kernel:
        return None
    account, _ = diffrhythm_kernel.split("/", 1)
    account = account.strip()
    if not account:
        return None
    return f"{account}/vocalis-x-musicgen-worker"


def _audio_url_for_path(path: str):
    if not path:
        return None
    if not os.path.exists(path):
        return None
    abs_path = os.path.abspath(path)
    try:
        rel_path = os.path.relpath(abs_path, _OUTPUT_ROOT)
    except ValueError:
        return f"/audio/{os.path.basename(path)}"
    if rel_path.startswith(".."):
        return f"/audio/{os.path.basename(path)}"
    rel_path = rel_path.replace("\\", "/")
    return f"/audio/{rel_path}"


def _resolve_audio_file(file_path: str):
    normalized = os.path.normpath((file_path or "").replace("/", os.sep))
    if not normalized or normalized in {".", ""}:
        return None
    if os.path.isabs(normalized):
        return None
    candidate = os.path.abspath(os.path.join(_OUTPUT_ROOT, normalized))
    if os.path.commonpath([candidate, _OUTPUT_ROOT]) != _OUTPUT_ROOT:
        return None
    if os.path.isfile(candidate):
        return candidate
    return None

@app.post("/generate")
def generate_music(semantic: SemanticVector):
    prompt = build_prompt(semantic)
    generation_config = semantic.generation_config
    audio_path = None
    warning = None

    musicgen_cloud_enabled = bool(getattr(generation_config, "musicgen_cloud_enabled", False)) if generation_config else False
    musicgen_kaggle_kernel = (
        getattr(generation_config, "musicgen_kaggle_kernel", None) if generation_config else None
    ) or _default_musicgen_kaggle_kernel()

    if musicgen_cloud_enabled and musicgen_kaggle_kernel:
        try:
            artifacts = run_musicgen_kaggle_generation(
                prompt=prompt,
                output_root=Path(_OUTPUT_ROOT),
                run_tag=f"{os.urandom(8).hex()}_musicgen_kaggle",
                kernel_slug=musicgen_kaggle_kernel,
                template_dir=Path(
                    (getattr(generation_config, "musicgen_kaggle_template_dir", None) if generation_config else None)
                    or os.environ.get("VOCALIS_MUSICGEN_KAGGLE_TEMPLATE_DIR")
                    or (Path(__file__).resolve().parent / "kaggle_musicgen_worker")
                ),
                model_name=(getattr(generation_config, "model_name", None) if generation_config else None) or "facebook/musicgen-medium",
                duration_sec=int((getattr(generation_config, "duration_sec", None) if generation_config else None) or 30),
                temperature=float((getattr(generation_config, "temperature", None) if generation_config else None) or 0.9),
                top_k=int((getattr(generation_config, "top_k", None) if generation_config else None) or 200),
                poll_interval_sec=int((getattr(generation_config, "musicgen_kaggle_poll_interval_sec", None) if generation_config else None) or os.environ.get("VOCALIS_MUSICGEN_KAGGLE_POLL_INTERVAL_SEC") or 20),
                timeout_sec=int(os.environ.get("VOCALIS_MUSICGEN_KAGGLE_TIMEOUT_SEC") or 3600),
            )
            audio_path = artifacts.audio_wav
        except MusicGenKaggleError as exc:
            warning = f"MusicGen Kaggle generation failed, falling back to local generation. Details: {exc}"

    if not audio_path:
        audio_path = generate_audio(prompt, generation_config)

    response = {
        "song_name": semantic.song_name,
        "prompt_used": prompt,
        "audio_url": _audio_url_for_path(audio_path)
    }
    if warning:
        response["warning"] = warning
    return response


@app.post("/generate_lyrics", response_model=LyricsGenerationResponse)
def generate_song_lyrics(request: LyricsGenerationRequest):
    llm_error = None
    try:
        llm_result = generate_lyrics_with_llm(
            song_type=request.song_type,
            time_signature=request.time_signature,
            bpm=request.bpm,
            description=request.description,
        )
        if llm_result:
            return LyricsGenerationResponse(
                title=llm_result.get("title") or "Untitled",
                song_type=request.song_type,
                time_signature=request.time_signature,
                bpm=request.bpm,
                structure=list(llm_result.get("structure") or []),
                lyrics=str(llm_result.get("lyrics") or "").strip(),
                notes=list(llm_result.get("notes") or ["Generated with LLM lyric mode."]),
            )
    except LyricsLLMError as exc:
        llm_error = str(exc)
        print(f"[Lyrics LLM] Falling back to local generator: {llm_error}")

    try:
        draft = generate_lyrics(
            song_type=request.song_type,
            time_signature=request.time_signature,
            bpm=request.bpm,
            description=request.description,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return LyricsGenerationResponse(
        title=draft.title,
        song_type=request.song_type,
        time_signature=request.time_signature,
        bpm=request.bpm,
        structure=draft.structure,
        lyrics=draft.lyrics,
        notes=([f"LLM fallback reason: {llm_error}"] if llm_error else []) + draft.notes,
    )


@app.get("/audio/{file_path:path}")
def get_audio(file_path: str):
    file_path = _resolve_audio_file(file_path)
    if not file_path:
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(
        file_path,
        media_type="audio/wav",
        headers={
            "Content-Disposition": "inline"
        }
    )


@app.post("/generate_with_vocals")
def generate_with_vocals(semantic: SemanticVector):
    global _LAST_INSTRUMENTAL_PATH
    
    # ====================================================
    # 1. THE JOY-PAD LOCK
    # ====================================================
    # If the user hasn't explicitly unlocked the UI, zero out the interference
    if semantic.singing_config and not semantic.singing_config.manual_emotion_override:
        print("🔒 Joy-Pad Locked: Neutralizing UI interference.")
        semantic.emotion.joy = 0.0
        semantic.emotion.sadness = 0.0
        semantic.emotion.tension = 0.0
    else:
        # LOCK IS OFF: 80/20 Rule applied!
        print("⚠️ Joy-Pad Unlocked: Applying 20% Throttle.")
        # Even if they drag the pad to 1.0 (100%), we mathematically crush it 
        # down to a maximum of 0.25 (25%) so it acts only as a "nudge".
        MAX_NUDGE = 0.25 
        
        semantic.emotion.joy *= MAX_NUDGE
        semantic.emotion.sadness *= MAX_NUDGE
        semantic.emotion.tension *= MAX_NUDGE
        # Now, a 0.95 Joy input safely becomes ~0.23!

    # 1. The Band (MusicGen) gets protected. 
    # prompt_builder.py only sees a max of 0.25, so your text prompt stays in charge!
    prompt = build_prompt(semantic)
        
   

    pipeline_mode = ""
    if semantic.singing_config:
        pipeline_mode = (getattr(semantic.singing_config, "pipeline_mode", None) or "").strip().lower()
    if pipeline_mode == "diffrhythm":
        if not semantic.singing_config:
            raise HTTPException(status_code=422, detail="singing_config is required for diffrhythm pipeline")
        if not semantic.lyrics:
            raise HTTPException(status_code=422, detail="lyrics is required for diffrhythm pipeline")
        print("[DiffRhythm] Entering diffrhythm pipeline from /generate_with_vocals")
        try:
            artifacts = run_diffrhythm_pipeline(semantic=semantic, prompt=prompt)
        except (SingingNotConfiguredError, DiffRhythmPipelineError) as exc:
            print(f"ERROR [diffrhythm_pipeline]: {exc}")
            traceback.print_exc()
            raise HTTPException(status_code=422, detail=str(exc))
        return {
            "song_name": semantic.song_name,
            "prompt_used": prompt,
            "vocals_enabled": True,
            "instrumental_url": _audio_url_for_path(artifacts.instrumental_wav),
            "vocals_url": _audio_url_for_path(artifacts.rendered_vocals_wav),
            "audio_url": _audio_url_for_path(artifacts.final_mix_wav),
            "warning": artifacts.warning,
            "pipeline_debug": {
                "mode": "diffrhythm",
                "openutau_fallback_used": artifacts.openutau_fallback_used,
                "full_song_url": _audio_url_for_path(artifacts.full_song_wav),
                "raw_vocals_url": _audio_url_for_path(artifacts.vocals_wav),
                "lead_vocals_url": _audio_url_for_path(artifacts.lead_vocals_wav),
                "backing_vocals_url": _audio_url_for_path(artifacts.backing_vocals_wav),
                "mapped_ustx": artifacts.mapped_ustx,
            },
        }

    # ====================================================
    # 2. THE DNA REFERENCE (TEACHER TRACK)
    # ====================================================
    # IMPORTANT: Update this path to point to one of your 12 Demuced rock tracks!
    teacher_track = "C:\\Users\\adolf\\vocalis-x\\separated\\htdemucs\\ref1\\no_vocals.wav"


    instrumental_path = None
    if semantic.instrumental_path:
        if not os.path.exists(semantic.instrumental_path):
            raise HTTPException(status_code=422, detail="instrumental_path does not exist")
        instrumental_path = semantic.instrumental_path
    elif semantic.reuse_last_instrumental:
        if _LAST_INSTRUMENTAL_PATH and os.path.exists(_LAST_INSTRUMENTAL_PATH):
            instrumental_path = _LAST_INSTRUMENTAL_PATH
        else:
            raise HTTPException(status_code=422, detail="No previous instrumental to reuse")

    if not instrumental_path:
        # ====================================================
        # 3. WIRING THE BAND 
        # ====================================================
        # Now passing the teacher track to lock the generation style
        instrumental_path = generate_audio(
            prompt=prompt, 
            generation_config=semantic.generation_config,
            melody_ref_path=teacher_track
        )
        _LAST_INSTRUMENTAL_PATH = instrumental_path

    # Groove template should follow the actual instrumental folder when possible.
    # Example: ...\separated\htdemucs\ref3\no_vocals.wav -> ref3_groove.json
    groove_template_name = None
    if instrumental_path:
        instrumental_folder = os.path.basename(os.path.dirname(instrumental_path))
        candidate = f"{instrumental_folder}_groove.json"
        if os.path.exists(os.path.join("swagger_templates", candidate)):
            groove_template_name = candidate

    # Fallback to the teacher-track groove if instrumental-specific groove is missing.
    if not groove_template_name:
        teacher_folder = os.path.basename(os.path.dirname(teacher_track))
        groove_template_name = f"{teacher_folder}_groove.json"

    response = {
        "song_name": semantic.song_name,
        "prompt_used": prompt,
        "instrumental_url": _audio_url_for_path(instrumental_path),
        "audio_url": _audio_url_for_path(instrumental_path),
        "vocals_enabled": False,
    }

    if not (semantic.singing_config and semantic.singing_config.enabled):
        return response

    if not semantic.lyrics:
        raise HTTPException(status_code=422, detail="lyrics is required for singing synthesis")

    try:
        if semantic.singing_config:
            # Pass emotion context to singing config for OpenUtau melody shaping
            semantic.singing_config.joy = semantic.emotion.joy
            semantic.singing_config.sadness = semantic.emotion.sadness
            semantic.singing_config.tension = semantic.emotion.tension
            semantic.singing_config.energy = semantic.energy
            semantic.singing_config.darkness = semantic.darkness
            semantic.singing_config.groove_template = groove_template_name
            semantic.singing_config.target_duration = get_audio_duration(instrumental_path)
            semantic.singing_config.instrumental_path = instrumental_path    
        vocals_path = generate_vocals(
            lyrics=semantic.lyrics,
            language=semantic.singing_config.language or "en",
            singing_config=semantic.singing_config,
        )
        mixed_path = mix_audio(
            instrumental_path,
            vocals_path,
            vocals_gain=semantic.singing_config.vocals_gain or 0.25,
            instrumental_gain=semantic.singing_config.instrumental_gain or 2.0,
        )
        print(f"Mix complete: {mixed_path}")
    except SingingNotConfiguredError as exc:
        print(f"ERROR [generate_with_vocals]: {exc}")
        traceback.print_exc()
        raise HTTPException(status_code=422, detail=str(exc))

    response["vocals_enabled"] = True
    response["vocals_url"] = _audio_url_for_path(vocals_path)
    response["audio_url"] = _audio_url_for_path(mixed_path)
    debug = getattr(semantic.singing_config, "_transcription_debug", None)
    if isinstance(debug, dict):
        response["transcription_debug"] = {
            "selected_source": debug.get("selected_source"),
            "mt3_midi_path": debug.get("mt3_midi_path"),
            "ustx_primary": debug.get("ustx_primary"),
            "ustx_mt3": debug.get("ustx_mt3"),
            "raw_vocals_primary": debug.get("raw_vocals_primary"),
            "raw_vocals_mt3": debug.get("raw_vocals_mt3"),
            "raw_vocals_primary_url": _audio_url_for_path(debug.get("raw_vocals_primary")),
            "raw_vocals_mt3_url": _audio_url_for_path(debug.get("raw_vocals_mt3")),
        }
    return response
