---
phase: 04-ocr-recognition-text-editing
plan: 03
subsystem: ocr-adapter (vendored MangaOcr singleton + TorchOCRModel + factory)
tags: [ocr, text-editing, manga-ocr, adapter, tdd, headless, vendoring, gpl]
requires:
  - Phase 01 D-01/D-07 adapter contract (OCRModel ABC, lazy-import discipline)
  - Phase 01 D-12 vendoring discipline (GPL v3 → GPL v3, pcleaner. → panelcleaner.)
  - Phase 03 plan 03-01 vendored panelcleaner/ocr/supported_languages.py (the re-path target sibling)
provides:
  - panelcleaner.ocr.ocr_mangaocr.MangaOcr (singleton wrapper, vendored near-verbatim)
  - manga_ai_studio.adapters.torch_impl.TorchOCRModel (OCRModel subclass; load/recognize/preprocess/postprocess/configure/get_info)
  - backend_factory("ocr", "torch") -> TorchOCRModel (factory.py branch resolved)
  - backend_factory("ocr", "onnx") -> NotImplementedError (D-14 designed-in hook, not built-out)
affects:
  - panelcleaner/ocr/ocr_mangaocr.py
  - manga_ai_studio/adapters/torch_impl.py
  - manga_ai_studio/adapters/factory.py
  - tests/test_core/test_torch_ocr_model.py
  - tests/test_core/test_adapters.py
  - tests/test_detection/test_ctd_adapter.py
tech-stack:
  added: []
  patterns:
    - OCR adapter mirrors TorchLamaModel shape-for-shape (lazy-import in load(), numpy→PIL in recognize(), plain str return, "Model not loaded" guard) — RESEARCH Pattern 1
    - numpy→PIL round-trip via Image.fromarray(image, mode="RGB") before the model call (Pitfall 2: manga-ocr's __call__ accepts PIL.Image, NOT numpy)
    - singleton wrapper (load-once per session) as the T-4-06 DoS mitigation — no repeated ~450MB HF downloads
    - lazy module-level import in the vendored wrapper (itself lazy-imported by TorchOCRModel.load) keeps the adapter importable without manga_ocr (D-07)
    - FakeMangaOcr injection + is_ocr_downloaded() skip-gate so CI forces no model download
key-files:
  created:
    - panelcleaner/ocr/ocr_mangaocr.py
    - tests/test_core/test_torch_ocr_model.py
  modified:
    - manga_ai_studio/adapters/torch_impl.py
    - manga_ai_studio/adapters/factory.py
    - tests/test_core/test_adapters.py
    - tests/test_detection/test_ctd_adapter.py
decisions:
  - Kept the upstream `langs()` staticmethod (returns {osl.LanguageCode.jpn}) in the vendored MangaOcr — D-14 leaves the language hook designed-in even though the v1 UI does not consume it; dropping surface was optional and the near-verbatim copy is the cleaner D-12 outcome
  - TorchOCRModel.load does NOT validate model_path as an existing file (unlike TorchLamaModel/TorchCTDModel) because manga-ocr resolves its own model from the HF cache via initialize_model(); model_path is accepted for ABC symmetry and stored, the GUI worker cache-checks via is_ocr_downloaded() before triggering the download (CR-11 pattern, Plan 06)
  - Kept `from manga_ocr import MangaOcr as MangaOcrModel` at the vendored module's top (NOT made lazy inside the wrapper) because the wrapper is itself lazy-imported by TorchOCRModel.load — so the manga_ocr dep is paid only when OCR is actually used, not at adapter import time
  - test_module_imports_without_manga_ocr uses an isolated subprocess with a MetaPathFinder blocking manga_ocr (NOT in-process importlib.reload) because reloading rebinds the adapter classes and poisons isinstance() checks for sibling factory tests sharing the process (Rule 1 fix)
metrics:
  duration: 7 min
  completed: 2026-08-06
  tasks: 2
  files: 6
status: complete
---

# Phase 04 Plan 03: OCR Adapter (Vendored MangaOcr + TorchOCRModel + Factory) Summary

Built the OCR adapter (D-14, TEXT-02) HEADLESSLY and in parallel with the already-landed Plans 01/02: vendored PanelCleaner's MangaOcr singleton wrapper near-verbatim into `panelcleaner/ocr/ocr_mangaocr.py` (re-pathed `pcleaner.` → `panelcleaner.`, GPL v3 header preserved), implemented `TorchOCRModel` in `adapters/torch_impl.py` mirroring `TorchLamaModel`'s exact shape (lazy-import in `load()`, numpy→PIL round-trip in `recognize()`, plain `str` return — Pitfall 2), and replaced the `backend_factory("ocr")` `NotImplementedError` stub with the `TorchOCRModel` resolution (plus the `onnx` branch raising `NotImplementedError` as the D-14 designed-in hook). All manga-ocr-dependent tests skip-gate on `is_ocr_downloaded()` so CI forces no ~450MB download. Plan 06 (OCR dispatcher) is now pure threading glue — the adapter substrate is complete and decoupled from the GUI.

## What Was Built

### Task 1 — Vendored MangaOcr singleton wrapper (D-14, GPL v3 → GPL v3)

`panelcleaner/ocr/ocr_mangaocr.py` (NEW, vendored near-verbatim from `../PanelCleaner/pcleaner/ocr/ocr_mangaocr.py`):

- **GPL v3 header** matching the established project convention used by `panelcleaner/inpainting.py` and `panelcleaner/structures.py` (`SPDX-License-Identifier: GPL-3.0-or-later` + the vendoring note), per D-12/D-14.
- **`class MangaOcr`** singleton wrapper copied near-verbatim: class attrs `_instance`, `_model`, `_init_args = ((), {})`; `__new__` creating the singleton (load-once per session); deferred `__init__` (pass); `initialize_model(*args, **kwargs)` lazy-constructing `MangaOcrModel(*args, **kwargs)` from the `manga_ocr` package on first call; `__call__(img_or_path)` accepting `Image.Image | Path | str` and returning `model(img_or_path) -> str`.
- **`langs()` staticmethod** kept (returns `{osl.LanguageCode.jpn}`) — the designed-in language hook (D-14 leaves it in; the v1 UI does not consume it).
- **Re-path**: `import pcleaner.ocr.supported_languages as osl` → `import panelcleaner.ocr.supported_languages as osl` (the sibling already vendored in plan 03-01). 0 `pcleaner.` references remain.
- **Module-top import kept**: `from manga_ocr import MangaOcr as MangaOcrModel` stays at the top because the wrapper is itself lazy-imported by `TorchOCRModel.load` — so `manga_ocr` is paid only when OCR is used, not at adapter import (D-07).
- Module imports cleanly alongside `supported_languages.py` (sibling co-existence verified).

### Task 2 — TorchOCRModel adapter + factory fix (TDD)

`manga_ai_studio/adapters/torch_impl.py` (added `TorchOCRModel(OCRModel)` after `TorchLamaModel`):

- **`__init__(self, config=None)`**: `self.config = config; self.model = None; self.model_path = None` — mirrors `TorchLamaModel.__init__` exactly.
- **`load(self, model_path, device="cpu")`**: lazy `from panelcleaner.ocr.ocr_mangaocr import MangaOcr` (D-07); `self.model = MangaOcr()` (singleton — load-once); `self.model.initialize_model()` (triggers the first-run HF download inside the worker thread, Plan 06 enforces off-GUI); `self.model_path = model_path`. The `model_path` is informational for manga-ocr (resolves from HF cache) but kept for ABC symmetry — NOT validated as a file, unlike `TorchLamaModel`/`TorchCTDModel`, because manga-ocr owns its model resolution.
- **`recognize(self, image: np.ndarray) -> str`**: guard `if self.model is None: raise RuntimeError("Model not loaded — call load() before recognize().")`; `pil_image = Image.fromarray(image, mode="RGB")`; `return self.model(pil_image)` (str). The numpy→PIL conversion is the Pitfall 2 load-bearing line (manga-ocr's `__call__` accepts `PIL.Image`, NOT numpy — verified in `manga_ocr/ocr.py`).
- **`preprocess` / `postprocess` / `configure` / `get_info`** — copied verbatim shape from `TorchLamaModel` (return-input-unchanged / return-metadata-dict). `get_info` returns `{"backend": "torch", "model": "manga-ocr/kha-white/manga-ocr-base", "model_path": ...}`.

`manga_ai_studio/adapters/factory.py`: replaced the two-line `if kind == "ocr": raise NotImplementedError("OCR adapter lands in Phase 4")` stub with the mirror of the detection block:
```python
if kind == "ocr":
    if backend == "torch":
        from manga_ai_studio.adapters.torch_impl import TorchOCRModel
        return TorchOCRModel()
    if backend == "onnx":
        raise NotImplementedError("ONNX OCR backend lands in a future phase")
    raise ValueError(f"Unknown backend: {kind}/{backend}")
```
The lazy import keeps the factory importable without `manga_ocr` (D-07).

Tests:
- `tests/test_core/test_torch_ocr_model.py` (NEW, 7 tests): `test_load_lazy_imports_model`, `test_recognize_converts_numpy_to_pil` (asserts `Image.fromarray` called with `mode="RGB"`), `test_recognize_returns_str`, `test_recognize_raises_when_not_loaded`, `test_module_imports_without_manga_ocr` (isolated subprocess), `test_load_constructs_via_panelcleaner_module` (guards the singleton seam), and the skip-gated `test_recognize_real_model_end_to_end` (integration marker, runs only when `is_ocr_downloaded()` is True).
- `tests/test_core/test_adapters.py` (extended): `test_ocr_factory_returns_torch_ocr_model`, `test_ocr_factory_onnx_not_implemented`.

## Verification

```
python -m pytest tests/test_core/test_torch_ocr_model.py tests/test_core/test_adapters.py -q
# 11 passed (7 OCR-model + 4 adapters; includes the cached real-model integration test)

python -m pytest tests/ -q
# 315 passed, 1 failed (PRE-EXISTING — see Deviations)
```

Acceptance criteria verified:
- `grep -c "class MangaOcr:" panelcleaner/ocr/ocr_mangaocr.py` = 1.
- `grep -c "import panelcleaner.ocr.supported_languages"` = 1; `grep -c "pcleaner\."` = 0 (full re-path).
- `grep -i -c "GPL"` ≥ 1 (license header preserved).
- `grep -c "class TorchOCRModel" torch_impl.py` = 1; `grep -c "def recognize"` = 1; `grep -c "Image.fromarray" torch_impl.py` = 4 (Lama 2 + OCR 1 + comment 1; both adapters do numpy→PIL).
- Old OCR stub gone (`grep -c 'OCR adapter lands in Phase 4' factory.py` = 0); `grep -c "TorchOCRModel()" factory.py` = 1.
- `backend_factory('ocr', 'torch')` returns `TorchOCRModel`; `torch_impl` imports without manga_ocr loaded at import time.

## Deviations from Plan

None — the plan executed exactly as written. Two in-flight adjustments that conform to the plan's intent (Rule 1/3 auto-fixes, not plan deviations):

- **[Rule 1 - Bug] Test poisons session state via `importlib.reload`**: the original `test_module_imports_without_manga_ocr` used in-process `importlib.reload(torch_impl)`, which rebinds the adapter class objects in the shared module namespace. Sibling factory tests (`test_factory_torch_detection`, `test_factory_inpainting_torch`) that did `from ... import TorchLamaModel` at module import held the OLD class identity while the factory returned NEW-class instances → `isinstance` failed, but only in the full-suite run (not in isolation). Rewrote the test to use an isolated subprocess with a `MetaPathFinder` blocking `manga_ocr`, which faithfully verifies the lazy-import invariant without polluting class identity. The D-07 invariant (module importable without manga_ocr) is still the assertion; only the verification mechanism changed.
- **[Rule 3 - Blocking] Stale pre-existing factory test encoded the removed stub**: `tests/test_detection/test_ctd_adapter.py::test_factory_ocr_not_implemented` asserted the OLD behavior (`backend_factory("ocr", "torch")` raises `NotImplementedError` matching "Phase 4"). My task explicitly removes that stub, so the test was stale. Updated it to `test_factory_ocr_torch_returns_ocr_model` — mirroring exactly how plan 05 updated the analogous `test_factory_inpainting_torch_returns_lama_model` when `TorchLamaModel` landed (asserts `isinstance(TorchOCRModel)` + the onnx `NotImplementedError`). Same contract-update pattern, established project convention.

No auth gates. No architectural changes (Rule 4). No package installs.

## Known Stubs

None that block the plan goal. `TorchOCRModel.preprocess` / `postprocess` / `configure` are intentional ABC-shape stubs (return-input-unchanged / store-kwargs) copied verbatim from the proven `TorchLamaModel` — manga-ocr handles its own preprocessing internally and Phase 4 uses its defaults. The vendored `MangaOcr.langs()` staticmethod is a designed-in language hook (D-14: no config UI in v1) — intentional, documented, not a stub. No placeholder text/TODO/FIXME in any new code path.

## Deferred Issues

- **`tests/test_gui_boxes.py::test_moved_box_via_real_events_persists_round_trip`** (PRE-EXISTING, out of scope): a real-event body-drag move lands a box at `(69,69,129,129)` instead of the asserted `(70,70,130,130)` — a 1px drag-coordinate rounding difference. Verified failing identically against pristine pre-04-01 source (commit `210a178`) in plans 04-01 and 04-02. It is a GUI drag-simulation rounding issue that does NOT exercise the OCR adapter, the vendored MangaOcr, the factory, or any new code path in this plan (all pure headless modules + the adapter ABC). Re-confirmed failing in this plan's full-suite run (`1 failed, 315 passed`). Already logged to `.planning/phases/04-ocr-recognition-text-editing/deferred-items.md`; not fixed.

## Threat Surface

No new security-relevant surface beyond the plan's `<threat_model>`. The HF cache → model load boundary (T-4-05/T-4-06) is the only trust boundary touched, and it is mitigated exactly as designed: the vendored MangaOcr is a singleton (load-once per session, no repeated ~450MB downloads — T-4-06 DoS mitigation), and the GUI worker (Plan 06) cache-checks via `is_ocr_downloaded()` before triggering `initialize_model()` (CR-11 pattern). The `manga_ocr` / `transformers` packages were confirmed false-positive SUS in RESEARCH §Package Legitimacy Audit and are already in `pyproject.toml`'s `[torch]` extra — no new install in this plan.

## TDD Gate Compliance

Plan frontmatter `type: tdd`. Task 2 is the `tdd="true"` task; the gate sequence was observed (RED confirmed failing before implementation, GREEN pass after). Per the project's established per-task commit convention (single `feat(...)` commit per task holding tests + implementation together — consistent with plans 04-01 and 04-02), the `test(...)` RED-only commit and `feat(...)` GREEN commit are combined into one `feat(...)` commit:

- **Task 2**: RED confirmed before implementation — `test_torch_ocr_model.py` raised `ImportError: cannot import name 'TorchOCRModel'` at collection, and `test_adapters.py::test_ocr_factory_*` failed with the old stub message (`'OCR adapter lands in Phase 4'` did not match `'ONNX OCR backend'`; factory did not return TorchOCRModel). GREEN after implementation — all 11 OCR/factory tests pass.

Both gates observed (RED failure confirmed before implementation, GREEN pass after). No separate `refactor(...)` commit needed — the implementation was clean on first pass.

## Self-Check: PASSED

Created/modified files:
- FOUND: panelcleaner/ocr/ocr_mangaocr.py
- FOUND: manga_ai_studio/adapters/torch_impl.py
- FOUND: manga_ai_studio/adapters/factory.py
- FOUND: tests/test_core/test_torch_ocr_model.py
- FOUND: tests/test_core/test_adapters.py
- FOUND: tests/test_detection/test_ctd_adapter.py

Commits:
- FOUND: 25fea98 (feat(04-03): vendor MangaOcr singleton wrapper near-verbatim (D-14))
- FOUND: 1680fdc (feat(04-03): implement TorchOCRModel adapter + factory fix (TDD))
