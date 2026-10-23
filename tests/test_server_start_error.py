"""A stdio server that dies on start must give a one-line error plus its stderr tail, not the
async `McpError: Connection closed` traceback. Real subprocesses, but tiny local scripts only:
no network, no LLM."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentgauge.cli import app
from agentgauge.client import (
    STDERR_TAIL_LINE_CHARS,
    STDERR_TAIL_LINES,
    ServerStartError,
    connect_stdio,
)

CRASHING_SERVER = """\
import sys
print("startup-marker: cannot import widget_backend (ModuleNotFoundError)", file=sys.stderr)
raise RuntimeError("server cannot start")
"""

NOISY_CRASHING_SERVER = """\
import sys
for i in range(200):
    print(f"noise line {i} " + "x" * 1000, file=sys.stderr)
print("final-line: the actual cause", file=sys.stderr)
sys.exit(3)
"""

SILENT_CRASHING_SERVER = "import sys\nsys.exit(1)\n"


def _server(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "server.py"
    path.write_text(body, encoding="utf-8")
    return path


class TestConnectStdioStartFailure:
    async def test_raises_server_start_error_with_stderr_tail(self, tmp_path: Path) -> None:
        script = _server(tmp_path, CRASHING_SERVER)
        with pytest.raises(ServerStartError) as info:
            await connect_stdio(sys.executable, [str(script)])
        assert "startup-marker" in info.value.stderr_tail
        assert "RuntimeError: server cannot start" in info.value.stderr_tail
        assert "\n" not in str(info.value)  # the message itself is one line

    async def test_stderr_tail_is_bounded(self, tmp_path: Path) -> None:
        script = _server(tmp_path, NOISY_CRASHING_SERVER)
        with pytest.raises(ServerStartError) as info:
            await connect_stdio(sys.executable, [str(script)])
        lines = info.value.stderr_tail.splitlines()
        assert len(lines) <= STDERR_TAIL_LINES
        assert all(len(ln) <= STDERR_TAIL_LINE_CHARS + 3 for ln in lines)
        assert "final-line: the actual cause" in lines[-1]  # the tail, not the head
        assert "noise line 0 " not in info.value.stderr_tail

    async def test_missing_script_is_also_a_start_error(self, tmp_path: Path) -> None:
        with pytest.raises(ServerStartError) as info:
            await connect_stdio(sys.executable, [str(tmp_path / "nope.py")])
        assert "nope.py" in str(info.value)


class TestCliCrashOutput:
    def _run(self, tmp_path: Path, body: str | None) -> object:
        target = str(_server(tmp_path, body)) if body is not None else str(tmp_path / "nope.py")
        return CliRunner().invoke(app, ["lint", target])

    def test_crash_prints_one_line_error_and_stderr_tail(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, CRASHING_SERVER)
        out = result.output  # type: ignore[attr-defined]
        assert result.exit_code == 2, out  # type: ignore[attr-defined]
        first = out.splitlines()[0]
        assert first.startswith("Error: server failed to start:")
        assert "server.py" in first
        assert "startup-marker: cannot import widget_backend" in out
        assert "RuntimeError: server cannot start" in out  # the server's own traceback tail
        assert "McpError" not in out
        assert "anyio" not in out
        assert "cancel scope" not in out

    def test_no_traceback_in_user_output(self, tmp_path: Path) -> None:
        out = self._run(tmp_path, CRASHING_SERVER).output  # type: ignore[attr-defined]
        assert "Traceback" not in out
        assert "File " not in out.split("Server stderr")[0]  # nothing before the stderr block

    def test_silent_crash_says_so(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, SILENT_CRASHING_SERVER)
        out = result.output  # type: ignore[attr-defined]
        assert result.exit_code == 2  # type: ignore[attr-defined]
        assert "The server wrote nothing to stderr." in out
        assert "Traceback" not in out

    def test_missing_script_is_one_line_error_not_a_traceback(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, None)
        out = result.output  # type: ignore[attr-defined]
        assert result.exit_code == 2, out  # type: ignore[attr-defined]
        assert out.splitlines()[0].startswith("Error: server failed to start:")
        assert "nope.py" in out
        assert "McpError" not in out
        assert "Traceback" not in out
