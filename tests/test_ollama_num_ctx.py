from __future__ import annotations

import json

import httpx
import pytest
import respx

from agentgauge.providers import (
    NUM_CTX_FLOOR,
    TRUNCATION_MARGIN,
    Message,
    OllamaProvider,
    OllamaTruncationError,
    check_truncation,
    compute_num_ctx,
    estimate_prompt_tokens,
)

URL = f"{OllamaProvider.BASE_URL}/api/chat"


def _msg(n_bytes: int) -> list[Message]:
    return [Message(role="user", content="a" * n_bytes)]


def _reply(prompt_eval_count: int | None, content: str = "ok") -> httpx.Response:
    body: dict = {"message": {"content": content}}
    if prompt_eval_count is not None:
        body["prompt_eval_count"] = prompt_eval_count
    return httpx.Response(200, json=body)


# -- estimator / num_ctx computation ------------------------------------------------------


def test_estimate_is_monotonic_and_covers_all_messages() -> None:
    one = estimate_prompt_tokens(_msg(300))
    two = estimate_prompt_tokens(_msg(300) + _msg(300))
    assert two > one > 100  # 300 bytes / 3 = 100 tokens plus overheads


def test_estimate_counts_bytes_not_characters() -> None:
    ascii_tokens = estimate_prompt_tokens([Message("user", "a" * 30)])
    cjk_tokens = estimate_prompt_tokens([Message("user", "漢" * 30)])  # 3 bytes per char
    assert cjk_tokens > ascii_tokens


def test_small_prompt_uses_floor() -> None:
    assert compute_num_ctx(_msg(10)) == NUM_CTX_FLOOR == 4096


def test_large_prompt_grows_and_is_at_least_formula() -> None:
    msgs = _msg(60_000)  # ~20k estimated tokens
    ctx = compute_num_ctx(msgs)
    assert ctx >= estimate_prompt_tokens(msgs) + 1024
    assert ctx == 32768  # next power of two, not an exact per-prompt value


def test_boundary_of_floor() -> None:
    # Find the first prompt size whose estimate + 1024 exceeds the 4096 floor.
    n = 1
    while estimate_prompt_tokens(_msg(n)) + 1024 <= 4096:
        n += 1
    assert estimate_prompt_tokens(_msg(n)) + 1024 == 4097
    assert compute_num_ctx(_msg(n - 1)) == 4096  # exactly at the floor: unchanged
    assert compute_num_ctx(_msg(n)) == 8192  # one token over: next bucket


# -- truncation detection -----------------------------------------------------------------


def test_check_truncation_passes_below_limit() -> None:
    check_truncation(4096 - TRUNCATION_MARGIN - 1, 4096, "m")
    check_truncation(None, 4096, "m")  # missing count is not checkable
    check_truncation(5, 4096, "m")  # far below: may be a KV-cache hit, never an error


@pytest.mark.parametrize("count", [4096 - TRUNCATION_MARGIN, 4096, 5000])
def test_check_truncation_raises_at_or_above_limit(count: int) -> None:
    with pytest.raises(OllamaTruncationError) as exc:
        check_truncation(count, 4096, "llama3.1:8b")
    text = str(exc.value)
    assert "llama3.1:8b" in text and "num_ctx=4096" in text
    assert "Raise num_ctx" in text and "shorten" in text


def test_truncation_error_is_runtime_error() -> None:
    assert issubclass(OllamaTruncationError, RuntimeError)


# -- provider wiring (HTTP mocked, no network) --------------------------------------------


@respx.mock
async def test_small_prompt_behaviour_unchanged_and_num_ctx_sent() -> None:
    route = respx.post(URL).mock(return_value=_reply(50, "7"))
    out = await OllamaProvider("llama3.1:8b").chat([Message("user", "hi")], seed=3)
    assert out == "7"
    payload = json.loads(route.calls[0].request.content)
    assert payload["options"] == {"seed": 3, "num_ctx": 4096}
    assert payload["stream"] is False
    assert payload["messages"] == [{"role": "user", "content": "hi"}]


@respx.mock
async def test_large_prompt_sends_larger_num_ctx() -> None:
    route = respx.post(URL).mock(return_value=_reply(20_000))
    await OllamaProvider().chat(_msg(60_000))
    assert json.loads(route.calls[0].request.content)["options"]["num_ctx"] == 32768


@respx.mock
async def test_response_at_limit_raises() -> None:
    respx.post(URL).mock(return_value=_reply(4096))
    with pytest.raises(OllamaTruncationError):
        await OllamaProvider().chat(_msg(10))


@respx.mock
async def test_response_above_limit_raises() -> None:
    respx.post(URL).mock(return_value=_reply(9000))
    with pytest.raises(OllamaTruncationError):
        await OllamaProvider().chat(_msg(10))


@respx.mock
async def test_response_below_limit_and_cached_prefix_ok() -> None:
    respx.post(URL).mock(side_effect=[_reply(3000), _reply(12), _reply(None)])
    p = OllamaProvider()
    assert await p.chat(_msg(10)) == "ok"
    assert await p.chat(_msg(10)) == "ok"  # prompt_eval_count=12: cached prefix, not truncation
    assert await p.chat(_msg(10)) == "ok"  # count absent
