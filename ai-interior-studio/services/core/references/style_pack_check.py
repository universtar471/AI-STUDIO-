"""Style Pack quality checks: roles, checksums, near-duplicates, small or blurry images (brief A5, item 4)."""
from __future__ import annotations

import hashlib
import io
from typing import Sequence

from PIL import Image, ImageFilter, ImageStat, UnidentifiedImageError
from pydantic import Field

from services.core.domain import Model, Reference, ReferenceRole, StylePack

MIN_SIDE_PX = 512
BLUR_THRESHOLD = 50.0  # Laplacian variance on a 512 px greyscale copy; GaussianBlur(2) on a room scene ~62, (3) ~39
DUPLICATE_DISTANCE = 6  # max differing bits of the 64-bit dHash

_LAPLACIAN = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128)


class ImageCheck(Model):
    artifact_id: str
    sha256: str
    width: int = 0
    height: int = 0
    dhash: str = ""
    sharpness: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class DuplicatePair(Model):
    first: str
    second: str
    distance: int


class StylePackReport(Model):
    images: list[ImageCheck] = Field(default_factory=list)
    duplicates: list[DuplicatePair] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)  # pack-level

    def warnings_for(self, artifact_id: str) -> list[str]:
        image = next((i for i in self.images if i.artifact_id == artifact_id), None)
        dup = [f'NEAR_DUPLICATE:{p.second if p.first == artifact_id else p.first}'
               for p in self.duplicates if artifact_id in (p.first, p.second)]
        return [*(image.warnings if image else []), *dup]


def dhash(image: Image.Image) -> int:
    """64-bit difference hash: robust to resizing and recompression, not to crops."""
    small = image.convert('L').resize((9, 8), Image.Resampling.LANCZOS)
    pixels = small.tobytes()  # mode L: one byte per pixel, row-major
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (pixels[row * 9 + col] > pixels[row * 9 + col + 1])
    return bits


def sharpness(image: Image.Image) -> float:
    grey = image.convert('L')
    grey.thumbnail((512, 512))
    return ImageStat.Stat(grey.filter(_LAPLACIAN)).var[0]


def check_image(artifact_id: str, data: bytes) -> ImageCheck:
    digest = hashlib.sha256(data).hexdigest()
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            width, height = image.size
            warnings = []
            if min(width, height) < MIN_SIDE_PX:
                warnings.append('SMALL_IMAGE')
            score = sharpness(image)
            if score < BLUR_THRESHOLD:
                warnings.append('BLURRY')
            return ImageCheck(artifact_id=artifact_id, sha256=digest, width=width, height=height,
                              dhash=f'{dhash(image):016x}', sharpness=round(score, 1), warnings=warnings)
    except (UnidentifiedImageError, OSError):
        return ImageCheck(artifact_id=artifact_id, sha256=digest, warnings=['UNREADABLE_IMAGE'])


def check_style_pack(pack: StylePack, images: dict[str, bytes]) -> StylePackReport:
    """`images` maps artifact_id -> bytes for every reference in the pack."""
    checks = [check_image(ref.artifact_id, images[ref.artifact_id]) for ref in pack.references if ref.artifact_id in images]
    warnings = _role_warnings(pack.references)
    missing = [ref.artifact_id for ref in pack.references if ref.artifact_id not in images]
    warnings += [f'MISSING_IMAGE:{a}' for a in missing]
    return StylePackReport(images=checks, duplicates=find_duplicates(checks), warnings=warnings)


def find_duplicates(checks: Sequence[ImageCheck]) -> list[DuplicatePair]:
    pairs = []
    hashed = [c for c in checks if c.dhash]
    for i, first in enumerate(hashed):
        for second in hashed[i + 1:]:
            distance = 0 if first.sha256 == second.sha256 else bin(int(first.dhash, 16) ^ int(second.dhash, 16)).count('1')
            if distance <= DUPLICATE_DISTANCE:
                pairs.append(DuplicatePair(first=first.artifact_id, second=second.artifact_id, distance=distance))
    return pairs


def _role_warnings(references: Sequence[Reference]) -> list[str]:
    roles = [ref.role for ref in references]
    warnings = []
    if ReferenceRole.STYLE_MASTER not in roles:
        warnings.append('NO_STYLE_MASTER')
    if roles.count(ReferenceRole.STYLE_MASTER) > 1:
        warnings.append('MULTIPLE_STYLE_MASTER')
    if ReferenceRole.BASE_PLAN in roles:
        warnings.append('BASE_PLAN_IN_STYLE_PACK')  # the base image belongs to the scene/room, not the pack
    return warnings


def replace_reference(pack: StylePack, reference_id: str, new: Reference) -> StylePack:
    """Swap one reference; returns the next version. The old version stays as it was."""
    if not any(ref.id == reference_id for ref in pack.references):
        raise KeyError(reference_id)
    return pack.next_version(references=[new if ref.id == reference_id else ref for ref in pack.references])
