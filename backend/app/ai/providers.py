"""AI provider abstraction.

Provides a common interface for OpenAI, Anthropic, Gemini, and local
(OpenAI-compatible) endpoints, configured entirely via environment variables.
Providers choose which agents use them through NEXUS_AGENT_PROVIDER_MAP or
per-agent admin configuration. API keys are never exposed to the frontend.
"""

import json
import logging
from abc import ABC, abstractmethod

import httpx

from ..core.config import settings

logger = logging.getLogger("nexus.ai.providers")

_MAX_RETRIES = 2
_TIMEOUT = 90.0


class AIProvider(ABC):
    key: str = "base"
    label: str = "Base AI"

    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    def model_name(self) -> str:
        ...

    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        temperature: float = 0.4,
        max_tokens: int = 1500,
        response_json: bool = False,
    ) -> str:
        ...

    def metadata(self) -> dict:
        return {
            "provider": self.key,
            "label": self.label,
            "model": self.model_name(),
            "configured": self.is_configured(),
        }


class OpenAIProvider(AIProvider):
    key = "openai"
    label = "OpenAI"

    def is_configured(self) -> bool:
        return bool(settings.OPENAI_API_KEY)

    def model_name(self) -> str:
        return settings.OPENAI_MODEL

    def complete(self, messages, temperature=0.4, max_tokens=1500, response_json=False):
        if not self.is_configured():
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("The 'openai' package is not installed.") from exc

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        kwargs = {}
        if response_json:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return resp.choices[0].message.content or ""


class AnthropicProvider(AIProvider):
    key = "anthropic"
    label = "Anthropic (Claude)"
    _url = "https://api.anthropic.com/v1/messages"

    def is_configured(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY)

    def model_name(self) -> str:
        return settings.ANTHROPIC_MODEL

    def complete(self, messages, temperature=0.4, max_tokens=1500, response_json=False):
        if not self.is_configured():
            raise RuntimeError("ANTHROPIC_API_KEY is not configured.")
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        body = {
            "model": self.model_name(),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system or "You are NEXUS, an enterprise AI assistant.",
            "messages": [
                {"role": m["role"], "content": m["content"]}
                for m in messages
                if m["role"] in ("user", "assistant")
            ],
        }
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                self._url,
                headers={
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
        data = resp.json()
        try:
            return data["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("Unexpected Anthropic response shape.")


class GeminiProvider(AIProvider):
    key = "gemini"
    label = "Google Gemini"

    def is_configured(self) -> bool:
        return bool(settings.GEMINI_API_KEY)

    def model_name(self) -> str:
        return settings.GEMINI_MODEL

    def complete(self, messages, temperature=0.4, max_tokens=1500, response_json=False):
        if not self.is_configured():
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name()}:generateContent?key={settings.GEMINI_API_KEY}"
        )
        contents = [
            {"role": "user" if m["role"] in ("user", "system") else "model",
             "parts": [{"text": m["content"]}]}
            for m in messages
            if m["role"] in ("user", "assistant", "system")
        ]
        body = {"contents": contents, "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(url, json=body)
            resp.raise_for_status()
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("Unexpected Gemini response shape.")


class LocalProvider(AIProvider):
    key = "local"
    label = "Local (OpenAI-compatible)"

    def is_configured(self) -> bool:
        return bool(settings.LOCAL_AI_ENDPOINT)

    def model_name(self) -> str:
        return settings.LOCAL_AI_MODEL

    def complete(self, messages, temperature=0.4, max_tokens=1500, response_json=False):
        if not self.is_configured():
            raise RuntimeError("LOCAL_AI_ENDPOINT is not configured.")
        headers = {"content-type": "application/json"}
        if settings.LOCAL_AI_API_KEY:
            headers["Authorization"] = f"Bearer {settings.LOCAL_AI_API_KEY}"
        url = settings.LOCAL_AI_ENDPOINT.rstrip("/")
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"
        body = {
            "model": self.model_name(),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("Unexpected local endpoint response shape.")


PROVIDER_CLASSES: list[type[AIProvider]] = [
    OpenAIProvider,
    AnthropicProvider,
    GeminiProvider,
    LocalProvider,
]

_PRIORITY = ["openai", "gemini", "anthropic", "local"]

_instances: dict[str, AIProvider] = {}


def get_provider(key: str) -> AIProvider:
    if key not in _instances:
        for cls in PROVIDER_CLASSES:
            if cls.key == key:
                _instances[key] = cls()
                break
    return _instances.get(key)


def configured_providers() -> list[AIProvider]:
    providers = [get_provider(k) for k in _PRIORITY]
    return [p for p in providers if p and p.is_configured()]


def default_provider() -> AIProvider | None:
    providers = configured_providers()
    return providers[0] if providers else None


def available_provider_metadata() -> list[dict]:
    """Non-sensitive metadata about every provider (never includes keys)."""
    result = []
    for key in _PRIORITY:
        p = get_provider(key)
        if p:
            result.append(p.metadata())
    return result


def _agent_map() -> dict[str, str]:
    try:
        data = json.loads(settings.NEXUS_AGENT_PROVIDER_MAP or "{}")
        return {str(k).lower(): str(v).lower() for k, v in data.items()}
    except (ValueError, TypeError):
        return {}


def provider_for_agent(agent_key: str, configured_override: str = "") -> AIProvider:
    """Resolve the provider for a specific agent.

    Precedence: per-agent admin override, env map, then the default configured
    provider. Returns None when no provider is configured.
    """
    requested = (configured_override or _agent_map().get(agent_key, "")).lower()
    if requested:
        provider = get_provider(requested)
        if provider and provider.is_configured():
            return provider
    return default_provider()


def synthesis_provider() -> AIProvider | None:
    """The strongest/pinned model for final NEXUS synthesis."""
    pinned = settings.NEXUS_SYNTHESIS_PROVIDER if getattr(settings, "NEXUS_SYNTHESIS_PROVIDER", "") else ""
    if pinned:
        provider = get_provider(pinned.lower())
        if provider and provider.is_configured():
            return provider
    return default_provider()