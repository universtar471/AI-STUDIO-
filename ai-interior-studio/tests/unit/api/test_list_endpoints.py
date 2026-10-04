from fastapi.testclient import TestClient

from services.api import create_app
from services.providers.mock import MockProvider


def test_list_scenes_and_style_pack_versions(tmp_path):
    with TestClient(create_app(tmp_path, providers=[MockProvider(delay=0)])) as client:
        first = client.post('/projects', json={'name': 'A'}).json()['id']
        second = client.post('/projects', json={'name': 'B'}).json()['id']
        for name in ('Living', 'Kitchen'):
            client.post(f'/projects/{first}/scenes/import', data={'name': name}, files={'file': (f'{name}.png', name.encode(), 'image/png')})
        assert sorted(s['name'] for s in client.get(f'/projects/{first}/scenes').json()) == ['Kitchen', 'Living']
        assert client.get(f'/projects/{second}/scenes').json() == []
        assert client.get('/projects/missing/scenes').status_code == 404

        pack = client.post('/style-packs', json={'name': 'Oak', 'project_id': first}).json()
        client.post(f"/style-packs/{pack['id']}/references", data={'role': 'FLOOR'}, files={'file': ('f.png', b'f', 'image/png')})
        assert client.get(f"/style-packs/{pack['id']}/versions").json() == [1, 2]
        assert client.get('/style-packs/missing/versions').status_code == 404
