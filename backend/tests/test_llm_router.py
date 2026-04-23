"""Unit tests for the LLM router 3-tier cascade. Pure mocks; no network."""
import asyncio
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.llm_router import (
    Tier,
    chat,
    LLMRouterError,
    categorise_exception,
)


def _tier(name: str, call, provider: str = "prov", model: str = "m"):
    return Tier(name=name, provider=provider, model=model, call=call)


# ---------- categoriser ----------
def test_categorise_timeout():
    assert categorise_exception(httpx.TimeoutException("x"))[0] == "timeout"


def test_categorise_401():
    resp = httpx.Response(401, request=httpx.Request("POST", "https://x.y"))
    err = httpx.HTTPStatusError("401", request=resp.request, response=resp)
    assert categorise_exception(err)[0] == "auth"


def test_categorise_429():
    resp = httpx.Response(429, request=httpx.Request("POST", "https://x.y"))
    err = httpx.HTTPStatusError("429", request=resp.request, response=resp)
    assert categorise_exception(err)[0] == "rate_limit"


def test_categorise_5xx():
    resp = httpx.Response(502, request=httpx.Request("POST", "https://x.y"))
    err = httpx.HTTPStatusError("502", request=resp.request, response=resp)
    assert categorise_exception(err)[0] == "5xx"


def test_categorise_unknown():
    assert categorise_exception(ValueError("weird"))[0] == "other"


# ---------- cascade ----------
@pytest.mark.asyncio
async def test_primary_succeeds_no_fallbacks():
    primary_call = AsyncMock(return_value="primary-ok")
    fallback_call = AsyncMock(return_value="fb-ok")
    result = await chat(
        [{"role": "user", "content": "hi"}],
        tiers=[_tier("primary", primary_call, "anthropic", "claude-opus-4-6"),
               _tier("fallback", fallback_call, "emergent", "claude-opus-4-6")],
    )
    assert result["text"] == "primary-ok"
    assert result["tier"] == "primary"
    assert result["fallbacks_tried"] == 0
    fallback_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_primary_fails_secondary_succeeds():
    resp = httpx.Response(401, request=httpx.Request("POST", "https://x.y"))
    primary_call = AsyncMock(side_effect=httpx.HTTPStatusError("401", request=resp.request, response=resp))
    secondary_call = AsyncMock(return_value="secondary-ok")
    fallback_call = AsyncMock(return_value="fb-ok")
    result = await chat(
        [{"role": "user", "content": "hi"}],
        tiers=[_tier("primary", primary_call),
               _tier("secondary", secondary_call),
               _tier("fallback", fallback_call)],
    )
    assert result["text"] == "secondary-ok"
    assert result["tier"] == "secondary"
    assert result["fallbacks_tried"] == 1
    fallback_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_all_fail_except_fallback():
    resp1 = httpx.Response(401, request=httpx.Request("POST", "https://x.y"))
    resp2 = httpx.Response(429, request=httpx.Request("POST", "https://a.b"))
    primary_call = AsyncMock(side_effect=httpx.HTTPStatusError("401", request=resp1.request, response=resp1))
    secondary_call = AsyncMock(side_effect=httpx.HTTPStatusError("429", request=resp2.request, response=resp2))
    fallback_call = AsyncMock(return_value="fb-ok")
    result = await chat(
        [{"role": "user", "content": "hi"}],
        tiers=[_tier("primary", primary_call),
               _tier("secondary", secondary_call),
               _tier("fallback", fallback_call, "emergent", "claude-opus-4-6")],
    )
    assert result["text"] == "fb-ok"
    assert result["tier"] == "fallback"
    assert result["fallbacks_tried"] == 2


@pytest.mark.asyncio
async def test_all_tiers_fail_raises():
    resp = httpx.Response(500, request=httpx.Request("POST", "https://x.y"))
    call = AsyncMock(side_effect=httpx.HTTPStatusError("500", request=resp.request, response=resp))
    with pytest.raises(LLMRouterError) as ei:
        await chat(
            [{"role": "user", "content": "hi"}],
            tiers=[_tier("primary", call), _tier("fallback", call, "emergent", "m")],
        )
    assert len(ei.value.failures) == 2
    assert all(f.category == "5xx" for f in ei.value.failures)


@pytest.mark.asyncio
async def test_rate_limit_falls_through():
    resp = httpx.Response(429, request=httpx.Request("POST", "https://x.y"))
    primary_call = AsyncMock(side_effect=httpx.HTTPStatusError("429", request=resp.request, response=resp))
    fallback_call = AsyncMock(return_value="fb-ok")
    result = await chat(
        [{"role": "user", "content": "hi"}],
        tiers=[_tier("primary", primary_call),
               _tier("fallback", fallback_call, "emergent", "m")],
    )
    assert result["tier"] == "fallback"


@pytest.mark.asyncio
async def test_4xx_still_falls_through():
    resp = httpx.Response(404, request=httpx.Request("POST", "https://x.y"))
    primary_call = AsyncMock(side_effect=httpx.HTTPStatusError("404", request=resp.request, response=resp))
    fallback_call = AsyncMock(return_value="fb-ok")
    result = await chat(
        [{"role": "user", "content": "hi"}],
        tiers=[_tier("primary", primary_call),
               _tier("fallback", fallback_call, "emergent", "m")],
    )
    assert result["tier"] == "fallback"


@pytest.mark.asyncio
async def test_empty_tiers_raises_value_error():
    with pytest.raises(ValueError):
        await chat([{"role": "user", "content": "hi"}], tiers=[])
