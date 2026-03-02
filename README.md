# Mouse-Warp-GUI

<img src="./icon/icon.png" width="250" alt="Mouse-Warp-GUI logo">
<br></br>

Mouse-Warp-GUI is a lightweight Windows overlay and optional mouse-warp utility inspired by PowerToys Mouse Warp.

- Blue `In` marker shows where warp input is detected.
- Orange `Out` marker shows where the cursor will appear.
- Works across multiple displays with odd layouts.
- Can run visual-only or with built-in `Mouse Warp` enabled.

## Features

<img src="https://i.imgur.com/YGn7iDx_d.webp?maxwidth=760&fidelity=grand" width="500" alt="Demo of App Being Used">

- Transparent always-on-top multi-monitor overlays
- Click-through overlays
- Built-in optional cursor warp (`Mouse Warp` toggle)
- Marker presets: `Boxes`, `Pong`, `Circle`, `Portals`, `Arrows` (`Portals` is a pulsing animation)
- Fully customizable fills/outlines: configure in-fill/out-fill colors, outline color, and outline width.
- Color, outline, scale, gradient, and image customization
- Color, outline, scale, gradient, and image customization
- Edge-offset control (positive/negative) and “use image markers” toggle to force shapes or image icons.
- Image animation sequence support (`name-0.png`, `name-1.png`, ...)
- Per-side image transform controls (rotate/flip)
- Marker size controls:
  - `Base size (px)`
  - `Size mode`: `Same Pixels`, `Per-Monitor DPI`, `Resolution Relative`
  - `Min scale` / `Max scale`
  - `Gradient range (px)`
- Settings persistence in `cursorwarp_gui_settings.json`
- Tray menu: `Turn Off/On`, `Debug`, `Settings`, `Quit`
- Global quit hotkey: `Ctrl + Shift + Alt + Q`


<img width="912" height="1284" alt="image" src="https://github.com/user-attachments/assets/57d4158c-d145-462a-aad6-f15192377882" />


## PowerToys Links

- PowerToys app: https://learn.microsoft.com/windows/powertoys/
- Mouse Warp docs (Mouse utilities): https://learn.microsoft.com/windows/powertoys/mouse-utilities

## Requirements

- Windows 10/11
- Python 3.10+

## Install

```powershell
python -m pip install -r requirements.txt
```

## Run

Primary entrypoint:

```powershell
python cursorwarp_gui.py
```

No-terminal launch on Windows:

```powershell
pythonw .\cursorwarp_gui.pyw
```

Compatibility entrypoints (still supported):

```powershell
python mouse_warp_gui.py
python edge_spotter.py
```

Debug mode:

```powershell
python cursorwarp_gui.py --debug
```

## Build `.exe` (Windows)

Install PyInstaller:

```powershell
python -m pip install pyinstaller
```

Build:

```powershell
pyinstaller --noconsole --onefile --name Mouse-Warp-GUI --icon .\icon\icon.ico --add-data "icon;icon" .\cursorwarp_gui.py
```

Output:

- `.\dist\Mouse-Warp-GUI.exe`

## Animation File Naming

If the selected image folder contains files like:

- `portalblue-0.png`
- `portalblue-1.png`
- `portalblue-2.png`

Mouse-Warp-GUI loops contiguous frames starting at `-0`.
If `-0` is missing, the selected image is treated as static.

## Credit

- Alex Sierputowski @ GameDirection.net
- GitHub: https://github.com/Gamedirection/Mouse-Warp-GUI.git
- Community: https://join.gamedirection.net
