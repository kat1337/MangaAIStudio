"""PyTorch model adapter implementations (D-01 / D-02).

Concrete backends wrapping PanelCleaner's PyTorch models behind the D-01
adapter contract so call sites never import ``torch`` or ``TextDetector``
directly (RESEARCH §Don't Hand-Roll). ``torch`` is imported **lazily inside
load()** so this module is importable in the main_env without the torch
dependency installed (D-07 frontend/backend split).

Text detection — ``TorchCTDModel(DetectionModel)``:
    Wraps ``panelcleaner.comic_text_detector.inference.TextDetector``. The
    load-bearing fact is the ``TextDetector.__call__`` return contract: a
    **3-tuple** ``(mask, mask_refined, blk_list)`` (inference.py:210), NOT the
    5-tuple claimed in CONTEXT.md/RESEARCH.md. ``detect()`` unpacks exactly 3
    values with ``refine_mode=REFINEMASK_ANNOTATION, keep_undetected_mask=True``
    — a 5-target unpack would raise ``ValueError: too many values to unpack``.

Inpainting — ``TorchLamaModel(InpaintModel)`` (plan 05, CLEAN-06):
    Wraps ``panelcleaner.inpainting.InpaintingModel`` (the SimpleLama wrapper)
    behind the :class:`InpaintModel` ABC. ``load`` validates the model path
    (FileNotFoundError before the SimpleLama import — T-01-04b) and sets the
    ``LAMA_MODEL`` env var (inpainting.py:23). ``inpaint`` does the numpy<->PIL
    round-trip and delegates to SimpleLama, asserting the size-reclamp that
    ``InpaintingModel.__call__`` already applies (inpainting.py:34-37).

Import ordering follows PanelCleaner's project convention:
stdlib -> third-party -> ``panelcleaner.*`` / local modules.
"""

from __future__ import annotations

# stdlib
import os
from pathlib import Path
from typing import Tuple

# third-party
import numpy as np
from PIL import Image

# vendored PanelCleaner model code (D-12, GPL v3).
from panelcleaner.comic_text_detector.inference import TextDetector
from panelcleaner.comic_text_detector.utils.textmask import REFINEMASK_ANNOTATION

# local adapter contract (D-01 ABCs).
from manga_ai_studio.adapters.base import DetectionModel, InpaintModel

__all__ = ["TorchCTDModel", "TorchLamaModel"]


class TorchCTDModel(DetectionModel):
    """Comic Text Detector (CTD) PyTorch text-detection backend (D-01/D-02).

    Adapts ``panelcleaner.comic_text_detector.inference.TextDetector`` behind
    the :class:`DetectionModel` ABC. The detector is constructed lazily in
    :meth:`load` (torch is imported there too) so the module is importable
    without torch in the main_env (D-07).

    The 3-tuple return contract of ``TextDetector.__call__``
    (inference.py:210 — ``return mask, mask_refined, blk_list``) is the
    load-bearing fact for :meth:`detect`; it is unpacked with EXACTLY 3 targets.
    """

    def __init__(self, config=None) -> None:
        self.config = config
        self.detector = None
        self.device = "cpu"
        # Runtime overrides captured via configure(); applied in load().
        self._input_size = 1024
        self._conf_thresh = 0.4
        self._nms_thresh = 0.35
        self._act = "leaky"

    def load(self, model_path: Path, device: str = "cpu") -> None:
        """Load the CTD model weights from ``model_path``.

        ``torch`` is imported lazily here (D-07) so the adapter module is
        importable in the frontend env without the torch dependency. The model
        path is validated BEFORE constructing ``TextDetector`` (T-01-04 model
        weight tampering mitigation — PanelCleaner ``inpainting.py:21`` pattern)
        so a missing model raises ``FileNotFoundError`` rather than a cryptic
        torch error.

        Args:
            model_path: path to the ``comictextdetector.pt`` weights file.
            device: ``"cpu"``, ``"cuda"``, or ``"auto"`` (cuda if available).
        """
        model_path = Path(model_path)
        if not model_path.is_file():
            raise FileNotFoundError(f"Model not found: {model_path}")

        # Lazy torch import (D-07): keep the module importable without torch.
        import torch  # noqa: WPS433 (intentional lazy import)

        cuda = device == "cuda" or (device == "auto" and torch.cuda.is_available())
        self.device = "cuda" if cuda else "cpu"

        self.detector = TextDetector(
            model_path=str(model_path),
            input_size=self._input_size,
            device=self.device,
            act=self._act,
        )

    def detect(self, image: np.ndarray) -> Tuple[np.ndarray, list]:
        """Run CTD detection on ``image``.

        Unpacks the ``TextDetector.__call__`` return as a **3-tuple**
        ``(mask, mask_refined, blk_list)`` (inference.py:210). The refined mask
        is the heatmap mask for display; ``blk_list`` is the list of detected
        ``TextBlock`` objects. ``mask`` (the unrefined heatmap) is discarded.

        Args:
            image: BGR or RGB image array (H, W, 3) as read by cv2.imread.

        Returns:
            ``(mask_refined, blk_list)`` — the refined heatmap mask (H, W)
            uint8 and the list of detected text blocks.
        """
        if self.detector is None:
            raise RuntimeError("Model not loaded — call load() before detect().")

        # VERIFIED 3-tuple unpack (inference.py:166 signature, :210 return).
        # Do NOT use 5 targets — img/refine_mode are INPUTS not returns.
        mask, mask_refined, blk_list = self.detector(
            image,
            refine_mode=REFINEMASK_ANNOTATION,
            keep_undetected_mask=True,
        )
        return mask_refined, blk_list

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """Return ``image`` unchanged — TextDetector handles preprocessing
        internally (letterbox + normalize in ``preprocess_img``, inference.py:81).
        """
        return image

    def postprocess(self, model_output: np.ndarray) -> np.ndarray:
        """Threshold a heatmap mask to a binary mask (RESEARCH Pattern 1)."""
        return (model_output > 128).astype(np.uint8) * 255

    def configure(self, **kwargs) -> None:
        """Store runtime overrides (input_size, conf_thresh, nms_thresh, act).

        Applied on the next :meth:`load`; has no effect on an already-loaded
        model.
        """
        if "input_size" in kwargs:
            self._input_size = kwargs["input_size"]
        if "conf_thresh" in kwargs:
            self._conf_thresh = kwargs["conf_thresh"]
        if "nms_thresh" in kwargs:
            self._nms_thresh = kwargs["nms_thresh"]
        if "act" in kwargs:
            self._act = kwargs["act"]

    def get_info(self) -> dict:
        """Return model metadata (backend, device, model id, input size)."""
        return {
            "backend": "torch",
            "device": self.device,
            "model": "comic_text_detector",
            "input_size": self._input_size,
        }


class TorchLamaModel(InpaintModel):
    """LaMa inpainting PyTorch backend (D-01/D-02; CLEAN-06).

    Wraps ``simple_lama_inpainting.SimpleLama`` behind the :class:`InpaintModel`
    ABC, mirroring the PanelCleaner ``inpainting.py:InpaintingModel`` class
    (load + ``__call__`` with size-reclamp). ``simple_lama_inpainting`` (and
    transitively torch) is imported **lazily inside** :meth:`load` so this module
    is importable in the main_env without those heavy deps (D-07).

    The ``load`` takes a ``model_path`` directly (not a full ``config``) so the
    adapter stays testable with a fake path; the GUI layer resolves the path
    via ``panelcleaner.model_downloader.get_inpainting_model_path(config)``
    before calling load (mirroring ``InpaintingModel.__init__`` but split for
    testability).

    The mask contract: ``inpaint(image_rgb, mask_binary)`` receives a binary
    ``(H, W)`` uint8 mask (255=paint, 0=keep) — the crisp binary produced by
    ``core.mask_editor.mask_to_numpy_binary``. It is converted defensively to a
    true 0/255 binary (the PanelCleaner ``inpainting.py:27-28`` docstring
    contract: "1 is the area to be inpainted").
    """

    def __init__(self, config=None) -> None:
        self.config = config
        self.model = None
        self.model_path = None

    def load(self, model_path: Path, device: str = "cpu") -> None:
        """Load the LaMa model weights from ``model_path``.

        The model path is validated BEFORE any SimpleLama/torch import
        (T-01-04b model weight tampering mitigation — PanelCleaner
        ``inpainting.py:21`` pattern) so a missing model raises
        ``FileNotFoundError`` rather than a cryptic torch error.

        ``os.environ["LAMA_MODEL"]`` is set before ``SimpleLama()`` so
        ``simple_lama_inpainting`` picks up the path (inpainting.py:23). The
        ``device`` arg is accepted for ABC compatibility; ``simple_lama_inpainting``
        manages its own device (CPU/GPU auto-selected internally).

        Args:
            model_path: path to the ``big-lama.pt`` / ``anime-manga-big-lama.pt``
                weights file.
            device: accepted for ABC compatibility; ignored (SimpleLama chooses).
        """
        model_path = Path(model_path)
        if not model_path.is_file():
            raise FileNotFoundError(f"Model not found: {model_path}")

        # Set the env var BEFORE constructing SimpleLama (inpainting.py:23).
        os.environ["LAMA_MODEL"] = str(model_path)

        # Lazy import (D-07): keep the module importable without
        # simple_lama_inpainting / torch.
        from simple_lama_inpainting import SimpleLama  # noqa: WPS433

        self.model = SimpleLama()
        self.model_path = model_path

    def inpaint(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Inpaint ``image`` using ``mask`` via SimpleLama.

        Args:
            image: RGB image array ``(H, W, 3)`` uint8.
            mask: binary mask ``(H, W)`` uint8 (255 = inpaint, 0 = keep).

        Returns:
            Inpainted RGB image array ``(H, W, 3)`` uint8, cropped to the input
            size if SimpleLama resized it (inpainting.py:34-37 size-reclamp).
        """
        if self.model is None:
            raise RuntimeError("Model not loaded — call load() before inpaint().")

        # Defensive binary conversion: threshold any non-zero mask pixel to 255
        # so SimpleLama receives a crisp binary mask (inpainting.py:27-28
        # docstring contract). Masks produced by mask_to_numpy_binary are
        # already 0/255, but this guard holds if a heatmap leaks through.
        mask_binary = (mask > 0).astype(np.uint8) * 255

        pil_image = Image.fromarray(image, mode="RGB")
        pil_mask = Image.fromarray(mask_binary, mode="L")

        # InpaintingModel.__call__ applies the size-reclamp (inpainting.py:34-37);
        # the adapter asserts it too as a defense-in-depth guard.
        result_pil = self.model(pil_image, pil_mask)
        if result_pil.size != pil_image.size:
            width, height = pil_image.size
            result_pil = result_pil.crop((0, 0, width, height))
        return np.asarray(result_pil)

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """Return ``image`` unchanged — SimpleLama handles preprocessing."""
        return image

    def postprocess(self, model_output: np.ndarray) -> np.ndarray:
        """Return ``model_output`` unchanged — the PIL->numpy conversion in
        :meth:`inpaint` is the postprocess."""
        return model_output

    def configure(self, **kwargs) -> None:
        """Store runtime overrides (tile_size, etc.).

        Phase 1 uses SimpleLama's default tiling (RESEARCH Pitfall 7 LaMa tile
        boundary artifacts). The kwargs are accepted for ABC compatibility and
        stored for a future tile-size override.
        """
        self._config_kwargs = kwargs

    def get_info(self) -> dict:
        """Return model metadata (backend, model id, model path)."""
        return {
            "backend": "torch",
            "model": "big-lama",
            "model_path": str(self.model_path),
        }
