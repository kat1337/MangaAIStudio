# SPDX-License-Identifier: GPL-3.0-or-later
# Vendored near-verbatim from PanelCleaner ``pcleaner/inpainting.py`` (GPL v3)
# per CONTEXT.md D-12. Only the ``InpaintingModel`` class (load + __call__) is
# vendored here — it is all Phase 1 interactive inpainting (CLEAN-06) needs.
# Imports were rewritten ``pcleaner.`` -> ``panelcleaner.``; the model-downloader
# dependency was vendored in plan 01-01.
#
# The batch ``inpaint_page`` driver and its MaskData/PageData dependencies
# (masker.py, structures.py, output_structures.py) are deferred to Phase 2
# (FLOW-03). Phase 1 interactive inpainting uses only ``InpaintingModel`` below.

import os
from pathlib import Path

from PIL import Image
from loguru import logger
from simple_lama_inpainting import SimpleLama

import panelcleaner.model_downloader as md


class InpaintingModel:
    def __init__(self, config) -> None:
        self.model_path = md.get_inpainting_model_path(config)
        # Sanity check: Make sure the model exists.
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Model not found: {self.model_path}")
        # Load the path into the env variable: LAMA_MODEL
        os.environ["LAMA_MODEL"] = str(self.model_path)
        self.simple_lama = SimpleLama()

    def __call__(self, image: Image, mask: Image) -> Image:
        """
        Inpaint the image using the mask.
        The mask must be a 1-channel image where 1 is the area to be inpainted and 0 is the area to keep.

        :param image: Input image.
        :param mask: Mask image.
        :return: The inpainted image.
        """
        # Run the model but ensure the output image is the same size as the input.
        inpainted_image = self.simple_lama(image, mask)
        if inpainted_image.size != image.size:
            width, height = image.size
            inpainted_image = inpainted_image.crop((0, 0, width, height))
        return inpainted_image


# The batch inpaint_page driver and its MaskData/PageData dependencies
# (masker.py, structures.py, output_structures.py) are deferred to Phase 2
# (FLOW-03). Phase 1 interactive inpainting uses only InpaintingModel above.
