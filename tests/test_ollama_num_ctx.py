from __future__ import annotations

import json

import httpx
import pytest
import respx

from agentgauge.providers import (
    NUM_CTX_FLOOR,
    OUTPUT_RESERVE_TOKENS,
    TRUNCATION_MARGIN,
    Message,
    OllamaProvider,
    OllamaTruncationError,
    check_truncation,
    compute_num_ctx,
    estimate_prompt_tokens,
    lower_bound_prompt_tokens,
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


# -- context-shift signature (measured on Ollama 0.40.3: truncated count ~ num_ctx/2 + 2) -----

# Real numbers: the 5307-token google_workspace selection prompt (about 26.5k utf-8 bytes,
# so L = ceil(bytes/6) ~ 4400) reported 2050 at num_ctx=4096 and 5325 at 8192.
_L_BIG = 4400


@pytest.mark.parametrize(
    ("count", "num_ctx"),
    [(2050, 4096), (1502, 3000), (1026, 2048), (2048 - 8, 4096), (2048 + 8, 4096)],
)
def test_context_shift_signature_raises(count: int, num_ctx: int) -> None:
    with pytest.raises(OllamaTruncationError) as exc:
        check_truncation(count, num_ctx, "llama3.1:8b", _L_BIG)
    assert f"num_ctx={num_ctx}" in str(exc.value) and "shorten" in str(exc.value)


def test_untruncated_count_with_big_prompt_passes() -> None:
    check_truncation(5325, 8192, "m", _L_BIG)  # measured: no truncation at 8192


def test_cached_prefix_low_count_does_not_raise() -> None:
    # Far below L but nowhere near num_ctx/2 (slack is 62 tokens here): KV-cache reuse.
    for count in (12, 300, 1200, 1900, 2200, 3500):
        check_truncation(count, 4096, "m", _L_BIG)


def test_shift_signature_needs_count_below_l() -> None:
    check_truncation(2050, 4096, "m", 2050)  # count == L: L is a lower bound, so a real count
    check_truncation(2050, 4096, "m", 2000)
    with pytest.raises(OllamaTruncationError):
        check_truncation(2050, 4096, "m", 2051)  # count < L: tokens were dropped


def test_shift_signature_skipped_without_lower_bound() -> None:
    check_truncation(2050, 4096, "m")  # old call shape: only the window-filled check


def test_old_boundary_still_raises_with_lower_bound() -> None:
    with pytest.raises(OllamaTruncationError):
        check_truncation(4096 - TRUNCATION_MARGIN, 4096, "m", _L_BIG)
    check_truncation(4096 - TRUNCATION_MARGIN - 1, 4096, "m", 100)


def test_lower_bound_is_below_estimate_and_scales_with_bytes() -> None:
    msgs = _msg(6000)
    assert lower_bound_prompt_tokens(msgs) < estimate_prompt_tokens(msgs)
    assert lower_bound_prompt_tokens(msgs) >= 1000


@respx.mock
async def test_small_prompt_with_count_near_half_window_unaffected() -> None:
    # A tiny prompt has a tiny L, so a count near num_ctx/2 cannot look like a shift.
    respx.post(URL).mock(return_value=_reply(2050))
    assert await OllamaProvider().chat([Message("user", "hi")]) == "ok"


# -- clamp to the model's maximum context (/api/show) ----------------------------------------
# Audit 2026-10-18: gemma2:9b (max 8192) was asked for num_ctx=32768, ran at 8192, reported
# prompt_eval_count 4099 (= 8192/2 + 3, context shift) and the guard keyed to 32768 stayed quiet.

SHOW_URL = f"{OllamaProvider.BASE_URL}/api/show"


def _show(context_length: int | None, arch: str = "gemma2") -> httpx.Response:
    info: dict = {"general.architecture": arch}
    if context_length is not None:
        info[f"{arch}.context_length"] = context_length
    return httpx.Response(200, json={"model_info": info})


@respx.mock
async def test_prompt_larger_than_model_max_raises_before_chat() -> None:
    respx.post(SHOW_URL).mock(return_value=_show(8192))
    chat = respx.post(URL).mock(return_value=_reply(100))
    with pytest.raises(OllamaTruncationError) as exc:
        await OllamaProvider("gemma2:9b").chat(_msg(60_000))  # lower bound ~10k > 8192
    text = str(exc.value)
    assert "8192" in text and "gemma2:9b" in text and "Shorten" in text
    assert "lower bound" in text
    assert chat.call_count == 0


@respx.mock
async def test_prompt_that_fits_is_sent_with_num_ctx_clamped_to_model_max() -> None:
    respx.post(SHOW_URL).mock(return_value=_show(6000))
    chat = respx.post(URL).mock(return_value=_reply(4000))
    # ~4.0k estimated tokens + 1024 headroom fits 6000, but the power-of-two bucket is 8192.
    assert compute_num_ctx(_msg(12_000)) == 8192
    await OllamaProvider("gemma2:9b").chat(_msg(12_000))
    assert json.loads(chat.calls[0].request.content)["options"]["num_ctx"] == 6000


@respx.mock
async def test_fitting_prompt_unchanged_when_model_max_is_large() -> None:
    respx.post(SHOW_URL).mock(return_value=_show(131072, "llama"))
    chat = respx.post(URL).mock(return_value=_reply(20_000))
    await OllamaProvider().chat(_msg(60_000))
    assert json.loads(chat.calls[0].request.content)["options"]["num_ctx"] == 32768


def test_context_shift_detected_at_the_clamped_window() -> None:
    # Requested 32768, effective 8192: count 4099 == 8192 // 2 + 3. Keyed to 32768 the
    # half-window is 16384 and nothing fires.
    check_truncation(4099, 32768, "gemma2:9b", 4600)
    with pytest.raises(OllamaTruncationError):
        check_truncation(4099, 8192, "gemma2:9b", 4600)


# google_workspace on gemma2:9b: 26,451 bytes = ~7,029 real tokens. The conservative upper
# estimate (3 bytes/token, 8,859) + 1024 exceeds 8192, but the prompt really fits.
_GW_BYTES = 26_451


@respx.mock
async def test_gw_sized_prompt_is_sent_clamped_and_passes_when_it_fits() -> None:
    assert estimate_prompt_tokens(_msg(_GW_BYTES)) + 1024 > 8192
    assert lower_bound_prompt_tokens(_msg(_GW_BYTES)) + 256 < 8192
    respx.post(SHOW_URL).mock(return_value=_show(8192))
    chat = respx.post(URL).mock(return_value=_reply(7029, "tool"))
    assert await OllamaProvider("gemma2:9b").chat(_msg(_GW_BYTES)) == "tool"
    assert json.loads(chat.calls[0].request.content)["options"]["num_ctx"] == 8192


@respx.mock
async def test_gw_sized_prompt_context_shift_at_effective_window_raises_post_call() -> None:
    # Requested 16384, effective 8192; count 4099 == 8192 // 2 + 3 (context shift). Keyed to
    # 16384 (half-window 8192) this was silent.
    respx.post(SHOW_URL).mock(return_value=_show(8192))
    chat = respx.post(URL).mock(return_value=_reply(4099))
    with pytest.raises(OllamaTruncationError) as exc:
        await OllamaProvider("gemma2:9b").chat(_msg(_GW_BYTES))
    assert "num_ctx=8192" in str(exc.value)
    assert chat.call_count == 1


@respx.mock
async def test_up_front_threshold_is_lower_bound_plus_output_reserve() -> None:
    msgs = _msg(30_000)
    lower = lower_bound_prompt_tokens(msgs)
    respx.post(URL).mock(return_value=_reply(100))
    respx.post(SHOW_URL).mock(return_value=_show(lower + OUTPUT_RESERVE_TOKENS))
    await OllamaProvider().chat(msgs)  # exactly fits the reserve: sent
    respx.post(SHOW_URL).mock(return_value=_show(lower + OUTPUT_RESERVE_TOKENS - 1))
    with pytest.raises(OllamaTruncationError):
        await OllamaProvider().chat(msgs)


@respx.mock
@pytest.mark.parametrize(
    "show",
    [
        httpx.Response(404, json={"error": "model not found"}),
        httpx.Response(200, json={"model_info": {"general.architecture": "x"}}),
        httpx.Response(200, text="not json"),
        httpx.ConnectError("down"),
    ],
)
async def test_show_unavailable_falls_back_to_old_behaviour(
    show: httpx.Response | Exception, caplog: pytest.LogCaptureFixture
) -> None:
    respx.post(SHOW_URL).mock(side_effect=show if isinstance(show, Exception) else [show] * 3)
    chat = respx.post(URL).mock(return_value=_reply(20_000))
    p = OllamaProvider()
    with caplog.at_level("WARNING", logger="agentgauge.providers"):
        await p.chat(_msg(60_000))
        await p.chat(_msg(60_000))
    assert json.loads(chat.calls[0].request.content)["options"]["num_ctx"] == 32768
    assert len([r for r in caplog.records if "/api/show" in r.getMessage()]) == 1  # logged once


@respx.mock
async def test_show_called_once_per_provider_instance() -> None:
    show = respx.post(SHOW_URL).mock(return_value=_show(8192))
    respx.post(URL).mock(return_value=_reply(50))
    p = OllamaProvider("gemma2:9b")
    for _ in range(3):
        await p.chat([Message("user", "hi")])
    assert show.call_count == 1
