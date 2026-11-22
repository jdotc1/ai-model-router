import time
import asyncio
import re
from typing import List, Optional, Tuple, Dict, Any
from app.models.schemas import ProviderResponse, ModelMetadata
from app.providers.registry import provider_registry
from app.fallback.circuit_breaker import circuit_breaker
from app.config.settings import get_settings

settings = get_settings()

RETRYABLE_ERRORS = [
    "timeout",
    "connection error",
    "rate limit",
    "429",
    "503",
    "service unavailable",
    "econnreset",
]



# Preserve the distinction between malformed client requests and provider outages.
# httpx.HTTPStatusError formats status as "Client error '400 ...'" or
# "Server error '503 ...'"; some adapters report "HTTP 500" instead.
_HTTP_STATUS = re.compile(
    r"(?:client|server)\s+error\s+['\"]?([45]\d{2})\b"
    r"|\b(?:http(?:\s+(?:error|status))?|status(?:_code)?)\s*[:=]?\s*['\"]?([45]\d{2})\b",
    re.IGNORECASE,
)


def is_provider_outage(error_str: Optional[str]) -> bool:
    """Count upstream/server or transport failures, never ordinary client 4xx."""
    if not error_str:
        return False
    match = _HTTP_STATUS.search(error_str)
    if match:
        status = int(match.group(1) or match.group(2))
        return status >= 500 or status in (408, 429)
    return is_retryable(error_str)


def is_retryable(error_str: Optional[str]) -> bool:
    if not error_str:
        return False
    low = error_str.lower()
    return any(keyword in low for keyword in RETRYABLE_ERRORS)


async def execute_with_fallback(
    prompt: str,
    selected_model_id: str,
    selected_provider_id: str,
    all_models: List[ModelMetadata],
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_retries: int = 1,
) -> Tuple[ProviderResponse, bool, Optional[str], Optional[str]]:
    """
    Executes model generation with configurable retries and fallback hierarchy.
    Returns: (ProviderResponse, fallback_used, original_model, fallback_reason)
    """
    current_model_id = selected_model_id
    current_provider_id = selected_provider_id
    fallback_used = False
    original_model = selected_model_id
    fallback_reason = None

    # Step 1: Attempt primary model with retries
    provider = provider_registry.get_provider(current_provider_id)
    if not provider:
        provider = provider_registry.get_provider("mock")
        current_provider_id = "mock"
        current_model_id = "mock-balanced"
        fallback_used = True
        fallback_reason = f"Provider '{selected_provider_id}' is not loaded. Fell back to Mock."

    if not circuit_breaker.is_available(current_provider_id):
        fallback_reason = f"Provider '{current_provider_id}' circuit breaker is OPEN."
        fallback_used = True
    else:
        for attempt in range(max_retries + 1):
            resp = await provider.generate(
                prompt=prompt,
                model_id=current_model_id,
                system_prompt=system_prompt,
                temperature=temperature,
            )

            if not resp.error and resp.finish_reason != "error":
                circuit_breaker.record_success(current_provider_id)
                return resp, fallback_used, original_model if fallback_used else None, fallback_reason

            if not is_retryable(resp.error) or attempt == max_retries:
                fallback_reason = resp.error or "Unknown primary model execution error."
                if is_provider_outage(resp.error):
                    circuit_breaker.record_failure(current_provider_id)
                break

            await asyncio.sleep(0.5 * (attempt + 1))

    # Step 2: Determine Fallback Candidate
    fallback_used = True
    # Priority: Mock model or alternative healthy active provider (excluding the failed provider)
    candidate_fallbacks = [
        m for m in all_models
        if m.id != selected_model_id
        and m.is_active
        and m.provider != current_provider_id
        and (m.provider == "mock" or circuit_breaker.is_available(m.provider))
    ]
    if not candidate_fallbacks:
        candidate_fallbacks = [m for m in all_models if m.id != selected_model_id and m.is_active]

    fallback_target = candidate_fallbacks[0] if candidate_fallbacks else None

    if fallback_target:
        fb_provider = provider_registry.get_provider(fallback_target.provider) or provider_registry.get_provider("mock")
        fb_resp = await fb_provider.generate(
            prompt=prompt,
            model_id=fallback_target.id,
            system_prompt=system_prompt,
            temperature=temperature,
        )
        if not fb_resp.error:
            return fb_resp, True, original_model, f"Primary model failed: {fallback_reason} -> Fallback to {fallback_target.id}"

    # Step 3: Emergency Hard Mock fallback
    emergency_mock = provider_registry.get_provider("mock")
    emergency_resp = await emergency_mock.generate(
        prompt=prompt,
        model_id="mock-balanced",
        system_prompt=system_prompt,
        temperature=temperature,
    )
    return emergency_resp, True, original_model, f"Emergency fallback triggered due to: {fallback_reason}"
