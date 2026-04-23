"""
LLM provider registry + model catalog (Phase 3).

Curated list of providers and their top models (verified late 2026 via
public documentation, OpenRouter rankings, and emergentintegrations playbook).
This list is intentionally short per-provider — it is a UI dropdown, not a
comprehensive catalog.

Sources consulted:
  • emergentintegrations playbook (authoritative for anthropic/openai/gemini)
  • x.ai docs (grok-4 / grok-4-fast / grok-code-fast)
  • openrouter.ai model registry + April 2026 usage rankings
  • straico.com/platform-changelog and straico api docs

Model IDs are provider-native (no prefix for direct providers; OpenRouter uses
provider-prefixed slugs).
"""
from typing import Dict, List, Any


PROVIDERS: Dict[str, Dict[str, Any]] = {
    "anthropic": {
        "label": "Anthropic (direct)",
        "key_env_hint": "sk-ant-...",
        "docs_url": "https://docs.anthropic.com/en/api/getting-started",
        "models": [
            {"id": "claude-opus-4-6",           "label": "Claude Opus 4.6"},
            {"id": "claude-sonnet-4-6",         "label": "Claude Sonnet 4.6"},
            {"id": "claude-opus-4-5-20251101",  "label": "Claude Opus 4.5"},
            {"id": "claude-sonnet-4-5-20250929","label": "Claude Sonnet 4.5"},
            {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
        ],
    },
    "openai": {
        "label": "OpenAI (direct)",
        "key_env_hint": "sk-...",
        "docs_url": "https://platform.openai.com/docs/models",
        "models": [
            {"id": "gpt-5.2",     "label": "GPT-5.2"},
            {"id": "gpt-5.1",     "label": "GPT-5.1"},
            {"id": "gpt-5",       "label": "GPT-5"},
            {"id": "gpt-5-mini",  "label": "GPT-5 Mini"},
            {"id": "o4-mini",     "label": "o4-mini (reasoning)"},
        ],
    },
    "openrouter": {
        "label": "OpenRouter (proxy)",
        "key_env_hint": "sk-or-v1-...",
        "docs_url": "https://openrouter.ai/docs/api-reference/authentication",
        "models": [
            {"id": "anthropic/claude-opus-4.6",    "label": "Claude Opus 4.6 (via OpenRouter)"},
            {"id": "anthropic/claude-sonnet-4.6",  "label": "Claude Sonnet 4.6 (via OpenRouter)"},
            {"id": "openai/gpt-5.1",               "label": "GPT-5.1 (via OpenRouter)"},
            {"id": "google/gemini-2.5-pro",        "label": "Gemini 2.5 Pro (via OpenRouter)"},
            {"id": "x-ai/grok-4-fast",             "label": "Grok 4 Fast (via OpenRouter)"},
        ],
    },
    "straico": {
        "label": "Straico (aggregator)",
        "key_env_hint": "Straico API key",
        "docs_url": "https://straico.com/api/",
        "models": [
            {"id": "anthropic/claude-sonnet-4-5-latest", "label": "Claude Sonnet 4.5 (Straico)"},
            {"id": "openai/gpt-5-chat",                  "label": "GPT-5 (Straico)"},
            {"id": "openai/gpt-5-mini",                  "label": "GPT-5 Mini (Straico)"},
            {"id": "xai/grok-4-fast",                    "label": "Grok 4 Fast (Straico)"},
            {"id": "google/gemini-2.5-flash",            "label": "Gemini 2.5 Flash (Straico)"},
        ],
    },
    "grok": {
        "label": "Grok (xAI, direct)",
        "key_env_hint": "xai-...",
        "docs_url": "https://docs.x.ai/docs/overview",
        "models": [
            {"id": "grok-4",           "label": "Grok 4"},
            {"id": "grok-4-fast",      "label": "Grok 4 Fast"},
            {"id": "grok-code-fast",   "label": "Grok Code Fast"},
            {"id": "grok-3",           "label": "Grok 3 (legacy)"},
        ],
    },
}


# Fallback (Emergent-key-powered) model dropdown shown under the built-in fallback card.
FALLBACK_MODELS: List[Dict[str, str]] = [
    {"id": "claude-opus-4-6",          "label": "Claude Opus 4.6"},
    {"id": "claude-opus-4-5-20251101", "label": "Claude Opus 4.5"},
    {"id": "claude-sonnet-4-5-20250929","label": "Claude Sonnet 4.5"},
]

DEFAULT_FALLBACK_MODEL = "claude-opus-4-6"


def provider_known(provider: str) -> bool:
    return provider in PROVIDERS


def model_known(provider: str, model: str) -> bool:
    if not provider_known(provider):
        return False
    return any(m["id"] == model for m in PROVIDERS[provider]["models"])


def mask_key(key: str) -> str:
    """Safe mask for display in the admin UI. Never returns the full key."""
    if not key:
        return ""
    if len(key) <= 8:
        return "••••" + key[-2:]
    return key[:4] + "••••" + key[-4:]


def public_providers_for_ui() -> Dict[str, Any]:
    """Return the provider catalog for the admin UI (no secrets)."""
    return {
        "providers": PROVIDERS,
        "fallback_models": FALLBACK_MODELS,
        "default_fallback_model": DEFAULT_FALLBACK_MODEL,
    }
