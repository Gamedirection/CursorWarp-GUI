from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import sys
import threading
import time
import webbrowser
from ctypes import wintypes
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pystray
import tkinter as tk
from PIL import Image, ImageDraw


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


@dataclass(frozen=True)
class Monitor:
    left: int
    top: int
    right: int
    bottom: int

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


@dataclass(frozen=True)
class Hotspot:
    monitor_index: int
    edge: str


class CursorWarpGUIApp:
    BG = "#ff00ff"
    SETTINGS_FILE = "cursorwarp_gui_settings.json"
    LEGACY_SETTINGS_FILE = "edge_spotter_settings.json"
    POWERTOYS_APP_URL = "https://learn.microsoft.com/windows/powertoys/"
    POWERTOYS_MOUSE_WARP_DOC_URL = "https://learn.microsoft.com/windows/powertoys/mouse-utilities"
    GITHUB_URL = "https://github.com/Gamedirection/Mouse-Warp-GUI.git"
    COMMUNITY_URL = "https://join.gamedirection.net"

    def __init__(self, debug: bool = False, click_through: bool = True) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.debug = debug
        self.active = True
        self.mouse_warp_enabled = False
        self.click_through_enabled = click_through
        self.box = 44
        self.edge_gap = 2
        self.activation_distance = 180
        self.display_mode = "2"
        self._overlays: List[Tuple[tk.Toplevel, tk.Canvas, Monitor]] = []
        self._monitors: List[Monitor] = []
        self._queue: queue.Queue[str] = queue.Queue()
        self._tray: Optional[pystray.Icon] = None
        self._settings_window: Optional[tk.Toplevel] = None
        self._last_pos: Optional[Tuple[int, int]] = None
        self._last_warp_t = 0.0
        self._cooldown = 0.2
        self._styled: set[int] = set()
        self._next_refresh = 0.0
        self._load_settings()
        self._rebuild_overlays()
        self._start_tray()
        self.root.after(16, self._tick)

    def _load_settings(self) -> None:
        p = os.path.abspath(self.SETTINGS_FILE)
        legacy = os.path.abspath(self.LEGACY_SETTINGS_FILE)
        if not os.path.isfile(p) and os.path.isfile(legacy):
            try:
                os.replace(legacy, p)
            except OSError:
                pass
        if not os.path.isfile(p):
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.mouse_warp_enabled = bool(d.get("mouse_warp_enabled", self.mouse_warp_enabled))
            self.click_through_enabled = bool(d.get("click_through_enabled", self.click_through_enabled))
        except Exception:
            pass

    def _save_settings(self) -> None:
        p = os.path.abspath(self.SETTINGS_FILE)
        data = {"mouse_warp_enabled": self.mouse_warp_enabled, "click_through_enabled": self.click_through_enabled}
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def _start_tray(self) -> None:
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 32, 32), radius=6, fill=(24, 141, 255, 255))
        draw.rounded_rectangle((32, 32, 56, 56), radius=6, fill=(255, 142, 41, 255))
        menu = pystray.Menu(
            pystray.MenuItem(lambda _i: "Turn Off" if self.active else "Turn On", self._on_toggle),
            pystray.MenuItem("Settings", self._on_settings),
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._tray = pystray.Icon("mouse_warp_gui", image, "Mouse-Warp-GUI", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _on_toggle(self, _icon, _item) -> None:
        self._queue.put("toggle")

    def _on_settings(self, _icon, _item) -> None:
        self._queue.put("settings")

    def _on_quit(self, _icon, _item) -> None:
        self._queue.put("quit")

    def _tick(self) -> None:
        while True:
            try:
                action = self._queue.get_nowait()
            except queue.Empty:
                break
            if action == "toggle":
                self.active = not self.active
            elif action == "settings":
                self._open_settings()
            elif action == "quit":
                self.shutdown()
                return
        now = time.monotonic()
        if now >= self._next_refresh:
            self._rebuild_overlays()
            self._next_refresh = now + 2.0
        self._ensure_click_through()
        self._draw()
        self.root.after(16, self._tick)

    def _ensure_click_through(self) -> None:
        if not self.click_through_enabled:
            return
        for w, c, _m in self._overlays:
            self._style_click_through(w, c)

    def _open_settings(self) -> None:
        if self._settings_window and self._settings_window.winfo_exists():
            self._settings_window.lift()
            return
        win = tk.Toplevel(self.root)
        win.title("Mouse-Warp-GUI Settings")
        win.geometry("540x520")
        win.attributes("-topmost", True)
        container = tk.Frame(win)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container)
        sb = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        content = tk.Frame(canvas, padx=14, pady=14)
        canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(1, width=e.width))
        win.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units") if e.delta else None)

        warp_var = tk.BooleanVar(value=self.mouse_warp_enabled)
        click_var = tk.BooleanVar(value=self.click_through_enabled)
        dark_var = tk.BooleanVar(value=False)
        tk.Checkbutton(content, text="Mouse Warp (PowerToys-style cursor teleport)", variable=warp_var, anchor="w").pack(fill="x", pady=(0, 8))
        tk.Checkbutton(content, text="Enable click-through", variable=click_var, anchor="w").pack(fill="x")
        tk.Checkbutton(content, text="Dark mode (settings UI)", variable=dark_var, anchor="w").pack(fill="x", pady=(0, 8))
        tk.Label(content, text="Links", font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", pady=(8, 4))
        lf = tk.Frame(content)
        lf.pack(fill="x")
        tk.Button(lf, text="PowerToys App", command=lambda: webbrowser.open(self.POWERTOYS_APP_URL)).pack(side="left", padx=(0, 6))
        tk.Button(lf, text="Mouse Warp Docs", command=lambda: webbrowser.open(self.POWERTOYS_MOUSE_WARP_DOC_URL)).pack(side="left")
        tk.Button(content, text="GitHub", command=lambda: webbrowser.open(self.GITHUB_URL)).pack(anchor="w", pady=(6, 0))
        tk.Button(content, text="Community", command=lambda: webbrowser.open(self.COMMUNITY_URL)).pack(anchor="w")
        tk.Label(content, text="Credit: Alex Sierputowski @ GameDirection.net", anchor="w").pack(fill="x", pady=(8, 0))

        def apply_and_close() -> None:
            self.mouse_warp_enabled = bool(warp_var.get())
            self.click_through_enabled = bool(click_var.get())
            self._styled.clear()
            self._save_settings()
            self._rebuild_overlays()
            win.destroy()

        bf = tk.Frame(content)
        bf.pack(fill="x", pady=(14, 0))
        tk.Button(bf, text="Apply", width=12, command=apply_and_close).pack(side="right")
        self._settings_window = win

    def _rebuild_overlays(self) -> None:
        monitors = self._get_monitors() or [Monitor(0, 0, 1920, 1080)]
        if monitors == self._monitors and self._overlays:
            return
        self._monitors = monitors
        for w, _c, _m in self._overlays:
            try:
                w.destroy()
            except tk.TclError:
                pass
        self._overlays = []
        self._styled.clear()
        for m in monitors:
            w = tk.Toplevel(self.root)
            w.overrideredirect(True)
            w.attributes("-topmost", True)
            w.configure(bg=self.BG)
            w.wm_attributes("-transparentcolor", self.BG)
            w.geometry(f"{m.right - m.left}x{m.bottom - m.top}+{m.left}+{m.top}")
            c = tk.Canvas(w, bg=self.BG, highlightthickness=0)
            c.pack(fill="both", expand=True)
            self._overlays.append((w, c, m))
            self._style_click_through(w, c)

    def _style_click_through(self, w: tk.Toplevel, c: tk.Canvas) -> None:
        if not self.click_through_enabled:
            return
        ids = [int(w.winfo_id()), int(c.winfo_id())]
        p = ctypes.windll.user32.GetParent(ids[0])
        if p:
            ids.append(int(p))
        for hwnd in ids:
            if hwnd in self._styled:
                continue
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOOLWINDOW = 0x00000080
            LWA_COLORKEY = 0x00000001
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0x00FF00FF, 0, LWA_COLORKEY)
            self._styled.add(hwnd)

    def _draw(self) -> None:
        for _w, c, _m in self._overlays:
            c.delete("all")
        if not self.active:
            return
        x, y = self._cursor_pos()
        idx = self._monitor_for_point(x, y)
        if idx is None:
            self._last_pos = (x, y)
            return
        m = self._monitors[idx]
        edge = self._nearest_edge(m, x, y)
        self._maybe_warp(idx, edge, x, y)
        in_x, in_y = self._edge_point(m, edge, x, y)
        out_x, out_y = self._target_point(idx, edge, x, y)
        self._draw_marker(in_x, in_y, "#0070ff")
        self._draw_marker(out_x, out_y, "#ff7f1f")
        self._last_pos = (x, y)

    def _maybe_warp(self, idx: int, edge: str, x: int, y: int) -> None:
        if not self.mouse_warp_enabled:
            return
        now = time.monotonic()
        if now - self._last_warp_t < self._cooldown:
            return
        prev = self._last_pos
        if prev is None:
            return
        m = self._monitors[idx]
        hit = (edge == "left" and x <= m.left + 1 and prev[0] > x) or (edge == "right" and x >= m.right - 2 and prev[0] < x) or (edge == "top" and y <= m.top + 1 and prev[1] > y) or (edge == "bottom" and y >= m.bottom - 2 and prev[1] < y)
        if not hit:
            return
        tx, ty = self._target_point(idx, edge, x, y)
        ctypes.windll.user32.SetCursorPos(int(tx), int(ty))
        self._last_warp_t = now

    def _draw_marker(self, x: int, y: int, color: str) -> None:
        idx = self._monitor_for_point(x, y)
        if idx is None:
            return
        _w, c, m = self._overlays[idx]
        lx, ly = x - m.left, y - m.top
        h = self.box // 2
        c.create_rectangle(lx - h, ly - h, lx + h, ly + h, fill=color, outline="#ffffff", width=2)

    def _target_point(self, idx: int, edge: str, x: int, y: int) -> Tuple[int, int]:
        src = self._monitors[idx]
        candidates = self._monitors
        if edge in ("left", "right"):
            line = [m for m in candidates if m.top <= y < m.bottom]
            if line:
                tgt = max(line, key=lambda m: m.right) if edge == "left" else min(line, key=lambda m: m.left)
            else:
                tgt = src
            target_edge = "right" if edge == "left" else "left"
            tx = tgt.right - self.edge_gap - 2 if target_edge == "right" else tgt.left + self.edge_gap + 2
            ty = max(tgt.top + self.box // 2, min(tgt.bottom - self.box // 2, y))
            return tx, ty
        line = [m for m in candidates if m.left <= x < m.right]
        if line:
            tgt = max(line, key=lambda m: m.bottom) if edge == "top" else min(line, key=lambda m: m.top)
        else:
            tgt = src
        target_edge = "bottom" if edge == "top" else "top"
        ty = tgt.bottom - self.edge_gap - 2 if target_edge == "bottom" else tgt.top + self.edge_gap + 2
        tx = max(tgt.left + self.box // 2, min(tgt.right - self.box // 2, x))
        return tx, ty

    def _edge_point(self, m: Monitor, edge: str, x: int, y: int) -> Tuple[int, int]:
        half = self.box // 2
        if edge == "left":
            return m.left + self.edge_gap + half, max(m.top + half, min(m.bottom - half, y))
        if edge == "right":
            return m.right - self.edge_gap - half, max(m.top + half, min(m.bottom - half, y))
        if edge == "top":
            return max(m.left + half, min(m.right - half, x)), m.top + self.edge_gap + half
        return max(m.left + half, min(m.right - half, x)), m.bottom - self.edge_gap - half

    @staticmethod
    def _nearest_edge(m: Monitor, x: int, y: int) -> str:
        d = {"left": abs(x - m.left), "right": abs(m.right - x), "top": abs(y - m.top), "bottom": abs(m.bottom - y)}
        return min(d, key=d.get)

    def _cursor_pos(self) -> Tuple[int, int]:
        p = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    def _monitor_for_point(self, x: int, y: int) -> Optional[int]:
        for i, m in enumerate(self._monitors):
            if m.contains(x, y):
                return i
        return None

    @staticmethod
    def _get_monitors() -> List[Monitor]:
        out: List[Monitor] = []
        cb_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

        def cb(_h, _d, r, _l):
            rc = r.contents
            out.append(Monitor(rc.left, rc.top, rc.right, rc.bottom))
            return 1

        ctypes.windll.user32.EnumDisplayMonitors(0, 0, cb_t(cb), 0)
        return out

    def shutdown(self) -> None:
        if self._tray is not None:
            self._tray.stop()
        for w, _c, _m in self._overlays:
            try:
                w.destroy()
            except tk.TclError:
                pass
        self.root.after(0, self.root.destroy)

    def run(self) -> None:
        self.root.mainloop()


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Mouse-Warp-GUI overlay app.")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-click-through", action="store_true")
    args = parser.parse_args()
    _enable_dpi_awareness()
    app = CursorWarpGUIApp(debug=args.debug, click_through=not args.no_click_through)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
