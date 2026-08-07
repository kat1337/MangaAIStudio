# SPDX-License-Identifier: GPL-3.0-or-later
# Vendored near-verbatim from PanelCleaner's upstream ocr_mangaocr.py module
# (GPL v3) per CONTEXT.md D-12 / D-14. The full singleton wrapper class is
# vendored (Phase 4 OCR adapter substrate — TEXT-02). Imports were rewritten
# from the upstream ``pcleaner`` package to the vendored ``panelcleaner``
# package; the ``supported_languages`` sibling was already vendored in plan
# 03-01 alongside this file.
#
# The upstream ``from manga_ocr import MangaOcr as MangaOcrModel`` import is
# kept at module top: this wrapper is itself lazy-imported by
# ``manga_ai_studio.adapters.torch_impl.TorchOCRModel.load`` (D-07), so the
# ``manga_ocr`` dep is only paid when OCR is actually used, not at adapter
# import time.

from pathlib import Path

from loguru import logger
from manga_ocr import MangaOcr as MangaOcrModel
from PIL import Image

import panelcleaner.ocr.supported_languages as osl


class MangaOcr:
    _instance = None
    _model = None
    _init_args = ((), {})

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            logger.info("Creating the MangaOcr instance")
            cls._instance = super(MangaOcr, cls).__new__(cls)
            cls._instance._model = None
            cls._instance._init_args = (args, kwargs)  # store just in case
        return cls._instance

    def __init__(self, *args, **kwargs):
        # Initialization logic is deferred to a separate method
        pass

    @staticmethod
    def langs() -> set[osl.LanguageCode]:
        return {osl.LanguageCode.jpn}

    def initialize_model(self, *args, **kwargs):
        if self._model is None:
            if args or kwargs:
                self._model = MangaOcrModel(*args, **kwargs)
            else:
                init_args = self._init_args
                self._model = MangaOcrModel(*init_args[0], **init_args[1])
        return self._model

    def __call__(self, img_or_path: Image.Image | Path | str, **kwargs) -> str:
        model = self.initialize_model()
        return model(img_or_path)
