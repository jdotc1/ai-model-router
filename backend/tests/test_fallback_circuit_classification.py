"""Do not let invalid client requests take shared providers offline."""

from unittest.mock import AsyncMock

import pytest

from app.fallback import handler
from app.models.schemas import ProviderResponse


@pytest.mark.parametrize(
    ("error", "outage"),
    [
        ("OpenAI error: Client error '400 Bad Request' for url", False),
        ("Client error '401 Unauthorized' for url", False),
        ("HTTP 403", False),
        ("HTTP status 422", False),
        ("Error: API key not configured in environment.", False),
        ("Unknown request validation error", False),
        ("Server error '500 Internal Server Error' for url", True),
        ("HTTP 502 Bad Gateway", True),
        ("Server error '503 Service Unavailable' for url", True),
        ("HTTP 504", True),
        ("HTTP 408 Request Timeout", True),
        ("Client error '429 Too Many Requests' for url", True),
        ("connection error: connection reset by peer", True),
        ("Timeout while connecting to provider", True),
        ("HTTP 400: service unavailable", False),
    ],
)
def test_only_provider_outages_are_counted(error, outage):
    assert handler.is_provider_outage(error) is outage


@pytest.mark.asyncio
async def test_client_errors_do_not_open_shared_provider_breaker(monkeypatch):
    provider = type("StubProvider", (), {})()
    provider.generate = AsyncMock(
        return_value=ProviderResponse(
            content="", error="Client error '400 Bad Request' for url",
            finish_reason="error", provider="openai",
        )
    )
    mock = type("MockProvider", (), {})()
    mock.generate = AsyncMock(
        return_value=ProviderResponse(
            content="fallback", model="mock-balanced", provider="mock",
        )
    )
    monkeypatch.setattr(
        handler.provider_registry, "get_provider",
        lambda provider_id: provider if provider_id == "openai" else mock,
    )
    for _ in range(4):
        response, used_fallback, _, _ = await handler.execute_with_fallback(
            prompt="bad request",
            selected_model_id="invalid-model",
            selected_provider_id="openai",
            all_models=[],
            max_retries=0,
        )
        assert response.content == "fallback"
        assert used_fallback
    assert handler.circuit_breaker.failures.get("openai", 0) == 0
    assert handler.circuit_breaker.is_available("openai")


@pytest.mark.asyncio
async def test_upstream_server_failures_still_trip_breaker(monkeypatch):
    provider = type("StubProvider", (), {})()
    provider.generate = AsyncMock(
        return_value=ProviderResponse(
            content="", error="Server error '503 Service Unavailable' for url",
            finish_reason="error", provider="openai",
        )
    )
    mock = type("MockProvider", (), {})()
    mock.generate = AsyncMock(return_value=ProviderResponse(
        content="fallback", model="mock-balanced", provider="mock",
    ))
    monkeypatch.setattr(
        handler.provider_registry, "get_provider",
        lambda provider_id: provider if provider_id == "openai" else mock,
    )
    for _ in range(3):
        await handler.execute_with_fallback(
            prompt="network outage", selected_model_id="test-model",
            selected_provider_id="openai", all_models=[], max_retries=0,
        )
    assert handler.circuit_breaker.failures["openai"] == 3
    assert not handler.circuit_breaker.is_available("openai")
