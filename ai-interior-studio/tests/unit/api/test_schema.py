from scripts.generate_types import generate, ts_type
from services.api import create_app


def test_schema_and_types_have_shared_models():
    schema = create_app().openapi()
    output = generate(schema)
    for name in ['RenderJob', 'RenderRequest', 'JobProgressEvent', 'StylePack', 'ProviderInfo']:
        assert f'export type {name} =' in output
    assert '/render/jobs/{identifier}/finalize' in schema['paths']
    assert '/projects/{identifier}/scenes/import' in schema['paths']
    assert not any('rooms' in path or 'plans' in path for path in schema['paths'])
    assert ts_type({'type': 'array', 'prefixItems': [{'type': 'number'}]}) == '[number]'
