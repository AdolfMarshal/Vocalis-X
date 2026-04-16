import json
import os
import shutil
import subprocess
import base64
from pathlib import Path

import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parent
WORK_ROOT = Path("/kaggle/working/vocalisx_job")
INPUTS = WORK_ROOT / "inputs"
ARTIFACTS = WORK_ROOT / "artifacts"
INPUTS.mkdir(parents=True, exist_ok=True)
ARTIFACTS.mkdir(parents=True, exist_ok=True)
REQUEST_JSON_B64 = "__VOCALIS_REQUEST_B64__"
REQUEST_JSON_SENTINEL = "__VOCALIS_REQUEST_SENTINEL__"


def run(cmd, cwd=None):
    print(f"[vocalisx_kaggle_runner] running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def ensure_espeak():
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        return
    run(["apt-get", "update"])
    run(["apt-get", "install", "-y", "espeak-ng", "libespeak-ng1"])


def ensure_repo(repo_url: str, ref: str | None) -> Path:
    repo_dir = Path("/tmp/DiffRhythm")
    dataset_slug = os.environ.get("VOCALIS_KAGGLE_DIFFRHYTHM_DATASET") or None
    dataset_subdir = os.environ.get("VOCALIS_KAGGLE_DIFFRHYTHM_DATASET_SUBDIR") or None
    if dataset_slug:
        dataset_root = Path("/kaggle/input") / dataset_slug.split("/")[-1]
        candidate = dataset_root / dataset_subdir if dataset_subdir else dataset_root
        if candidate.exists():
            return candidate
        if dataset_root.exists() and (dataset_root / "DiffRhythm").exists():
            return dataset_root / "DiffRhythm"

    bundled_repo = ROOT / "DiffRhythm"
    if bundled_repo.exists():
        if repo_dir.exists():
            shutil.rmtree(repo_dir)
        shutil.copytree(bundled_repo, repo_dir)
        return repo_dir
    if not repo_dir.exists():
        run(["git", "clone", repo_url, str(repo_dir)])
    if ref:
        run(["git", "fetch", "--all"], cwd=str(repo_dir))
        run(["git", "checkout", ref], cwd=str(repo_dir))
    return repo_dir


def install_requirements(repo_dir: Path, extra_pip_packages: str):
    req = repo_dir / "requirements.txt"
    if req.exists():
        run(["python", "-m", "pip", "install", "-r", str(req)])
    run(["python", "-m", "pip", "install", "demucs", "soundfile", "numpy"])
    if extra_pip_packages.strip():
        run(["python", "-m", "pip", "install", *extra_pip_packages.split()])


def newest_wav(root: Path):
    wavs = [p for p in root.rglob("*.wav") if p.is_file()]
    if not wavs:
        return None
    wavs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return wavs[0]


def build_no_vocals(track_dir: Path):
    bass = track_dir / "bass.wav"
    drums = track_dir / "drums.wav"
    other = track_dir / "other.wav"
    if not (bass.exists() and drums.exists() and other.exists()):
        return None

    b, sr_b = sf.read(str(bass), always_2d=True)
    d, sr_d = sf.read(str(drums), always_2d=True)
    o, sr_o = sf.read(str(other), always_2d=True)
    if sr_b != sr_d or sr_b != sr_o:
        raise RuntimeError("Demucs stem sample rate mismatch while building no_vocals.wav")

    n = min(len(b), len(d), len(o))
    if n <= 0:
        raise RuntimeError("Demucs stems are empty")

    combined = b[:n] + d[:n] + o[:n]
    peak = float(np.max(np.abs(combined))) if combined.size else 0.0
    if peak > 1.0:
        combined = combined / peak
    out = track_dir / "no_vocals.wav"
    sf.write(str(out), combined, sr_b)
    return out


def clean_working_dir():
    """
    Remove everything from /kaggle/working except the final artifacts tree.
    Kaggle bundles /kaggle/working as output, so keep it minimal.
    """
    keep = ARTIFACTS.resolve()
    working = Path("/kaggle/working")
    if not working.exists():
        return

    for item in working.iterdir():
        item_resolved = item.resolve()
        try:
            item_resolved.relative_to(keep)
            continue
        except ValueError:
            pass

        try:
            keep.relative_to(item_resolved)
            for sibling in item.iterdir():
                sibling_resolved = sibling.resolve()
                try:
                    sibling_resolved.relative_to(keep)
                    continue
                except ValueError:
                    pass
                if sibling.is_dir():
                    shutil.rmtree(sibling, ignore_errors=True)
                else:
                    sibling.unlink(missing_ok=True)
            continue
        except ValueError:
            pass

        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)

    print("[vocalisx_kaggle_runner] /kaggle/working cleaned - only artifacts remain")


def main():
    clean_working_dir()
    INPUTS.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    src_inputs = ROOT / "inputs"
    if src_inputs.exists():
        shutil.copytree(src_inputs, INPUTS, dirs_exist_ok=True)

    request_file = INPUTS / "request.json"
    if request_file.exists():
        request = json.loads(request_file.read_text(encoding="utf-8"))
    elif REQUEST_JSON_B64 and REQUEST_JSON_B64 != REQUEST_JSON_SENTINEL:
        request = json.loads(base64.b64decode(REQUEST_JSON_B64.encode("ascii")).decode("utf-8"))
        request_file.write_text(json.dumps(request, indent=2), encoding="utf-8")
    else:
        raise FileNotFoundError(f"Missing request payload at {request_file}")

    if request.get("diffrhythm_dataset_slug"):
        os.environ["VOCALIS_KAGGLE_DIFFRHYTHM_DATASET"] = request["diffrhythm_dataset_slug"]
    if request.get("diffrhythm_dataset_subdir"):
        os.environ["VOCALIS_KAGGLE_DIFFRHYTHM_DATASET_SUBDIR"] = request["diffrhythm_dataset_subdir"]
    ensure_espeak()
    repo_dir = ensure_repo(request["diffrhythm_repo"], request.get("diffrhythm_ref"))
    install_requirements(repo_dir, request.get("extra_pip_packages", ""))

    if request.get("setup_command"):
        run(request["setup_command"].split(), cwd=str(repo_dir))

    prompt_file = INPUTS / "prompt.txt"
    lyrics_file = INPUTS / "lyrics.txt"
    lrc_file = INPUTS / "lyrics.lrc"
    prompt_file.write_text(request["prompt"], encoding="utf-8")
    lyrics_file.write_text(request["lyrics_text"], encoding="utf-8")
    lrc_file.write_text(request["lyrics_lrc"], encoding="utf-8")

    infer_out = ARTIFACTS / "diffrhythm_output"
    infer_out.mkdir(parents=True, exist_ok=True)

    infer_script = repo_dir / request.get("infer_relpath", "infer/infer.py")
    run(
        [
            request.get("python_bin", "python"),
            str(infer_script),
            "--lrc-path",
            str(lrc_file),
            "--ref-prompt",
            request["prompt"],
            "--audio-length",
            str(request["audio_length_sec"]),
            "--output-dir",
            str(infer_out),
            "--chunked",
        ],
        cwd=str(repo_dir),
    )

    full_song = newest_wav(infer_out)
    if not full_song:
        raise RuntimeError("DiffRhythm did not produce any wav output")
    shutil.copy2(full_song, ARTIFACTS / "full_song.wav")

    demucs_out = ARTIFACTS / "demucs"
    run(
        [
            "demucs",
            "-n",
            request.get("demucs_model", "htdemucs_ft"),
            "-o",
            str(demucs_out),
            str(full_song),
        ]
    )

    track_root = demucs_out / request.get("demucs_model", "htdemucs_ft")
    track_dirs = [p for p in track_root.glob("*") if p.is_dir()]
    if not track_dirs:
        raise RuntimeError("Demucs output folder was not created")
    track_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    track_dir = track_dirs[0]

    vocals = track_dir / "vocals.wav"
    no_vocals = track_dir / "no_vocals.wav"
    if not no_vocals.exists():
        alt = track_dir / "accompaniment.wav"
        if alt.exists():
            no_vocals = alt
        else:
            built = build_no_vocals(track_dir)
            if built is not None:
                no_vocals = built

    if vocals.exists():
        shutil.copy2(vocals, ARTIFACTS / "vocals.wav")
    if no_vocals.exists():
        shutil.copy2(no_vocals, ARTIFACTS / "no_vocals.wav")

    (ARTIFACTS / "result.json").write_text(
        json.dumps(
            {
                "full_song": str((ARTIFACTS / "full_song.wav").resolve()),
                "vocals": str((ARTIFACTS / "vocals.wav").resolve()) if (ARTIFACTS / "vocals.wav").exists() else None,
                "no_vocals": str((ARTIFACTS / "no_vocals.wav").resolve()) if (ARTIFACTS / "no_vocals.wav").exists() else None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    clean_working_dir()


if __name__ == "__main__":
    main()
