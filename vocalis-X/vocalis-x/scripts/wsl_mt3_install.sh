#!/usr/bin/env bash
set -euo pipefail

MT3_REPO="${HOME}/mt3-work/mt3"
MT3_VENV="${HOME}/mt3-venv"
PY311="${HOME}/.pyenv/versions/3.11.11/bin/python"

if [[ ! -x "${PY311}" ]]; then
  echo "Missing Python 3.11.11 at ${PY311}" >&2
  exit 1
fi

mkdir -p "${HOME}/mt3-work"
if [[ ! -d "${MT3_REPO}" ]]; then
  git clone https://github.com/magenta/mt3.git "${MT3_REPO}"
fi

if [[ ! -d "${MT3_VENV}" ]]; then
  "${PY311}" -m venv "${MT3_VENV}"
fi
source "${MT3_VENV}/bin/activate"

python -m pip install -U pip setuptools wheel

# MT3 setup.py currently pins flax HEAD, which conflicts with t5x/optax HEAD.
# Remove that one requirement and let t5x resolve a compatible stack.
cp "${MT3_REPO}/setup.py" "${MT3_REPO}/setup.py.bak"
grep -v "flax @ git+https://github.com/google/flax#egg=flax" "${MT3_REPO}/setup.py.bak" > "${MT3_REPO}/setup.py"

python -m pip install -e "${MT3_REPO}"
python -m pip show mt3 || true
python -c "import mt3; print('mt3_import_ok')"
