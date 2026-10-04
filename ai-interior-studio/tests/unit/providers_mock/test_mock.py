import asyncio
import struct
import zlib

import pytest

from services.core.domain import ImageProvider, ProviderJobState, RenderRequest
from services.providers.mock import MockProvider


@pytest.mark.parametrize('failure,expected', [(None, 'succeeded'), ('vram', 'failed'), ('timeout', 'running')])
def test_mock_modes(failure, expected):
    async def run():
        provider = MockProvider(delay=0, failure=failure)
        assert isinstance(provider, ImageProvider)
        request = RenderRequest(project_id='p', mode='sketchup_render', source={'artifact_id': 'a'})
        assert (await provider.health()).status == 'ok'
        assert (await provider.validate(request)).ok
        job = await provider.submit(request)
        status = await provider.poll(job.provider_job_id)
        assert status.state == expected
        if status.state == ProviderJobState.SUCCEEDED:
            outputs = await provider.fetch_result(job.provider_job_id)
            assert outputs[0].data.startswith(b'\x89PNG\r\n\x1a\n')
            png = outputs[0].data
            offset = 8
            while offset < len(png):
                size = struct.unpack('>I', png[offset:offset + 4])[0]
                chunk = png[offset + 4:offset + 8 + size]
                checksum = struct.unpack('>I', png[offset + 8 + size:offset + 12 + size])[0]
                assert zlib.crc32(chunk) == checksum
                if chunk[:4] == b'IDAT':
                    assert zlib.decompress(chunk[4:])
                offset += 12 + size
        if failure == 'vram':
            assert status.error.code == 'OUT_OF_VRAM'
        await provider.cancel(job.provider_job_id)
        assert (await provider.poll(job.provider_job_id)).state == 'cancelled'
    asyncio.run(run())
