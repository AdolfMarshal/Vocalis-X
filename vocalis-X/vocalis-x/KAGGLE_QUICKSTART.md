# Kaggle Quickstart

This setup keeps the frontend unchanged and makes Kaggle the primary DiffRhythm
GPU path, with your local GPU as fallback.

## What the backend now does
- If `VOCALIS_KAGGLE_KERNEL` is set, `diffrhythm_pipeline.py` tries Kaggle first.
- It packages a Kaggle worker bundle from `kaggle_worker/`.
- It pushes the kernel with the Kaggle CLI.
- It polls Kaggle until the run completes.
- It downloads:
  - `artifacts/full_song.wav`
  - `artifacts/vocals.wav`
  - `artifacts/no_vocals.wav`
- If Kaggle fails, backend falls back to local DiffRhythm.

## One-time local setup
1. Install Kaggle CLI in the backend venv:
   - `pip install kaggle`
2. Put your Kaggle API credentials in:
   - `%USERPROFILE%\\.kaggle\\kaggle.json`
3. Ensure file permissions are valid for Kaggle CLI.

## Required env vars
- `VOCALIS_KAGGLE_KERNEL=username/kernel-slug`

Optional:
- `VOCALIS_KAGGLE_TEMPLATE_DIR=C:/Users/adolf/vocalis-x/kaggle_worker`
- `VOCALIS_KAGGLE_POLL_INTERVAL_SEC=20`
- `VOCALIS_KAGGLE_DIFFRHYTHM_REPO=https://github.com/ASLP-lab/DiffRhythm.git`
- `VOCALIS_KAGGLE_DIFFRHYTHM_REF=main`
- `VOCALIS_KAGGLE_DIFFRHYTHM_DATASET=username/dataset-slug`
- `VOCALIS_KAGGLE_DIFFRHYTHM_DATASET_SUBDIR=optional-subfolder-inside-dataset`
- `VOCALIS_KAGGLE_SETUP_COMMAND=` custom setup command if you need one
- `VOCALIS_KAGGLE_INFER_RELPATH=infer/infer.py`
- `VOCALIS_KAGGLE_EXTRA_PIP_PACKAGES=` extra packages for the Kaggle worker

## Important Kaggle note
Best option: upload your DiffRhythm code + pretrained assets as a Kaggle
Dataset and set `VOCALIS_KAGGLE_DIFFRHYTHM_DATASET`. The worker will then load
the repo from `/kaggle/input/...` and will not need GitHub clone access.

Your local `C:\Users\adolf\DiffRhythm` is roughly 8.24 GB, mostly in
`pretrained/`, so the dataset must include both code and weights if you want
fully offline Kaggle execution.

## Recommended demo plan
1. Set `VOCALIS_KAGGLE_KERNEL`.
2. Start backend normally.
3. Run one practice generation end-to-end.
4. Keep pre-generated Supabase songs ready.
5. If Kaggle is slow or fails, pivot to saved songs immediately.

## Where to customize the remote worker
- Worker script:
  - `C:\\Users\\adolf\\vocalis-x\\kaggle_worker\\vocalisx_kaggle_runner.py`
- Local bridge:
  - `C:\\Users\\adolf\\vocalis-x\\kaggle_cloud.py`
