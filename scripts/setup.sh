#!/usr/bin/env bash
# city-score 開発環境セットアップ
# Python 3.12 を想定。venv を作成し dev 依存をインストールする。
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"

if [ ! -d .venv ]; then
  echo "[setup] creating .venv"
  "$PYTHON" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "[setup] upgrading pip"
python -m pip install --upgrade pip >/dev/null

echo "[setup] installing city-score (editable, with dev extras)"
python -m pip install -e ".[dev]"

echo "[setup] running tests"
python -m pytest

echo "[setup] done. activate with: source .venv/bin/activate"
