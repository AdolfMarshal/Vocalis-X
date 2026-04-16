## Vocalis-X Kaggle Worker

This folder is a template. The backend copies it into a temporary Kaggle kernel
bundle, injects request files into `inputs/`, generates `kernel-metadata.json`,
pushes the kernel with the Kaggle CLI, waits for completion, and downloads
`artifacts/`.

Expected artifacts:
- `artifacts/full_song.wav`
- `artifacts/vocals.wav`
- `artifacts/no_vocals.wav`
- `artifacts/result.json`

Local backend env vars used by the Kaggle bridge:
- `VOCALIS_KAGGLE_KERNEL` = `username/kernel-slug`
- `VOCALIS_KAGGLE_TEMPLATE_DIR` = optional override for this template folder
- `VOCALIS_KAGGLE_POLL_INTERVAL_SEC` = status poll interval
- `VOCALIS_KAGGLE_DIFFRHYTHM_REPO` = DiffRhythm git repo URL
- `VOCALIS_KAGGLE_DIFFRHYTHM_REF` = optional branch/tag/commit
- `VOCALIS_KAGGLE_SETUP_COMMAND` = optional custom setup command run inside repo
- `VOCALIS_KAGGLE_INFER_RELPATH` = DiffRhythm infer script path
- `VOCALIS_KAGGLE_EXTRA_PIP_PACKAGES` = optional extra pip packages

The worker script expects internet access to clone/install dependencies unless
you modify it to rely on Kaggle datasets or cached notebook assets.
