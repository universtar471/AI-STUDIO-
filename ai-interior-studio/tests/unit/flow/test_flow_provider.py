import asyncio

from services.core.domain import ProviderJobState, RenderRequest
from services.providers.flow import FlowConfig, FlowError, FlowProvider


class Images:
    def base_image(self, request):
        return 'base-art', b'base-bytes', 'image/jpeg'

    def image(self, artifact_id):
        return f'{artifact_id}-bytes'.encode(), 'image/png'


class FakeDriver:
    def __init__(self, error=None):
        self.error, self.jobs = error, []

    def render(self, job, progress):
        self.jobs.append(job)
        progress('uploading', .2)
        if self.error:
            raise self.error
        return b'png-bytes', 'image/png', {'ratio': '16:9', 'resolution': '2K'}


def request(**changes):
    body = {'project_id': 'p', 'mode': 'sketchup_render', 'source': {'artifact_id': 'base-art'},
            'references': [{'artifact_id': 'floor', 'role': 'FLOOR'}, {'artifact_id': 'master', 'role': 'STYLE_MASTER'},
                           {'artifact_id': 'decor', 'role': 'DECOR'}]}
    return RenderRequest(**{**body, **changes})


def provider(tmp_path, driver):
    return FlowProvider(Images(), data_root=tmp_path, config=FlowConfig(driver_path=tmp_path / 'run.js'), driver=driver)


async def finish(p, job_id):
    for _ in range(200):
        status = await p.poll(job_id)
        if status.state not in (ProviderJobState.QUEUED, ProviderJobState.RUNNING):
            return status
        await asyncio.sleep(.01)
    raise AssertionError(status)


def test_render_sends_base_and_the_strongest_reference_as_style(tmp_path):
    async def run():
        driver = FakeDriver()
        p = provider(tmp_path, driver)
        job = await p.submit(request())
        status = await finish(p, job.provider_job_id)
        assert status.state == ProviderJobState.SUCCEEDED and status.metrics.extra['resolution'] == '2K'
        [out] = await p.fetch_result(job.provider_job_id)
        assert out.data == b'png-bytes' and out.suggested_name.endswith('.png')
        [sent] = driver.jobs
        assert sent['base'] == (b'base-bytes', 'image/jpeg') and sent['style'] == (b'master-bytes', 'image/png')
        assert sent['prompt'].startswith('You are editing') and 'Image 2' in sent['prompt']
        record = job.provider_request
        assert [i['role'] for i in record['images']] == ['BASE_PLAN', 'STYLE_MASTER']
        assert set(record['dropped_references']) == {'floor', 'decor'}
        assert 'bytes' not in str(record)  # bytes never enter provider_request.json
    asyncio.run(run())


def test_flow_errors_become_job_errors_without_leaking_details(tmp_path):
    async def run():
        for error, code in [(FlowError('FLOW_NEEDS_ATTENTION', 'sign in'), 'FLOW_NEEDS_ATTENTION'),
                            (RuntimeError('secret token xyz'), 'FLOW_ERROR')]:
            p = provider(tmp_path, FakeDriver(error))
            job = await p.submit(request())
            status = await finish(p, job.provider_job_id)
            assert status.state == ProviderJobState.FAILED and status.error.code == code
            assert 'secret' not in status.error.message
    asyncio.run(run())


def test_validation_and_health(tmp_path):
    async def run():
        p = provider(tmp_path, FakeDriver())
        assert (await p.health()).status == 'ok'
        assert not (await p.validate(request(ratio='21:9'))).ok
        assert not (await p.validate(request(image_size='2K'))).ok
        assert not p.capabilities.supports_seed and not p.capabilities.has_usage_cost
        assert p.capabilities.max_reference_images == 1
        missing = FlowProvider(Images(), data_root=tmp_path, config=FlowConfig(driver_path=tmp_path / 'nope.js'))
        assert (await missing.health()).status == 'unavailable'
    asyncio.run(run())


def test_jobs_run_one_at_a_time(tmp_path):
    async def run():
        driver = FakeDriver()
        p = provider(tmp_path, driver)
        jobs = [await p.submit(request()) for _ in range(3)]
        for job in jobs:
            assert (await finish(p, job.provider_job_id)).state == ProviderJobState.SUCCEEDED
        assert len(driver.jobs) == 3
    asyncio.run(run())
