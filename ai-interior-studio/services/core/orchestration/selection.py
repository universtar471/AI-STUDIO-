"""Provider eligibility shared by the scheduler and diagnostics."""
import asyncio

from services.core.domain import ImageProvider, ProviderHealth, RenderRequest


class OrchestrationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


async def provider_health(provider: ImageProvider) -> ProviderHealth:
    try:
        return await asyncio.wait_for(provider.health(), timeout=2)
    except Exception:
        # Provider exceptions can contain credentials or request headers.
        return ProviderHealth(status='unavailable', detail='Provider health check failed')


async def select_provider(providers: list[ImageProvider], request: RenderRequest) -> ImageProvider:
    ordered = sorted(providers, key=lambda p: not p.capabilities.supports_local)
    for provider in ordered:
        c = provider.capabilities
        if request.provider_id and provider.id != request.provider_id:
            continue
        if request.provider_policy == 'local_only' and not c.supports_local:
            continue
        if request.provider_policy == 'cloud_only' and c.supports_local:
            continue
        if request.mode not in c.supported_modes:
            continue
        # Providers pack extra references into their own slots (select_references) and describe
        # the dropped ones in the prompt, so only a provider without any reference slot is unfit.
        if request.references and c.max_reference_images == 0:
            continue
        if c.supported_ratios and request.ratio not in c.supported_ratios:
            continue
        if request.image_size and c.supported_sizes and request.image_size not in c.supported_sizes:
            continue
        if request.seed is not None and not c.supports_seed:
            continue
        if c.has_usage_cost and request.image_size == '4K' and not request.confirm_high_cost:
            continue
        if (await provider_health(provider)).status != 'ok':
            continue
        try:
            validation = await asyncio.wait_for(provider.validate(request), timeout=2)
        except Exception:
            continue
        if validation.ok:
            return provider
    raise OrchestrationError('NO_ELIGIBLE_PROVIDER', 'No healthy provider supports this request and policy')
