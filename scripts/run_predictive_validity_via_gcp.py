#!/usr/bin/env python3
"""Launcher that routes predictive_validity_study.py's OllamaProvider calls to the
remote agentgauge-agent Cloud Run proxy (port 11435) instead of local Ollama (11434).

Local Ollama on this machine is contended by an unrelated process and auto-respawns
after being killed, so redirecting via monkeypatch (rather than fighting the respawn
or editing the already-verified predictive_validity_study.py) is the stable fix.

Prerequisite: `gcloud run services proxy agentgauge-agent --port=11435 --region=us-central1
--project=expense-tracker-498014` must already be running, and both `gemma2:9b` and
`llama3.1:8b` must already be pulled onto that remote service.

Usage:
    python scripts/run_predictive_validity_via_gcp.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agentgauge.providers import OllamaProvider

OllamaProvider.BASE_URL = "http://localhost:11435"

from predictive_validity_study import main  # noqa: E402 -- must patch BASE_URL first

if __name__ == "__main__":
    asyncio.run(main())
