"""
LLM Router — 3-tier cascade: primary -> secondary -> Emergent (hard-coded).

Used by Phase 5 (AI Fluency Discussion) and Phase 7 (Synthesis). Not wired
into any user-facing flow yet.

Design:
  • Router has a single async entry point `chat(messages, ...)`.
  • Each tier is a ProviderCall — an async callable that takes (messages, system,
    max_tokens, model) and returns str. Tier construction is separated from
    the cascade logic so unit tests can inject mocks without touching real
    providers.
  • Errors are categorised; non-quota 4xx + quota 429 + 5xx all trigger fallback.
  • No plaintext API keys are logged.
"""
from __future__ import annotations
import os
import time
import logging
import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# Type of a provider call: (messages, system, max_tokens, model) -> str
ProviderCall = Callable[
    [List[Dict[str, str]], Optional[str], int, str],
    Awaitable[str],
]


@dataclass
class TierFailure:
    tier: str  # "primary" | "secondary" | "fallback"
    category: str  # "auth" | "rate_limit" | "timeout" | "5xx" | "4xx" | "other"
    message: str


class LLMRouterError(Exception):
    def __init__(self, failures: List[TierFailure]):
        super().__init__("All LLM tiers failed")
        self.failures = failures


def categorise_exception(exc: Exception) -> Tuple[str, str]:
    """Convert a provider exception into (category, short_message).
    category ∈ {auth, rate_limit, timeout, 5xx, 4xx, other}."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout", "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        sc = exc.response.status_code
        if sc in (401, 403):
            return "auth", f"HTTP {sc}"
        if sc == 429:
            return "rate_limit", "HTTP 429"
        if 500 <= sc < 600:
            return "5xx", f"HTTP {sc}"
        if 400 <= sc < 500:
            return "4xx", f"HTTP {sc}"
        return "other", f"HTTP {sc}"
    if isinstance(exc, httpx.HTTPError):
        return "other", type(exc).__name__
    text = str(exc).lower()
    if "unauthorized" in text or "invalid api key" in text or "authentication" in text:
        return "auth", "auth"
    if "rate limit" in text or "quota" in text:
        return "rate_limit", "rate_limit"
    if "timeout" in text:
        return "timeout", "timeout"
    return "other", type(exc).__name__


@dataclass
class Tier:
    name: str              # "primary" | "secondary" | "fallback"
    provider: str
    model: str
    call: ProviderCall


async def chat(
    messages: List[Dict[str, str]],
    tiers: List[Tier],
    system: Optional[str] = None,
    max_tokens: int = 2000,
    purpose: str = "generic",
) -> Dict[str, Any]:
    """Execute the cascade. `tiers` must have at least one element (the fallback).
    Returns: {text, provider, model, latency_ms, tier, fallbacks_tried}"""
    if not tiers:
        raise ValueError("At least one tier (the fallback) is required.")
    failures: List[TierFailure] = []
    for idx, tier in enumerate(tiers):
        started = time.time()
        try:
            logger.info("LLM cascade[%s/%s] tier=%s provider=%s model=%s purpose=%s",
                        idx + 1, len(tiers), tier.name, tier.provider, tier.model, purpose)
            text = await tier.call(messages, system, max_tokens, tier.model)
            latency_ms = int((time.time() - started) * 1000)
            return {
                "text": text,
                "provider": tier.provider,
                "model": tier.model,
                "latency_ms": latency_ms,
                "tier": tier.name,
                "fallbacks_tried": idx,
            }
        except Exception as exc:  # noqa: BLE001
            category, msg = categorise_exception(exc)
            failures.append(TierFailure(tier=tier.name, category=category, message=msg))
            logger.warning(
                "LLM tier failed: name=%s provider=%s model=%s category=%s msg=%s",
                tier.name, tier.provider, tier.model, category, msg,
            )
            # auth / rate_limit / timeout / 5xx / 4xx / other — all fall through.
    raise LLMRouterError(failures)


# --------------------------------------------------------------------------- #
# Concrete provider calls
# --------------------------------------------------------------------------- #
async def _anthropic_call(
    api_key: str,
) -> ProviderCall:
    async def _call(messages, system, max_tokens, model):
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as c:
            resp = await c.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            parts = data.get("content", [])
            return "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    return _call


async def _openai_call(api_key: str) -> ProviderCall:
    async def _call(messages, system, max_tokens, model):
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        payload = {"model": model, "messages": msgs, "max_tokens": max_tokens}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as c:
            resp = await c.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    return _call


async def _openrouter_call(api_key: str) -> ProviderCall:
    async def _call(messages, system, max_tokens, model):
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        payload = {"model": model, "messages": msgs, "max_tokens": max_tokens}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as c:
            resp = await c.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    return _call


async def _grok_call(api_key: str) -> ProviderCall:
    async def _call(messages, system, max_tokens, model):
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        payload = {"model": model, "messages": msgs, "max_tokens": max_tokens}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as c:
            resp = await c.post("https://api.x.ai/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    return _call


async def _straico_call(api_key: str) -> ProviderCall:
    async def _call(messages, system, max_tokens, model):
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        payload = {"model": model, "messages": msgs, "max_tokens": max_tokens}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        # Straico supports an OpenAI-compatible /v1/chat/completions
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as c:
            resp = await c.post("https://api.straico.com/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            # Fallback shape per some Straico endpoints
            return data.get("response") or data.get("output") or ""
    return _call


async def _emergent_call_factory() -> ProviderCall:
    """Emergent LLM key call via emergentintegrations. Always uses Anthropic-side
    through the universal key. Session ID is per-call so no history leaks."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    import uuid as _uuid

    emergent_key = os.environ.get("EMERGENT_LLM_KEY")

    async def _call(messages, system, max_tokens, model):
        if not emergent_key:
            raise RuntimeError("EMERGENT_LLM_KEY is not configured.")
        chat_obj = LlmChat(
            api_key=emergent_key,
            session_id=f"soe-tra-{_uuid.uuid4()}",
            system_message=system or "You are a helpful assistant.",
        ).with_model("anthropic", model)
        # Flatten multi-turn messages into a single user prompt (tiers collapse).
        if len(messages) == 1 and messages[0].get("role") == "user":
            text = messages[0]["content"]
        else:
            lines = []
            for m in messages:
                role = m.get("role", "user")
                prefix = {"user": "User", "assistant": "Assistant", "system": "System"}.get(role, role)
                lines.append(f"{prefix}: {m.get('content', '')}")
            text = "\n".join(lines)
        user_message = UserMessage(text=text)
        return await chat_obj.send_message(user_message)
    return _call


PROVIDER_CALL_FACTORIES: Dict[str, Any] = {
    "anthropic": _anthropic_call,
    "openai": _openai_call,
    "openrouter": _openrouter_call,
    "straico": _straico_call,
    "grok": _grok_call,
}


async def build_tier(name: str, provider: str, model: str, api_key: str) -> Tier:
    factory = PROVIDER_CALL_FACTORIES.get(provider)
    if not factory:
        raise ValueError(f"Unknown provider '{provider}'")
    call = await factory(api_key)
    return Tier(name=name, provider=provider, model=model, call=call)


async def build_fallback_tier(model: str) -> Tier:
    call = await _emergent_call_factory()
    return Tier(name="fallback", provider="emergent", model=model, call=call)
