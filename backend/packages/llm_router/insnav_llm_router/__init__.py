"""
insnav_llm_router — the ONLY place in the backend that imports an LLM SDK.

PRD § Hard constraint #9: agents never import google-genai or anthropic
directly. They call `llm.generate(...)`. This lets us:
  - swap models (Gemini 3.0 Preview default; Claude fallback per D6)
  - version prompts centrally
  - add retry / rate-limit / cost-cap policies in one place
  - test agents with a stub provider without monkey-patching SDKs
"""
from .router import (
    DEFAULT_MODEL_ID,
    MODELS,
    LLMProvider,
    LLMResponse,
    LLMRouter,
    build_router,
    get_default_router,
    list_models,
)

__all__ = [
    "LLMResponse",
    "LLMRouter",
    "LLMProvider",
    "get_default_router",
    "build_router",
    "list_models",
    "MODELS",
    "DEFAULT_MODEL_ID",
]

__version__ = "0.2.0"
