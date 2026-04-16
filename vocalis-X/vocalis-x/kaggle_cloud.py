import json
import os
import shutil
import subprocess
import time
import uuid
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class KaggleCloudError(RuntimeError):
    pass


@dataclass
class KaggleJobArtifacts:
    full_song_wav: str
    instrumental_wav: Optional[str] = None
    vocals_wav: Optional[str] = None


def _log(step: str, message: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[KaggleCloud][{ts}][{step}] {message}")


def _run_capture(cmd, cwd: Optional[str] = None, timeout_sec: Optional[int] = None) -> subprocess.CompletedProcess:
    _log("command.start", f"cwd={cwd or os.getcwd()} timeout={timeout_sec} cmd={' '.join(cmd)}")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
        timeout=timeout_sec,
    )
    _log("command.end", f"exit_code={proc.returncode}")
    if proc.stdout.strip():
        _log("stdout", proc.stdout.strip())
    if proc.stderr.strip():
        _log("stderr", proc.stderr.strip())
    return proc


def _require_cli():
    proc = _run_capture(["kaggle", "--version"])
    if proc.returncode != 0:
        raise KaggleCloudError(
            "Kaggle CLI is not available. Install it in the backend venv with `pip install kaggle`, "
            "and configure kaggle.json credentials before using Kaggle cloud generation."
        )


def _copy_worker_template(src_dir: Path, dst_dir: Path):
    if not src_dir.exists():
        raise KaggleCloudError(f"Kaggle worker template directory not found: {src_dir}")
    shutil.copytree(src_dir, dst_dir)


def _copy_local_diffrhythm_repo(src_dir: Path, dst_dir: Path):
    if not src_dir.exists():
        raise KaggleCloudError(f"Local DiffRhythm repo not found for Kaggle bundle: {src_dir}")
    ignore = shutil.ignore_patterns(
        ".git",
        "__pycache__",
        "*.pyc",
        "*.pyo",
        ".pytest_cache",
        "output",
        "outputs",
        "venv",
        "venv-mt3",
        ".mypy_cache",
        ".idea",
        ".vscode",
    )
    shutil.copytree(src_dir, dst_dir / "DiffRhythm", ignore=ignore)


def _write_kernel_metadata(job_dir: Path, kernel_slug: str):
    dataset_sources = []
    dataset_slug = os.environ.get("VOCALIS_KAGGLE_DIFFRHYTHM_DATASET")
    if dataset_slug:
        dataset_sources.append(dataset_slug)
    title = kernel_slug.split("/", 1)[-1].replace("-", " ").strip() or "vocalisx kaggle worker"
    metadata = {
        "id": kernel_slug,
        "title": title[:50],
        "code_file": "vocalisx_kaggle_runner.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "dataset_sources": dataset_sources,
        "kernel_sources": [],
        "model_sources": [],
    }
    (job_dir / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _write_request_payload(
    job_dir: Path,
    *,
    prompt: str,
    lyrics_text: str,
    lyrics_lrc: str,
    audio_length_sec: int,
    demucs_model: str,
):
    inputs_dir = job_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "prompt": prompt,
        "lyrics_text": lyrics_text,
        "lyrics_lrc": lyrics_lrc,
        "audio_length_sec": int(audio_length_sec),
        "demucs_model": demucs_model,
        "diffrhythm_repo": os.environ.get("VOCALIS_KAGGLE_DIFFRHYTHM_REPO", "https://github.com/ASLP-lab/DiffRhythm.git"),
        "diffrhythm_ref": os.environ.get("VOCALIS_KAGGLE_DIFFRHYTHM_REF"),
        "setup_command": os.environ.get("VOCALIS_KAGGLE_SETUP_COMMAND"),
        "infer_relpath": os.environ.get("VOCALIS_KAGGLE_INFER_RELPATH", "infer/infer.py"),
        "python_bin": os.environ.get("VOCALIS_KAGGLE_PYTHON_BIN", "python"),
        "extra_pip_packages": os.environ.get("VOCALIS_KAGGLE_EXTRA_PIP_PACKAGES", ""),
        "diffrhythm_dataset_slug": os.environ.get("VOCALIS_KAGGLE_DIFFRHYTHM_DATASET"),
        "diffrhythm_dataset_subdir": os.environ.get("VOCALIS_KAGGLE_DIFFRHYTHM_DATASET_SUBDIR"),
    }
    (inputs_dir / "request.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _inject_request_payload_into_script(job_dir: Path, payload: dict):
    script_path = job_dir / "vocalisx_kaggle_runner.py"
    if not script_path.exists():
        raise KaggleCloudError(f"Kaggle worker script not found: {script_path}")
    request_b64 = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    text = script_path.read_text(encoding="utf-8")
    text = text.replace("__VOCALIS_REQUEST_B64__", request_b64)
    script_path.write_text(text, encoding="utf-8")


def _poll_kernel_status(kernel_slug: str, poll_interval_sec: int, timeout_sec: int):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        proc = _run_capture(["kaggle", "kernels", "status", kernel_slug], timeout_sec=120)
        output = f"{proc.stdout}\n{proc.stderr}".lower()
        if proc.returncode != 0:
            raise KaggleCloudError(f"Could not read Kaggle kernel status for {kernel_slug}.")
        if "complete" in output:
            return
        if "error" in output or "failed" in output or "cancel" in output:
            raise KaggleCloudError(f"Kaggle kernel run failed for {kernel_slug}.")
        time.sleep(max(5, poll_interval_sec))
    raise KaggleCloudError(f"Kaggle kernel did not finish within {timeout_sec} seconds.")


def _copy_artifact(src: Path, prefix: str, output_root: Path) -> Optional[str]:
    if not src.exists():
        return None
    dst = output_root / f"{uuid.uuid4().hex}_{prefix}{src.suffix}"
    shutil.copy2(src, dst)
    return str(dst.resolve())


def _find_downloaded_artifact(download_dir: Path, name: str) -> Optional[Path]:
    exact = list(download_dir.rglob(name))
    for path in exact:
        if path.is_file():
            return path
    return None


def run_kaggle_generation(
    *,
    prompt: str,
    lyrics_text: str,
    lyrics_lrc: str,
    output_root: Path,
    run_tag: str,
    kernel_slug: str,
    template_dir: Path,
    audio_length_sec: int,
    demucs_model: str,
    poll_interval_sec: int,
    timeout_sec: int,
    local_diffrhythm_dir: Optional[Path] = None,
) -> KaggleJobArtifacts:
    _require_cli()
    output_root.mkdir(parents=True, exist_ok=True)
    jobs_root = output_root / "kaggle_jobs"
    jobs_root.mkdir(parents=True, exist_ok=True)
    job_dir = jobs_root / run_tag
    if job_dir.exists():
        shutil.rmtree(job_dir)

    _copy_worker_template(template_dir, job_dir)
    if local_diffrhythm_dir and local_diffrhythm_dir.exists():
        _copy_local_diffrhythm_repo(local_diffrhythm_dir, job_dir)
    _write_kernel_metadata(job_dir, kernel_slug)
    payload = _write_request_payload(
        job_dir,
        prompt=prompt,
        lyrics_text=lyrics_text,
        lyrics_lrc=lyrics_lrc,
        audio_length_sec=audio_length_sec,
        demucs_model=demucs_model,
    )
    _inject_request_payload_into_script(job_dir, payload)

    push_proc = _run_capture(["kaggle", "kernels", "push", "-p", str(job_dir.resolve())], timeout_sec=900)
    if push_proc.returncode != 0:
        raise KaggleCloudError(f"Failed to push Kaggle kernel {kernel_slug}.")

    _poll_kernel_status(kernel_slug, poll_interval_sec=poll_interval_sec, timeout_sec=timeout_sec)

    download_dir = job_dir / "download"
    download_dir.mkdir(parents=True, exist_ok=True)
    output_proc = _run_capture(
        ["kaggle", "kernels", "output", kernel_slug, "-p", str(download_dir.resolve()), "-o"],
        timeout_sec=900,
    )
    artifact_root = download_dir / "artifacts"
    if not artifact_root.exists():
        nested = _find_downloaded_artifact(download_dir, "full_song.wav")
        if nested is not None:
            artifact_root = nested.parent
    if output_proc.returncode != 0 and not artifact_root.exists():
        raise KaggleCloudError(f"Failed to download Kaggle output for {kernel_slug}.")

    if not artifact_root.exists():
        raise KaggleCloudError("Kaggle output download did not contain an artifacts folder.")

    full_song = _copy_artifact(artifact_root / "full_song.wav", "kaggle_full_song", output_root)
    vocals = _copy_artifact(artifact_root / "vocals.wav", "kaggle_vocals", output_root)
    instrumental = _copy_artifact(artifact_root / "no_vocals.wav", "kaggle_no_vocals", output_root)

    if not full_song:
        raise KaggleCloudError("Kaggle run completed but full_song.wav was missing.")

    return KaggleJobArtifacts(
        full_song_wav=full_song,
        instrumental_wav=instrumental,
        vocals_wav=vocals,
    )
