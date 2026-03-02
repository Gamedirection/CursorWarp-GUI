# Changelog

## 2026-03-02 (Update 3)

### Fixed
- Gradient rendering now updates correctly from edge distance (approach marker trends blue, exit marker trends orange).
- Marker scaling is now applied at draw-time and no longer fixed to a hardcoded size.
- Large marker/icon edge placement now uses size-aware padding to prevent clipping.
- Packaged executable icon asset lookup now works using app base path (`_MEIPASS` for frozen builds).

### Added
- Marker sizing settings:
  - `Base size (px)`
  - `Size mode`: `Same Pixels`, `Per-Monitor DPI`, `Resolution Relative`
  - `Min scale` / `Max scale`
  - `Gradient range (px)`
- Numeric setting parsing guards to avoid render-loop failures from invalid input values.
- README packaging instructions for PyInstaller `.exe` builds.

## 2026-03-02 (Update 2)

### Fixed
- Restored reliable click-through by reapplying overlay pass-through styles continuously during runtime.

### Changed
- New primary entrypoint naming scheme: `cursorwarp_gui.py`.
- Renamed primary app class to `CursorWarpGUIApp`.
- `mouse_warp_gui.py` and `edge_spotter.py` now forward to `cursorwarp_gui.py` for backward compatibility.
- README updated to reflect new run commands.

## 2026-03-02

### Added
- Renamed app branding to `Mouse-Warp-GUI`.
- New primary entrypoint `mouse_warp_gui.py` (with compatibility shim `edge_spotter.py`).
- Optional built-in `Mouse Warp` toggle in settings to emulate PowerToys-style cursor warp.
- PowerToys and mouse-utility documentation links in settings and README.
- Credit and community links.
- Animation sequence scan/loop support for image markers (`*-0.png`, `*-1.png`, ...).
- Animation FPS setting.
- Scrollable settings UI.
- Dark-mode theme tuning with improved text contrast.
- Color picker button previews.
- Reset-to-defaults settings action.
- Side-specific image rotate/flip controls.
- Aspect-ratio-preserving image rendering (optional stretch mode).

### Changed
- Multi-monitor edge warp target handling for exterior edges.
- Overlay click-through reliability improvements.
- Settings persistence expanded via `cursorwarp_gui_settings.json` (with legacy migration support).
