#!/usr/bin/env python3
"""Launcher that routes build_fixed_fixtures.py's generator/judge Provider calls to the
remote agentgauge-agent Cloud Run proxy (port 11435) instead of local Ollama (11434).

Same rationale as run_predictive_validity_via_gcp.py: local Ollama on this machine is
contended by an unrelated process and auto-respawns after being killed, so redirecting
via monkeypatch is the stable fix. qwen3:8b (generator), llama3.1:8b (judge), and
gemma2:9b are all already pulled onto the remote agentgauge-agent service.

Prerequisite: `gcloud run services proxy agentgauge-agent --port=11435 ...` already running.

Usage:
    python scripts/run_build_fixed_fixtures_via_gcp.py <fixture_name> [<fixture_name> ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.providers import OllamaProvider

OllamaProvider.BASE_URL = "http://localhost:11435"

from build_fixed_fixtures import main  # noqa: E402 -- must patch BASE_URL first

if __name__ == "__main__":
    main()
