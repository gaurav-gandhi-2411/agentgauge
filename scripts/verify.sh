#!/usr/bin/env bash
# AgentGauge verification gate — exit non-zero on any failure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "=== AgentGauge verify.sh ==="
echo ""

# ── 1. Install (idempotent) ─────────────────────────────────────────────────
if command -v uv &>/dev/null; then
    echo "[1/4] Installing with uv..."
    uv sync --extra dev
    RUNNER="uv run"
else
    echo "[1/4] uv not found — falling back to pip install..."
    pip install -e ".[dev]" -q
    RUNNER=""
fi

# ── 2. Lint ─────────────────────────────────────────────────────────────────
echo ""
echo "[2/4] Ruff lint..."
$RUNNER ruff check agentgauge/ tests/
echo "[2/4] Ruff format check..."
$RUNNER ruff format --check agentgauge/ tests/

# ── 3. Type check ───────────────────────────────────────────────────────────
echo ""
echo "[3/4] Mypy..."
$RUNNER mypy agentgauge/ --ignore-missing-imports || true   # non-blocking until strict is on

# ── 4. Tests ─────────────────────────────────────────────────────────────────
echo ""
echo "[4/4] pytest..."
$RUNNER pytest tests/ -v

echo ""
echo "=== verify.sh PASSED ==="
