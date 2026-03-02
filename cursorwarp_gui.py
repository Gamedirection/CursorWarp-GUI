from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import re
import sys
import threading
import time
import webbrowser
from ctypes import wintypes
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pystray
import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageDraw, ImageOps, ImageTk


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


@dataclass(frozen=True)
class Monitor:
    handle: int
    left: int
    top: int
    right: int
    bottom: int

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


class CursorWarpGUIApp:
    SETTINGS_FILE = "cursorwarp_gui_settings.json"
    LEGACY_SETTINGS_FILE = "edge_spotter_settings.json"
    BG = "#ff00ff"
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
        self.display_mode = "2"
        self.span_across_displays = True
        self.show_out_marker = True
        self.hide_out_marker_on_touching_edges = False
        self.edge_gap = 2
        self.marker_size_px = 44
        self.size_mode = "Same Pixels"
        self.min_scale = 1.0
        self.max_scale = 1.8
        self.gradient_range_px = 240
        self.scale_with_proximity = True
        self.gradient_enabled = True
        self.dark_mode_enabled = False
        self.clean_png_alpha = True
        self.stretch_image_to_bounds = False
        self.marker_preset = "Boxes"
        self.arrow_direction_mode = "Toward Edge"
        self.animation_fps = 12.0
        self.in_image_path = ""
        self.out_image_path = ""
        self.left_rotate_deg = 0
        self.right_rotate_deg = 0
        self.top_rotate_deg = 90
        self.bottom_rotate_deg = 270
        self.left_flip = False
        self.right_flip = True
        self.top_flip = False
        self.bottom_flip = False
        self._load_settings()

        self._queue: queue.Queue[str] = queue.Queue()
        self._tray: Optional[pystray.Icon] = None
        self._settings_window: Optional[tk.Toplevel] = None
        self._running = True
        self._overlays: List[Tuple[tk.Toplevel, tk.Canvas, Monitor]] = []
        self._monitors: List[Monitor] = []
        self._styled: set[int] = set()
        self._last_pos: Optional[Tuple[int, int]] = None
        self._last_warp_t = 0.0
        self._next_refresh = 0.0

        self._icon_ico = os.path.abspath(os.path.join(self._app_base_dir(), "icon", "icon.ico"))
        self._icon_png = os.path.abspath(os.path.join(self._app_base_dir(), "icon", "icon.png"))
        self._icon_refs: List[tk.PhotoImage] = []
        self._image_cache: dict[Tuple, tk.PhotoImage] = {}
        self._animation_cache: dict[str, List[str]] = {}
        self._frame_images: List[tk.PhotoImage] = []
        self._window_dpi_scale: dict[int, float] = {}

        self._rebuild_overlays(force=True)
        self._start_tray()
        self.root.after(16, self._tick)

    @staticmethod
    def _app_base_dir() -> str:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return str(sys._MEIPASS)
        return os.path.dirname(os.path.abspath(__file__))

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
            for k, v in d.items():
                if hasattr(self, k):
                    setattr(self, k, v)
        except Exception:
            pass

    def _save_settings(self) -> None:
        data = {
            "mouse_warp_enabled": self.mouse_warp_enabled,
            "click_through_enabled": self.click_through_enabled,
            "display_mode": self.display_mode,
            "span_across_displays": self.span_across_displays,
            "show_out_marker": self.show_out_marker,
            "hide_out_marker_on_touching_edges": self.hide_out_marker_on_touching_edges,
            "edge_gap": self.edge_gap,
            "marker_size_px": self.marker_size_px,
            "size_mode": self.size_mode,
            "min_scale": self.min_scale,
            "max_scale": self.max_scale,
            "gradient_range_px": self.gradient_range_px,
            "scale_with_proximity": self.scale_with_proximity,
            "gradient_enabled": self.gradient_enabled,
            "dark_mode_enabled": self.dark_mode_enabled,
            "clean_png_alpha": self.clean_png_alpha,
            "stretch_image_to_bounds": self.stretch_image_to_bounds,
            "marker_preset": self.marker_preset,
            "arrow_direction_mode": self.arrow_direction_mode,
            "animation_fps": self.animation_fps,
            "in_image_path": self.in_image_path,
            "out_image_path": self.out_image_path,
            "left_rotate_deg": self.left_rotate_deg,
            "right_rotate_deg": self.right_rotate_deg,
            "top_rotate_deg": self.top_rotate_deg,
            "bottom_rotate_deg": self.bottom_rotate_deg,
            "left_flip": self.left_flip,
            "right_flip": self.right_flip,
            "top_flip": self.top_flip,
            "bottom_flip": self.bottom_flip,
        }
        with open(self.SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _start_tray(self) -> None:
        image = self._load_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem(lambda _i: "Turn Off" if self.active else "Turn On", self._on_toggle),
            pystray.MenuItem("Settings", self._on_settings),
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._tray = pystray.Icon("cursorwarp_gui", image, "CursorWarp-GUI", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _load_icon_image(self) -> Image.Image:
        for p in (self._icon_png, self._icon_ico):
            if os.path.isfile(p):
                try:
                    return Image.open(p)
                except Exception:
                    pass
        fallback = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(fallback)
        draw.rounded_rectangle((8, 8, 56, 56), radius=8, fill=(60, 140, 255, 255))
        return fallback

    def _on_toggle(self, _icon, _item) -> None:
        self._queue.put("toggle")

    def _on_settings(self, _icon, _item) -> None:
        self._queue.put("settings")

    def _on_quit(self, _icon, _item) -> None:
        self._queue.put("quit")

    def _tick(self) -> None:
        if not self._running:
            return
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
        if time.monotonic() >= self._next_refresh:
            self._rebuild_overlays(force=False)
            self._next_refresh = time.monotonic() + 2.0
        self._ensure_clickthrough()
        self._draw()
        self.root.after(16, self._tick)

    def _open_settings(self) -> None:
        if self._settings_window and self._settings_window.winfo_exists():
            self._settings_window.lift()
            return
        win = tk.Toplevel(self.root)
        win.title("CursorWarp-GUI Settings")
        win.geometry("640x760")
        win.attributes("-topmost", True)
        self._apply_window_icon(win)

        container = tk.Frame(win)
        container.pack(fill="both", expand=True)
        scroll_canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scroll_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        frame = tk.Frame(scroll_canvas, padx=14, pady=14)
        content_window = scroll_canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda _e: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.bind("<Configure>", lambda e: scroll_canvas.itemconfigure(content_window, width=e.width))
        win.bind("<MouseWheel>", lambda e: scroll_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units") if e.delta else None)
        vars_ = {}
        for name in [
            "mouse_warp_enabled", "click_through_enabled", "display_mode", "span_across_displays", "show_out_marker",
            "hide_out_marker_on_touching_edges",
            "marker_size_px", "size_mode", "min_scale", "max_scale", "gradient_range_px",
            "scale_with_proximity", "gradient_enabled", "dark_mode_enabled", "clean_png_alpha", "stretch_image_to_bounds",
            "marker_preset", "arrow_direction_mode", "animation_fps", "in_image_path", "out_image_path",
            "left_rotate_deg", "right_rotate_deg", "top_rotate_deg", "bottom_rotate_deg", "left_flip", "right_flip", "top_flip", "bottom_flip",
        ]:
            val = getattr(self, name)
            if isinstance(val, bool):
                vars_[name] = tk.BooleanVar(value=val)
            else:
                vars_[name] = tk.StringVar(value=str(val))

        tk.Checkbutton(frame, text="Mouse Warp (PowerToys-style cursor teleport)", variable=vars_["mouse_warp_enabled"], anchor="w").pack(fill="x")
        tk.Checkbutton(frame, text="Enable click-through", variable=vars_["click_through_enabled"], anchor="w").pack(fill="x")
        tk.Checkbutton(frame, text="Span Across Displays", variable=vars_["span_across_displays"], anchor="w").pack(fill="x")
        tk.Checkbutton(frame, text="Show Out marker", variable=vars_["show_out_marker"], anchor="w").pack(fill="x")
        tk.Checkbutton(frame, text="Hide Out marker on touching display edges", variable=vars_["hide_out_marker_on_touching_edges"], anchor="w").pack(fill="x")
        tk.Checkbutton(frame, text="Scale with proximity", variable=vars_["scale_with_proximity"], anchor="w").pack(fill="x")
        tk.Checkbutton(frame, text="Gradient enabled", variable=vars_["gradient_enabled"], anchor="w").pack(fill="x")
        tk.Checkbutton(frame, text="Dark mode (settings UI)", variable=vars_["dark_mode_enabled"], anchor="w").pack(fill="x")
        tk.Checkbutton(frame, text="Clean PNG alpha edges", variable=vars_["clean_png_alpha"], anchor="w").pack(fill="x")
        tk.Checkbutton(frame, text="Stretch image to marker bounds", variable=vars_["stretch_image_to_bounds"], anchor="w").pack(fill="x", pady=(0, 8))

        row = tk.Frame(frame); row.pack(fill="x")
        tk.Label(row, text="Display mode").pack(side="left")
        tk.OptionMenu(row, vars_["display_mode"], "2", "8").pack(side="left", padx=6)
        tk.Label(row, text="Preset").pack(side="left", padx=(10, 0))
        tk.OptionMenu(row, vars_["marker_preset"], "Boxes", "Pong", "Portal", "Arrows").pack(side="left", padx=6)
        tk.Label(row, text="Arrow dir").pack(side="left", padx=(10, 0))
        tk.OptionMenu(row, vars_["arrow_direction_mode"], "Toward Edge", "Into Screen").pack(side="left", padx=6)

        row2 = tk.Frame(frame); row2.pack(fill="x", pady=(8, 0))
        tk.Label(row2, text="Anim FPS").pack(side="left")
        tk.Entry(row2, textvariable=vars_["animation_fps"], width=8).pack(side="left", padx=6)
        tk.Label(row2, text="Base size(px)").pack(side="left", padx=(12, 0))
        tk.Entry(row2, textvariable=vars_["marker_size_px"], width=8).pack(side="left", padx=6)

        row3 = tk.Frame(frame); row3.pack(fill="x", pady=(8, 0))
        tk.Label(row3, text="Size mode").pack(side="left")
        tk.OptionMenu(row3, vars_["size_mode"], "Same Pixels", "Per-Monitor DPI", "Resolution Relative").pack(side="left", padx=6)
        tk.Label(row3, text="Min scale").pack(side="left", padx=(10, 0))
        tk.Entry(row3, textvariable=vars_["min_scale"], width=8).pack(side="left", padx=6)
        tk.Label(row3, text="Max scale").pack(side="left", padx=(10, 0))
        tk.Entry(row3, textvariable=vars_["max_scale"], width=8).pack(side="left", padx=6)
        tk.Label(row3, text="Gradient range(px)").pack(side="left", padx=(10, 0))
        tk.Entry(row3, textvariable=vars_["gradient_range_px"], width=8).pack(side="left", padx=6)

        def browse(var_name: str) -> None:
            p = filedialog.askopenfilename(parent=win, filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.webp"), ("All", "*.*")])
            if p:
                vars_[var_name].set(p)

        imgf = tk.Frame(frame); imgf.pack(fill="x", pady=(8, 0))
        tk.Label(imgf, text="In image").grid(row=0, column=0, sticky="w")
        tk.Entry(imgf, textvariable=vars_["in_image_path"], width=54).grid(row=0, column=1, sticky="w", padx=6)
        tk.Button(imgf, text="Browse", command=lambda: browse("in_image_path")).grid(row=0, column=2)
        tk.Label(imgf, text="Out image").grid(row=1, column=0, sticky="w")
        tk.Entry(imgf, textvariable=vars_["out_image_path"], width=54).grid(row=1, column=1, sticky="w", padx=6)
        tk.Button(imgf, text="Browse", command=lambda: browse("out_image_path")).grid(row=1, column=2)

        tk.Label(frame, text="Transforms (deg / flip)", anchor="w").pack(fill="x", pady=(8, 2))
        tf = tk.Frame(frame); tf.pack(fill="x")
        for r, side in enumerate(("left", "right", "top", "bottom")):
            tk.Label(tf, text=side.capitalize()).grid(row=r, column=0, sticky="w")
            tk.Entry(tf, textvariable=vars_[f"{side}_rotate_deg"], width=8).grid(row=r, column=1, padx=6, sticky="w")
            tk.Checkbutton(tf, variable=vars_[f"{side}_flip"]).grid(row=r, column=2, sticky="w")

        tk.Label(frame, text="Links", font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", pady=(12, 4))
        lf = tk.Frame(frame); lf.pack(fill="x")
        tk.Button(lf, text="PowerToys App", command=lambda: webbrowser.open(self.POWERTOYS_APP_URL)).pack(side="left", padx=(0, 6))
        tk.Button(lf, text="Mouse Warp Docs", command=lambda: webbrowser.open(self.POWERTOYS_MOUSE_WARP_DOC_URL)).pack(side="left")
        tk.Button(frame, text="GitHub", command=lambda: webbrowser.open(self.GITHUB_URL)).pack(anchor="w", pady=(6, 0))
        tk.Button(frame, text="Community", command=lambda: webbrowser.open(self.COMMUNITY_URL)).pack(anchor="w")
        tk.Label(frame, text="Credit: Alex Sierputowski @ GameDirection.net", anchor="w").pack(fill="x", pady=(8, 0))

        def apply_close() -> None:
            for k, v in vars_.items():
                cur = getattr(self, k)
                if isinstance(cur, bool):
                    setattr(self, k, bool(v.get()))
                elif isinstance(cur, float):
                    try: setattr(self, k, float(v.get()))
                    except Exception: pass
                elif isinstance(cur, int):
                    try: setattr(self, k, int(float(v.get())))
                    except Exception: pass
                else:
                    setattr(self, k, str(v.get()))
            self._save_settings()
            self._styled.clear()
            self._image_cache.clear()
            self._animation_cache.clear()
            self._window_dpi_scale.clear()
            self._rebuild_overlays(force=True)
            win.destroy()

        b = tk.Frame(frame); b.pack(fill="x", pady=(12, 0))
        tk.Button(b, text="Apply", width=12, command=apply_close).pack(side="right")

        def apply_theme_preview(*_args) -> None:
            self._apply_settings_theme(win, bool(vars_["dark_mode_enabled"].get()))

        vars_["dark_mode_enabled"].trace_add("write", apply_theme_preview)
        apply_theme_preview()
        self._settings_window = win

    def _apply_settings_theme(self, root: tk.Widget, dark: bool) -> None:
        bg = "#3a3a3a" if dark else "#f4f4f4"
        fg = "#ffffff" if dark else "#101010"
        entry_bg = "#4a4a4a" if dark else "#ffffff"
        btn_bg = "#5a5a5a" if dark else "#e6e6e6"
        menu_bg = "#4a4a4a" if dark else "#ffffff"
        try:
            root.configure(bg=bg)
        except tk.TclError:
            pass
        for child in root.winfo_children():
            cls = child.winfo_class()
            try:
                if cls in ("Frame", "LabelFrame"):
                    child.configure(bg=bg)
                elif cls == "Canvas":
                    child.configure(bg=bg)
                elif cls == "Label":
                    child.configure(bg=bg, fg=fg)
                elif cls in ("Button", "Checkbutton", "Radiobutton"):
                    child.configure(bg=bg, fg=fg, activebackground=btn_bg, activeforeground=fg, selectcolor=bg)
                elif cls == "Entry":
                    child.configure(bg=entry_bg, fg=fg, insertbackground=fg)
                elif cls == "Menubutton":
                    child.configure(bg=btn_bg, fg=fg, activebackground=btn_bg, activeforeground=fg, highlightbackground=bg)
                    menu_name = child.cget("menu")
                    if menu_name:
                        child.nametowidget(menu_name).configure(bg=menu_bg, fg=fg, activebackground=btn_bg, activeforeground=fg)
            except tk.TclError:
                pass
            self._apply_settings_theme(child, dark)

    def _apply_window_icon(self, window: tk.Toplevel) -> None:
        if os.path.isfile(self._icon_ico):
            try:
                window.iconbitmap(self._icon_ico)
                return
            except Exception:
                pass
        if os.path.isfile(self._icon_png):
            try:
                p = tk.PhotoImage(file=self._icon_png)
                self._icon_refs.append(p)
                window.iconphoto(True, p)
            except Exception:
                pass

    def _rebuild_overlays(self, force: bool) -> None:
        monitors = self._get_monitors() or [Monitor(0, 0, 0, 1920, 1080)]
        if not force and monitors == self._monitors and self._overlays:
            return
        self._monitors = monitors
        for w, _c, _m in self._overlays:
            try: w.destroy()
            except tk.TclError: pass
        self._overlays = []
        self._styled.clear()
        self._window_dpi_scale.clear()
        for m in monitors:
            w = tk.Toplevel(self.root)
            w.withdraw()
            w.overrideredirect(True); w.attributes("-topmost", True)
            w.configure(bg=self.BG); w.wm_attributes("-transparentcolor", self.BG)
            w.geometry(f"{m.right-m.left}x{m.bottom-m.top}+{m.left}+{m.top}")
            c = tk.Canvas(w, bg=self.BG, highlightthickness=0); c.pack(fill="both", expand=True)
            self._overlays.append((w, c, m))
            w.after(0, w.deiconify)

    def _ensure_clickthrough(self) -> None:
        if not self.click_through_enabled:
            return
        for w, c, _m in self._overlays:
            try:
                ids = [int(w.winfo_id()), int(c.winfo_id())]
            except tk.TclError:
                continue
            p = ctypes.windll.user32.GetParent(ids[0])
            if p: ids.append(int(p))
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
        self._frame_images = []
        for _w, c, _m in self._overlays:
            try:
                c.delete("all")
            except tk.TclError:
                continue
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
        touching_adjacent = self._find_adjacent(idx, edge, x, y) is not None
        proximity = self._edge_proximity(m, edge, x, y)
        in_color, out_color = self._marker_colors(proximity)
        ix, iy = self._edge_point(m, edge, x, y)
        ox, oy, out_edge = self._target_point(idx, edge, x, y)
        self._draw_marker(ix, iy, in_color, edge, is_out=False, proximity=proximity)
        if self.show_out_marker and not (self.hide_out_marker_on_touching_edges and touching_adjacent):
            self._draw_marker(ox, oy, out_color, out_edge, is_out=True, proximity=proximity)
        self._last_pos = (x, y)

    def _draw_marker(self, x: int, y: int, color: str, edge: str, is_out: bool, proximity: float) -> None:
        idx = self._monitor_for_point(x, y)
        if idx is None:
            return
        _w, c, m = self._overlays[idx]
        lx, ly = x - m.left, y - m.top
        h = max(6, self._marker_half_size(idx, proximity))

        image = self._get_marker_image(size=h * 2, edge=edge, is_out=is_out)
        if image is not None:
            self._frame_images.append(image)
            c.create_image(lx, ly, image=image, anchor="center")
            return

        preset = self.marker_preset
        if preset == "Portal":
            c.create_oval(lx - h, ly - h, lx + h, ly + h, fill=color, outline="#ffffff", width=2)
            return
        if preset == "Pong":
            t = max(5, h // 3)
            if edge in ("left", "right"):
                c.create_rectangle(lx - t, ly - h, lx + t, ly + h, fill=color, outline="#ffffff", width=2)
            else:
                c.create_rectangle(lx - h, ly - t, lx + h, ly + t, fill=color, outline="#ffffff", width=2)
            return
        if preset == "Arrows":
            into_screen = self.arrow_direction_mode == "Into Screen"
            points = self._arrow_points(lx, ly, h, edge, into_screen, is_out)
            c.create_polygon(points, fill=color, outline="#ffffff", width=2)
            return
        c.create_rectangle(lx - h, ly - h, lx + h, ly + h, fill=color, outline="#ffffff", width=2)

    def _get_marker_image(self, size: int, edge: str, is_out: bool) -> Optional[tk.PhotoImage]:
        path = (self.out_image_path if is_out else self.in_image_path).strip()
        if not path:
            return None
        frame_path = self._animation_frame_path(path)
        if not os.path.isfile(frame_path):
            return None

        rot, flip = self._side_transform(edge)
        key = (frame_path, size, rot, flip, self.stretch_image_to_bounds, self.clean_png_alpha)
        if key in self._image_cache:
            return self._image_cache[key]
        try:
            img = Image.open(frame_path).convert("RGBA")
            if rot:
                img = img.rotate(-rot, expand=True, resample=Image.Resampling.BICUBIC)
            if flip:
                img = ImageOps.mirror(img)
            if self.stretch_image_to_bounds:
                img = img.resize((size, size), Image.Resampling.LANCZOS)
            else:
                img = self._contain_center(img, size, size)
            if self.clean_png_alpha:
                img = self._clean_alpha_edges(img)
            photo = ImageTk.PhotoImage(img, master=self.root)
            self._image_cache[key] = photo
            return photo
        except Exception:
            return None

    def _animation_frame_path(self, selected_path: str) -> str:
        seq = self._animation_cache.get(selected_path)
        if seq is None:
            seq = self._scan_animation_sequence(selected_path)
            self._animation_cache[selected_path] = seq
        if not seq:
            return selected_path
        idx = int(time.monotonic() * max(0.1, float(self.animation_fps))) % len(seq)
        return seq[idx]

    def _scan_animation_sequence(self, selected_path: str) -> List[str]:
        if not os.path.isfile(selected_path):
            return [selected_path]
        folder = os.path.dirname(selected_path)
        stem, ext = os.path.splitext(os.path.basename(selected_path))
        base = re.sub(r"-\d+$", "", stem)
        pattern = re.compile(rf"^{re.escape(base)}-(\d+){re.escape(ext)}$", re.IGNORECASE)
        indexed: dict[int, str] = {}
        try:
            for name in os.listdir(folder):
                if os.path.splitext(name)[1].lower() != ext.lower():
                    continue
                m = pattern.match(name)
                if not m:
                    continue
                indexed[int(m.group(1))] = os.path.join(folder, name)
        except OSError:
            return [selected_path]
        if 0 not in indexed:
            return [selected_path]
        out: List[str] = []
        i = 0
        while i in indexed:
            out.append(indexed[i])
            i += 1
        return out if out else [selected_path]

    def _side_transform(self, edge: str) -> Tuple[int, bool]:
        if edge == "left":
            return int(self.left_rotate_deg), bool(self.left_flip)
        if edge == "right":
            return int(self.right_rotate_deg), bool(self.right_flip)
        if edge == "top":
            return int(self.top_rotate_deg), bool(self.top_flip)
        return int(self.bottom_rotate_deg), bool(self.bottom_flip)

    @staticmethod
    def _contain_center(image: Image.Image, width: int, height: int) -> Image.Image:
        contained = ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.paste(contained, ((width - contained.width) // 2, (height - contained.height) // 2), contained)
        return canvas

    @staticmethod
    def _clean_alpha_edges(image: Image.Image) -> Image.Image:
        px = image.load()
        w, h = image.size
        for yy in range(h):
            for xx in range(w):
                r, g, b, a = px[xx, yy]
                if a <= 16:
                    px[xx, yy] = (0, 0, 0, 0)
                elif a < 255:
                    px[xx, yy] = (r, g, b, 255)
        return image

    def _maybe_warp(self, idx: int, edge: str, x: int, y: int) -> None:
        if not self.mouse_warp_enabled:
            return
        now = time.monotonic()
        if now - self._last_warp_t < 0.2 or self._last_pos is None:
            return
        prev = self._last_pos
        m = self._monitors[idx]
        hit = (edge == "left" and x <= m.left + 1 and prev[0] > x) or (edge == "right" and x >= m.right - 2 and prev[0] < x) or (edge == "top" and y <= m.top + 1 and prev[1] > y) or (edge == "bottom" and y >= m.bottom - 2 and prev[1] < y)
        if not hit:
            return
        tx, ty, _target_edge = self._target_point(idx, edge, x, y)
        ctypes.windll.user32.SetCursorPos(int(tx), int(ty))
        self._last_warp_t = now

    def _edge_point(self, m: Monitor, edge: str, x: int, y: int) -> Tuple[int, int]:
        h = self._edge_pad()
        if edge == "left":
            return m.left + h, max(m.top + h, min(m.bottom - h, y))
        if edge == "right":
            return m.right - h, max(m.top + h, min(m.bottom - h, y))
        if edge == "top":
            return max(m.left + h, min(m.right - h, x)), m.top + h
        return max(m.left + h, min(m.right - h, x)), m.bottom - h

    def _target_point(self, idx: int, edge: str, x: int, y: int) -> Tuple[int, int, str]:
        src = self._monitors[idx]
        adjacent = self._find_adjacent(idx, edge, x, y)
        if adjacent is not None:
            tgt, target_edge = adjacent
        elif edge in ("left", "right"):
            line = [m for m in self._monitors if m.top <= y < m.bottom]
            tgt = (max(line, key=lambda m: m.right) if edge == "left" else min(line, key=lambda m: m.left)) if line else src
            target_edge = "right" if edge == "left" else "left"
        else:
            line = [m for m in self._monitors if m.left <= x < m.right]
            tgt = (max(line, key=lambda m: m.bottom) if edge == "top" else min(line, key=lambda m: m.top)) if line else src
            target_edge = "bottom" if edge == "top" else "top"

        pad = self._edge_pad()
        if target_edge == "left":
            tx = tgt.left + pad
            ty = max(tgt.top + pad, min(tgt.bottom - pad, y))
        elif target_edge == "right":
            tx = tgt.right - pad
            ty = max(tgt.top + pad, min(tgt.bottom - pad, y))
        elif target_edge == "top":
            tx = max(tgt.left + pad, min(tgt.right - pad, x))
            ty = tgt.top + pad
        else:
            tx = max(tgt.left + pad, min(tgt.right - pad, x))
            ty = tgt.bottom - pad
        return tx, ty, target_edge

    def _edge_pad(self) -> int:
        base = max(8.0, self._safe_float(self.marker_size_px, 44.0))
        hi = max(1.0, self._safe_float(self.max_scale, 1.8))
        gap = self._safe_float(self.edge_gap, 2.0)
        return int(max(10, round((base * hi) / 2.0 + gap)))

    @staticmethod
    def _lerp_color_hex(a_hex: str, b_hex: str, t: float) -> str:
        t = max(0.0, min(1.0, t))
        ar = int(a_hex[1:3], 16); ag = int(a_hex[3:5], 16); ab = int(a_hex[5:7], 16)
        br = int(b_hex[1:3], 16); bg = int(b_hex[3:5], 16); bb = int(b_hex[5:7], 16)
        rr = int(ar + (br - ar) * t)
        rg = int(ag + (bg - ag) * t)
        rb = int(ab + (bb - ab) * t)
        return f"#{rr:02x}{rg:02x}{rb:02x}"

    def _marker_colors(self, proximity: float) -> Tuple[str, str]:
        if not self.gradient_enabled:
            return "#0070ff", "#ff7f1f"
        in_color = self._lerp_color_hex("#ff7f1f", "#0070ff", proximity)
        out_color = self._lerp_color_hex("#0070ff", "#ff7f1f", proximity)
        return in_color, out_color

    def _edge_proximity(self, m: Monitor, edge: str, x: int, y: int) -> float:
        if edge == "left":
            d = abs(x - m.left)
        elif edge == "right":
            d = abs(m.right - x)
        elif edge == "top":
            d = abs(y - m.top)
        else:
            d = abs(m.bottom - y)
        r = max(16.0, self._safe_float(self.gradient_range_px, 240.0))
        return max(0.0, min(1.0, 1.0 - (float(d) / r)))

    def _marker_half_size(self, monitor_idx: int, proximity: float) -> int:
        base = max(8.0, self._safe_float(self.marker_size_px, 44.0))
        mode = str(self.size_mode or "Same Pixels")
        if mode == "Per-Monitor DPI":
            base *= self._dpi_scale_for_monitor(monitor_idx)
        elif mode == "Resolution Relative":
            base *= self._resolution_scale_for_monitor(monitor_idx)
        if self.scale_with_proximity:
            lo = max(0.2, self._safe_float(self.min_scale, 1.0))
            hi = max(lo, self._safe_float(self.max_scale, 1.8))
            base *= lo + (hi - lo) * max(0.0, min(1.0, proximity))
        return int(round(base / 2.0))

    @staticmethod
    def _safe_float(value: object, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _dpi_scale_for_monitor(self, monitor_idx: int) -> float:
        if monitor_idx < 0 or monitor_idx >= len(self._overlays):
            return 1.0
        w = self._overlays[monitor_idx][0]
        try:
            hwnd = int(w.winfo_id())
        except tk.TclError:
            return 1.0
        cached = self._window_dpi_scale.get(hwnd)
        if cached is not None:
            return cached
        scale = 1.0
        try:
            dpi = int(ctypes.windll.user32.GetDpiForWindow(hwnd))
            if dpi > 0:
                scale = dpi / 96.0
        except Exception:
            pass
        self._window_dpi_scale[hwnd] = scale
        return scale

    def _resolution_scale_for_monitor(self, monitor_idx: int) -> float:
        if monitor_idx < 0 or monitor_idx >= len(self._monitors):
            return 1.0
        m = self._monitors[monitor_idx]
        w = max(1, m.right - m.left)
        h = max(1, m.bottom - m.top)
        # 1080p baseline.
        return max(0.6, min(2.5, min(w / 1920.0, h / 1080.0)))

    def _find_adjacent(self, src_idx: int, edge: str, x: int, y: int) -> Optional[Tuple[Monitor, str]]:
        src = self._monitors[src_idx]
        for i, m in enumerate(self._monitors):
            if i == src_idx:
                continue
            if edge == "left" and m.right == src.left and max(src.top, m.top) < min(src.bottom, m.bottom):
                return m, "right"
            if edge == "right" and m.left == src.right and max(src.top, m.top) < min(src.bottom, m.bottom):
                return m, "left"
            if edge == "top" and m.bottom == src.top and max(src.left, m.left) < min(src.right, m.right):
                return m, "bottom"
            if edge == "bottom" and m.top == src.bottom and max(src.left, m.left) < min(src.right, m.right):
                return m, "top"
        return None

    @staticmethod
    def _arrow_points(x: int, y: int, half: int, edge: str, into_screen: bool, is_out: bool) -> List[int]:
        # In marker points toward edge by default, out marker points opposite.
        flip_for_out = is_out
        if into_screen:
            flip_for_out = not flip_for_out
        point_left = edge == "left"
        point_right = edge == "right"
        point_up = edge == "top"
        point_down = edge == "bottom"
        if flip_for_out:
            point_left, point_right = point_right, point_left
            point_up, point_down = point_down, point_up
        if point_left:
            return [x - half, y, x + half, y - half, x + half, y + half]
        if point_right:
            return [x + half, y, x - half, y - half, x - half, y + half]
        if point_up:
            return [x, y - half, x - half, y + half, x + half, y + half]
        return [x, y + half, x - half, y - half, x + half, y - half]

    @staticmethod
    def _nearest_edge(m: Monitor, x: int, y: int) -> str:
        d = {"left": abs(x - m.left), "right": abs(m.right - x), "top": abs(y - m.top), "bottom": abs(m.bottom - y)}
        return min(d, key=d.get)

    def _cursor_pos(self) -> Tuple[int, int]:
        p = POINT(); ctypes.windll.user32.GetCursorPos(ctypes.byref(p)); return p.x, p.y

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
            out.append(Monitor(int(_h), rc.left, rc.top, rc.right, rc.bottom))
            return 1
        ctypes.windll.user32.EnumDisplayMonitors(0, 0, cb_t(cb), 0)
        return out

    def shutdown(self) -> None:
        self._running = False
        if self._tray is not None:
            self._tray.stop()
        for w, _c, _m in self._overlays:
            try: w.destroy()
            except tk.TclError: pass
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


def _hide_console_window() -> None:
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            SW_HIDE = 0
            ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="CursorWarp-GUI overlay app.")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-click-through", action="store_true")
    parser.add_argument("--show-console", action="store_true", help="Keep console window visible.")
    args = parser.parse_args()
    _enable_dpi_awareness()
    if not args.show_console:
        _hide_console_window()
    app = CursorWarpGUIApp(debug=args.debug, click_through=not args.no_click_through)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
