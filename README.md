# Manga AI Studio

A PySide6 desktop application for manga scanlators and preservationists that unifies
page cleaning (PanelCleaner mask detection + LaMa inpainting), manga OCR, and a
lightweight canvas editor into a single workspace.

## Core Value

One app where a scanlator can clean pages, fix inpainting masks, run/correct OCR,
and lay out translation text — instead of switching between PanelCleaner, mokuro,
and an image editor.

## Requirements

- Python >= 3.12
- See `pyproject.toml` for the dependency list

## Install (development)

```bash
python -m pip install -e ".[dev]"
```

For the optional PyTorch model backends (detection / inpainting / OCR):

```bash
python -m pip install -e ".[torch]"
```

## Run

```bash
python -m manga_ai_studio
```

## License

This project is licensed under **GPL v3**.

It is a derivative work of [PanelCleaner](https://github.com/VoxelCubes/PanelCleaner)
(GPL v3). The `panelcleaner/` package contains PanelCleaner source adapted
near-verbatim under the terms of the GPL v3, which requires that this derivative
also remains GPL v3 and that its source code is provided. See the upstream
PanelCleaner `LICENSE` for the full GPL v3 text.
