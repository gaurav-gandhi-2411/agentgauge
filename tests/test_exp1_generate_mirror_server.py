from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from exp1_generate_mirror_server import (  # noqa: E402
    assert_docstrings_verbatim_in_source,
    generate_server_source,
)

from agentgauge.exp1_mirror import MirrorParam, MirrorTool, ServerMirror  # noqa: E402


def _make_mirror() -> ServerMirror:
    return ServerMirror(
        server_id="test-server",
        source_repo="example/test-server",
        language="python",
        stars=0,
        stratum="near_empty",
        notes="test fixture",
        tools=[
            MirrorTool(
                name="create",
                docstring="Create a new wiki page.",
                params=[MirrorParam(name="title", annotation="str")],
                source_hash="abc123",
            ),
            MirrorTool(
                name="create_knowledge_base",
                docstring="Create a new knowledge base.",
                params=[MirrorParam(name="name", annotation="str", default="'default'")],
                source_hash="def456",
            ),
        ],
    )


def test_generate_server_source_is_valid_python() -> None:
    source = generate_server_source(_make_mirror())
    ast.parse(source)  # must not raise


def test_generate_server_source_contains_verbatim_docstrings() -> None:
    mirror = _make_mirror()
    source = generate_server_source(mirror)
    assert "Create a new wiki page." in source
    assert "Create a new knowledge base." in source


def test_generate_server_source_includes_all_tool_names() -> None:
    source = generate_server_source(_make_mirror())
    assert '"create"' in source
    assert '"create_knowledge_base"' in source


def test_generate_server_source_required_params_exclude_defaulted() -> None:
    source = generate_server_source(_make_mirror())
    # "title" has no default -> required; "name" has a default -> not required.
    assert '"required": [\n            "title"\n        ]' in source


def test_assert_docstrings_verbatim_passes_on_generated_source() -> None:
    mirror = _make_mirror()
    source = generate_server_source(mirror)
    assert assert_docstrings_verbatim_in_source(mirror, source) == []


def test_assert_docstrings_verbatim_catches_mutation() -> None:
    mirror = _make_mirror()
    source = generate_server_source(mirror)
    mutated = source.replace("Create a new wiki page.", "A DIFFERENT description entirely.")
    violations = assert_docstrings_verbatim_in_source(mirror, mutated)
    assert violations != []
