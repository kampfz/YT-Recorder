"""
Custom tab bar matching the HTML prototype exactly:
- Dark background (#0d1015)
- Active tab: panel bg (#14181e), 1px border on 3 sides, bottom gap blends into panel
- Colored dot indicator per tab
- Pending-count badge support
"""
import tkinter as tk
from gui.theme import BG_PANEL, BD, FG, FG_MUTED, FG_FAINT, ACCENT, WARN, MONO, UI

_TAB_BG     = "#0d1015"
_HOVER_BG   = "#11151b"
_ACTIVE_BG  = BG_PANEL     # matches panel — creates seamless join
_BORDER     = BD
_H          = 38            # tab bar height


class TabBar(tk.Frame):
    def __init__(self, parent, tabs: list[str], on_switch: callable):
        super().__init__(parent, bg=_TAB_BG, height=_H, bd=0,
                         highlightthickness=0)
        self.pack_propagate(False)
        self._tabs: dict[str, dict] = {}
        self._on_switch = on_switch
        self._active: str | None = None
        self._badges: dict[str, tk.Label] = {}

        for name in tabs:
            self._add_tab(name)

        # Bottom border drawn as a 1-px frame (except we overdraw at active tab)
        self._bottom = tk.Frame(self, bg=_BORDER, height=1, bd=0)
        self._bottom.place(x=0, y=_H - 1, relwidth=1.0)

    # ── public ───────────────────────────────────────────────────────────────

    def activate(self, name: str):
        if self._active:
            self._set_tab_state(self._active, active=False)
        self._active = name
        self._set_tab_state(name, active=True)
        self._on_switch(name)

    def set_badge(self, name: str, count: int):
        """Show/hide a count badge on a tab."""
        if name in self._badges:
            if count > 0:
                self._badges[name].configure(text=str(count))
                self._badges[name].pack(side="left", padx=(4, 0))
            else:
                self._badges[name].pack_forget()

    # ── internal ─────────────────────────────────────────────────────────────

    def _add_tab(self, name: str):
        tab = tk.Frame(self, bg=_TAB_BG, bd=0, highlightthickness=0,
                       cursor="hand2")
        tab.pack(side="left", padx=(8 if not self._tabs else 2, 0), fill="y")

        # Inner content frame (provides the 1px side+top borders for active state)
        inner = tk.Frame(tab, bg=_TAB_BG, bd=0, highlightthickness=0)
        inner.pack(expand=True, fill="both", padx=1, pady=(1, 0))

        dot = tk.Canvas(inner, width=6, height=6, bg=_TAB_BG,
                        highlightthickness=0)
        dot.pack(side="left", padx=(12, 5), pady=0)
        _draw_dot(dot, FG_FAINT)

        lbl = tk.Label(inner, text=name, bg=_TAB_BG, fg=FG_MUTED,
                       font=(UI, 11), pady=0, padx=0)
        lbl.pack(side="left", pady=8, padx=(0, 4))

        # Optional badge
        badge = tk.Label(inner, text="", bg=_TAB_BG, fg=WARN,
                         font=(MONO, 9),
                         padx=5, pady=1,
                         relief="flat", bd=0,
                         highlightthickness=1, highlightbackground="#4a3a18")
        self._badges[name] = badge

        # Blank spacer after label
        tk.Label(inner, text="", bg=_TAB_BG, width=1).pack(side="left", padx=(0, 10))

        # Bind hover + click to all children
        for widget in (tab, inner, dot, lbl):
            widget.bind("<Button-1>", lambda e, n=name: self.activate(n))
            widget.bind("<Enter>",    lambda e, n=name: self._hover(n, True))
            widget.bind("<Leave>",    lambda e, n=name: self._hover(n, False))

        self._tabs[name] = {"tab": tab, "inner": inner, "dot": dot, "lbl": lbl}

    def _set_tab_state(self, name: str, active: bool):
        t = self._tabs[name]
        if active:
            bg = _ACTIVE_BG
            # Draw border on tab frame: 1px left/top/right, no bottom
            t["tab"].configure(
                highlightthickness=0,
                bd=0,
            )
            t["inner"].configure(
                bg=bg,
                highlightthickness=0,
            )
            # Simulate top+sides border by adding a thin highlight frame
            t["tab"].configure(
                highlightbackground=_BORDER,
                highlightthickness=1,
            )
            # Cover the bottom border at this tab's position with panel color
            t["tab"].after(1, lambda: self._cover_bottom(t["tab"]))
        else:
            bg = _TAB_BG
            t["tab"].configure(highlightthickness=0, highlightbackground=_TAB_BG)
            t["inner"].configure(bg=bg)

        t["lbl"].configure(bg=bg, fg=FG if active else FG_MUTED)
        t["dot"].configure(bg=bg)
        _draw_dot(t["dot"], ACCENT if active else FG_FAINT)

        # Update badge bg too
        self._badges[name].configure(bg=bg)

    def _hover(self, name: str, entering: bool):
        if name == self._active:
            return
        bg = _HOVER_BG if entering else _TAB_BG
        t = self._tabs[name]
        t["tab"].configure(bg=bg)
        t["inner"].configure(bg=bg)
        t["lbl"].configure(bg=bg, fg=FG if entering else FG_MUTED)
        t["dot"].configure(bg=bg)
        _draw_dot(t["dot"], FG_MUTED if entering else FG_FAINT)

    def _cover_bottom(self, tab_widget: tk.Frame):
        """Paint a 1-px line at y=_H-1 under the active tab in panel color."""
        x = tab_widget.winfo_x()
        w = tab_widget.winfo_width()
        self._bottom.place_forget()
        # Redraw: full line in BD, then cover active tab section in panel color
        self._bottom = tk.Frame(self, bg=_BORDER, height=1, bd=0)
        self._bottom.place(x=0, y=_H - 1, relwidth=1.0)
        cover = tk.Frame(self, bg=_ACTIVE_BG, height=1, bd=0)
        cover.place(x=x + 1, y=_H - 1, width=w - 1)


def _draw_dot(canvas: tk.Canvas, color: str):
    canvas.delete("all")
    canvas.create_oval(0, 0, 6, 6, fill=color, outline="")
