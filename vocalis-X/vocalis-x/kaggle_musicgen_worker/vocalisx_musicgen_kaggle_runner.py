import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
import torch


ROOT = Path(__file__).resolve().parent
WORK_ROOT = Path("/kaggle/working/vocalisx_musicgen_job")
INPUTS = WORK_ROOT / "inputs"
ARTIFACTS = WORK_ROOT / "artifacts"
INPUTS.mkdir(parents=True, exist_ok=True)
ARTIFACTS.mkdir(parents=True, exist_ok=True)
REQUEST_JSON_B64 = "__VOCALIS_REQUEST_B64__"
REQUEST_JSON_SENTINEL = "__VOCALIS_REQUEST_SENTINEL__"


def run(cmd, cwd=None):
    print(f"[vocalisx_musicgen_runner] running: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def clean_working_dir():
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


def install_requirements(extra_pip_packages: str):
    # Prefer the Hugging Face MusicGen stack here because it is more reliable on
    # Kaggle's current Python image than installing audiocraft on the fly.
    run(
        [
            "python",
            "-m",
            "pip",
            "install",
            "transformers",
            "accelerate",
            "sentencepiece",
            "safetensors",
            "soundfile",
            "numpy",
        ]
    )
    if extra_pip_packages.strip():
        run(["python", "-m", "pip", "install", *extra_pip_packages.split()])


def load_request():
    src_inputs = ROOT / "inputs"
    if src_inputs.exists():
        shutil.copytree(src_inputs, INPUTS, dirs_exist_ok=True)
    request_file = INPUTS / "request.json"
    if request_file.exists():
        return json.loads(request_file.read_text(encoding="utf-8"))
    if REQUEST_JSON_B64 and REQUEST_JSON_B64 != REQUEST_JSON_SENTINEL:
        payload = json.loads(base64.b64decode(REQUEST_JSON_B64.encode("ascii")).decode("utf-8"))
        request_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    raise FileNotFoundError(f"Missing request payload at {request_file}")


def main():
    clean_working_dir()
    INPUTS.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    request = load_request()
    install_requirements(request.get("extra_pip_packages", ""))
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    model_name = request.get("model_name") or "facebook/musicgen-medium"
    duration_sec = int(request.get("duration_sec") or 30)
    temperature = float(request.get("temperature") or 0.9)
    top_k = int(request.get("top_k") or 200)
    prompt = request["prompt"]
    # Kaggle's current GPU image is failing for this MusicGen runtime with
    # "no kernel image is available for execution on the device". Make CPU the
    # primary path here so the cloud attempt is stable, then let the backend's
    # existing local fallback handle any remaining failures.
    requested_device = "cpu"
    print(f"[vocalisx_musicgen_runner] requested_device={requested_device} model={model_name} duration={duration_sec}s")

    processor = AutoProcessor.from_pretrained(model_name)
    model = MusicgenForConditionalGeneration.from_pretrained(model_name)
    inputs = processor(text=[prompt], padding=True, return_tensors="pt")

    # MusicGen uses roughly 50 decoder tokens per second of audio.
    max_new_tokens = max(64, int(duration_sec * 50))
    active_device = requested_device
    try:
        model = model.to(active_device)
        moved_inputs = {key: value.to(active_device) for key, value in inputs.items()}
        with torch.no_grad():
            generated = model.generate(
                **moved_inputs,
                do_sample=True,
                temperature=temperature,
                top_k=top_k,
                max_new_tokens=max_new_tokens,
            )
    except Exception as exc:
        if active_device != "cuda":
            raise
        print(f"[vocalisx_musicgen_runner] cuda_failed={exc}; retrying on cpu")
        active_device = "cpu"
        if torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
        model = model.to(active_device)
        moved_inputs = {key: value.to(active_device) for key, value in inputs.items()}
        with torch.no_grad():
            generated = model.generate(
                **moved_inputs,
                do_sample=True,
                temperature=temperature,
                top_k=top_k,
                max_new_tokens=max_new_tokens,
            )

    generated = generated[0].detach().cpu().numpy()
    sampling_rate = int(model.config.audio_encoder.sampling_rate)

    peak = np.max(np.abs(generated)) if generated.size else 0.0
    if peak > 1.0:
        generated = generated / peak

    out_wav = ARTIFACTS / "musicgen_output.wav"
    if generated.ndim == 3:
        generated = generated[0]
    if generated.ndim == 2:
        audio_to_write = generated.T
    else:
        audio_to_write = generated
    sf.write(out_wav, audio_to_write, sampling_rate)
    (ARTIFACTS / "result.json").write_text(
        json.dumps(
            {
                "audio": str(out_wav.resolve()),
                "model_name": model_name,
                "duration_sec": duration_sec,
                "temperature": temperature,
                "top_k": top_k,
                "backend": "transformers_musicgen",
                "device": active_device,
                "requested_device": requested_device,
                "sampling_rate": sampling_rate,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    clean_working_dir()


if __name__ == "__main__":
    main()
