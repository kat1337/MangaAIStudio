# Placeholder module satisfying the ``import panelcleaner.structures as st``
# reference at panelcleaner/image_ops.py:17 (vendored near-verbatim from
# PanelCleaner). The upstream module defines the batch-pipeline data structures
# (Box, PageData, MaskData, MaskerData, InpainterData, MaskFittingResults,
# MaskFittingAnalytic, InpaintingAnalytic) consumed by the batch masker and
# inpaint_page driver. Those batch structures + drivers are Phase 2 scope
# (FLOW-03), deferred here.
#
# image_ops.py references ``st.Box`` / ``st.MaskFittingResults`` only inside
# (a) function *annotations* — which are lazy strings under
#     ``from __future__ import annotations`` (set at the top of image_ops.py),
#     so they never resolve at def-time — and
# (b) the bodies of batch-only helpers (pick_best_mask, combine_best_masks,
#     generate_noise_mask, the visualize_* debug drawers) that Phase 1
#     interactive inpainting never calls.
# This empty placeholder is therefore sufficient for ``import image_ops`` to
# succeed without pulling in Phase 2's batch data structures.
