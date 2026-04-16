## Vocalis-X MusicGen Kaggle Worker

This folder is a template for MusicGen-only Kaggle generation.

Expected artifacts:
- `artifacts/musicgen_output.wav`
- `artifacts/result.json`

Backend env vars used by the MusicGen Kaggle bridge:
- `VOCALIS_MUSICGEN_KAGGLE_KERNEL` = `username/kernel-slug`
- `VOCALIS_MUSICGEN_KAGGLE_TEMPLATE_DIR` = optional override for this template folder
- `VOCALIS_MUSICGEN_KAGGLE_POLL_INTERVAL_SEC` = status poll interval
- `VOCALIS_MUSICGEN_KAGGLE_TIMEOUT_SEC` = overall timeout in seconds
- `VOCALIS_MUSICGEN_KAGGLE_EXTRA_PIP_PACKAGES` = optional extra pip packages

This worker installs `audiocraft` on Kaggle and generates a single instrumental
clip from the provided prompt and MusicGen settings.
