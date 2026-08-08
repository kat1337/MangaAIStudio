"""Tests for ``manga_ai_studio/core/image_ops.py`` (plan 05-02, PROJ-04).

This is the Phase 5 Wave-0 suite for the pure pixel + geometry math module —
rotate (90° steps, D-10), crop (exact slice + D-16 drop/clip), resize
(LANCZOS image / NEAREST mask, D-18), levels (numpy LUT, D-12). The
load-bearing contracts under test:

- D-15/D-17: geometry ops transform the mask AND every box's bbox AND
  ``TextBlock.lines`` quad polygons along with the page image.
- D-18: pixel-exact mask transforms (np.rot90 equality, exact slice, NEAREST
  resize with no interpolated grays).
- RESEARCH Pitfall 2/3: every transform returns ``.copy()``-detached arrays
  and fresh PageBox/TextBlock objects — the originals (image, mask, frozen
  Box, ``payload.lines``) are byte-identical after each op (undo-snapshot
  safety for plan 05-04).
- D-16: crop drops fully-outside boxes with a returned count and clips
  partial boxes' bbox AND line quads to the crop rect.

The tests are pure stdlib+numpy+PIL; they carry the ``unit`` marker and
require NO Qt (headless CI — the same discipline as ``test_box_model.py``).
The rotation expectations are computed with an independent in-test
implementation of the RESEARCH Common Operation 2 math (never importing the
module's ``_rotate_point``), so a transcription error in the module surfaces.
"""

from __future__ import annotations

import copy

import numpy as np
import pytest
from PIL import Image

from manga_ai_studio.core.box_model import DETECTED, USER, PageBox
from panelcleaner.comic_text_detector.utils.textblock import TextBlock
from panelcleaner.structures import Box

from manga_ai_studio.core import image_ops


def _rotate_point_expected(x: int, y: int, w: int, h: int, k: int) -> tuple[int, int]:
    """Independent copy of the RESEARCH Common Operation 2 rotation math."""
    if k == -1:  # 90 CW
        return h - 1 - y, x
    if k == 1:  # 90 CCW
        return y, w - 1 - x
    if k == 2:  # 180
        return w - 1 - x, h - 1 - y
    return x, y


def _expected_box(box: Box, w: int, h: int, k: int) -> Box:
    x1, y1, x2, y2 = box.as_tuple
    nx1, ny1 = _rotate_point_expected(x1, y1, w, h, k)
    nx2, ny2 = _rotate_point_expected(x2, y2, w, h, k)
    return Box(min(nx1, nx2), min(ny1, ny2), max(nx1, nx2), max(ny1, ny2))


def _expected_lines(lines: list, w: int, h: int, k: int) -> list:
    return [
        [list(_rotate_point_expected(px, py, w, h, k)) for px, py in quad]
        for quad in lines
    ]


def _sample_page() -> tuple[np.ndarray, np.ndarray, list[PageBox]]:
    """A 4x6 (H,W) page: asymmetric image, binary mask, two PageBoxes.

    Image: a bright 2x1 block at the top-left corner on black — asymmetric,
    so every 90° orientation is distinguishable. Mask: one nonzero pixel at
    a known offset. Box A: a 2-line payload box with every Phase 4 peer field
    set (edited/bubble_no/manual_override); Box B: a payload-None user box.
    """
    img = np.zeros((4, 6, 3), dtype=np.uint8)
    img[0, 0:2] = [200, 100, 50]
    mask = np.zeros((4, 6), dtype=np.uint8)
    mask[2, 5] = 255
    payload_a = TextBlock(
        xyxy=[1, 2, 5, 3],
        lines=[
            [[1, 2], [5, 2], [5, 3], [1, 3]],
            [[1, 3], [5, 3], [5, 4], [1, 4]],
        ],
        vertical=False,
        language="ja",
        font_size=12,
        text="\u7b2c\u4e00\u884c\n\u7b2c\u4e8c\u884c",
        translation="First line\nSecond line",
    )
    box_a = PageBox(
        box=Box(1, 2, 5, 3),
        origin=DETECTED,
        payload=payload_a,
        edited=True,
        bubble_no=3,
        manual_override=True,
    )
    box_b = PageBox(box=Box(0, 0, 2, 1), origin=USER)
    return img, mask, [box_a, box_b]


def _snapshot_boxes(boxes: list[PageBox]) -> list:
    """Deep copies of box geometry + payload state for the untouched-guard."""
    return [
        (
            pb.box.as_tuple,
            None if pb.payload is None else copy.deepcopy(pb.payload.lines),
            None if pb.payload is None else pb.payload.text,
            None if pb.payload is None else pb.payload.translation,
            pb.origin,
            pb.edited,
            pb.bubble_no,
            pb.manual_override,
        )
        for pb in boxes
    ]


@pytest.mark.unit
def test_rotate_transforms_all() -> None:
    """k=-1/1/2 rotate image + mask pixel-exactly AND every box's bbox + line
    quads with fresh objects; the originals stay byte-identical (D-15/D-17/
    D-18; Pitfall 2/3)."""
    img, mask, boxes = _sample_page()
    h, w = img.shape[:2]
    before_img = img.copy()
    before_mask = mask.copy()
    before_boxes = _snapshot_boxes(boxes)

    for k in (-1, 1, 2):
        new_img, new_mask = image_ops.rotate_page(img, mask, k)
        # D-18 pixel-exact: image+mask equal np.rot90 elementwise; dims swap
        # for the quarter turns (k=2 keeps (H,W)).
        assert new_img.shape == np.rot90(img, k=k).shape
        assert np.array_equal(new_img, np.rot90(img, k=k))
        assert np.array_equal(new_mask, np.rot90(mask, k=k))
        # .copy() detachment (Pitfall 2): results own their buffers.
        assert new_img.flags["OWNDATA"]
        assert new_mask.flags["OWNDATA"]
        assert not np.shares_memory(new_img, img)
        assert not np.shares_memory(new_mask, mask)

        rotated = image_ops.rotate_boxes(boxes, w, h, k)
        assert len(rotated) == 2
        # Box A: bbox + line quads equal the research math (D-15/D-17).
        assert rotated[0].box == _expected_box(boxes[0].box, w, h, k)
        assert rotated[0].payload.lines == _expected_lines(
            boxes[0].payload.lines, w, h, k
        )
        # Payload fields ride along (vertical/language/font_size/text/
        # translation + Phase 4 peers).
        assert rotated[0].origin == DETECTED
        assert rotated[0].payload.vertical == boxes[0].payload.vertical
        assert rotated[0].payload.language == "ja"
        assert rotated[0].payload.font_size == 12
        assert rotated[0].payload.text == "\u7b2c\u4e00\u884c\n\u7b2c\u4e8c\u884c"
        assert rotated[0].payload.translation == "First line\nSecond line"
        assert rotated[0].edited is True
        assert rotated[0].bubble_no == 3
        assert rotated[0].manual_override is True
        # Fresh payload per box — never the original TextBlock.
        assert rotated[0].payload is not boxes[0].payload
        # Box B: payload-None box keeps payload None, bbox transformed.
        assert rotated[1].box == _expected_box(boxes[1].box, w, h, k)
        assert rotated[1].payload is None
        assert rotated[1].origin == USER

    # No-in-place-mutation guard (Pitfall 3): originals byte-identical.
    assert np.array_equal(img, before_img)
    assert np.array_equal(mask, before_mask)
    assert _snapshot_boxes(boxes) == before_boxes


@pytest.mark.unit
def test_rotate_composes_identity() -> None:
    """Two 180° rotations return the identity geometry and dims (the probe's
    rotation-composition truth)."""
    img, mask, boxes = _sample_page()
    h, w = img.shape[:2]

    img2, mask2 = image_ops.rotate_page(img, mask, 2)
    img4, mask4 = image_ops.rotate_page(img2, mask2, 2)
    assert img4.shape == img.shape
    assert np.array_equal(img4, img)
    assert np.array_equal(mask4, mask)

    boxes2 = image_ops.rotate_boxes(boxes, w, h, 2)
    boxes4 = image_ops.rotate_boxes(boxes2, w, h, 2)
    for original, final in zip(boxes, boxes4):
        assert final.box == original.box
        if original.payload is not None:
            assert final.payload.lines == original.payload.lines
            assert final.payload.text == original.payload.text
        assert final.origin == original.origin
        assert final.edited == original.edited
        assert final.bubble_no == original.bubble_no
        assert final.manual_override == original.manual_override


@pytest.mark.unit
def test_rotate_rejects_bad_shapes() -> None:
    """Non-(H,W,3) image or non-(H,W) mask raises ValueError before any
    work (image_io.py:65-72 discipline; T-05-06)."""
    img, mask, _ = _sample_page()
    with pytest.raises(ValueError):
        image_ops.rotate_page(np.zeros((4, 6), np.uint8), mask, -1)  # 2D image
    with pytest.raises(ValueError):
        image_ops.rotate_page(np.zeros((4, 6, 4), np.uint8), mask, -1)  # 4 ch
    with pytest.raises(ValueError):
        image_ops.rotate_page(img.astype(np.float32), mask, -1)  # wrong dtype
    with pytest.raises(ValueError):
        image_ops.rotate_page(img, np.zeros((4, 6, 1), np.uint8), -1)  # 3D mask
    with pytest.raises(ValueError):
        image_ops.rotate_page(img, np.zeros((5, 6), np.uint8), -1)  # H mismatch
    with pytest.raises(ValueError):
        image_ops.rotate_page(img, mask.astype(np.float64), -1)  # mask dtype
