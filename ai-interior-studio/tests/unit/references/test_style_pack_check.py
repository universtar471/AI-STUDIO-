import io
import random

from PIL import Image, ImageDraw, ImageFilter

from services.core.domain import Project, Reference, ReferenceRole as R, StylePack
from services.core.references import check_image, check_style_pack, replace_reference


def room_image(seed=1, size=(1024, 768)) -> Image.Image:
    rng = random.Random(seed)
    image = Image.new('RGB', size, (200, 190, 170))
    draw = ImageDraw.Draw(image)
    for _ in range(40):
        x, y = rng.randrange(size[0] - 20), rng.randrange(size[1] - 20)
        draw.rectangle([x, y, x + rng.randrange(20, 200), y + rng.randrange(20, 200)],
                       outline=(rng.randrange(255),) * 3, width=2,
                       fill=(rng.randrange(255), rng.randrange(255), rng.randrange(255)))
    return image


def encode(image: Image.Image, fmt='PNG', **options) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, fmt, **options)
    return buffer.getvalue()


def test_sharp_large_image_has_no_warning():
    check = check_image('a', encode(room_image()))
    assert check.warnings == []
    assert (check.width, check.height) == (1024, 768)
    assert len(check.sha256) == 64 and len(check.dhash) == 16


def test_small_and_blurry_and_unreadable():
    assert 'SMALL_IMAGE' in check_image('s', encode(room_image(size=(400, 300)))).warnings
    assert 'BLURRY' in check_image('b', encode(room_image().filter(ImageFilter.GaussianBlur(4)))).warnings
    assert check_image('u', b'not an image').warnings == ['UNREADABLE_IMAGE']


def test_near_duplicate_found_across_resize_and_jpeg():
    original = room_image(1)
    copy = encode(original.resize((800, 600)), 'JPEG', quality=70)
    other = encode(room_image(2))
    pack = StylePack(name='Oak', references=[
        Reference(artifact_id='orig', role=R.STYLE_MASTER),
        Reference(artifact_id='copy', role=R.FLOOR),
        Reference(artifact_id='other', role=R.WALL),
    ])
    report = check_style_pack(pack, {'orig': encode(original), 'copy': copy, 'other': other})
    assert [(p.first, p.second) for p in report.duplicates] == [('orig', 'copy')]
    assert report.warnings_for('copy') == ['NEAR_DUPLICATE:orig']
    assert report.warnings_for('other') == []
    assert report.warnings == []


def test_pack_role_warnings_and_missing_image():
    pack = StylePack(name='x', references=[
        Reference(artifact_id='a', role=R.STYLE_MASTER), Reference(artifact_id='b', role=R.STYLE_MASTER),
        Reference(artifact_id='c', role=R.BASE_PLAN),
    ])
    report = check_style_pack(pack, {'a': encode(room_image(1)), 'b': encode(room_image(3))})
    assert report.warnings == ['MULTIPLE_STYLE_MASTER', 'BASE_PLAN_IN_STYLE_PACK', 'MISSING_IMAGE:c']
    assert 'NO_STYLE_MASTER' in check_style_pack(StylePack(name='empty'), {}).warnings


def test_replacing_one_reference_creates_version_and_keeps_history(db):
    project = db.projects.add(Project(name='P'))
    floor = Reference(artifact_id='floor-1', role=R.FLOOR)
    v1 = db.style_packs.add_version(StylePack(name='Oak', project_id=project.id, references=[
        Reference(artifact_id='master', role=R.STYLE_MASTER), floor]))
    v2 = db.style_packs.add_version(replace_reference(v1, floor.id, Reference(artifact_id='floor-2', role=R.FLOOR)))
    assert v2.version == v1.version + 1
    assert [r.artifact_id for r in db.style_packs.get(v1.id).references] == ['master', 'floor-2']
    old = db.style_packs.get(v1.id, version=1)
    assert [r.artifact_id for r in old.references] == ['master', 'floor-1']
    assert list(db.style_packs.versions(v1.id)) == [1, 2]
