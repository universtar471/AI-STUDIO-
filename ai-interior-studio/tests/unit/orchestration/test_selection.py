import asyncio

import pytest

from services.core.domain import ProviderHealth, RenderRequest
from services.core.orchestration import OrchestrationError, select_provider
from services.providers.mock import MockProvider


@pytest.mark.parametrize('changes', [
    {'supported_modes': []}, {'supported_ratios': ['1:1']},
    {'supported_sizes': ['4K']}, {'supports_seed': False},
    {'max_reference_images': 0}, {'supports_multi_reference': False},
])
def test_capability_rejection(changes):
    provider = MockProvider(delay=0)
    provider.capabilities = provider.capabilities.model_copy(update=changes)
    request = RenderRequest(project_id='p', mode='sketchup_render', source={'artifact_id': 'a'},
                            image_size='1K', seed=1, references=[{'artifact_id': 'a', 'role': 'WALL'}, {'artifact_id': 'b', 'role': 'FLOOR'}])
    with pytest.raises(OrchestrationError, match='No healthy provider'):
        asyncio.run(select_provider([provider], request))


def test_policies_explicit_choice_health_and_cost():
    async def run():
        local, cloud = MockProvider(), MockProvider()
        cloud.id = 'cloud'
        cloud.capabilities = cloud.capabilities.model_copy(update={'supports_local': False, 'has_usage_cost': True})
        request = RenderRequest(project_id='p', mode='sketchup_render', source={'artifact_id': 'a'})
        assert await select_provider([cloud, local], request) is local
        assert await select_provider([local, cloud], request.model_copy(update={'provider_policy': 'cloud_only'})) is cloud
        with pytest.raises(OrchestrationError):
            await select_provider([local, cloud], request.model_copy(update={'provider_id': 'cloud', 'provider_policy': 'local_only'}))
        expensive = request.model_copy(update={'provider_id': 'cloud', 'image_size': '4K'})
        with pytest.raises(OrchestrationError):
            await select_provider([cloud], expensive)
        assert await select_provider([cloud], expensive.model_copy(update={'confirm_high_cost': True})) is cloud
        async def broken():
            raise RuntimeError('secret must not be exposed')
        local.health = broken
        assert await select_provider([local, cloud], request) is cloud
        async def degraded():
            return ProviderHealth(status='degraded')
        cloud.health = degraded
        with pytest.raises(OrchestrationError):
            await select_provider([local, cloud], request)
    asyncio.run(run())
