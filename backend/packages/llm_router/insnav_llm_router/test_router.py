"""Router tests using the StubProvider so they don't hit paid APIs."""
import pytest
from insnav_llm_router.router import StubProvider, LLMRouter, get_default_router


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
