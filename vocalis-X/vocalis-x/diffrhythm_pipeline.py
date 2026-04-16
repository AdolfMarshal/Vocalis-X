import os
import re
import json
import uuid
import shlex
import shutil
import string
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import soundfile as sf

from singing_synth import SingingNotConfiguredError, mix_audio
from openutau_ustx import write_ustx, RENA_MID_TONE
from openutau_automation import render_ustx_to_wav, OpenUtauAutomationError
from kaggle_cloud import run_kaggle_generation, KaggleCloudError


class DiffRhythmPipelineError(RuntimeError):
    pass


def _log_step(step: str, message: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[DiffRhythm][{ts}][{step}] {message}")


@dataclass
class PipelineArtifacts:
    full_song_wav: str
    instrumental_wav: str
    vocals_wav: str
    lead_vocals_wav: str
    backing_vocals_wav: str
    mapped_ustx: str
    rendered_vocals_wav: Optional[str]
    final_mix_wav: str
    openutau_fallback_used: bool = False
    warning: Optional[str] = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _clean_words(text: str) -> List[str]:
    raw = re.findall(r"[A-Za-z0-9']+", text or "")
    return [w.strip(string.punctuation) for w in raw if w.strip(string.punctuation)]


def _sanitize_lyric(lyric: str) -> str:
    if "'" in lyric or '"' in lyric:
        return '"' + lyric.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return lyric


def _split_command(cmd: str) -> List[str]:
    return shlex.split(cmd, posix=False)


def _plain_lyrics_to_lrc(lyrics: str) -> str:
    lines = [ln.strip() for ln in (lyrics or "").splitlines() if ln.strip()]
    if not lines:
        lines = ["la"]
    cur = 0.0
    out = []
    for ln in lines:
        m = int(cur // 60)
        s = cur % 60.0
        out.append(f"[{m:02d}:{s:05.2f}] {ln}")
        # Simple deterministic spacing; good enough as a seed for DiffRhythm.
        cur += max(4.0, min(12.0, 0.4 * len(ln.split()) + 4.0))
    return "\n".join(out) + "\n"


def _run_command(cmd: List[str], cwd: Optional[str] = None, timeout_sec: Optional[int] = None):
    start = time.time()
    _log_step(
        "command.start",
        f"cwd={cwd or os.getcwd()} timeout={timeout_sec} cmd={' '.join(cmd)}",
    )
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        check=False,
        timeout=timeout_sec,
    )
    dur = time.time() - start
    _log_step(
        "command.end",
        f"exit_code={proc.returncode} duration_sec={dur:.2f}",
    )
    if proc.returncode != 0:
        raise DiffRhythmPipelineError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}"
        )
    return proc


def _extract_audio_length(cmd: str, default_len: int = 95) -> int:
    m = re.search(r"--audio-length\s+(\d+)", cmd)
    if not m:
        return default_len
    try:
        return int(m.group(1))
    except Exception:
        return default_len


def _override_audio_length(cmd: str, target_len: int) -> str:
    if re.search(r"--audio-length\s+\d+", cmd):
        return re.sub(r"--audio-length\s+\d+", f"--audio-length {int(target_len)}", cmd)
    return f"{cmd} --audio-length {int(target_len)}"


def _split_lyrics_sections(lyrics: str) -> List[str]:
    lines = [ln.rstrip() for ln in (lyrics or "").splitlines()]
    chunks: List[str] = []
    cur: List[str] = []
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            if cur:
                chunks.append("\n".join(cur).strip())
                cur = []
            continue
        if re.match(r"^\[[A-Za-z0-9 _-]+\]$", stripped) and cur:
            chunks.append("\n".join(cur).strip())
            cur = [stripped]
            continue
        cur.append(stripped)
    if cur:
        chunks.append("\n".join(cur).strip())
    return [c for c in chunks if c]


def _merge_wavs_crossfade(wavs: List[str], crossfade_sec: float = 1.0) -> str:
    if not wavs:
        raise DiffRhythmPipelineError("No chunk wavs were generated for fallback merge.")
    if len(wavs) == 1:
        return wavs[0]

    merged = None
    merged_sr = None
    for idx, path in enumerate(wavs):
        y, sr = sf.read(path, always_2d=True)
        if y.size == 0:
            continue
        if merged is None:
            merged = y
            merged_sr = sr
            continue
        if sr != merged_sr:
            raise DiffRhythmPipelineError(
                f"Chunk sample-rate mismatch during merge: {sr} vs {merged_sr}"
            )
        fade = int(max(0.1, crossfade_sec) * sr)
        fade = min(fade, len(merged), len(y))
        if fade <= 0:
            merged = np.concatenate([merged, y], axis=0)
            continue
        a = np.linspace(1.0, 0.0, fade, dtype=np.float32)[:, None]
        b = np.linspace(0.0, 1.0, fade, dtype=np.float32)[:, None]
        xfade = merged[-fade:] * a + y[:fade] * b
        merged = np.concatenate([merged[:-fade], xfade, y[fade:]], axis=0)

    if merged is None or merged.size == 0:
        raise DiffRhythmPipelineError("Fallback merge produced empty audio.")
    out = Path("output") / f"{uuid.uuid4().hex}_diffrhythm_local_fallback.wav"
    sf.write(out, merged, merged_sr or 44100)
    return str(out.resolve())


def _find_newest_file(root: Path, suffix: str = ".wav") -> Optional[Path]:
    files = [p for p in root.rglob(f"*{suffix}") if p.is_file()]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0]


def _copy_to_output(src: str, prefix: str) -> str:
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    dst = out_dir / f"{uuid.uuid4().hex}_{prefix}{Path(src).suffix}"
    shutil.copy2(src, dst)
    return str(dst.resolve())


def _use_existing_or_none(path_value: Optional[str]) -> Optional[str]:
    if not path_value:
        return None
    if os.path.exists(path_value):
        return str(Path(path_value).resolve())
    return None


def _demucs_track_folder(demucs_out_dir: Path, src_wav: str, model: str) -> Path:
    stem = Path(src_wav).stem
    candidate = demucs_out_dir / model / stem
    if candidate.exists():
        return candidate
    # Some demucs wrappers normalize track name differently.
    matches = [p for p in (demucs_out_dir / model).glob("*") if p.is_dir()]
    if not matches:
        raise DiffRhythmPipelineError(f"Demucs output not found under {demucs_out_dir / model}")
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def _split_lead_backing(vocals_path: str, lead_override: Optional[str] = None, backing_override: Optional[str] = None) -> Tuple[str, str]:
    if lead_override and os.path.exists(lead_override):
        lead = _copy_to_output(lead_override, "lead_vocals_override")
        if backing_override and os.path.exists(backing_override):
            backing = _copy_to_output(backing_override, "backing_vocals_override")
            return lead, backing
        y, sr = sf.read(vocals_path, always_2d=True)
        lead_y, _ = sf.read(lead_override, always_2d=True)
        n = min(len(y), len(lead_y))
        residual = y[:n] - lead_y[:n]
        out_backing = Path("output") / f"{uuid.uuid4().hex}_backing_from_residual.wav"
        sf.write(out_backing, residual, sr)
        return lead, str(out_backing.resolve())

    y, sr = sf.read(vocals_path, always_2d=True)
    if y.size == 0:
        raise DiffRhythmPipelineError(f"Vocals stem is empty: {vocals_path}")
    if y.shape[1] == 1:
        lead = y
        backing = np.zeros_like(y)
    else:
        left = y[:, 0]
        right = y[:, 1]
        mid = ((left + right) * 0.5)[:, None]
        side_l = (left - right)[:, None] * 0.5
        side_r = (right - left)[:, None] * 0.5
        lead = np.repeat(mid, 2, axis=1)
        backing = np.concatenate([side_l, side_r], axis=1)
    lead_path = Path("output") / f"{uuid.uuid4().hex}_lead_vocals.wav"
    backing_path = Path("output") / f"{uuid.uuid4().hex}_backing_vocals.wav"
    sf.write(lead_path, lead, sr)
    sf.write(backing_path, backing, sr)
    return str(lead_path.resolve()), str(backing_path.resolve())


def _build_instrumental_from_demucs_stems(track_folder: Path) -> Optional[Path]:
    """Build no_vocals.wav from Demucs 4-stem output when no_vocals is absent."""
    bass = track_folder / "bass.wav"
    drums = track_folder / "drums.wav"
    other = track_folder / "other.wav"
    if not (bass.exists() and drums.exists() and other.exists()):
        return None

    b, sr_b = sf.read(str(bass), always_2d=True)
    d, sr_d = sf.read(str(drums), always_2d=True)
    o, sr_o = sf.read(str(other), always_2d=True)
    if sr_b != sr_d or sr_b != sr_o:
        raise DiffRhythmPipelineError(
            f"Demucs stem sample-rate mismatch: bass={sr_b}, drums={sr_d}, other={sr_o}"
        )

    n = min(len(b), len(d), len(o))
    if n <= 0:
        raise DiffRhythmPipelineError("Demucs stems are empty; cannot build instrumental.")
    instrumental = b[:n] + d[:n] + o[:n]
    peak = float(np.max(np.abs(instrumental))) if instrumental.size else 0.0
    if peak > 1.0:
        instrumental = instrumental / peak

    out_path = track_folder / "no_vocals.wav"
    sf.write(str(out_path), instrumental, sr_b)
    return out_path


def _parse_ustx_bpm(text: str) -> int:
    m = re.search(r"^\s*bpm:\s*(\d+)\s*$", text, flags=re.MULTILINE)
    return int(m.group(1)) if m else 120


def _parse_ustx_notes(text: str):
    pattern = re.compile(
        r"(?m)^(\s*-\sposition:\s*(?P<pos>-?\d+)\s*\n"
        r"\s*duration:\s*(?P<dur>\d+)\s*\n"
        r"\s*tone:\s*(?P<tone>-?\d+)\s*\n"
        r"\s*lyric:\s*(?P<lyric>[^\n]+))"
    )
    notes = []
    for m in pattern.finditer(text):
        notes.append(
            {
                "block": m.group(1),
                "pos": int(m.group("pos")),
                "dur": int(m.group("dur")),
                "tone": int(m.group("tone")),
                "lyric": m.group("lyric").strip(),
            }
        )
    if not notes:
        raise DiffRhythmPipelineError("No notes found in USTX text.")
    return notes


def _parse_textgrid_words(textgrid_path: str) -> List[Tuple[float, float, str]]:
    txt = Path(textgrid_path).read_text(encoding="utf-8", errors="ignore")
    out = []
    starts = re.findall(r"\bxmin\s*=\s*([0-9.]+)", txt)
    ends = re.findall(r"\bxmax\s*=\s*([0-9.]+)", txt)
    texts = re.findall(r'\btext\s*=\s*"([^"]*)"', txt)
    n = min(len(starts), len(ends), len(texts))
    for i in range(n):
        w = texts[i].strip()
        if not w:
            continue
        if w in {"sil", "sp", "spn"}:
            continue
        out.append((float(starts[i]), float(ends[i]), w))
    return out


def _build_fallback_word_intervals(lyrics: str, note_count: int, bpm: int) -> List[Tuple[float, float, str]]:
    words = _clean_words(lyrics)
    if not words:
        return []
    sec_per_tick = 60.0 / (float(bpm) * 480.0)
    total_sec = max(2.0, note_count * 480 * sec_per_tick)
    step = total_sec / max(1, len(words))
    out = []
    t = 0.0
    for w in words:
        out.append((t, t + step, w))
        t += step
    return out


def _map_words_to_notes(words_timed: List[Tuple[float, float, str]], notes, bpm: int) -> List[str]:
    if not notes:
        return []
    if not words_timed:
        cleaned = ["la"] * len(notes)
        if cleaned:
            cleaned[0] = "a"
        return cleaned
    sec_per_tick = 60.0 / (float(bpm) * 480.0)
    assignments = [None] * len(notes)
    for i, note in enumerate(notes):
        ns = note["pos"] * sec_per_tick
        ne = (note["pos"] + note["dur"]) * sec_per_tick
        best_idx = -1
        best_overlap = 0.0
        for j, (ws, we, _w) in enumerate(words_timed):
            overlap = max(0.0, min(ne, we) - max(ns, ws))
            if overlap > best_overlap:
                best_overlap = overlap
                best_idx = j
        assignments[i] = best_idx

    lyrics_out = ["-"] * len(notes)
    seen_word = set()
    for i, widx in enumerate(assignments):
        if widx is None or widx < 0 or widx >= len(words_timed):
            continue
        word = words_timed[widx][2]
        if widx not in seen_word:
            lyrics_out[i] = word
            seen_word.add(widx)
    for i, lyr in enumerate(lyrics_out):
        if lyr == "-":
            prev = lyrics_out[i - 1] if i > 0 else ""
            if prev in {"", "-"}:
                lyrics_out[i] = "la"
    return lyrics_out


def _write_mapped_ustx(src_ustx: str, mapped_lyrics: List[str]) -> str:
    text = Path(src_ustx).read_text(encoding="utf-8", errors="ignore")
    notes = _parse_ustx_notes(text)
    if len(mapped_lyrics) < len(notes):
        mapped_lyrics = mapped_lyrics + ["-"] * (len(notes) - len(mapped_lyrics))

    idx = {"value": 0}

    def _replace(m):
        i = idx["value"]
        idx["value"] += 1
        lyric = mapped_lyrics[i] if i < len(mapped_lyrics) else "-"
        lyric = _sanitize_lyric(lyric)
        block = m.group(0)
        return re.sub(r"(?m)^(\s*lyric:\s*).*$", rf"\1{lyric}", block, count=1)

    pattern = re.compile(
        r"(?ms)^\s*-\sposition:\s*-?\d+\s*\n"
        r"\s*duration:\s*\d+\s*\n"
        r"\s*tone:\s*-?\d+\s*\n"
        r"\s*lyric:\s*[^\n]+.*?(?=^\s*-\sposition:|\Z)"
    )
    mapped_text = pattern.sub(_replace, text)
    out_path = Path("output") / f"{uuid.uuid4().hex}_mapped.ustx"
    out_path.write_text(mapped_text, encoding="utf-8")
    return str(out_path.resolve())


def _align_words_with_mfa_or_fallback(lead_vocals_wav: str, lyrics: str, note_count: int, bpm: int, singing_config) -> List[Tuple[float, float, str]]:
    textgrid_path = getattr(singing_config, "mfa_textgrid_path", None)
    if textgrid_path and os.path.exists(textgrid_path):
        words = _parse_textgrid_words(textgrid_path)
        if words:
            return words

    mfa_cmd_template = (
        getattr(singing_config, "mfa_command", None)
        or os.environ.get("VOCALIS_MFA_COMMAND")
        or os.environ.get("MFA_COMMAND")
    )
    if mfa_cmd_template:
        out_dir = Path("output")
        out_dir.mkdir(exist_ok=True)
        lyrics_txt = out_dir / f"{uuid.uuid4().hex}_lyrics.txt"
        tg_out = out_dir / f"{uuid.uuid4().hex}_mfa.TextGrid"
        lyrics_txt.write_text(lyrics or "", encoding="utf-8")
        cmd = mfa_cmd_template.format(
            audio_wav=str(Path(lead_vocals_wav).resolve()),
            lyrics_txt=str(lyrics_txt.resolve()),
            output_textgrid=str(tg_out.resolve()),
        )
        _run_command(_split_command(cmd))
        if tg_out.exists():
            words = _parse_textgrid_words(str(tg_out))
            if words:
                return words
    return _build_fallback_word_intervals(lyrics, note_count=note_count, bpm=bpm)


def _run_diffrhythm_once(
    cmd_template: str,
    prompt: str,
    lyrics_text: str,
    out_dir: Path,
    run_tag: str,
    cwd: Optional[str],
    timeout_sec: Optional[int] = None,
) -> str:
    _log_step("diffrhythm.once", f"run_tag={run_tag}")
    prompt_single_line = " ".join((prompt or "").splitlines())
    prompt_single_line = " ".join(prompt_single_line.split())
    prompt_file = out_dir / f"{run_tag}_prompt.txt"
    lyrics_file = out_dir / f"{run_tag}_lyrics.txt"
    lyrics_lrc_file = out_dir / f"{run_tag}_lyrics.lrc"
    full_song_target = out_dir / f"{run_tag}_diffrhythm_full.wav"
    diffrhythm_output_dir = out_dir / f"{run_tag}_diffrhythm_out"
    diffrhythm_output_dir.mkdir(exist_ok=True)

    prompt_file.write_text(prompt_single_line, encoding="utf-8")
    lyrics_file.write_text(lyrics_text or "", encoding="utf-8")
    lyrics_lrc_file.write_text(_plain_lyrics_to_lrc(lyrics_text or ""), encoding="utf-8")

    cmd = cmd_template.format(
        prompt_file=str(prompt_file.resolve()),
        prompt_text=prompt_single_line,
        lyrics_file=str(lyrics_file.resolve()),
        lyrics_lrc=str(lyrics_lrc_file.resolve()),
        output_wav=str(full_song_target.resolve()),
        output_dir=str(diffrhythm_output_dir.resolve()),
    )
    _log_step(
        "diffrhythm.once.inputs",
        f"prompt_file={prompt_file} lyrics_file={lyrics_file} lyrics_lrc={lyrics_lrc_file} output_wav={full_song_target}",
    )
    _run_command(_split_command(cmd), cwd=cwd, timeout_sec=timeout_sec)

    if full_song_target.exists():
        return str(full_song_target.resolve())
    newest = _find_newest_file(diffrhythm_output_dir) or _find_newest_file(out_dir)
    if not newest:
        raise DiffRhythmPipelineError("DiffRhythm command did not produce a WAV output.")
    return str(newest.resolve())


def _run_local_chunk_fallback(
    cmd_template: str,
    prompt: str,
    lyrics_text: str,
    out_dir: Path,
    cwd: Optional[str],
    singing_config,
) -> str:
    _log_step("local.chunk_fallback.start", "starting section-based local chunk fallback")
    chunk_len = int(
        getattr(singing_config, "local_chunk_audio_length_sec", None)
        or os.environ.get("VOCALIS_LOCAL_CHUNK_AUDIO_LENGTH_SEC")
        or 30
    )
    chunk_len = max(20, min(95, chunk_len))
    crossfade = float(
        getattr(singing_config, "local_chunk_crossfade_sec", None)
        or os.environ.get("VOCALIS_LOCAL_CHUNK_CROSSFADE_SEC")
        or 1.0
    )
    sections = _split_lyrics_sections(lyrics_text)
    if not sections:
        sections = [lyrics_text or "la"]
    _log_step(
        "local.chunk_fallback.config",
        f"sections={len(sections)} chunk_len={chunk_len} crossfade_sec={crossfade}",
    )

    cmd_chunk = _override_audio_length(cmd_template, chunk_len)
    wavs: List[str] = []
    for i, sec in enumerate(sections):
        _log_step("local.chunk_fallback.section", f"section_index={i + 1}/{len(sections)}")
        sec_prompt = f"{prompt} section={i + 1}/{len(sections)}"
        run_tag = f"{uuid.uuid4().hex}_chunk{i + 1}"
        wavs.append(
            _run_diffrhythm_once(
                cmd_template=cmd_chunk,
                prompt=sec_prompt,
                lyrics_text=sec,
                out_dir=out_dir,
                run_tag=run_tag,
                cwd=cwd,
                timeout_sec=None,
            )
        )
    return _merge_wavs_crossfade(wavs, crossfade_sec=crossfade)


def run_diffrhythm_pipeline(semantic, prompt: str) -> PipelineArtifacts:
    _log_step("pipeline.start", "enter run_diffrhythm_pipeline")
    singing_config = semantic.singing_config
    if not singing_config:
        raise SingingNotConfiguredError("singing_config is required for DiffRhythm pipeline")
    if not semantic.lyrics:
        raise SingingNotConfiguredError("lyrics is required for DiffRhythm pipeline")
    openutau_enabled = bool(getattr(singing_config, "enabled", False))

    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)

    prebuilt_song = getattr(singing_config, "diffrhythm_song_path", None)
    prebuilt_inst_from_cloud = _use_existing_or_none(getattr(singing_config, "diffrhythm_instrumental_path", None))
    prebuilt_vocals_from_cloud = _use_existing_or_none(getattr(singing_config, "diffrhythm_vocals_path", None))
    if prebuilt_song and os.path.exists(prebuilt_song):
        _log_step("pipeline.prebuilt_song", f"using prebuilt full song: {prebuilt_song}")
        full_song_wav = _copy_to_output(prebuilt_song, "diffrhythm_fullsong")
    else:
        cloud_first = getattr(singing_config, "cloud_first_enabled", None)
        if cloud_first is None:
            cloud_first = True

        cloud_cmd_template = (
            getattr(singing_config, "cloud_command", None)
            or os.environ.get("VOCALIS_CLOUD_COMMAND")
        )
        cloud_cwd = getattr(singing_config, "cloud_cwd", None) or os.environ.get("VOCALIS_CLOUD_CWD")
        cloud_timeout = int(getattr(singing_config, "cloud_timeout_sec", None) or os.environ.get("VOCALIS_CLOUD_TIMEOUT_SEC") or 3600)
        kaggle_kernel = (
            getattr(singing_config, "kaggle_kernel", None)
            or os.environ.get("VOCALIS_KAGGLE_KERNEL")
        )
        kaggle_template_dir = Path(
            getattr(singing_config, "kaggle_template_dir", None)
            or os.environ.get("VOCALIS_KAGGLE_TEMPLATE_DIR")
            or (_repo_root() / "kaggle_worker")
        )
        kaggle_poll_interval = int(
            getattr(singing_config, "kaggle_poll_interval_sec", None)
            or os.environ.get("VOCALIS_KAGGLE_POLL_INTERVAL_SEC")
            or 20
        )

        local_cmd_template = (
            getattr(singing_config, "diffrhythm_command", None)
            or os.environ.get("VOCALIS_DIFFRHYTHM_COMMAND")
            or os.environ.get("DIFFRHYTHM_COMMAND")
        )
        _log_step(
            "pipeline.command_config",
            f"cloud_first={cloud_first} has_kaggle={bool(kaggle_kernel)} has_cloud_cmd={bool(cloud_cmd_template)} has_local_cmd={bool(local_cmd_template)}",
        )
        if not local_cmd_template and not cloud_cmd_template and not kaggle_kernel:
            raise DiffRhythmPipelineError(
                "Missing generation command. Set kaggle_kernel/VOCALIS_KAGGLE_KERNEL, "
                "cloud_command/VOCALIS_CLOUD_COMMAND, or VOCALIS_DIFFRHYTHM_COMMAND."
            )
        local_cwd = (
            getattr(singing_config, "diffrhythm_cwd", None)
            or os.environ.get("VOCALIS_DIFFRHYTHM_CWD")
        )
        if not local_cwd:
            default_repo = Path.home() / "DiffRhythm"
            if default_repo.exists():
                local_cwd = str(default_repo.resolve())

        full_song_wav = None
        generation_errors: List[str] = []

        if cloud_first and kaggle_kernel:
            try:
                _log_step("pipeline.kaggle.try", f"attempting Kaggle generation kernel={kaggle_kernel}")
                audio_length = _extract_audio_length(local_cmd_template or cloud_cmd_template or "", default_len=95)
                demucs_model = getattr(singing_config, "demucs_model", None) or "htdemucs_ft"
                kaggle_artifacts = run_kaggle_generation(
                    prompt=prompt,
                    lyrics_text=semantic.lyrics or "",
                    lyrics_lrc=_plain_lyrics_to_lrc(semantic.lyrics or ""),
                    output_root=out_dir,
                    run_tag=f"{uuid.uuid4().hex}_kaggle",
                    kernel_slug=kaggle_kernel,
                    template_dir=kaggle_template_dir,
                    audio_length_sec=audio_length,
                    demucs_model=demucs_model,
                    poll_interval_sec=kaggle_poll_interval,
                    timeout_sec=cloud_timeout,
                    local_diffrhythm_dir=Path(local_cwd).resolve() if local_cwd and Path(local_cwd).exists() else None,
                )
                full_song_wav = kaggle_artifacts.full_song_wav
                if kaggle_artifacts.instrumental_wav:
                    prebuilt_inst_from_cloud = kaggle_artifacts.instrumental_wav
                if kaggle_artifacts.vocals_wav:
                    prebuilt_vocals_from_cloud = kaggle_artifacts.vocals_wav
                _log_step("pipeline.kaggle.ok", f"kaggle generation succeeded: {full_song_wav}")
            except (KaggleCloudError, Exception) as exc:
                generation_errors.append(f"kaggle failed: {exc}")
                _log_step("pipeline.kaggle.fail", f"kaggle generation failed: {exc}")

        if not full_song_wav and cloud_first and cloud_cmd_template:
            try:
                _log_step("pipeline.cloud.try", "attempting cloud generation")
                full_song_wav = _run_diffrhythm_once(
                    cmd_template=cloud_cmd_template,
                    prompt=prompt,
                    lyrics_text=semantic.lyrics or "",
                    out_dir=out_dir,
                    run_tag=f"{uuid.uuid4().hex}_cloud",
                    cwd=cloud_cwd,
                    timeout_sec=cloud_timeout,
                )
                _log_step("pipeline.cloud.ok", f"cloud generation succeeded: {full_song_wav}")
            except Exception as exc:
                generation_errors.append(f"cloud failed: {exc}")
                _log_step("pipeline.cloud.fail", f"cloud generation failed: {exc}")

        if not full_song_wav and local_cmd_template:
            try:
                _log_step("pipeline.local_full.try", "attempting local full generation")
                full_song_wav = _run_diffrhythm_once(
                    cmd_template=local_cmd_template,
                    prompt=prompt,
                    lyrics_text=semantic.lyrics or "",
                    out_dir=out_dir,
                    run_tag=f"{uuid.uuid4().hex}_local",
                    cwd=local_cwd,
                    timeout_sec=None,
                )
                _log_step("pipeline.local_full.ok", f"local full generation succeeded: {full_song_wav}")
            except Exception as exc:
                generation_errors.append(f"local full failed: {exc}")
                _log_step("pipeline.local_full.fail", f"local full generation failed: {exc}")

                chunk_fallback_enabled = getattr(singing_config, "local_chunk_fallback_enabled", None)
                if chunk_fallback_enabled is None:
                    chunk_fallback_enabled = True
                if chunk_fallback_enabled:
                    try:
                        _log_step("pipeline.local_chunk.try", "attempting local chunk fallback")
                        full_song_wav = _run_local_chunk_fallback(
                            cmd_template=local_cmd_template,
                            prompt=prompt,
                            lyrics_text=semantic.lyrics or "",
                            out_dir=out_dir,
                            cwd=local_cwd,
                            singing_config=singing_config,
                        )
                        _log_step("pipeline.local_chunk.ok", f"local chunk fallback succeeded: {full_song_wav}")
                    except Exception as exc2:
                        generation_errors.append(f"local chunk fallback failed: {exc2}")
                        _log_step("pipeline.local_chunk.fail", f"local chunk fallback failed: {exc2}")

        if not full_song_wav:
            _log_step("pipeline.fail", "all generation paths failed")
            raise DiffRhythmPipelineError(
                "All generation paths failed.\n" + "\n".join(generation_errors)
            )

    # Hybrid mode: if cloud-generated stems are provided, skip local Demucs.
    prebuilt_inst = prebuilt_inst_from_cloud
    prebuilt_vocals = prebuilt_vocals_from_cloud
    if prebuilt_inst and prebuilt_vocals:
        _log_step("pipeline.stems", "using prebuilt instrumental/vocals stems")
        instrumental_wav = Path(prebuilt_inst)
        vocals_wav = Path(prebuilt_vocals)
    else:
        _log_step("pipeline.demucs.start", "running demucs stem separation")
        demucs_out = out_dir / "demucs"
        demucs_out.mkdir(exist_ok=True)
        demucs_model = getattr(singing_config, "demucs_model", None) or "htdemucs_ft"
        demucs_cmd = ["demucs", "-n", demucs_model, "-o", str(demucs_out.resolve()), str(Path(full_song_wav).resolve())]
        _run_command(demucs_cmd)
        _log_step("pipeline.demucs.ok", f"demucs completed model={demucs_model}")

        track_folder = _demucs_track_folder(demucs_out, full_song_wav, demucs_model)
        vocals_wav = track_folder / "vocals.wav"
        instrumental_wav = track_folder / "no_vocals.wav"
        if not instrumental_wav.exists():
            alt = track_folder / "accompaniment.wav"
            if alt.exists():
                instrumental_wav = alt
            else:
                built = _build_instrumental_from_demucs_stems(track_folder)
                if built is not None:
                    instrumental_wav = built
        if not vocals_wav.exists():
            raise DiffRhythmPipelineError(f"Demucs did not produce vocals stem: {vocals_wav}")
        if not instrumental_wav.exists():
            raise DiffRhythmPipelineError(f"Demucs did not produce instrumental stem: {instrumental_wav}")

    if not openutau_enabled:
        _log_step("pipeline.openutau.skip", "OpenUtau disabled; returning pure DiffRhythm stems and mix")
        return PipelineArtifacts(
            full_song_wav=str(Path(full_song_wav).resolve()),
            instrumental_wav=str(instrumental_wav.resolve()),
            vocals_wav=str(vocals_wav.resolve()),
            lead_vocals_wav=str(vocals_wav.resolve()),
            backing_vocals_wav=str(vocals_wav.resolve()),
            mapped_ustx="",
            rendered_vocals_wav=str(vocals_wav.resolve()),
            final_mix_wav=str(Path(full_song_wav).resolve()),
            openutau_fallback_used=False,
            warning=None,
        )

    lead_override = getattr(singing_config, "lead_vocals_path", None)
    backing_override = getattr(singing_config, "backing_vocals_path", None)
    _log_step("pipeline.split", "splitting lead/backing vocals")
    lead_wav, backing_wav = _split_lead_backing(str(vocals_wav.resolve()), lead_override, backing_override)

    transcribed_ustx_path = getattr(singing_config, "openutau_transcribed_ustx_path", None)
    if transcribed_ustx_path and os.path.exists(transcribed_ustx_path):
        _log_step("pipeline.ustx.base", f"using transcribed USTX: {transcribed_ustx_path}")
        base_ustx = str(Path(transcribed_ustx_path).resolve())
    else:
        _log_step("pipeline.ustx.base", "building base USTX with write_ustx")
        base_ustx = str(
            write_ustx(
                lyrics="la",
                bpm=getattr(singing_config, "openutau_bpm", None) or 120,
                base_tone=getattr(singing_config, "openutau_base_tone", None) or RENA_MID_TONE,
                emotion={"joy": 0.2, "sadness": 0.2, "tension": 0.1},
                darkness=0.2,
                energy=0.5,
                vocals_path=lead_wav,
            )
        )

    export_dir = getattr(singing_config, "openutau_export_dir", None) or r"output\openutau"
    autostart = getattr(singing_config, "openutau_autostart", None)
    if autostart is None:
        autostart = True
    rendered_vocals = None
    final_mix = full_song_wav
    openutau_fallback_used = False
    warning = None
    mapped_ustx = base_ustx

    try:
        ustx_text = Path(base_ustx).read_text(encoding="utf-8", errors="ignore")
        bpm = _parse_ustx_bpm(ustx_text)
        notes = _parse_ustx_notes(ustx_text)
        _log_step("pipeline.word_align", f"aligning words to notes note_count={len(notes)} bpm={bpm}")
        timed_words = _align_words_with_mfa_or_fallback(
            lead_vocals_wav=lead_wav,
            lyrics=semantic.lyrics,
            note_count=len(notes),
            bpm=bpm,
            singing_config=singing_config,
        )
        mapped_lyrics = _map_words_to_notes(timed_words, notes=notes, bpm=bpm)
        mapped_ustx = _write_mapped_ustx(base_ustx, mapped_lyrics)
        _log_step("pipeline.ustx.mapped", f"mapped USTX generated: {mapped_ustx}")

        _log_step("pipeline.openutau.start", f"rendering mapped USTX via OpenUtau export_dir={export_dir}")
        rendered_vocals = render_ustx_to_wav(
            ustx_path=mapped_ustx,
            export_dir=export_dir,
            exe_path=getattr(singing_config, "openutau_exe_path", None),
            autostart=autostart,
            wait_sec=getattr(singing_config, "openutau_wait_sec", None) or 20,
            open_key=getattr(singing_config, "openutau_open_key", None) or "^o",
            export_key=getattr(singing_config, "openutau_export_key", None) or "^e",
            export_menu_down=getattr(singing_config, "openutau_export_menu_down", None),
            export_submenu_down=getattr(singing_config, "openutau_export_submenu_down", None),
            export_timeout_sec=getattr(singing_config, "openutau_export_timeout_sec", None) or 900,
        )
        _log_step("pipeline.openutau.ok", f"rendered vocals: {rendered_vocals}")

        _log_step("pipeline.mix.start", "mixing instrumental + rendered vocals")
        final_mix = mix_audio(
            str(instrumental_wav.resolve()),
            rendered_vocals,
            vocals_gain=getattr(singing_config, "vocals_gain", None) or 0.45,
            instrumental_gain=getattr(singing_config, "instrumental_gain", None) or 1.4,
        )
        _log_step("pipeline.mix.ok", f"final mix: {final_mix}")
    except (OpenUtauAutomationError, DiffRhythmPipelineError, Exception) as exc:
        openutau_fallback_used = True
        warning = (
            "Refinement pipeline did not complete; falling back to DiffRhythm output."
        )
        _log_step("pipeline.openutau.fail", f"{warning} Details: {exc}")

    _log_step("pipeline.end", f"complete final_mix={final_mix}")
    return PipelineArtifacts(
        full_song_wav=full_song_wav,
        instrumental_wav=str(instrumental_wav.resolve()),
        vocals_wav=str(vocals_wav.resolve()),
        lead_vocals_wav=lead_wav,
        backing_vocals_wav=backing_wav,
        mapped_ustx=mapped_ustx,
        rendered_vocals_wav=rendered_vocals,
        final_mix_wav=final_mix,
        openutau_fallback_used=openutau_fallback_used,
        warning=warning,
    )
