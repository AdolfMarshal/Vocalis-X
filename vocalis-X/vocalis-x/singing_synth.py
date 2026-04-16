import os
import time
import uuid
from typing import Optional, List, Tuple, Iterable
import re
import urllib.request
import urllib.parse
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torchaudio


class SingingNotConfiguredError(RuntimeError):
    pass


_MAJOR_PCS = {0, 2, 4, 5, 7, 9, 11}
_MINOR_PCS = {0, 2, 3, 5, 7, 8, 10}


def _require_path(path: Optional[str], label: str) -> str:
    if not path or not os.path.exists(path):
        raise SingingNotConfiguredError(
            f"Missing {label}. Set it in singing_config or install the required assets."
        )
    return path


def _normalize_audio(audio: np.ndarray) -> np.ndarray:
    if audio.size == 0:
        raise SingingNotConfiguredError("Cannot normalize empty audio buffer.")
    peak = np.max(np.abs(audio))
    if peak > 1.0:
        audio = audio / peak
    return audio


def mix_audio(
    instrumental_path: str,
    vocals_path: str,
    vocals_gain: float = 0.6,
    instrumental_gain: float = 1.0,
) -> str:
    inst, sr = sf.read(instrumental_path)
    voc, sr_v = sf.read(vocals_path)

    if inst.size == 0:
        raise SingingNotConfiguredError(
            f"Instrumental audio is empty: {instrumental_path}"
        )
    if voc.size == 0:
        raise SingingNotConfiguredError(
            f"Vocals audio is empty: {vocals_path}. OpenUtau export may not have completed."
        )

    if sr_v != sr:
        # Resample vocals to match instrumental sample rate
        if voc.ndim == 1:
            voc = voc[:, None]
        voc_tensor = torch.from_numpy(voc).permute(1, 0)
        voc_resampled = torchaudio.functional.resample(voc_tensor, sr_v, sr)
        voc = voc_resampled.permute(1, 0).numpy()

    if inst.ndim == 1:
        inst = inst[:, None]
    if voc.ndim == 1:
        voc = voc[:, None]

    # Match channels
    if voc.shape[1] == 1 and inst.shape[1] > 1:
        voc = np.repeat(voc, inst.shape[1], axis=1)
    elif voc.shape[1] != inst.shape[1]:
        raise SingingNotConfiguredError(
            f"Channel mismatch: instrumental {inst.shape[1]} vs vocals {voc.shape[1]}."
        )

    length = min(inst.shape[0], voc.shape[0])
    if length <= 0:
        raise SingingNotConfiguredError(
            "Cannot mix audio: one track has zero duration after alignment."
        )
    mixed = (inst[:length] * instrumental_gain) + (vocals_gain * voc[:length])
    mixed = _normalize_audio(mixed)

    out_dir = "output"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{uuid.uuid4()}_mix.wav")
    sf.write(out_path, mixed, sr)
    return out_path


def _estimate_key_pc_from_scale(scale_notes: List[int]) -> int:
    if not scale_notes:
        return 0
    counts = {}
    for n in scale_notes:
        pc = int(n) % 12
        counts[pc] = counts.get(pc, 0) + 1
    return max(counts, key=counts.get)


def _nearest_scale_midi(midi: float, key_pc: int, scale_mode: str) -> int:
    pcs = _MINOR_PCS if scale_mode == "minor" else _MAJOR_PCS
    allowed = {((pc + key_pc) % 12) for pc in pcs}
    center = int(round(midi))
    lo = center - 24
    hi = center + 24
    best = center
    best_dist = 1e9
    for cand in range(lo, hi + 1):
        if cand % 12 not in allowed:
            continue
        dist = abs(midi - cand)
        if dist < best_dist:
            best_dist = dist
            best = cand
    return best


def _autotune_vocals_after_export(
    vocals_path: str,
    singing_config,
    scale_notes: List[int],
    is_minor: bool,
) -> str:
    enabled = getattr(singing_config, "autotune_enabled", None)
    if enabled is None:
        enabled = True
    if not enabled:
        return vocals_path

    strength = float(getattr(singing_config, "autotune_strength", None) or 0.55)
    max_shift = float(getattr(singing_config, "autotune_max_shift", None) or 1.25)
    strength = max(0.0, min(1.0, strength))
    max_shift = max(0.1, min(6.0, max_shift))
    mode = (getattr(singing_config, "autotune_scale_mode", None) or "auto").lower()
    if mode == "off":
        return vocals_path
    if mode not in {"auto", "major", "minor"}:
        mode = "auto"
    if mode == "auto":
        mode = "minor" if is_minor else "major"

    key_pc = getattr(singing_config, "autotune_key_pc", None)
    if key_pc is None:
        key_pc = _estimate_key_pc_from_scale(scale_notes or [])
    key_pc = int(key_pc) % 12

    try:
        import librosa  # type: ignore
    except Exception as exc:
        print(f"âš ï¸ Autotune skipped: librosa missing ({exc})")
        return vocals_path

    try:
        y, sr = sf.read(vocals_path)
    except Exception as exc:
        print(f"âš ï¸ Autotune skipped: could not read vocals ({exc})")
        return vocals_path

    if y.size == 0:
        return vocals_path
    y_np = np.asarray(y, dtype=np.float32)
    mono = y_np if y_np.ndim == 1 else np.mean(y_np, axis=1)

    try:
        f0, _, _ = librosa.pyin(
            mono,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C6"),
            frame_length=2048,
            hop_length=256,
        )
    except Exception as exc:
        print(f"âš ï¸ Autotune skipped: pyin failed ({exc})")
        return vocals_path

    voiced = f0[np.isfinite(f0)]
    if voiced.size < 16:
        print("âš ï¸ Autotune skipped: insufficient voiced frames")
        return vocals_path

    midi = 69.0 + 12.0 * np.log2(voiced / 440.0)
    deltas = []
    for m in midi.tolist():
        target = _nearest_scale_midi(m, key_pc=key_pc, scale_mode=mode)
        deltas.append(m - target)
    median_delta = float(np.median(np.array(deltas, dtype=np.float32)))
    shift = float(np.clip(-median_delta * strength, -max_shift, max_shift))

    if abs(shift) < 0.03:
        print(f"ðŸŽ›ï¸ Autotune: no shift needed (median detune {median_delta:+.3f} st)")
        return vocals_path

    tuned = None
    engine = None
    try:
        import pyrubberband as pyrb  # type: ignore

        if y_np.ndim == 1:
            tuned = pyrb.pitch_shift(y_np, sr, n_steps=shift)
        else:
            chans = []
            for c in range(y_np.shape[1]):
                chans.append(pyrb.pitch_shift(y_np[:, c], sr, n_steps=shift))
            tuned = np.stack(chans, axis=1)
        engine = "pyrubberband"
    except Exception:
        try:
            if y_np.ndim == 1:
                tuned = librosa.effects.pitch_shift(y_np, sr=sr, n_steps=shift)
            else:
                chans = []
                for c in range(y_np.shape[1]):
                    chans.append(librosa.effects.pitch_shift(y_np[:, c], sr=sr, n_steps=shift))
                tuned = np.stack(chans, axis=1)
            engine = "librosa"
            print("âš ï¸ Autotune fallback: pyrubberband unavailable, using librosa pitch shift")
        except Exception as exc:
            print(f"âš ï¸ Autotune skipped: pitch shift failed ({exc})")
            return vocals_path

    tuned = np.asarray(tuned, dtype=np.float32)
    tuned = _normalize_audio(tuned)
    out_dir = "output"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{uuid.uuid4()}_vocals_tuned.wav")
    sf.write(out_path, tuned, sr)
    print(
        f"ðŸŽ›ï¸ Autotune applied ({engine}): shift={shift:+.3f} st, mode={mode}, key_pc={key_pc} -> {out_path}"
    )
    return out_path


def _resample_to(y: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return y
    if y.ndim == 1:
        yt = torch.from_numpy(y).unsqueeze(0)
        out = torchaudio.functional.resample(yt, src_sr, dst_sr).squeeze(0).numpy()
        return out
    chans = []
    for c in range(y.shape[1]):
        yt = torch.from_numpy(y[:, c]).unsqueeze(0)
        out = torchaudio.functional.resample(yt, src_sr, dst_sr).squeeze(0).numpy()
        chans.append(out)
    return np.stack(chans, axis=1)


def _build_time_map_from_dtw(
    vocals_mono: np.ndarray,
    inst_mono: np.ndarray,
    sr: int,
    anchor_hop_sec: float = 0.35,
    max_warp_ratio: float = 1.6,
) -> List[Tuple[int, int]]:
    import librosa  # type: ignore

    hop = max(128, int(sr * 0.01))
    n_fft = 2048
    vm = librosa.feature.melspectrogram(y=vocals_mono, sr=sr, n_fft=n_fft, hop_length=hop, n_mels=64)
    im = librosa.feature.melspectrogram(y=inst_mono, sr=sr, n_fft=n_fft, hop_length=hop, n_mels=64)
    vdb = librosa.power_to_db(vm + 1e-9)
    idb = librosa.power_to_db(im + 1e-9)

    # DTW path (instrument frames vs vocal frames)
    _, wp = librosa.sequence.dtw(X=idb, Y=vdb, metric="cosine")
    wp = np.asarray(wp[::-1], dtype=np.int64)  # ascending path
    if wp.size == 0:
        return [(0, 0), (len(vocals_mono), len(inst_mono))]

    vf = wp[:, 1]  # vocal frames
    tf = wp[:, 0]  # target/instrument frames

    # Build sparse, monotonic anchors.
    step = max(1, int(anchor_hop_sec * sr / hop))
    anchors = []
    last_in = -1
    last_out = -1
    for i in range(0, len(vf), step):
        inf = int(vf[i] * hop)
        outf = int(tf[i] * hop)
        if inf <= last_in or outf <= last_out:
            continue
        # Local warp clamp to avoid robotic artifacts.
        if last_in >= 0 and last_out >= 0:
            din = inf - last_in
            dout = outf - last_out
            if din > 0:
                r = dout / float(din)
                if r > max_warp_ratio:
                    outf = int(last_out + din * max_warp_ratio)
                elif r < 1.0 / max_warp_ratio:
                    outf = int(last_out + din / max_warp_ratio)
        anchors.append((inf, outf))
        last_in, last_out = inf, outf

    if not anchors or anchors[0][0] > 0:
        anchors = [(0, 0)] + anchors
    end_in = len(vocals_mono)
    end_out = len(inst_mono)
    if anchors[-1][0] >= end_in:
        anchors[-1] = (end_in, end_out)
    else:
        anchors.append((end_in, end_out))
    return anchors


def _timemap_align_vocals_after_export(
    vocals_path: str,
    instrumental_path: Optional[str],
    singing_config,
) -> str:
    enabled = getattr(singing_config, "timemap_align_enabled", None)
    if enabled is None:
        enabled = False
    if not enabled:
        return vocals_path
    if not instrumental_path or not os.path.exists(instrumental_path):
        print("âš ï¸ Timemap align skipped: instrumental missing")
        return vocals_path

    if shutil.which("rubberband") is None:
        print("âš ï¸ Timemap align skipped: rubberband executable not found in PATH")
        return vocals_path

    try:
        import librosa  # type: ignore
        import pyrubberband as pyrb  # type: ignore
    except Exception as exc:
        print(f"âš ï¸ Timemap align skipped: missing deps ({exc})")
        return vocals_path

    try:
        v, vsr = sf.read(vocals_path)
        i, isr = sf.read(instrumental_path)
    except Exception as exc:
        print(f"âš ï¸ Timemap align skipped: read failed ({exc})")
        return vocals_path
    if v.size == 0 or i.size == 0:
        print("âš ï¸ Timemap align skipped: empty vocals or instrumental")
        return vocals_path

    target_sr = 22050
    v = _resample_to(np.asarray(v, dtype=np.float32), vsr, target_sr)
    i = _resample_to(np.asarray(i, dtype=np.float32), isr, target_sr)
    vmono = v if v.ndim == 1 else np.mean(v, axis=1)
    imono = i if i.ndim == 1 else np.mean(i, axis=1)

    anchor_hop = float(getattr(singing_config, "timemap_anchor_hop_sec", None) or 0.35)
    max_warp = float(getattr(singing_config, "timemap_max_warp_ratio", None) or 1.6)
    anchor_hop = max(0.10, min(1.2, anchor_hop))
    max_warp = max(1.1, min(3.0, max_warp))

    try:
        time_map = _build_time_map_from_dtw(
            vocals_mono=vmono,
            inst_mono=imono,
            sr=target_sr,
            anchor_hop_sec=anchor_hop,
            max_warp_ratio=max_warp,
        )
        aligned = pyrb.timemap_stretch(v, target_sr, time_map=time_map, rbargs={"--fine": ""})
    except Exception as exc:
        print(f"âš ï¸ Timemap align skipped: DTW/rubberband failed ({exc})")
        return vocals_path

    aligned = np.asarray(aligned, dtype=np.float32)
    aligned = _normalize_audio(aligned)
    out_dir = "output"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{uuid.uuid4()}_vocals_aligned.wav")
    sf.write(out_path, aligned, target_sr)
    print(f"ðŸ§­ Timemap alignment applied: anchors={len(time_map)} -> {out_path}")
    return out_path


def _http_post_json(url: str, payload: dict, timeout: int = 300) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get(url: str, timeout: int = 300) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read()


def _to_aah_lyrics(lyrics: str) -> str:
    out_lines = []
    for raw in lyrics.splitlines():
        line = raw.strip()
        if not line:
            out_lines.append("")
            continue
        if re.match(r"^\s*\[[^\]]+\]\s*$", raw):
            out_lines.append(raw)
            continue
        toks = raw.split()
        out_toks = []
        for tok in toks:
            if re.search(r"[A-Za-z0-9]", tok):
                out_toks.append("aah")
            else:
                out_toks.append(tok)
        out_lines.append(" ".join(out_toks) if out_toks else "aah")
    return "\n".join(out_lines)


def _win_to_wsl_path(path: str) -> str:
    p = os.path.abspath(path).replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", p):
        drive = p[0].lower()
        tail = p[2:]
        return f"/mnt/{drive}{tail}"
    return p


def _resolve_mt3_midi_path(
    singing_config,
    input_wav_path: Optional[str],
) -> Optional[str]:
    explicit = getattr(singing_config, "mt3_midi_path", None)
    if explicit and os.path.exists(explicit):
        print(f"ðŸŽ¼ MT3 MIDI: using provided file {explicit}")
        return explicit

    cmd_template = getattr(singing_config, "mt3_command", None)
    if not cmd_template:
        # Convenience fallback: set once in environment and reuse from UI/backend.
        cmd_template = os.environ.get("VOCALIS_MT3_COMMAND") or os.environ.get("MT3_COMMAND")
    if not cmd_template:
        print("âš ï¸  MT3: no mt3_midi_path and no mt3_command configured (tip: set VOCALIS_MT3_COMMAND)")
        return None
    if not input_wav_path or not os.path.exists(input_wav_path):
        print("âš ï¸  MT3: input wav missing, cannot run mt3_command")
        return None

    out_dir = "output"
    os.makedirs(out_dir, exist_ok=True)
    out_mid = os.path.abspath(os.path.join(out_dir, f"{uuid.uuid4()}_mt3.mid"))
    try:
        cmd = cmd_template.format(
            input_wav=input_wav_path,
            output_mid=out_mid,
            input_wav_wsl=_win_to_wsl_path(input_wav_path),
            output_mid_wsl=_win_to_wsl_path(out_mid),
        )
    except Exception as exc:
        print(f"âš ï¸  MT3: invalid mt3_command template ({exc})")
        return None

    print("ðŸŽ¼ MT3: running transcription command...")
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except Exception as exc:
        print(f"âš ï¸  MT3: command failed to start ({exc})")
        return None

    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        if err:
            print(f"âš ï¸  MT3 stderr: {err[-600:]}")
        print(f"âš ï¸  MT3: command exit code {proc.returncode}")
        return None
    if not os.path.exists(out_mid):
        print("âš ï¸  MT3: command succeeded but no MIDI output found")
        return None
    print(f"âœ… MT3 MIDI generated: {out_mid}")
    return out_mid


def _simple_english_phonemes(word: str) -> List[str]:
    # Rough fallback G2P if g2p_en isn't available.
    word = "".join([c.lower() for c in word if c.isalpha()])
    if not word:
        return []

    digraphs = {
        "ch": "en/ch",
        "sh": "en/sh",
        "th": "en/th",
        "ng": "en/ng",
        "ph": "en/f",
        "wh": "en/w",
    }
    vowels = {
        "a": "en/aa",
        "e": "en/eh",
        "i": "en/ih",
        "o": "en/ow",
        "u": "en/uh",
        "y": "en/iy",
    }
    consonants = {
        "b": "en/b",
        "c": "en/k",
        "d": "en/d",
        "f": "en/f",
        "g": "en/g",
        "h": "en/hh",
        "j": "en/jh",
        "k": "en/k",
        "l": "en/l",
        "m": "en/m",
        "n": "en/n",
        "p": "en/p",
        "q": "en/k",
        "r": "en/r",
        "s": "en/s",
        "t": "en/t",
        "v": "en/v",
        "w": "en/w",
        "x": "en/k",
        "z": "en/z",
    }

    phonemes = []
    i = 0
    while i < len(word):
        if i + 1 < len(word):
            dg = word[i:i + 2]
            if dg in digraphs:
                phonemes.append(digraphs[dg])
                i += 2
                continue
        ch = word[i]
        if ch in vowels:
            phonemes.append(vowels[ch])
        elif ch in consonants:
            phonemes.append(consonants[ch])
        i += 1
    return phonemes


_CMU_TO_RENA = {
    "AA": "en/aa",
    "AE": "en/ae",
    "AH": "en/ah",
    "AO": "en/ao",
    "AW": "en/aw",
    "AX": "en/ax",
    "AY": "en/ay",
    "EH": "en/eh",
    "ER": "en/er",
    "EY": "en/ey",
    "IH": "en/ih",
    "IY": "en/iy",
    "OW": "en/ow",
    "OY": "en/oy",
    "UH": "en/uh",
    "UW": "en/uw",
    "B": "en/b",
    "CH": "en/ch",
    "D": "en/d",
    "DH": "en/dh",
    "F": "en/f",
    "G": "en/g",
    "HH": "en/hh",
    "JH": "en/jh",
    "K": "en/k",
    "L": "en/l",
    "M": "en/m",
    "N": "en/n",
    "NG": "en/ng",
    "P": "en/p",
    "R": "en/r",
    "S": "en/s",
    "SH": "en/sh",
    "T": "en/t",
    "TH": "en/th",
    "V": "en/v",
    "W": "en/w",
    "Y": "en/y",
    "Z": "en/z",
    "ZH": "en/zh",
}

_CMU_DICT = None


def _get_cmu_dict():
    global _CMU_DICT
    if _CMU_DICT is None:
        try:
            from nltk.corpus import cmudict  # type: ignore
            _CMU_DICT = cmudict.dict()
        except LookupError as exc:
            print(f"âš ï¸ NLTK cmudict not found: {exc}.")
            _CMU_DICT = {}
    return _CMU_DICT


def _clean_word(word: str) -> str:
    # Keep letters and apostrophes for contractions.
    return re.sub(r"[^a-zA-Z']+", "", word).lower()


def _cmudict_word_phonemes(word: str) -> List[str]:
    cmu = _get_cmu_dict()
    if not cmu:
        return []
    cleaned = _clean_word(word)
    if not cleaned:
        return []
    if cleaned not in cmu:
        return []
    phones = cmu[cleaned][0]
    mapped = []
    for ph in phones:
        base = "".join([c for c in ph if not c.isdigit()])
        rena = _CMU_TO_RENA.get(base)
        if rena:
            mapped.append(rena)
    return mapped


def _g2p_en_phonemes(words: Iterable[str]) -> List[str]:
    # Uses g2p_en if installed. Returns Rena phoneme set (en/.. + SP).
    try:
        from g2p_en import G2p  # type: ignore
    except Exception:
        return []

    g2p = G2p()
    try:
        raw = g2p(" ".join(words))
    except LookupError as exc:
        print(f"âš ï¸ g2p_en missing NLTK data: {exc}. Falling back to simple phonemes.")
        return []
    phonemes: List[str] = []
    for ph in raw:
        if ph == " ":
            phonemes.append("SP")
            continue
        if ph == "sil":
            phonemes.append("SP")
            continue
        # remove stress digits
        base = "".join([c for c in ph if not c.isdigit()])
        mapped = _CMU_TO_RENA.get(base)
        if mapped:
            phonemes.append(mapped)
    # cleanup consecutive SPs
    cleaned: List[str] = []
    for ph in phonemes:
        if ph == "SP" and cleaned and cleaned[-1] == "SP":
            continue
        cleaned.append(ph)
    if cleaned and cleaned[-1] == "SP":
        cleaned.pop()
    return cleaned


def _lyrics_to_phonemes(lyrics: str, language: str) -> List[str]:
    lyrics = lyrics.strip()
    if lyrics.lower().startswith("@ph:"):
        raw = lyrics[4:].strip()
        return [p for p in raw.split() if p]

    words = [w for w in lyrics.split() if w]
    phonemes = []
    for w in words:
        if language == "en":
            phs = _simple_english_phonemes(w)
        else:
            # Fallback for non-English: treat each token as a phoneme if possible.
            # Users can provide explicit phonemes with "@ph:".
            phs = [w]
        if phs:
            phonemes.extend(phs)
            phonemes.append("SP")
    if phonemes and phonemes[-1] == "SP":
        phonemes.pop()
    return phonemes


def _lyrics_to_phonemes_en(lyrics: str, debug_lexicon: bool = False) -> List[str]:
    lyrics = lyrics.strip()
    if lyrics.lower().startswith("@ph:"):
        raw = lyrics[4:].strip()
        return [p for p in raw.split() if p]

    words = [w for w in lyrics.split() if w]
    phonemes = []
    lexicon_trace = []
    for w in words:
        phs = _cmudict_word_phonemes(w)
        source = "cmu"
        if not phs:
            phs = _g2p_en_phonemes([w])
            phs = [p for p in phs if p != "SP"]
            source = "g2p"
        if not phs:
            phs = _simple_english_phonemes(w)
            source = "simple"
        if phs:
            phonemes.extend(phs)
            phonemes.append("SP")
        lexicon_trace.append(f"{w}:{source}")
    if debug_lexicon and lexicon_trace:
        print(f"ðŸ”Ž Lexicon: {', '.join(lexicon_trace)}")
    if phonemes and phonemes[-1] == "SP":
        phonemes.pop()
    return phonemes


def _build_f0_from_melody(midi_notes: List[int], durations: List[float], timestep: float = 0.01) -> dict:
    values = []
    for midi, dur in zip(midi_notes, durations):
        hz = 440.0 * (2 ** ((midi - 69) / 12))
        steps = max(1, int(dur / timestep))
        values.extend([hz] * steps)
    return {"timestep": timestep, "values": values}


def _build_melody(num_units: int, base_midi: int = 60) -> List[int]:
    # Slower, more "sung" contour: longer holds and small steps.
    steps = [0, 0, 2, 2, 4, 4, 2, 2, 0, 0, -1, 0, 2, 2, 0, 0]
    melody = []
    idx = 0
    while len(melody) < num_units:
        step = steps[idx % len(steps)]
        # Hold each pitch for 2 units
        melody.extend([base_midi + step, base_midi + step])
        idx += 1
    return melody[:num_units]


_RENA_VOWELS = {
    "en/aa", "en/ae", "en/ah", "en/ao", "en/aw", "en/ax", "en/ay",
    "en/eh", "en/er", "en/ey", "en/ih", "en/iy", "en/ow", "en/oy",
    "en/uh", "en/uw",
}


def _phonemes_with_durations(
    phonemes: List[str],
    unit_duration: float = 0.4,
    pause_multiplier: float = 1.5,
    vowel_multiplier: float = 1.0,
    consonant_multiplier: float = 1.0,
) -> Tuple[List[dict], List[float]]:
    durations = []
    items = []
    for ph in phonemes:
        if ph == "SP":
            dur = unit_duration * pause_multiplier
        elif ph in _RENA_VOWELS:
            dur = unit_duration * vowel_multiplier
        else:
            dur = unit_duration * consonant_multiplier
        items.append({"name": ph, "duration": dur})
        durations.append(dur)
    return items, durations


def _synthesize_with_mini_engine(lyrics: str, language: str, singing_config) -> str:
    engine_url = singing_config.engine_url or "http://127.0.0.1:9266"
    model_name = singing_config.model_name or "rena_acoustic"
    speedup = getattr(singing_config, "speedup", None) or 1

    if language == "en":
        phonemes = _lyrics_to_phonemes_en(lyrics, debug_lexicon=getattr(singing_config, "debug_lexicon", False))
    else:
        phonemes = _lyrics_to_phonemes(lyrics, language)
    if not phonemes:
        raise SingingNotConfiguredError("Failed to derive phonemes from lyrics.")

    target_duration = getattr(singing_config, "target_duration", None)
    sps = getattr(singing_config, "syllables_per_second", None)
    min_dur = getattr(singing_config, "min_phoneme_duration", None) or 0.08
    max_dur = getattr(singing_config, "max_phoneme_duration", None) or 0.8
    pause_mult = getattr(singing_config, "pause_multiplier", None) or 1.5
    vowel_mult = getattr(singing_config, "vowel_multiplier", None) or 0.85
    consonant_mult = getattr(singing_config, "consonant_multiplier", None) or 1.25
    repeat_until_target = getattr(singing_config, "repeat_lyrics_until_target", None)
    if repeat_until_target is None:
        repeat_until_target = True

    base_unit = 0.4
    if sps and sps > 0:
        base_unit = 1.0 / sps

    sp_count = sum(1 for p in phonemes if p == "SP")
    vowel_count = sum(1 for p in phonemes if p in _RENA_VOWELS)
    consonant_count = len(phonemes) - sp_count - vowel_count
    effective_units = (
        (sp_count * pause_mult)
        + (vowel_count * vowel_mult)
        + (consonant_count * consonant_mult)
    )
    if target_duration and target_duration > 1 and effective_units > 0:
        base_unit = target_duration / effective_units

    base_unit = max(min_dur, min(max_dur, base_unit))

    # If lyrics are too short for the target, repeat them to fill time (unless disabled).
    if repeat_until_target and target_duration and target_duration > 1 and effective_units > 0:
        est_total = effective_units * base_unit
        if est_total < target_duration * 0.98:
            repeats = int((target_duration / est_total) + 0.999)
            max_repeats = 64
            repeats = max(1, min(repeats, max_repeats))
            if repeats > 1:
                # Avoid leading SPs when repeating
                seq = phonemes[:]
                if seq and seq[-1] == "SP":
                    seq = seq[:-1]
                phonemes = []
                for _ in range(repeats):
                    phonemes.extend(seq)
                    phonemes.append("SP")
                if phonemes and phonemes[-1] == "SP":
                    phonemes.pop()

                # Recompute base_unit against the repeated sequence to match target
                sp_count = sum(1 for p in phonemes if p == "SP")
                vowel_count = sum(1 for p in phonemes if p in _RENA_VOWELS)
                consonant_count = len(phonemes) - sp_count - vowel_count
                effective_units = (
                    (sp_count * pause_mult)
                    + (vowel_count * vowel_mult)
                    + (consonant_count * consonant_mult)
                )
                if effective_units > 0:
                    base_unit = target_duration / effective_units
                    base_unit = max(min_dur, min(max_dur, base_unit))

    phoneme_items, durations = _phonemes_with_durations(
        phonemes,
        unit_duration=base_unit,
        pause_multiplier=pause_mult,
        vowel_multiplier=vowel_mult,
        consonant_multiplier=consonant_mult,
    )
    if getattr(singing_config, "debug_phonemes", False):
        print(f"ðŸ”Ž MiniEngine model={model_name} url={engine_url} speedup={speedup}")
        print(f"ðŸ”Ž Timing mult: vowel={vowel_mult:.2f} consonant={consonant_mult:.2f} pause={pause_mult:.2f}")
        print(f"ðŸ”Ž Phonemes ({len(phonemes)}): {' '.join(phonemes)}")
    if getattr(singing_config, "debug_durations", False):
        total = sum(durations)
        print(f"ðŸ”Ž Durations: base_unit={base_unit:.3f}s pause_mult={pause_mult:.2f} total={total:.2f}s target={target_duration}")
        preview = ", ".join([f"{p['name']}:{p['duration']:.2f}" for p in phoneme_items[:40]])
        print(f"ðŸ”Ž Duration preview: {preview}{' ...' if len(phoneme_items) > 40 else ''}")
    melody = _build_melody(len(phoneme_items), base_midi=60)
    f0 = _build_f0_from_melody(melody, durations, timestep=0.01)

    submit_payload = {
        "model": model_name,
        "phonemes": phoneme_items,
        "f0": f0,
        "speedup": speedup
    }

    submit_res = _http_post_json(f"{engine_url}/submit", submit_payload, timeout=300)
    token = submit_res.get("token")
    if not token:
        raise SingingNotConfiguredError("MiniEngine submit failed (no token).")

    # Poll
    max_wait = singing_config.max_wait_sec if singing_config and singing_config.max_wait_sec else 900
    for _ in range(max_wait):
        time.sleep(1)
        status_res = _http_post_json(f"{engine_url}/query", {"token": token}, timeout=60)
        status = status_res.get("status")
        if status == "FINISHED" or status == "HIT_CACHE":
            wav_bytes = _http_get(f"{engine_url}/download?token={token}", timeout=300)
            out_dir = "output"
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{uuid.uuid4()}_vocals.wav")
            with open(out_path, "wb") as f:
                f.write(wav_bytes)
            return out_path
        if status == "FAILED":
            raise SingingNotConfiguredError(status_res.get("message", "MiniEngine failed."))

    raise SingingNotConfiguredError("MiniEngine timed out.")


def generate_vocals(
    lyrics: str,
    language: str,
    singing_config,
) -> str:
    if not lyrics:
        raise SingingNotConfiguredError("Lyrics are required for singing synthesis.")

    backend = (singing_config.backend or "diffsinger").lower()

    # Allow external pre-rendered vocals for now (useful during setup).
    if backend == "external":
        return _require_path(singing_config.vocals_path, "singing_config.vocals_path")

    if backend == "mini_engine":
        return _synthesize_with_mini_engine(lyrics, language, singing_config)

    if backend == "openutau":
        return _synthesize_with_openutau(
            lyrics, singing_config,
            instrumental_path=getattr(singing_config, "instrumental_path", None)
        )

    if backend != "diffsinger":
        raise SingingNotConfiguredError(
            f"Unsupported singing backend: {backend}. Use 'openutau', 'mini_engine', 'diffsinger' or 'external'."
        )

    # DiffSinger integration is scaffolding for now.
    _require_path(singing_config.diffsinger_root, "singing_config.diffsinger_root")
    _require_path(singing_config.voicebank_path, "singing_config.voicebank_path")
    _require_path(singing_config.vocoder_path, "singing_config.vocoder_path")

    raise SingingNotConfiguredError(
        "DiffSinger backend not wired yet. Install the models and configure paths, "
        "then follow the setup steps in README.md."
    )


def _synthesize_with_openutau(lyrics: str, singing_config, instrumental_path: str = None) -> str:
    try:
        from openutau_ustx import write_ustx, RENA_MID_TONE
        from openutau_automation import render_ustx_to_wav
    except Exception as exc:
        raise SingingNotConfiguredError(f"OpenUtau import failed: {exc}")

    bpm        = getattr(singing_config, "openutau_bpm",       None) or 120
    base_tone  = getattr(singing_config, "openutau_base_tone", None) or RENA_MID_TONE
    export_dir = getattr(singing_config, "openutau_export_dir", None) or r"output\openutau"
    if export_dir.strip().lower() == "output":
        export_dir = r"output\openutau"

    scale_notes     = []
    is_minor        = False
    chords          = []
    vocals_path     = None
    blended_emotion = {
        "joy":     getattr(singing_config, "joy",     None) or 0.3,
        "sadness": getattr(singing_config, "sadness", None) or 0.2,
        "tension": getattr(singing_config, "tension", None) or 0.1,
    }

   # â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
    # DIAGNOSTIC CHAIN
    # â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”
    chain = {}

    if instrumental_path:
        chain["instrumental_path"] = ("âœ…", instrumental_path)

        # â”€â”€ librosa â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        try:
            from librosa_analysis import analyze_instrumental, blend_with_user_emotion
            music       = analyze_instrumental(instrumental_path)
            bpm         = int(music["tempo"])
            base_tone   = music["suggested_base_tone"]
            scale_notes = music.get("scale_tones", [])
            is_minor    = music.get("is_minor", False)
            blended_emotion = blend_with_user_emotion(
                music=music,
                user_joy=getattr(singing_config, "joy",      None) or 0.3,
                user_sadness=getattr(singing_config, "sadness",  None) or 0.2,
                user_tension=getattr(singing_config, "tension",  None) or 0.1,
                user_energy=getattr(singing_config, "energy",   None) or 0.5,
                user_darkness=getattr(singing_config, "darkness", None) or 0.2,
                music_weight=0.5,
            )
            chain["librosa"] = ("âœ…", f"{music['key_name']} {'minor' if is_minor else 'major'} @ {bpm} BPM")
        except Exception as e:
            chain["librosa"] = ("âŒ", str(e))

        # â”€â”€ chords â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        # Chord extraction disabled: prefer guide-vocal/basic-pitch notes.
        chords = []
        chain["chords"] = ("SKIP", "disabled (guide-vocal pitch mode)")

        # â”€â”€ groove template â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        groove_name = getattr(singing_config, "groove_template", None)
        if groove_name:
            from pathlib import Path as _P
            groove_file = _P("swagger_templates") / groove_name
            if groove_file.exists():
                import json as _json
                g = _json.load(open(groove_file))
                hits = len(g.get("word_slots", []) or g.get("syllable_hits", []))
                chain["groove"] = ("âœ…", f"{groove_name} ({hits} hits)")
            else:
                chain["groove"] = ("âŒ", f"{groove_name} not found in swagger_templates/")
        else:
            chain["groove"] = ("âŒ", "groove_template not set on singing_config")

        # Melody-note guide audio:
        # 1) explicit singing_config.vocals_path, else
        # 2) generated instrumental_path (AI lead from music itself).
        vocals_path = getattr(singing_config, "vocals_path", None) or instrumental_path
        if vocals_path and os.path.exists(vocals_path):
            chain["melody_source"] = ("âœ…", vocals_path)
        else:
            chain["melody_source"] = ("âŒ", "No valid melody-source audio for basic_pitch")

    else:
        chain["instrumental_path"] = ("âŒ", "None â€” chord/librosa/groove all skipped")
        chain["librosa"]           = ("â­ ", "skipped")
        chain["chords"]            = ("â­ ", "skipped")
        chain["groove"]            = ("â­ ", "skipped")
        chain["melody_source"]     = ("â­ ", "skipped")

    # â”€â”€ Print diagnostic â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print("\n" + "â”" * 54)
    print("  ðŸŽµ VOCALIS-X GENERATION CHAIN")
    print("â”" * 54)
    for key, (icon, msg) in chain.items():
        print(f"  {icon}  {key.ljust(20)}: {msg}")
    print("â”" * 54 + "\n")

    aah_primary = getattr(singing_config, "openutau_aah_primary_enabled", None)
    if aah_primary is None:
        aah_primary = False
    mt3_fallback = getattr(singing_config, "mt3_fallback_enabled", None)
    if mt3_fallback is None:
        mt3_fallback = True
    mt3_force = getattr(singing_config, "mt3_force_enabled", None)
    if mt3_force is None:
        mt3_force = False
    mt3_force = bool(mt3_force)
    mt3_compare = getattr(singing_config, "mt3_compare_enabled", None)
    if mt3_compare is None:
        mt3_compare = False
    mt3_compare = bool(mt3_compare)
    mt3_input_source = (getattr(singing_config, "mt3_input_source", None) or "instrumental").lower()

    print(f"AAH guide mode: {'on' if aah_primary else 'off'}")

    mt3_input_wav = vocals_path if (mt3_input_source == "guide_vocals" and vocals_path) else instrumental_path
    mt3_requested = bool(
        mt3_force
        or mt3_compare
        or getattr(singing_config, "mt3_midi_path", None)
        or getattr(singing_config, "mt3_command", None)
        or os.environ.get("VOCALIS_MT3_COMMAND")
        or os.environ.get("MT3_COMMAND")
    )
    mt3_midi_path = _resolve_mt3_midi_path(singing_config, mt3_input_wav) if mt3_requested else None
    explicit_melody_midi = getattr(singing_config, "melody_midi_path", None)
    if explicit_melody_midi and os.path.exists(explicit_melody_midi):
        mt3_midi_path = explicit_melody_midi

    primary_ustx = write_ustx(
        lyrics,
        bpm=bpm,
        base_tone=base_tone,
        groove_template=getattr(singing_config, "groove_template", None),
        emotion=blended_emotion,
        darkness=blended_emotion.get("darkness", getattr(singing_config, "darkness", None) or 0.2),
        energy=blended_emotion.get("energy",     getattr(singing_config, "energy",   None) or 0.5),
        scale_notes=scale_notes,
        is_minor=is_minor,
        chords=[],
        vocals_path=vocals_path,
        melody_midi_path=None,
    )
    print(f"Primary USTX (lyrics): {primary_ustx}")

    mt3_ustx = None
    if mt3_midi_path:
        mt3_ustx = write_ustx(
            lyrics,
            bpm=bpm,
            base_tone=base_tone,
            groove_template=getattr(singing_config, "groove_template", None),
            emotion=blended_emotion,
            darkness=blended_emotion.get("darkness", getattr(singing_config, "darkness", None) or 0.2),
            energy=blended_emotion.get("energy",     getattr(singing_config, "energy",   None) or 0.5),
            scale_notes=scale_notes,
            is_minor=is_minor,
            chords=[],
            vocals_path=None,
            melody_midi_path=mt3_midi_path,
        )
        print(f"MT3 USTX: {mt3_ustx}")
    else:
        print("MT3 USTX not built (no MIDI available)")
        if mt3_force:
            print("⚠️  MT3 primary requested but unavailable; falling back to primary melody path")

    autostart = getattr(singing_config, "openutau_autostart", None)
    if autostart is None:
        autostart = True

    def _render(ustx_path: str) -> str:
        return render_ustx_to_wav(
            str(ustx_path),
            export_dir=export_dir,
            exe_path=getattr(singing_config, "openutau_exe_path", None),
            autostart=autostart,
            wait_sec=getattr(singing_config, "openutau_wait_sec", None) or 20,
            open_key=getattr(singing_config, "openutau_open_key", None) or "^o",
            export_key=getattr(singing_config, "openutau_export_key", None) or "^e",
            export_menu_down=getattr(singing_config, "openutau_export_menu_down", None),
            export_submenu_down=getattr(singing_config, "openutau_export_submenu_down", None),
            export_timeout_sec=getattr(singing_config, "openutau_export_timeout_sec", None) or 900,
            merge_parts_before_pitch=False,
            min_duration_sec=getattr(singing_config, "target_duration", None),
        )

    selected_source = "lyrics_openutau"
    selected_ustx = mt3_ustx if (mt3_force and mt3_ustx) else primary_ustx
    if mt3_force and mt3_ustx:
        selected_source = "mt3"

    debug = {
        "selected_source": selected_source,
        "mt3_midi_path": mt3_midi_path,
        "ustx_primary": str(primary_ustx),
        "ustx_mt3": str(mt3_ustx) if mt3_ustx else None,
        "raw_vocals_primary": None,
        "raw_vocals_mt3": None,
        "raw_vocals_selected": None,
    }

    try:
        raw_vocals = _render(selected_ustx)
        if selected_source == "mt3":
            debug["raw_vocals_mt3"] = raw_vocals
        else:
            debug["raw_vocals_primary"] = raw_vocals
    except Exception as exc:
        if selected_source != "mt3" and mt3_fallback and mt3_ustx:
            print(f"Primary OpenUtau render failed ({exc}); trying MT3 fallback...")
            raw_vocals = _render(mt3_ustx)
            selected_source = "mt3_fallback"
            debug["selected_source"] = selected_source
            debug["raw_vocals_mt3"] = raw_vocals
        else:
            raise

    if mt3_compare and mt3_ustx and selected_source != "mt3":
        try:
            debug["raw_vocals_mt3"] = _render(mt3_ustx)
        except Exception as exc:
            print(f"MT3 compare render failed: {exc}")
    if mt3_compare and selected_source == "mt3":
        try:
            debug["raw_vocals_primary"] = _render(primary_ustx)
        except Exception as exc:
            print(f"Primary compare render failed: {exc}")

    debug["raw_vocals_selected"] = raw_vocals
    setattr(singing_config, "_transcription_debug", debug)
    aligned_vocals = _timemap_align_vocals_after_export(
        raw_vocals,
        instrumental_path=instrumental_path,
        singing_config=singing_config,
    )
    return _autotune_vocals_after_export(
        aligned_vocals,
        singing_config=singing_config,
        scale_notes=scale_notes,
        is_minor=is_minor,
    )


