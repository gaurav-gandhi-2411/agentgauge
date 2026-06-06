from __future__ import annotations

import pytest

from agentgauge._json import extract_json_object  # noqa: E402

# ── bare JSON ─────────────────────────────────────────────────────────────────


def test_bare_json_parses_correctly() -> None:
    result, failed = extract_json_object('{"key": "value"}')
    assert result == {"key": "value"}
    assert failed is False


def test_bare_json_with_whitespace() -> None:
    result, failed = extract_json_object('  {"a": 1}  ')
    assert result == {"a": 1}
    assert failed is False


def test_bare_json_nested() -> None:
    result, failed = extract_json_object('{"outer": {"inner": 42}}')
    assert result == {"outer": {"inner": 42}}
    assert failed is False


# ── fenced JSON ───────────────────────────────────────────────────────────────


def test_fenced_json_json_tag() -> None:
    resp = '```json\n{"message": "hello"}\n```'
    result, failed = extract_json_object(resp)
    assert result == {"message": "hello"}
    assert failed is False


def test_fenced_json_no_tag() -> None:
    resp = '```\n{"x": 1}\n```'
    result, failed = extract_json_object(resp)
    assert result == {"x": 1}
    assert failed is False


def test_fenced_json_uppercase_tag() -> None:
    resp = '```JSON\n{"k": "v"}\n```'
    result, failed = extract_json_object(resp)
    assert result == {"k": "v"}
    assert failed is False


def test_fenced_json_no_trailing_newline() -> None:
    resp = '```json\n{"a": true}```'
    result, failed = extract_json_object(resp)
    assert result == {"a": True}
    assert failed is False


# ── JSON with preamble ────────────────────────────────────────────────────────


def test_json_with_preamble() -> None:
    resp = 'Sure! Here are the arguments: {"tool": "echo", "message": "hi"}'
    result, failed = extract_json_object(resp)
    assert result == {"tool": "echo", "message": "hi"}
    assert failed is False


def test_json_with_trailing_prose() -> None:
    resp = '{"value": 42} (I used 42 because it is a good default)'
    result, failed = extract_json_object(resp)
    assert result == {"value": 42}
    assert failed is False


def test_json_with_preamble_and_fence() -> None:
    resp = 'Here is the JSON:\n```json\n{"n": 7}\n```'
    result, failed = extract_json_object(resp)
    assert result == {"n": 7}
    assert failed is False


# ── junk / unparseable ────────────────────────────────────────────────────────


def test_junk_returns_empty_and_flags_failure() -> None:
    result, failed = extract_json_object("not json at all")
    assert result == {}
    assert failed is True


def test_empty_string_returns_empty_and_flags_failure() -> None:
    result, failed = extract_json_object("")
    assert result == {}
    assert failed is True


def test_list_response_returns_empty_and_flags_failure() -> None:
    # JSON arrays are not objects; should flag as failed
    result, failed = extract_json_object("[1, 2, 3]")
    assert result == {}
    assert failed is True


def test_scalar_response_returns_empty_and_flags_failure() -> None:
    result, failed = extract_json_object('"just a string"')
    assert result == {}
    assert failed is True


def test_malformed_braces_returns_empty_and_flags_failure() -> None:
    result, failed = extract_json_object("{key: value}")  # not valid JSON
    assert result == {}
    assert failed is True


# ── parse_failed is True only when extraction genuinely fails ─────────────────


@pytest.mark.parametrize(
    "resp",
    [
        '{"a": 1}',
        '```json\n{"b": 2}\n```',
        'preamble {"c": 3}',
    ],
)
def test_valid_inputs_never_flag_parse_failed(resp: str) -> None:
    _, failed = extract_json_object(resp)
    assert failed is False


@pytest.mark.parametrize(
    "resp",
    [
        "no json here",
        "",
        "42",
        "[1,2]",
    ],
)
def test_invalid_inputs_always_flag_parse_failed(resp: str) -> None:
    _, failed = extract_json_object(resp)
    assert failed is True
