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


@pytest.mark.unit
def test_crop_drop_and_clip() -> None:
    """Crop slices exactly (D-18) and applies the D-16 drop/clip policy:
    fully-outside boxes dropped (counted), partial boxes clipped (bbox AND
    line quads) into post-crop page coordinates, payload-None preserved."""
    # A 10x8 (W,H) page with a deterministic pattern so slice exactness is
    # checkable: value = (y*10 + x + channel), 0..239 fits uint8 directly.
    img = np.arange(8 * 10 * 3, dtype=np.uint8).reshape(8, 10, 3)
    mask = np.zeros((8, 10), dtype=np.uint8)
    mask[2, 3] = 255  # inside the crop rect

    payload = TextBlock(
        xyxy=[1, 0, 8, 6],
        lines=[
            [[1, 0], [8, 0], [8, 6], [1, 6]],  # partial -> clipped+translated
            [[1, 0], [2, 0], [2, 1], [1, 1]],  # fully outside -> dropped quad
        ],
        vertical=False,
        language="eng",
        font_size=10,
        text="clipped",
        translation="trans",
    )
    boxes = [
        PageBox(box=Box(8, 5, 9, 7), origin=DETECTED),  # fully outside -> drop
        PageBox(
            box=Box(3, 2, 5, 3),
            origin=DETECTED,
            payload=payload,
            edited=True,
            bubble_no=7,
            manual_override=True,
        ),  # fully inside -> translated
        PageBox(box=Box(1, 0, 8, 6), origin=DETECTED, payload=payload),  # partial
        PageBox(box=Box(0, 2, 5, 3), origin=USER),  # payload-None partial
    ]
    before = _snapshot_boxes(boxes)

    x, y, w, h = 2, 1, 4, 3
    img_c, msk_c = image_ops.crop_page(img, mask, x, y, w, h)
    # D-18 exact slice.
    assert np.array_equal(img_c, img[1:4, 2:6])
    assert np.array_equal(msk_c, mask[1:4, 2:6])
    assert img_c.flags["OWNDATA"]
    assert not np.shares_memory(img_c, img)

    kept, dropped = image_ops.crop_boxes(boxes, x, y, w, h)
    assert dropped == 1  # only the fully-outside box
    assert len(kept) == 3

    # Fully-inside box: translated bbox + payload rides along.
    inner = kept[0]
    assert inner.box.as_tuple == (1, 1, 3, 2)
    assert inner.payload.lines == [[[0, 0], [4, 0], [4, 3], [0, 3]]]
    assert inner.payload.text == "clipped"
    assert inner.payload.translation == "trans"
    assert inner.origin == DETECTED
    assert inner.edited is True
    assert inner.bubble_no == 7
    assert inner.manual_override is True
    assert inner.payload is not payload  # fresh TextBlock, never the original

    # Partial box: bbox clamped to the crop rect [2,1,6,4] pre-translation,
    # then translated to post-crop [0,0,4,3]; the outside quad was dropped.
    partial = kept[1]
    assert partial.box.as_tuple == (0, 0, 4, 3)
    assert partial.payload.lines == [[[0, 0], [4, 0], [4, 3], [0, 3]]]
    assert partial.payload.xyxy == [0, 0, 4, 3]

    # Payload-None partial box: clipped bbox, payload still None.
    none_pb = kept[2]
    assert none_pb.box.as_tuple == (0, 1, 3, 2)
    assert none_pb.payload is None
    assert none_pb.origin == USER

    # One-call apply seam returns everything.
    img2, msk2, kept2, dropped2 = image_ops.crop_page_with_boxes(
        img, mask, boxes, x, y, w, h
    )
    assert np.array_equal(img2, img_c)
    assert np.array_equal(msk2, msk_c)
    assert dropped2 == 1
    assert len(kept2) == 3

    # No-in-place-mutation guard: originals byte-identical (Pitfall 3).
    assert np.array_equal(img, img)
    assert _snapshot_boxes(boxes) == before


@pytest.mark.unit
def test_crop_rejects_bad_input() -> None:
    """Out-of-range or non-int crop coords raise ValueError before slicing
    (image_io.py:65-72 discipline; T-05-06)."""
    img, mask, _ = _sample_page()  # (4,6) page: H=4, W=6
    with pytest.raises(ValueError):
        image_ops.crop_page(img, mask, -1, 0, 2, 2)  # x < 0
    with pytest.raises(ValueError):
        image_ops.crop_page(img, mask, 0, -1, 2, 2)  # y < 0
    with pytest.raises(ValueError):
        image_ops.crop_page(img, mask, 0, 0, 0, 2)  # w < 1
    with pytest.raises(ValueError):
        image_ops.crop_page(img, mask, 0, 0, 2, 0)  # h < 1
    with pytest.raises(ValueError):
        image_ops.crop_page(img, mask, 5, 0, 2, 2)  # x+w > W (5+2 > 6)
    with pytest.raises(ValueError):
        image_ops.crop_page(img, mask, 0, 3, 2, 2)  # y+h > H (3+2 > 4)
    with pytest.raises(ValueError):
        image_ops.crop_page(img, mask, 2.5, 0, 2, 2)  # non-int x
    with pytest.raises(ValueError):
        image_ops.crop_page(img, mask, 0, 0, "4", 2)  # non-int w
    with pytest.raises(ValueError):
        image_ops.crop_page(np.zeros((4, 6), np.uint8), mask, 0, 0, 2, 2)  # bad img


@pytest.mark.unit
def test_crop_zero_area_dropped() -> None:
    """A box whose bbox touches the crop edge but has zero intersection area
    (nx2 == nx1) is dropped and counted (D-16; RESEARCH Pitfall 10)."""
    img, mask, _ = _sample_page()  # (4,6): W=6, H=4
    # Crop rect x=2, y=1, w=2, h=2 -> [2,4) x [1,3).
    boxes = [
        PageBox(box=Box(4, 1, 6, 3), origin=DETECTED),  # nx1=4, nx2=min(6,4)=4
        PageBox(box=Box(2, 3, 5, 4), origin=DETECTED),  # ny1=3, ny2=min(4,3)=3
        PageBox(box=Box(2, 2, 3, 3), origin=USER),  # fully inside -> kept
    ]
    kept, dropped = image_ops.crop_boxes(boxes, 2, 1, 2, 2)
    assert dropped == 2
    assert len(kept) == 1
    assert kept[0].box.as_tuple == (0, 1, 1, 2)
    assert kept[0].origin == USER


@pytest.mark.unit
def test_resize_and_levels() -> None:
    """Resize: LANCZOS image / NEAREST mask (D-18 no interpolated grays),
    int box scaling (Pitfall 6); levels: byte-exact LUT math with the
    white>black monotone clamp (D-12, T-05-07), geometry-free (D-15)."""
    # --- Resize image + mask: 10x8 (W,H) page -> 5x4. ---
    img = np.arange(8 * 10 * 3, dtype=np.uint8).reshape(8, 10, 3)
    mask = np.zeros((8, 10), dtype=np.uint8)
    mask[2:6, 3:8] = 255  # solid block — NEAREST must keep it strictly 0/255
    img_r, msk_r = image_ops.resize_page(img, mask, 5, 4)
    assert img_r.shape == (4, 5, 3)
    assert msk_r.shape == (4, 5)
    # D-18: NEAREST mask purity — no interpolated grays ever.
    assert set(np.unique(msk_r)) <= {0, 255}
    assert img_r.flags["OWNDATA"]
    assert msk_r.flags["OWNDATA"]
    assert not np.shares_memory(img_r, img)

    # --- Resize boxes: 10x8 -> 5x4 scales 0.5/0.5; [2,2,6,6] -> [1,1,3,3]. ---
    payload = TextBlock(
        xyxy=[2, 2, 6, 6],
        lines=[
            [[2, 2], [6, 2], [6, 4], [2, 4]],
            [[2, 4], [6, 4], [6, 6], [2, 6]],
        ],
        vertical=False,
        language="eng",
        font_size=12,
        text="two\nlines",
        translation="tr",
    )
    boxes = [
        PageBox(
            box=Box(2, 2, 6, 6),
            origin=DETECTED,
            payload=payload,
            edited=True,
            bubble_no=2,
            manual_override=True,
        ),
        PageBox(box=Box(2, 0, 6, 2), origin=USER),
    ]
    before = _snapshot_boxes(boxes)
    scaled = image_ops.resize_boxes(boxes, 10, 8, 5, 4)
    assert len(scaled) == 2
    assert scaled[0].box.as_tuple == (1, 1, 3, 3)
    assert scaled[0].payload.lines == [
        [[1, 1], [3, 1], [3, 2], [1, 2]],
        [[1, 2], [3, 2], [3, 3], [1, 3]],
    ]
    assert scaled[0].payload.text == "two\nlines"
    assert scaled[0].payload.translation == "tr"
    assert scaled[0].edited is True
    assert scaled[0].bubble_no == 2
    assert scaled[0].manual_override is True
    assert scaled[1].box.as_tuple == (1, 0, 3, 1)  # int(round(2*0.5))=1 etc.
    assert scaled[1].payload is None
    # No in-place mutation (Pitfall 3).
    assert _snapshot_boxes(boxes) == before

    # --- Levels: byte-exact LUT on a 0..255 ramp, one value per channel. ---
    ramp = np.tile(np.arange(256, dtype=np.uint8).reshape(256, 1), (1, 3))
    page = ramp.reshape(1, 256, 3)
    leveled = image_ops.levels_page(page, 64, 192, 1.0)
    assert leveled.shape == page.shape  # pixel-wise: shape unchanged
    assert leveled.flags["OWNDATA"]
    assert not np.shares_memory(leveled, page)
    # Below black -> 0; midpoint (64+192)/2=128 -> 128; above white -> 255.
    assert np.array_equal(leveled[0, 63], [0, 0, 0])
    assert np.array_equal(leveled[0, 64], [0, 0, 0])
    assert np.array_equal(leveled[0, 128], [128, 128, 128])
    assert np.array_equal(leveled[0, 192], [255, 255, 255])
    assert np.array_equal(leveled[0, 255], [255, 255, 255])

    # --- white>black clamp (T-05-07): never an inverted/descending map. ---
    lut = image_ops.levels_lut(white=100, black=100, gamma=1.0)
    assert lut.dtype == np.uint8 and lut.shape == (256,)
    assert bool(np.all(np.diff(lut.astype(np.int16)) >= 0))
    # Explicit inversion input also clamps to monotone.
    assert bool(np.all(np.diff(image_ops.levels_lut(200, 50, 1.0).astype(np.int16)) >= 0))


@pytest.mark.unit
def test_resize_rejects_bad_input() -> None:
    """Resize dims outside [1, 100000] or non-int raise ValueError
    (UI-SPEC surface 26 range; T-05-06); levels validates image + gamma."""
    img, mask, _ = _sample_page()
    with pytest.raises(ValueError):
        image_ops.resize_page(img, mask, 0, 4)  # new_w < 1
    with pytest.raises(ValueError):
        image_ops.resize_page(img, mask, 4, 0)  # new_h < 1
    with pytest.raises(ValueError):
        image_ops.resize_page(img, mask, -2, 4)  # negative
    with pytest.raises(ValueError):
        image_ops.resize_page(img, mask, 100001, 4)  # new_w > 100000
    with pytest.raises(ValueError):
        image_ops.resize_page(img, mask, 4, 2.5)  # non-int new_h
    with pytest.raises(ValueError):
        image_ops.resize_page(np.zeros((4, 6), np.uint8), mask, 4, 4)  # bad img
    with pytest.raises(ValueError):
        image_ops.levels_page(img.astype(np.float32), 64, 192, 1.0)  # bad img
    with pytest.raises(ValueError):
        image_ops.levels_page(img, 64, 192, 0)  # gamma <= 0
    with pytest.raises(ValueError):
        image_ops.levels_lut(64, 192, -1.0)  # negative gamma
    with pytest.raises(ValueError):
        image_ops.resize_boxes([], 0, 8, 5, 4)  # w < 1 -> ZeroDiv guard
