# Deferred items (out-of-scope discoveries)

## 07-02: TextOverlayItem paint UAF (heap-layout-dependent, latent)

- **Found during:** plan 07-02 continuation (QAction crash investigation)
- **Description:** `TextOverlayItem.paint` (manga_ai_studio/gui/box_item.py:333,
  `painter.drawPixmap(..., self._pixmap)`) can read a freed QPixmap C++ object
  when a bare-scene GUI test's `QGraphicsScene` is garbage-collected while a
  paint event is still queued; pytest-qt's next-test `_process_events` flush
  then dispatches paint on freed memory → native access violation (exit
  -1073741819). Heap-layout-dependent: an extra QAction allocation in
  `__init__` deterministically exposes it; removing the allocation makes it
  vanish. Not reproducible at baseline HEAD or with 07-02's actual code.
- **Why deferred:** out of scope for 07-02 (does not manifest with plan code);
  proper fix belongs in a robustness plan (e.g., ensure scenes are fully
  drained/cleared before Python GC in tests, or guard paint against
  shiboken-deleted pixmaps).
- **Status:** open
