"""
Shared design system for the voice search launcher UI.

Every window in the app pulls its colors, fonts, and spacing from a single
Theme object so the whole app looks and feels consistent (unlike the
previous version, where each window improvised its own palette).
"""

import tkinter as tk
from tkinter import ttk


FONT_FAMILY = "Segoe UI"
FONT_FAMILY_FALLBACKS = ("Segoe UI", "SF Pro Text", "Ubuntu", "Noto Sans", "Sans")
MONO_FAMILY_FALLBACKS = ("Cascadia Code", "SF Mono", "Consolas", "Ubuntu Mono", "Monospace")


def _first_available_font(root, candidates):
    try:
        import tkinter.font as tkfont
        available = set(tkfont.families(root))
    except Exception:
        return candidates[-1]
    for name in candidates:
        if name in available:
            return name
    return candidates[-1]


class Theme:
    """A resolved set of design tokens for one appearance (dark/light)."""

    # 8px spacing scale used everywhere instead of ad-hoc padx/pady values.
    SPACE_XS = 4
    SPACE_SM = 8
    SPACE_MD = 12
    SPACE_LG = 16
    SPACE_XL = 24
    SPACE_XXL = 32

    RADIUS_NOTE = "Tk has no native rounded rects for plain widgets; " \
                  "canvas-drawn surfaces use ROUND_* below for rounded corners."
    ROUND_SM = 6
    ROUND_MD = 10
    ROUND_LG = 14

    def __init__(self, name, tokens, font_family="Sans", mono_family="Monospace"):
        self.name = name
        self.font_family = font_family
        self.mono_family = mono_family
        for k, v in tokens.items():
            setattr(self, k, v)

    # -- font helpers -----------------------------------------------------
    def font(self, size, weight="normal", slant="roman", mono=False):
        family = self.mono_family if mono else self.font_family
        return (family, size, weight, slant) if slant != "roman" else (family, size, weight)

    def font_title(self):
        return self.font(15, "bold")

    def font_subtitle(self):
        return self.font(10, "normal")

    def font_body(self):
        return self.font(11, "normal")

    def font_body_bold(self):
        return self.font(11, "bold")

    def font_small(self):
        return self.font(9, "normal")

    def font_small_bold(self):
        return self.font(9, "bold")

    def font_mono(self, size=11):
        return self.font(size, "normal", mono=True)


DARK_TOKENS = {
    "bg": "#111217",            # app background (slightly deeper for more contrast with cards)
    "bg_elevated": "#1c1e24",   # cards / panels
    "bg_elevated_2": "#22242b", # nested panels / inputs
    "bg_hover": "#2a2d36",
    "border": "#2e313a",
    "border_strong": "#3c4049",
    "fg": "#e7e8ec",
    "fg_muted": "#9498a3",
    "fg_faint": "#5f6470",
    "accent": "#7c8cff",        # indigo accent (buttons, active states)
    "accent_hover": "#8f9dff",
    "accent_press": "#6a79e6",  # pressed state -- distinct from hover, not just a re-use
    "accent_soft": "#2a2c58",   # low-opacity-look accent fill for subtle highlights/selection
    "accent_fg": "#0d0e12",
    "success": "#3ddc97",
    "warning": "#f5b942",
    "danger": "#ff6b6b",
    "danger_hover": "#ff8787",
    "danger_press": "#e65a5a",
    "meter_low": "#3ddc97",
    "meter_mid": "#f5b942",
    "meter_high": "#ff6b6b",
    "meter_off": "#2a2d36",
    "scrollbar": "#3c4049",
    "shadow": "#000000",
    "shadow_soft": "#0a0a0d",   # elevation ring around floating cards (StatusWindow/ConfirmWindow)
}

LIGHT_TOKENS = {
    "bg": "#f4f5f8",
    "bg_elevated": "#ffffff",
    "bg_elevated_2": "#eef0f4",
    "bg_hover": "#e6e8ee",
    "border": "#dde0e7",
    "border_strong": "#c7cbd6",
    "fg": "#1c1e24",
    "fg_muted": "#5c6070",
    "fg_faint": "#8b8f9c",
    "accent": "#5a67f2",
    "accent_hover": "#4a56e0",
    "accent_press": "#3d48c9",
    "accent_soft": "#e4e6fd",
    "accent_fg": "#ffffff",
    "success": "#1f9d6f",
    "warning": "#b8790f",
    "danger": "#d64545",
    "danger_hover": "#c23a3a",
    "danger_press": "#a83030",
    "meter_low": "#1f9d6f",
    "meter_mid": "#b8790f",
    "meter_high": "#d64545",
    "meter_off": "#e0e2e8",
    "scrollbar": "#c7cbd6",
    "shadow": "#9aa0ab",
    "shadow_soft": "#c3c7d1",
}


_THEME_CACHE = {}


def get_theme(root, name="Dark"):
    """Resolve (and cache) a Theme for the given appearance name."""
    key = name
    if key in _THEME_CACHE:
        return _THEME_CACHE[key]
    tokens = DARK_TOKENS if name == "Dark" else LIGHT_TOKENS
    font_family = _first_available_font(root, FONT_FAMILY_FALLBACKS)
    mono_family = _first_available_font(root, MONO_FAMILY_FALLBACKS)
    theme = Theme(name, tokens, font_family=font_family, mono_family=mono_family)
    _THEME_CACHE[key] = theme
    return theme


def clear_theme_cache():
    _THEME_CACHE.clear()


def style_ttk(root, theme):
    """Configure ttk styles (Combobox, Scrollbar, Scale, Treeview) to match the theme."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure("TCombobox",
                     fieldbackground=theme.bg_elevated_2,
                     background=theme.bg_elevated_2,
                     foreground=theme.fg,
                     arrowcolor=theme.fg_muted,
                     bordercolor=theme.border,
                     lightcolor=theme.bg_elevated_2,
                     darkcolor=theme.bg_elevated_2,
                     borderwidth=1,
                     padding=6)
    style.map("TCombobox",
              fieldbackground=[("readonly", theme.bg_elevated_2)],
              foreground=[("readonly", theme.fg)],
              selectbackground=[("readonly", theme.bg_elevated_2)],
              selectforeground=[("readonly", theme.fg)])

    style.configure("Vertical.TScrollbar",
                     background=theme.scrollbar,
                     troughcolor=theme.bg,
                     bordercolor=theme.bg,
                     arrowcolor=theme.fg_muted,
                     relief="flat")
    style.map("Vertical.TScrollbar", background=[("active", theme.border_strong)])

    style.configure("TScale",
                     background=theme.bg_elevated,
                     troughcolor=theme.bg_elevated_2,
                     bordercolor=theme.bg_elevated,
                     lightcolor=theme.accent,
                     darkcolor=theme.accent)

    style.configure("Treeview",
                     background=theme.bg_elevated,
                     fieldbackground=theme.bg_elevated,
                     foreground=theme.fg,
                     bordercolor=theme.border,
                     rowheight=28,
                     borderwidth=0,
                     font=theme.font_body())
    style.map("Treeview",
              background=[("selected", theme.accent)],
              foreground=[("selected", theme.accent_fg)])
    style.configure("Treeview.Heading",
                     background=theme.bg_elevated_2,
                     foreground=theme.fg_muted,
                     borderwidth=0,
                     relief="flat",
                     font=theme.font_small_bold())
    style.map("Treeview.Heading", background=[("active", theme.bg_hover)])

    style.configure("TNotebook", background=theme.bg, borderwidth=0)
    style.configure("TNotebook.Tab",
                     background=theme.bg_elevated,
                     foreground=theme.fg_muted,
                     padding=(14, 8),
                     borderwidth=0,
                     font=theme.font_small_bold())
    style.map("TNotebook.Tab",
              background=[("selected", theme.bg_elevated_2)],
              foreground=[("selected", theme.fg)])

    return style


def apply_window_chrome(win, theme):
    """Best-effort dark titlebar + base background for a Toplevel/Tk window."""
    win.configure(bg=theme.bg)
    try:
        win.attributes("-alpha", 1.0)
    except Exception:
        pass
    # Best-effort Windows dark titlebar (no-op elsewhere).
    try:
        import ctypes
        HWND = ctypes.windll.user32.GetParent(win.winfo_id())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1 if theme.name == "Dark" else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            HWND, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


class PillButton(tk.Canvas):
    """A flat, rounded, hoverable button drawn on a canvas.

    Replaces the raw tk.Button-with-hardcoded-hex-colors pattern used
    throughout the old UI so every button shares consistent radius,
    hover/press states, and theme awareness.
    """

    def __init__(self, parent, theme, text, command=None, kind="secondary",
                 width=None, height=34, font=None, icon=None):
        self._theme = theme
        self._kind = kind
        self._text = text
        self._icon = icon
        self._command = command
        self._enabled = True
        self._font = font or theme.font_body_bold()

        bg_parent = parent.cget("bg") if "bg" in parent.keys() else theme.bg
        super().__init__(parent, height=height, bg=bg_parent, highlightthickness=0, bd=0)

        self._colors = self._resolve_colors(kind)
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", lambda e: self._on_press())
        self.bind("<ButtonRelease-1>", lambda e: self._on_release())
        self._hover = False
        self._pressed = False

        if width:
            self.config(width=width)
        else:
            # Rough auto-width based on text length; caller can override via pack/grid opts.
            self.config(width=max(64, 16 * len(text) + (26 if icon else 0)))

        self._redraw()

    def _resolve_colors(self, kind):
        t = self._theme
        if kind == "primary":
            return {"fill": t.accent, "hover": t.accent_hover, "press": t.accent_press, "fg": t.accent_fg, "border": None}
        if kind == "danger":
            return {"fill": t.danger, "hover": t.danger_hover, "press": t.danger_press, "fg": "#ffffff", "border": None}
        if kind == "ghost":
            return {"fill": t.bg_elevated, "hover": t.bg_hover, "press": t.bg_hover, "fg": t.fg_muted, "border": t.border}
        # secondary (default)
        return {"fill": t.bg_elevated_2, "hover": t.bg_hover, "press": t.border, "fg": t.fg, "border": t.border}

    def set_enabled(self, enabled):
        self._enabled = enabled
        self._redraw()

    def set_text(self, text):
        self._text = text
        self._redraw()

    def set_kind(self, kind):
        self._kind = kind
        self._colors = self._resolve_colors(kind)
        self._redraw()

    def _set_hover(self, is_hover):
        if not self._enabled:
            return
        self._hover = is_hover
        self.config(cursor="hand2" if is_hover else "")
        self._redraw()

    def _on_press(self):
        if not self._enabled:
            return
        self._pressed = True
        self._redraw()

    def _on_release(self):
        was_pressed = self._pressed
        self._pressed = False
        self._redraw()
        if was_pressed and self._enabled and self._command:
            self._command()

    def _redraw(self):
        self.delete("all")
        w = self.winfo_width() or int(self.cget("width"))
        h = self.winfo_height() or int(self.cget("height"))
        c = self._colors
        if not self._enabled:
            fill = self._theme.bg_elevated_2
        elif self._pressed:
            fill = c.get("press", c["hover"])
        elif self._hover:
            fill = c["hover"]
        else:
            fill = c["fill"]
        # Pressed state insets by 1px on each side -- a small tactile "settle"
        # instead of an instant flat color swap, so clicks feel acknowledged.
        inset = 1 if (self._pressed and self._enabled) else 0
        r = min(Theme.ROUND_SM + 2, h // 2)
        self._round_rect(1 + inset, 1 + inset, max(w - 1 - inset, 2), max(h - 1 - inset, 2), r, fill=fill,
                          outline=(c["border"] or fill), width=1 if c["border"] else 0)
        fg = c["fg"] if self._enabled else self._theme.fg_faint
        label = f"{self._icon}  {self._text}" if self._icon else self._text
        self.create_text(w // 2, h // 2, text=label, fill=fg, font=self._font)

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)





class Card(tk.Frame):
    """A flat elevated panel with a subtle border -- the base unit of the layout."""

    def __init__(self, parent, theme, padding=Theme.SPACE_MD, **kwargs):
        super().__init__(parent, bg=theme.bg_elevated,
                          highlightbackground=theme.border, highlightthickness=1,
                          bd=0, **kwargs)
        self._inner = tk.Frame(self, bg=theme.bg_elevated)
        self._inner.pack(fill="both", expand=True, padx=padding, pady=padding)

    @property
    def body(self):
        return self._inner


def _blend_hex(hex_color, target_hex, amount):
    """Blend hex_color toward target_hex by `amount` (0=hex_color, 1=target_hex)."""
    h = hex_color.lstrip("#")
    t = target_hex.lstrip("#")
    r1, g1, b1 = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r2, g2, b2 = int(t[0:2], 16), int(t[2:4], 16), int(t[4:6], 16)
    r = round(r1 + (r2 - r1) * amount)
    g = round(g1 + (g2 - g1) * amount)
    b = round(b1 + (b2 - b1) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


class RoundedCard(tk.Frame):
    """A true rounded-corner elevated surface for floating/borderless windows.

    Where Card uses a plain 1px-border tk.Frame (fine for panels embedded in
    an ordinary titled window), RoundedCard draws its own rounded outline and
    a soft one-pixel-wider "elevation ring" behind it on a canvas -- used for
    windows that set overridedirect(True) (StatusWindow, ConfirmWindow),
    where there's no OS chrome to imply the window has depth, so the card
    itself needs to look like it's floating rather than a plain rectangle.
    """

    def __init__(self, parent, theme, radius=Theme.ROUND_LG, **kwargs):
        self._theme = theme
        self._radius = radius
        bg_parent = parent.cget("bg") if "bg" in parent.keys() else theme.bg
        super().__init__(parent, bg=bg_parent, **kwargs)

        self._canvas = tk.Canvas(self, bg=bg_parent, highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)
        self._inner = tk.Frame(self._canvas, bg=theme.bg_elevated)
        self._canvas.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        self._canvas.delete("card")
        w, h = event.width, event.height
        # Soft elevation: two stacked rings, each offset a little further
        # down-and-right and blended toward black/white respectively, read
        # together as a soft drop shadow without needing real alpha
        # compositing (Tk canvases don't support translucent fills).
        is_light = self._theme.name == "Light"
        target = "#ffffff" if is_light else "#000000"
        ring_far = _blend_hex(self._theme.bg, target, 0.35 if is_light else 0.55)
        ring_near = _blend_hex(self._theme.bg, target, 0.18 if is_light else 0.3)
        self._round_rect(self._canvas, 4, 7, w - 4, h - 1, self._radius, fill=ring_far, tags="card")
        self._round_rect(self._canvas, 2, 4, w - 3, h - 2, self._radius, fill=ring_near, tags="card")
        self._round_rect(self._canvas, 0, 0, w - 5, h - 6, self._radius, fill=self._theme.bg_elevated,
                          outline=self._theme.border, width=1, tags="card")
        self._canvas.create_window(1, 1, window=self._inner, anchor="nw",
                                    width=max(w - 7, 1), height=max(h - 8, 1), tags="card")

    @staticmethod
    def _round_rect(canvas, x1, y1, x2, y2, r, **kwargs):
        r = max(0, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return canvas.create_polygon(points, smooth=True, **kwargs)

    @property
    def body(self):
        return self._inner


class SectionLabel(tk.Label):
    """Small caps-style section heading used in Settings and elsewhere."""

    def __init__(self, parent, theme, text, **kwargs):
        super().__init__(parent, text=text.upper(), bg=parent.cget("bg"),
                          fg=theme.fg_faint, font=theme.font_small_bold(),
                          anchor="w", **kwargs)


def toggle_switch(parent, theme, initial, on_change, width=40, height=22):
    """A macOS/iOS-style toggle switch drawn on a small canvas."""
    canvas = tk.Canvas(parent, width=width, height=height,
                        bg=parent.cget("bg"), highlightthickness=0, bd=0, cursor="hand2")
    state = {"on": bool(initial)}

    def redraw():
        canvas.delete("all")
        on = state["on"]
        track_fill = theme.accent if on else theme.bg_elevated_2
        outline = theme.accent if on else theme.border_strong
        r = height // 2
        canvas.create_oval(1, 1, height - 1, height - 1, fill=track_fill, outline=outline)
        canvas.create_oval(width - height + 1, 1, width - 1, height - 1, fill=track_fill, outline=outline)
        canvas.create_rectangle(r, 1, width - r, height - 1, fill=track_fill, outline=track_fill)
        knob_x = (width - height + 2) if on else 2
        canvas.create_oval(knob_x, 2, knob_x + height - 4, height - 2,
                            fill="#ffffff", outline=theme.shadow if theme.name == "Light" else "")

    def on_click(_evt):
        state["on"] = not state["on"]
        redraw()
        on_change(state["on"])

    canvas.bind("<Button-1>", on_click)
    redraw()
    canvas.set_value = lambda v: (state.update(on=bool(v)), redraw())
    canvas.get_value = lambda: state["on"]
    return canvas