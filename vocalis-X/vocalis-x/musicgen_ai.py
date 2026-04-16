import os
import uuid

import numpy as np
import soundfile as sf
import torch
import torchaudio
from audiocraft.models import MusicGen

print("MusicGen module loaded")

model = None
model_name_loaded = None

CHUNK_DURATION_SEC = 30.0
OVERLAP_SEC = 2.0
TEMPERATURE = 0.9
TOP_K = 200
DURATION_SEC = 30


def _resolve_gen_config(gen_cfg):
    if gen_cfg is None:
        return {
            "chunk_duration": CHUNK_DURATION_SEC,
            "overlap_sec": OVERLAP_SEC,
            "temperature": TEMPERATURE,
            "top_k": TOP_K,
            "model_name": "facebook/musicgen-medium",
            "duration_sec": DURATION_SEC,
        }
    return {
        "chunk_duration": float(gen_cfg.chunk_duration) if getattr(gen_cfg, "chunk_duration", None) else CHUNK_DURATION_SEC,
        "overlap_sec": float(gen_cfg.overlap_sec) if getattr(gen_cfg, "overlap_sec", None) else OVERLAP_SEC,
        "temperature": float(gen_cfg.temperature) if getattr(gen_cfg, "temperature", None) else TEMPERATURE,
        "top_k": int(gen_cfg.top_k) if getattr(gen_cfg, "top_k", None) else TOP_K,
        "model_name": gen_cfg.model_name if getattr(gen_cfg, "model_name", None) else "facebook/musicgen-medium",
        "duration_sec": int(gen_cfg.duration_sec) if getattr(gen_cfg, "duration_sec", None) else DURATION_SEC,
    }


def get_model(model_name="facebook/musicgen-medium"):
    global model, model_name_loaded
    if model is None or model_name_loaded != model_name:
        print(f"Loading MusicGen model: {model_name}...")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"MusicGen device: {device}")
        model = MusicGen.get_pretrained(model_name, device=device)
        model_name_loaded = model_name
        print("MusicGen loaded")
    return model


def get_audio_duration(file_path):
    waveform, sample_rate = torchaudio.load(file_path)
    return waveform.shape[1] / sample_rate


def _load_melody_slice(melody_ref_path, duration_sec, skip_intro_sec=0.0):
    melody_ref, sr_ref = torchaudio.load(melody_ref_path)
    start_sample = int(skip_intro_sec * sr_ref)
    required = int(float(duration_sec) * sr_ref)
    melody_slice = melody_ref[:, start_sample:start_sample + required]
    if melody_slice.shape[1] < required:
        padding = torch.zeros((melody_slice.shape[0], required - melody_slice.shape[1]))
        melody_slice = torch.cat([melody_slice, padding], dim=1)
    return melody_slice, sr_ref


def _generate_single_pass(prompt, duration_sec, temperature, top_k, model_name, melody_ref_path=None, skip_intro_sec=0.0):
    model = get_model(model_name)
    model.set_generation_params(duration=float(duration_sec), temperature=float(temperature), top_k=int(top_k))
    if melody_ref_path and os.path.exists(melody_ref_path):
        melody_slice, sr_ref = _load_melody_slice(melody_ref_path, duration_sec, skip_intro_sec=skip_intro_sec)
        generated = model.generate_with_chroma([prompt], melody_slice[None], sr_ref, progress=True)[0]
    else:
        generated = model.generate([prompt], progress=True)[0]
    return generated.cpu().numpy(), model.sample_rate


def _crossfade_pair(left, right, overlap_samples):
    safe_overlap = min(overlap_samples, left.shape[1], right.shape[1])
    if safe_overlap <= 0:
        return np.concatenate([left, right], axis=1)
    fade = np.linspace(0.0, 1.0, safe_overlap, dtype=np.float32)
    fade_out = np.cos(fade * np.pi / 2.0)
    fade_in = np.sin(fade * np.pi / 2.0)
    blended = (left[:, -safe_overlap:] * fade_out) + (right[:, :safe_overlap] * fade_in)
    return np.concatenate([left[:, :-safe_overlap], blended, right[:, safe_overlap:]], axis=1)


def _generate_chunked(prompt, duration_sec, temperature, top_k, model_name):
    pieces = []
    remaining = float(duration_sec)
    chunk_duration = 30.0
    overlap_sec = 2.0
    while remaining > 0:
        current = min(chunk_duration, remaining)
        piece, sample_rate = _generate_single_pass(prompt, current, temperature, top_k, model_name)
        pieces.append(piece)
        remaining -= current
    output = pieces[0]
    overlap_samples = int(sample_rate * overlap_sec)
    for piece in pieces[1:]:
        output = _crossfade_pair(output, piece, overlap_samples)
    return output, sample_rate


def generate_audio(prompt: str, generation_config=None, melody_ref_path=None):
    cfg = _resolve_gen_config(generation_config)
    total_duration = max(1.0, float(cfg["duration_sec"]))
    current_model_name = cfg["model_name"]
    if melody_ref_path and os.path.exists(melody_ref_path):
        current_model_name = "facebook/musicgen-melody"
        print(f"Reference detected. Switching to: {current_model_name}")

    print(f"Target duration: {total_duration:.2f}s")

    try:
        if melody_ref_path and os.path.exists(melody_ref_path):
            full_audio, sample_rate = _generate_single_pass(
                prompt,
                min(total_duration, 30.0),
                cfg["temperature"],
                cfg["top_k"],
                current_model_name,
                melody_ref_path=melody_ref_path,
                skip_intro_sec=65.0,
            )
        elif total_duration <= 30.0:
            full_audio, sample_rate = _generate_single_pass(
                prompt,
                total_duration,
                cfg["temperature"],
                cfg["top_k"],
                current_model_name,
            )
        else:
            full_audio, sample_rate = _generate_chunked(
                prompt,
                total_duration,
                cfg["temperature"],
                cfg["top_k"],
                current_model_name,
            )
    except AssertionError:
        print("MusicGen assertion failed. Retrying with musicgen-small...")
        current_model_name = "facebook/musicgen-small"
        full_audio, sample_rate = _generate_single_pass(
            prompt,
            min(total_duration, 30.0),
            cfg["temperature"],
            cfg["top_k"],
            current_model_name,
        )

    peak = float(np.max(np.abs(full_audio))) if full_audio.size else 0.0
    if peak > 1.0:
        full_audio = full_audio / peak

    os.makedirs("output", exist_ok=True)
    path = os.path.join("output", f"{uuid.uuid4()}.wav")
    sf.write(path, full_audio.T, sample_rate)
    print(f"Final MusicGen file saved: {path}")
    return path
