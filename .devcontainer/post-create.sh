#!/usr/bin/env bash
# Codespace bootstrap: Python deps, browser engine, Xvfb, Octop plugins.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[octop] Installing uv + project dependencies..."
pip install -q uv
uv sync

echo "[octop] Installing Chromium (system deps included)..."
uv run python -m playwright install --with-deps chromium

echo "[octop] Installing Xvfb (lets the browser run headed inside a codespace)..."
sudo apt-get update -qq && sudo apt-get install -y -qq xvfb xauth

echo "[octop] Installing agent toolkits (browser-driver, github-scout)..."
uv run octop plugin install ./plugins/browser-driver --force
uv run octop plugin install ./plugins/github-scout --force

echo "[octop] Codespace ready."
echo "  Start the server:   uv run octop run"
echo "  Headed browser UI:  xvfb-run -a uv run octop run"
echo "  Verify toolkits:    uv run octop plugin list"
