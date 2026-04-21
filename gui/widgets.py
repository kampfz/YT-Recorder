"""
Lightweight styled widget helpers matching the HTML prototype design.
All widgets use plain tkinter so colors/borders are fully controllable.
"""
import tkinter as tk
from gui.theme import (
    BG_PANEL, BG_ELEV, BG_INPUT, BD, BD_SUBTLE, BD_FOCUS,
    FG, FG_MUTED, FG_DIM, FG_FAINT,
    ACCENT, ACCENT_HI, OK, WARN, ERR, INFO,
    MONO, UI, badge_colors,
)

# ── font helpers ──────────────────────────────────────────────────────────────

def font(family=UI, size=12, bold=False):
    return (family, size, "bold" if bold else "normal")

def mono(size=11, bold=False):  return font(MONO, size, bold)
def ui(size=12, bold=False):    return font(UI,   size, bold)


# ── containers ────────────────────────────────────────────────────────────────

def Frame(parent, bg=BG_PANEL, **kw):
    return tk.Frame(parent, bg=bg, bd=0, highlightthickness=0, **kw)

def ElevFrame(parent, **kw):
    return Frame(parent, bg=BG_ELEV, **kw)

def Sep(parent, bg=BD_SUBTLE, horizontal=True, **kw):
    """1-px separator line."""
    if horizontal:
        return tk.Frame(parent, bg=bg, height=1, bd=0, **kw)
    return tk.Frame(parent, bg=bg, width=1, bd=0, **kw)

def Label(parent, text="", fg=FG, bg=BG_PANEL, size=12, bold=False,
          family=UI, anchor="w", **kw):
    return tk.Label(parent, text=text, fg=fg, bg=bg,
                    font=(family, size, "bold" if bold else "normal"),
                    anchor=anchor, bd=0, **kw)

def MonoLabel(parent, text="", fg=FG_MUTED, bg=BG_PANEL, size=11, **kw):
    return Label(parent, text=text, fg=fg, bg=bg, size=size, family=MONO, **kw)

def SectionHeader(parent, text, hint="", bg=BG_PANEL):
    """Uppercase section label with optional hint."""
    f = Frame(parent, bg=bg)
    tk.Label(f, text=text, fg=FG_DIM, bg=bg,
             font=(MONO, 9, "bold")).pack(side="left")
    if hint:
        tk.Label(f, text=hint, fg=FG_FAINT, bg=bg,
                 font=(MONO, 9)).pack(side="left", padx=(10, 0))
    return f


class FlowFrame(tk.Frame):
    """A frame that wraps children to the next line when width is exceeded."""

    def __init__(self, parent, bg=BG_PANEL, padx=4, pady=4, **kw):
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0, **kw)
        self._padx = padx
        self._pady = pady
        self._widgets = []
        self.bind("<Configure>", self._on_configure)

    def add_widget(self, widget):
        self._widgets.append(widget)
        self._layout()

    def clear(self):
        for w in self._widgets:
            w.destroy()
        self._widgets.clear()

    def _on_configure(self, event=None):
        self._layout()

    def _layout(self):
        if not self._widgets:
            return
        max_width = self.winfo_width()
        if max_width <= 1:
            max_width = self.winfo_reqwidth() or 400

        x, y = 0, 0
        row_height = 0

        for w in self._widgets:
            w.update_idletasks()
            w_width = w.winfo_reqwidth()
            w_height = w.winfo_reqheight()

            if x + w_width > max_width and x > 0:
                x = 0
                y += row_height + self._pady
                row_height = 0

            w.place(x=x, y=y)
            x += w_width + self._padx
            row_height = max(row_height, w_height)

        self.configure(height=y + row_height + self._pady)


# ── inputs ────────────────────────────────────────────────────────────────────

def Entry(parent, textvariable=None, mono_font=False, width=0, placeholder="", **kw):
    e = tk.Entry(
        parent,
        bg=BG_INPUT, fg=FG,
        insertbackground=FG,
        disabledbackground="#0a0d11",
        disabledforeground=FG_DIM,
        readonlybackground="#0a0d11",
        selectbackground=ACCENT,
        selectforeground="#fff",
        relief="flat",
        highlightthickness=1,
        highlightbackground=BD,
        highlightcolor=BD_FOCUS,
        font=(MONO if mono_font else UI, 11),
        bd=0,
        **kw,
    )
    if textvariable:
        e.configure(textvariable=textvariable)
    if placeholder and not textvariable:
        _placeholder(e, placeholder)
    return e

def _placeholder(entry, text):
    """Fake placeholder text using FocusIn/FocusOut."""
    entry.insert(0, text)
    entry.configure(fg=FG_FAINT)
    def _on_focus_in(e):
        if entry.get() == text:
            entry.delete(0, "end")
            entry.configure(fg=FG)
    def _on_focus_out(e):
        if not entry.get():
            entry.insert(0, text)
            entry.configure(fg=FG_FAINT)
    entry.bind("<FocusIn>", _on_focus_in)
    entry.bind("<FocusOut>", _on_focus_out)


# ── buttons ───────────────────────────────────────────────────────────────────

def Button(parent, text="", command=None, primary=False, ghost=False,
           danger=False, small=False, width=0, **kw):
    if primary:
        bg, fg, abg, hborder = "#357ed4", "#fff",   "#4ea3f5", "#2467ac"
    elif danger:
        bg, fg, abg, hborder = BG_ELEV,   ERR,     "#2b1a1c",  "#6b2a2e"
    elif ghost:
        bg, fg, abg, hborder = BG_PANEL,  FG_MUTED, BG_ELEV,   BD
    else:
        bg, fg, abg, hborder = "#1e232b", FG,       "#262c35",  BD

    pady = 3 if small else 5
    fsize = 10 if small else 11

    btn = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg,
        activebackground=abg, activeforeground=fg,
        relief="flat", bd=0,
        highlightthickness=1,
        highlightbackground=hborder,
        highlightcolor=hborder,
        padx=10, pady=pady,
        font=(UI, fsize),
        cursor="hand2",
        **kw,
    )
    if width:
        btn.configure(width=width)
    return btn

def IconButton(parent, text="✕", command=None, **kw):
    return tk.Button(
        parent, text=text, command=command,
        bg=BG_PANEL, fg=FG_DIM,
        activebackground="#2b1a1c", activeforeground=ERR,
        relief="flat", bd=0,
        highlightthickness=1,
        highlightbackground="transparent",
        highlightcolor=BD,
        padx=4, pady=3,
        font=(MONO, 11),
        cursor="hand2",
        **kw,
    )


# ── progress bar (Canvas-based, 4px) ─────────────────────────────────────────

class ProgressBar(tk.Canvas):
    COLORS = {
        "download": ACCENT,
        "record":   ERR,
        "done":     OK,
        "warn":     WARN,
        "error":    "#6b2a2e",
        "cancel":   "#363d48",
    }

    def __init__(self, parent, mode="download", bg=BG_PANEL, **kw):
        super().__init__(parent, height=4, bg=bg,
                         highlightthickness=0, bd=0, **kw)
        self._mode = mode
        self._value = 0.0
        self._track = None
        self._fill = None
        self.bind("<Configure>", self._redraw)

    def set(self, value: float, mode: str | None = None):
        self._value = max(0.0, min(1.0, value))
        if mode:
            self._mode = mode
        self._redraw()

    def _redraw(self, event=None):
        self.delete("all")
        w = self.winfo_width() or 1
        h = 4
        self.configure(height=h)
        # Track
        self.create_rectangle(0, 0, w, h, fill="#0b0e12", outline="#1b2028")
        # Fill
        fw = int(w * self._value)
        if fw > 0:
            col = self.COLORS.get(self._mode, ACCENT)
            self.create_rectangle(0, 0, fw, h, fill=col, outline="")


# ── status badge ──────────────────────────────────────────────────────────────

class Badge(tk.Frame):
    def __init__(self, parent, status="Downloading", **kw):
        col, bg, border = badge_colors(status)
        super().__init__(parent, bg=bg, bd=1, relief="flat",
                         highlightthickness=1, highlightbackground=border, **kw)
        # Dot
        dot = tk.Canvas(self, width=6, height=6, bg=bg,
                        highlightthickness=0)
        dot.pack(side="left", padx=(7, 3), pady=4)
        dot.create_oval(0, 0, 6, 6, fill=col, outline="")
        self._dot = dot

        self._lbl = tk.Label(self, text=status.upper(), fg=col, bg=bg,
                              font=(MONO, 10, "bold"), padx=0, pady=0)
        self._lbl.pack(side="left", padx=(0, 7), pady=3)
        self._col = col
        self._bg = bg

    def set_status(self, status: str):
        col, bg, border = badge_colors(status)
        self.configure(bg=bg, highlightbackground=border)
        self._dot.configure(bg=bg)
        self._dot.delete("all")
        self._dot.create_oval(0, 0, 6, 6, fill=col, outline="")
        self._lbl.configure(text=status.upper(), fg=col, bg=bg)


# ── thumbnail placeholder ─────────────────────────────────────────────────────

THUMB_PALETTES = [
    ("#1a2030", "#0f1520"), ("#162438", "#0a1628"),
    ("#1a1530", "#2a1a3a"), ("#1a2010", "#242a18"),
    ("#102030", "#183040"), ("#201018", "#301828"),
]

def Thumbnail(parent, idx=0, mode="video", width=76, height=44, bg=BG_PANEL):
    dark, light = THUMB_PALETTES[idx % len(THUMB_PALETTES)]
    c = tk.Canvas(parent, width=width, height=height,
                  bg=dark, highlightthickness=1, highlightbackground=BD,
                  cursor="arrow")
    _draw_thumb(c, width, height, mode, dark)
    return c

def _draw_thumb(canvas, w, h, mode, bg):
    canvas.delete("all")
    cx, cy = w // 2, h // 2
    if mode == "live":
        canvas.create_rectangle(0, 0, w, h, fill="#0a1628", outline="")
        canvas.create_rectangle(3, 3, 32, 12, fill=ERR, outline="")
        canvas.create_oval(5, 5, 10, 10, fill="#fff", outline="")
        canvas.create_text(13, 7, text="LIVE", fill="#fff", font=(MONO, 7, "bold"), anchor="w")
    elif mode == "soon":
        canvas.create_rectangle(3, 3, 36, 12, fill="black", outline="", stipple="gray50")
        canvas.create_text(4, 7, text="SOON", fill=WARN, font=(MONO, 7, "bold"), anchor="w")
    elif mode == "audio":
        canvas.create_text(cx, cy, text="♪", fill=FG_DIM, font=(UI, 14))
    elif mode == "broken":
        canvas.configure(bg="#160e10", highlightbackground="#3a2126")
        canvas.create_text(cx, cy, text="×", fill=ERR, font=(MONO, 16, "bold"))
        return
    else:
        # VOD: play triangle
        canvas.create_polygon(cx-8, cy-6, cx-8, cy+6, cx+8, cy,
                               fill="white", outline="")
    # Duration badge bottom-right
    canvas.create_rectangle(w-28, h-14, w-2, h-2, fill="black", outline="")
    canvas.create_text(w-15, h-8, text="—:—", fill="#fff", font=(MONO, 7))


# ── pill ─────────────────────────────────────────────────────────────────────

def Pill(parent, key="", value="", bg=BG_PANEL):
    f = tk.Frame(parent, bg="#0d1015",
                 highlightthickness=1, highlightbackground=BD_SUBTLE, bd=0)
    if key:
        tk.Label(f, text=key, fg=FG_DIM, bg="#0d1015",
                 font=(MONO, 10)).pack(side="left", padx=(6, 3), pady=2)
    tk.Label(f, text=value, fg=FG, bg="#0d1015",
             font=(MONO, 10)).pack(side="left", padx=(0, 6), pady=2)
    return f


# ── spinbox (numeric input with +/- buttons) ─────────────────────────────────

class Spinbox(tk.Frame):
    """Dark-themed numeric input with increment/decrement buttons."""

    def __init__(self, parent, value=0, min_val=1, max_val=999, width=5,
                 variable=None, bg=BG_ELEV, **kw):
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0, **kw)
        self._min = min_val
        self._max = max_val
        self._var = variable or tk.StringVar(value=str(value))
        self._bg = bg

        # Main container with border
        box = tk.Frame(self, bg=BG_INPUT, bd=0,
                       highlightthickness=1, highlightbackground=BD)
        box.pack(side="left")

        # Entry
        self._entry = tk.Entry(
            box, textvariable=self._var, width=width,
            bg=BG_INPUT, fg=FG, insertbackground=FG,
            relief="flat", bd=0, highlightthickness=0,
            font=(MONO, 11), justify="center",
        )
        self._entry.pack(side="left", padx=(8, 0), pady=4, ipady=2)

        # Buttons container
        btn_frame = tk.Frame(box, bg=BG_INPUT)
        btn_frame.pack(side="left", padx=(2, 4), pady=2)

        # Up button
        self._up = tk.Button(
            btn_frame, text="▲", command=self._increment,
            bg=BG_INPUT, fg=FG_DIM, activebackground=BG_ELEV, activeforeground=FG,
            relief="flat", bd=0, highlightthickness=0,
            font=(UI, 6), padx=4, pady=0, cursor="hand2",
        )
        self._up.pack(side="top")

        # Down button
        self._down = tk.Button(
            btn_frame, text="▼", command=self._decrement,
            bg=BG_INPUT, fg=FG_DIM, activebackground=BG_ELEV, activeforeground=FG,
            relief="flat", bd=0, highlightthickness=0,
            font=(UI, 6), padx=4, pady=0, cursor="hand2",
        )
        self._down.pack(side="top")

    def _increment(self):
        try:
            val = int(self._var.get()) + 1
            if val <= self._max:
                self._var.set(str(val))
        except ValueError:
            pass

    def _decrement(self):
        try:
            val = int(self._var.get()) - 1
            if val >= self._min:
                self._var.set(str(val))
        except ValueError:
            pass

    def get(self):
        return self._var.get()

    def set(self, value):
        self._var.set(str(value))

    @property
    def variable(self):
        return self._var


# ── slider with value display ─────────────────────────────────────────────────

class Slider(tk.Frame):
    """Dark-themed slider with min/max labels and value display box."""

    def __init__(self, parent, from_=1, to=10, value=5, variable=None,
                 width=160, bg=BG_ELEV, command=None, **kw):
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0, **kw)
        self._from = from_
        self._to = to
        self._var = variable or tk.IntVar(value=value)
        self._command = command
        self._bg = bg
        self._dragging = False

        # Min label
        tk.Label(self, text=str(from_), fg=FG_FAINT, bg=bg,
                 font=(MONO, 9)).pack(side="left", padx=(0, 4))

        # Canvas for custom slider track
        self._canvas = tk.Canvas(self, width=width, height=20, bg=bg,
                                  highlightthickness=0, bd=0)
        self._canvas.pack(side="left")
        self._canvas.bind("<ButtonPress-1>", self._on_click)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)

        # Max label
        tk.Label(self, text=str(to), fg=FG_FAINT, bg=bg,
                 font=(MONO, 9)).pack(side="left", padx=(4, 8))

        # Value display box
        self._val_lbl = tk.Label(self, text=str(self._var.get()), fg=FG, bg=BG_INPUT,
                                  font=(MONO, 11, "bold"), width=3,
                                  highlightthickness=1, highlightbackground=BD)
        self._val_lbl.pack(side="left", ipady=2)

        self._width = width
        self._var.trace_add("write", self._on_var_change)
        self.after(10, self._draw)

    def _draw(self):
        c = self._canvas
        c.delete("all")
        w = self._width
        h = 20
        track_y = h // 2

        # Track background
        c.create_line(8, track_y, w - 8, track_y, fill=BD, width=3, capstyle="round")

        # Calculate thumb position
        val = self._var.get()
        frac = (val - self._from) / (self._to - self._from)
        thumb_x = 8 + int(frac * (w - 16))

        # Filled portion
        c.create_line(8, track_y, thumb_x, track_y, fill=ACCENT, width=3, capstyle="round")

        # Thumb - white square with blue outline when dragging
        thumb_size = 6
        outline_color = ACCENT if self._dragging else ""
        outline_width = 2 if self._dragging else 0
        c.create_rectangle(
            thumb_x - thumb_size, track_y - thumb_size,
            thumb_x + thumb_size, track_y + thumb_size,
            fill="#ffffff", outline=outline_color, width=outline_width
        )

    def _on_click(self, event):
        self._dragging = True
        self._set_from_x(event.x)

    def _on_drag(self, event):
        self._set_from_x(event.x)

    def _on_release(self, event):
        self._dragging = False
        self._draw()

    def _set_from_x(self, x):
        w = self._width
        frac = max(0, min(1, (x - 8) / (w - 16)))
        val = int(self._from + frac * (self._to - self._from))
        val = max(self._from, min(self._to, val))
        self._var.set(val)

    def _on_var_change(self, *_):
        self._val_lbl.configure(text=str(self._var.get()))
        self._draw()
        if self._command:
            self._command(self._var.get())

    def get(self):
        return self._var.get()

    def set(self, value):
        self._var.set(value)

    @property
    def variable(self):
        return self._var


# ── scrollable container ──────────────────────────────────────────────────────

class ScrollFrame(tk.Frame):
    """Vertically scrollable frame."""
    def __init__(self, parent, bg=BG_PANEL, **kw):
        super().__init__(parent, bg=bg, **kw)
        vbar = tk.Scrollbar(self, orient="vertical",
                            troughcolor="#0b0e12", bg=BD, activebackground=BD_SUBTLE,
                            relief="flat", bd=0, width=10)
        vbar.pack(side="right", fill="y")

        canvas = tk.Canvas(self, bg=bg, bd=0, highlightthickness=0,
                           yscrollcommand=vbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        vbar.configure(command=canvas.yview)

        self.inner = tk.Frame(canvas, bg=bg)
        self._win = canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._vbar = vbar

        def _resize_inner(event=None):
            w = canvas.winfo_width()
            if w > 1:
                canvas.itemconfig(self._win, width=w)
                self.inner.configure(width=w)
                self.inner.update_idletasks()

        self.inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", _resize_inner)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(
            int(-1 * (e.delta / 120)), "units"))
        self._canvas = canvas
        self.after(100, _resize_inner)
