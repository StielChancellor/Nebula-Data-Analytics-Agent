"""Router tests using the StubProvider so they don't hit paid APIs."""
import pytest
from insnav_llm_router import build_router, list_models
from insnav_llm_router.router import StubProvider, LLMRouter, get_default_router


def test_list_models_marks_stub_available_and_one_default() -> None:
    models = list_models()
    ids = {m["id"] for m in models}
    assert {"gemini-3.0-preview", "claude-sonnet-4-5", "stub"} <= ids
    by_id = {m["id"]: m for m in models}
    assert by_id["stub"]["available"] is True
    assert sum(1 for m in models if m["default"]) == 1
    assert by_id["gemini-3.0-preview"]["default"] is True


def test_build_router_stub_choice() -> None:
    r = build_router("stub")
    assert r.primary.name == "stub"


def test_build_router_unknown_falls_back_to_stub() -> None:
    r = build_router("does-not-exist")
    assert r.primary.name == "stub"


def test_build_router_claude_without_key_degrades_to_stub(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = build_router("claude-sonnet-4-5")  # no key → not available → stub
    assert r.primary.name == "stub"


@pytest.mark.asyncio
async def test_stub_provider_returns_deterministic_text() -> None:
    p = StubProvider()
    r = await p.generate(prompt="hello world")
    assert r.provider == "stub"
    assert "hello world" in r.text


@pytest.mark.asyncio
async def test_router_falls_back_when_primary_raises() -> None:
    class _Broken:
        name = "gemini"
        model = "broken"
        async def generate(self, **_: object):
            raise RuntimeError("simulated outage")

    router = LLMRouter(_Broken(), fallback=StubProvider())
    r = await router.generate(prompt="x")
    assert r.provider == "stub"


@pytest.mark.asyncio
async def test_router_raises_when_no_fallback_configured() -> None:
    class _Broken:
        name = "gemini"
        model = "broken"
        async def generate(self, **_: object):
            raise RuntimeError("simulated outage")

    router = LLMRouter(_Broken(), fallback=None)
    with pytest.raises(RuntimeError):
        await router.generate(prompt="x")


def test_get_default_router_with_stub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSNAV_LLM_PRIMARY", "stub")
    r = get_default_router()
    assert r.primary.name == "stub"
