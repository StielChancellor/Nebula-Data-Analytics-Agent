"""
LLM router.

Default brain: Gemini 3.0 Preview (per PRD D6).
Fallback:     Anthropic Claude (configurable via env).

If neither SDK is installed or no credentials are configured, the router
returns a deterministic stub response so unit tests and dev environments
work without hitting paid APIs.

Importing this module does NOT import the underlying SDKs — those are
imported lazily inside the provider methods so test envs don't need them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

# ---------- public surface ----------

ProviderName = Literal["gemini", "claude", "stub"]


@dataclass(frozen=True)
class LLMResponse:
    """Provider-agnostic response."""
    text: str
    model: str
    provider: ProviderName
    usage: dict[str, int] = field(default_factory=dict)   # tokens in/out
    finish_reason: str = "stop"


class LLMProvider(Protocol):
    name: ProviderName
    model: str
    async def generate(self, *, prompt: str, system: str | None = None, max_tokens: int = 16_384) -> LLMResponse: ...


# ---------- concrete providers ----------

class GeminiProvider:
    """
    Vertex AI / google-genai backed Gemini 3.0 Preview client.
    Lazy-imports google-genai so this module is import-safe without it.
    """
    name: ProviderName = "gemini"

    def __init__(self, model: str = "gemini-3.0-preview", project: str | None = None, location: str = "us-central1"):
        self.model = model
        self.project = project or os.getenv("GOOGLE_CLOUD_PROJECT", "insights-navigator-v2")
        self.location = location

    async def generate(self, *, prompt: str, system: str | None = None, max_tokens: int = 16_384) -> LLMResponse:
        try:
            from google import genai  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError("google-genai not installed; install backend with `pip install -e .[dev]`") from e

        client = genai.Client(vertexai=True, project=self.project, location=self.location)
        # Note: avoid asyncio.to_thread here — google-genai's async API surface
        # is still in flux. Keep this sync-call shape and run in a worker if
        # the caller is in an event loop. TODO Phase 6 — wire properly.
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        cfg: dict[str, Any] = {"max_output_tokens": max_tokens}
        if system:
            cfg["system_instruction"] = system
        resp = client.models.generate_content(model=self.model, contents=contents, config=cfg)
        text = getattr(resp, "text", "") or ""
        finish = getattr(resp, "finish_reason", "stop")
        return LLMResponse(text=text, model=self.model, provider=self.name, finish_reason=str(finish))


class ClaudeProvider:
    """Anthropic Claude fallback."""
    name: ProviderName = "claude"

    def __init__(self, model: str = "claude-sonnet-4-5"):
        self.model = model

    async def generate(self, *, prompt: str, system: str | None = None, max_tokens: int = 16_384) -> LLMResponse:
        try:
            from anthropic import AsyncAnthropic  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError("anthropic SDK not installed") from e

        client = AsyncAnthropic()  # picks up ANTHROPIC_API_KEY env var
        kwargs: dict[str, Any] = {"model": self.model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        if system:
            kwargs["system"] = system
        msg = await client.messages.create(**kwargs)
        # Anthropic returns content as a list of blocks; take the first text block.
        text = ""
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                text = block.text  # type: ignore[attr-defined]
                break
        usage = {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
        return LLMResponse(text=text, model=self.model, provider=self.name, usage=usage, finish_reason=msg.stop_reason or "stop")


class StubProvider:
    """
    Deterministic, zero-cost provider. Used in tests and when no real LLM
    credentials are configured. Returns a fixed string keyed on the prompt
    so tests can assert against it.
    """
    name: ProviderName = "stub"
    model = "stub-1"

    async def generate(self, *, prompt: str, system: str | None = None, max_tokens: int = 16_384) -> LLMResponse:
        echo = prompt[:80].replace("\n", " ")
        return LLMResponse(
            text=f"[stub:{self.model}] {echo}",
            model=self.model,
            provider=self.name,
        )


# ---------- router ----------

class LLMRouter:
    """Picks a provider; retries on the fallback if the primary fails."""

    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None = None) -> None:
        self.primary = primary
        self.fallback = fallback

    async def generate(self, *, prompt: str, system: str | None = None, max_tokens: int = 16_384) -> LLMResponse:
        try:
            return await self.primary.generate(prompt=prompt, system=system, max_tokens=max_tokens)
        except Exception as e:
            if self.fallback is None:
                raise
            # TODO Phase 6: emit a "llm_failover" audit event
            return await self.fallback.generate(prompt=prompt, system=system, max_tokens=max_tokens)


def get_default_router() -> LLMRouter:
    """
    Factory honoring PRD D6:
      - Default brain: Gemini 3.0 Preview (when google-genai is available).
      - Fallback: Claude (when anthropic + ANTHROPIC_API_KEY are present).
      - If neither: StubProvider so tests + local dev work offline.

    Env knobs:
      INSNAV_LLM_PRIMARY  — "gemini" | "claude" | "stub"
      INSNAV_LLM_MODEL    — override the primary's model string
    """
    requested = (os.getenv("INSNAV_LLM_PRIMARY") or "gemini").lower()
    model_override = os.getenv("INSNAV_LLM_MODEL")

    primary: LLMProvider
    fallback: LLMProvider | None = None

    if requested == "stub":
        primary = StubProvider()
        return LLMRouter(primary)

    if requested == "claude":
        try:
            primary = ClaudeProvider(model=model_override or "claude-sonnet-4-5")
        except Exception:
            primary = StubProvider()
        return LLMRouter(primary)

    # Default: gemini primary + claude fallback if creds present
    try:
        primary = GeminiProvider(model=model_override or "gemini-3.0-preview")
    except Exception:
        primary = StubProvider()

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            fallback = ClaudeProvider()
        except Exception:
            fallback = None

    return LLMRouter(primary, fallback)
