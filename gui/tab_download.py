import io
import json
import re
import subprocess
import threading
import tkinter as tk
import urllib.request
import uuid

try:
    from PIL import Image, ImageTk
    _PIL = True
except ImportError:
    _PIL = False

from services.recorder import DownloadJob, FORMAT_MAP, DEFAULT_FORMAT
from services.scheduler import RecordingScheduler
from utils.binaries import get_binary_path
from gui.theme import (
    BG_PANEL, BG_ELEV, BG_INPUT, BD, BD_SUBTLE,
    FG, FG_MUTED, FG_DIM, FG_FAINT,
    ACCENT, OK, WARN, ERR, INFO, MONO, UI, badge_colors,
)
from gui.widgets import (
    Frame, Sep, SectionHeader,
    Entry, Button, Badge, ProgressBar, ScrollFrame,
)

FORMATS = list(FORMAT_MAP.keys())

_DL_RE = re.compile(
    r'([\d.]+)%\s+of\s+~?([\d.]+\S+)\s+at\s+([\d.]+\S+)\s+ETA\s+(\S+)'
)

def _fmt_progress(line: str) -> str:
    m = _DL_RE.search(line)
    if m:
        pct = m.group(1)
        return f"{float(pct):.0f}%"
    return ""

# Shared column widths for header + job rows
_C_ID    = 62   # ID hash
_C_THUMB = 96   # thumbnail canvas + gap
_C_STAT  = 112  # badge
_C_PROG  = 140  # progress bar only
_C_PCT   = 52   # percentage text
_C_CNCL  = 38   # cancel button


# ── metadata fetch ────────────────────────────────────────────────────────────

def _fetch_info(url: str) -> dict | None:
    try:
        r = subprocess.run(
            [get_binary_path("yt-dlp.exe"),
             "--dump-json", "--no-download", "--no-playlist", url],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout.strip())
    except Exception:
        pass
    return None


# ── video info card ───────────────────────────────────────────────────────────

class VideoCard(tk.Frame):
    """Resolved-video card. Call .show_data(), .show_error(), .hide()."""

    THUMB_W, THUMB_H = 132, 74

    def __init__(self, parent):
        super().__init__(parent, bg=BG_ELEV, bd=0,
                         highlightthickness=1, highlightbackground=BD)
        self._duration_sec = 0
        self._is_live = False
        self._dur_str = ""
        self._thumb_photo = None
        self._build()

    def _build(self):
        self._thumb = tk.Canvas(self, width=self.THUMB_W, height=self.THUMB_H,
                                 bg="#1a2030", highlightthickness=1,
                                 highlightbackground=BD)
        self._thumb.pack(side="left", padx=(10, 10), pady=10)
        self._draw_thumb_placeholder()

        meta = Frame(self, bg=BG_ELEV)
        meta.pack(side="left", fill="both", expand=True, padx=(0, 12), pady=10)

        self._title_var = tk.StringVar(value="")
        self._title_lbl = tk.Label(meta, textvariable=self._title_var,
                                    fg=FG, bg=BG_ELEV, font=(UI, 12, "bold"),
                                    anchor="w", wraplength=580, justify="left")
        self._title_lbl.pack(fill="x")

        ch_row = Frame(meta, bg=BG_ELEV)
        ch_row.pack(fill="x", pady=(3, 0))
        self._channel_var = tk.StringVar(value="")
        tk.Label(ch_row, textvariable=self._channel_var,
                 fg=FG_MUTED, bg=BG_ELEV, font=(UI, 11), anchor="w"
                 ).pack(side="left")
        self._status_lbl = tk.Label(ch_row, text="",
                                     fg=FG_DIM, bg=BG_ELEV, font=(MONO, 11))
        self._status_lbl.pack(side="left", padx=(8, 0))

        self._pills_row = Frame(meta, bg=BG_ELEV)
        self._pills_row.pack(fill="x", pady=(6, 0))

    # ── public ───────────────────────────────────────────────────────────────

    def show_data(self, data: dict):
        title   = (data.get("title") or "Unknown")[:120]
        channel = data.get("uploader") or data.get("channel") or ""
        dur_str = data.get("duration_string") or ""
        is_live = bool(data.get("is_live") or data.get("was_live"))
        height  = data.get("height") or 0
        self._duration_sec = int(data.get("duration") or 0)
        self._is_live = is_live
        self._dur_str = dur_str

        self._title_var.set(title)
        self._channel_var.set(channel)
        self._status_lbl.configure(text="✓ resolved", fg=OK)

        thumb_url = data.get("thumbnail") or ""
        if thumb_url and _PIL:
            self._fetch_thumbnail(thumb_url, is_live)
        elif is_live:
            self._thumb.configure(bg="#0a1628")
            self._draw_thumb_live()
        else:
            self._thumb.configure(bg="#1a2030")
            self._draw_thumb_placeholder()
            self._overlay_duration()

        for w in self._pills_row.winfo_children():
            w.destroy()
        pills = [("type", "LIVE" if is_live else "VOD")]
        if dur_str:
            pills.append(("dur", dur_str))
        if height:
            pills.append(("best", f"{height}p"))
        subs = data.get("subtitles") or {}
        if subs:
            langs = ", ".join(list(subs.keys())[:3])
            pills.append(("subs", langs))
        for k, v in pills:
            self._pill(k, v).pack(side="left", padx=(0, 6))

        self.pack(fill="x", padx=14, pady=(4, 4))

    def show_error(self):
        self._title_var.set("Could not resolve URL")
        self._channel_var.set("")
        self._status_lbl.configure(text="✗ error", fg=ERR)
        self._draw_thumb_placeholder()
        for w in self._pills_row.winfo_children():
            w.destroy()
        self.pack(fill="x", padx=14, pady=(4, 4))

    def hide(self):
        self.pack_forget()

    @property
    def duration_sec(self) -> int:
        return self._duration_sec

    @property
    def is_live(self) -> bool:
        return self._is_live

    # ── thumbnail ─────────────────────────────────────────────────────────────

    def _fetch_thumbnail(self, url: str, is_live: bool):
        def _go():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = resp.read()
                img = Image.open(io.BytesIO(raw)).convert("RGB")
                img = img.resize((self.THUMB_W, self.THUMB_H), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.after(0, self._apply_thumbnail, photo)
            except Exception:
                self.after(0, self._draw_thumb_live if is_live else self._draw_thumb_placeholder)
        threading.Thread(target=_go, daemon=True).start()

    def _apply_thumbnail(self, photo):
        self._thumb_photo = photo
        self._thumb.delete("all")
        self._thumb.create_image(0, 0, anchor="nw", image=photo)
        self._overlay_duration()

    def _overlay_duration(self):
        if not self._dur_str:
            return
        txt = self._dur_str
        pad_x, pad_y = 4, 3
        x0 = self.THUMB_W - len(txt) * 6 - pad_x * 2 - 2
        y0 = self.THUMB_H - 14
        self._thumb.create_rectangle(x0, y0, self.THUMB_W - 2, self.THUMB_H - 2,
                                      fill="#0a0a0a", outline="")
        self._thumb.create_text(x0 + pad_x, y0 + pad_y, text=txt,
                                 fill="white", font=(MONO, 8, "bold"), anchor="nw")

    def _draw_thumb_placeholder(self):
        self._thumb.delete("all")
        cx, cy = self.THUMB_W // 2, self.THUMB_H // 2
        self._thumb.create_polygon(
            cx - 18, cy - 13, cx - 18, cy + 13, cx + 18, cy,
            fill="#ffffff", outline="",
        )

    def _draw_thumb_live(self):
        self._thumb.delete("all")
        self._thumb.create_rectangle(6, 6, 46, 20, fill=ERR, outline="")
        self._thumb.create_oval(9, 9, 15, 15, fill="white", outline="")
        self._thumb.create_text(18, 13, text="LIVE", fill="white",
                                 font=(MONO, 8, "bold"), anchor="w")

    def _pill(self, key, val):
        f = tk.Frame(self._pills_row, bg="#0d1015", bd=0,
                     highlightthickness=1, highlightbackground=BD_SUBTLE)
        tk.Label(f, text=key, fg=FG_DIM, bg="#0d1015",
                 font=(MONO, 10)).pack(side="left", padx=(6, 3), pady=2)
        tk.Label(f, text=val, fg=FG, bg="#0d1015",
                 font=(MONO, 10)).pack(side="left", padx=(0, 6), pady=2)
        return f


# ── clip bar ─────────────────────────────────────────────────────────────────

class ClipBar(tk.Frame):
    """Canvas-based visual clip range selector with draggable handles."""

    HANDLE_HIT = 10  # px tolerance for hit detection

    def __init__(self, parent, on_change=None):
        super().__init__(parent, bg=BG_PANEL, bd=0, highlightthickness=0)
        self._duration = 0
        self._start_frac = 0.0
        self._end_frac   = 1.0
        self._on_change  = on_change  # callable(start_str, end_str)
        self._drag       = None       # "start" | "end" | None

        self._canvas = tk.Canvas(self, height=42, bg=BG_INPUT, bd=0,
                                  highlightthickness=1, highlightbackground=BD,
                                  cursor="arrow")
        self._canvas.pack(fill="x")
        self._canvas.bind("<Configure>",       lambda _e: self._draw())
        self._canvas.bind("<ButtonPress-1>",   self._on_press)
        self._canvas.bind("<B1-Motion>",       self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Motion>",          self._on_hover)

        # Scale labels row
        self._scale = tk.Frame(self, bg=BG_PANEL, bd=0, highlightthickness=0)
        self._scale.pack(fill="x", pady=(2, 0))
        self._scale_lbls: list[tk.Label] = []
        for _ in range(5):
            lbl = tk.Label(self._scale, text="", fg=FG_FAINT, bg=BG_PANEL,
                           font=(MONO, 9))
            self._scale_lbls.append(lbl)
        self._update_scale()

    def set_duration(self, seconds: int):
        self._duration = seconds
        self._update_scale()
        self._draw()

    def set_range(self, start_str: str, end_str: str):
        s = self._parse(start_str)
        e = self._parse(end_str)
        dur = self._duration or 1
        self._start_frac = max(0.0, min(1.0, s / dur))
        self._end_frac   = max(0.0, min(1.0, e / dur))
        if self._end_frac <= self._start_frac:
            self._end_frac = min(1.0, self._start_frac + 0.02)
        self._draw()

    # ── mouse interaction ────────────────────────────────────────────────────

    def _handle_positions(self):
        w = self._canvas.winfo_width() or 400
        return int(w * self._start_frac), int(w * self._end_frac)

    def _on_press(self, event):
        sx, ex = self._handle_positions()
        if abs(event.x - sx) <= self.HANDLE_HIT:
            self._drag = "start"
        elif abs(event.x - ex) <= self.HANDLE_HIT:
            self._drag = "end"
        else:
            self._drag = None

    def _on_drag(self, event):
        if not self._drag:
            return
        w = self._canvas.winfo_width() or 400
        frac = max(0.0, min(1.0, event.x / w))
        if self._drag == "start":
            self._start_frac = min(frac, self._end_frac - 0.02)
        else:
            self._end_frac = max(frac, self._start_frac + 0.02)
        self._draw()
        self._update_scale()
        self._notify()

    def _on_release(self, event):
        self._drag = None

    def _on_hover(self, event):
        sx, ex = self._handle_positions()
        near = (abs(event.x - sx) <= self.HANDLE_HIT or
                abs(event.x - ex) <= self.HANDLE_HIT)
        self._canvas.configure(cursor="sb_h_double_arrow" if near else "arrow")

    def _notify(self):
        if self._on_change and self._duration:
            s = int(self._start_frac * self._duration)
            e = int(self._end_frac   * self._duration)
            self._on_change(self._fmt_time(s), self._fmt_time(e))

    # ── drawing ──────────────────────────────────────────────────────────────

    def _draw(self):
        c = self._canvas
        c.delete("all")
        w = c.winfo_width() or 400
        h = 42

        sx = int(w * self._start_frac)
        ex = int(w * self._end_frac)

        # Alternating columns — blue-tinted inside selection
        n = 12
        cw = w / n
        COLS_OUT = ["#1a2030", "#201528"]
        COLS_IN  = ["#1a3558", "#1e2d50"]
        for i in range(n):
            x1, x2 = int(i * cw), int((i + 1) * cw)
            in_sel = x2 > sx and x1 < ex
            c.create_rectangle(x1, 0, x2, h,
                                fill=(COLS_IN if in_sel else COLS_OUT)[i % 2],
                                outline="#0a0d11")

        # Ticks — slightly brighter inside selection
        for x in range(0, w, 3):
            fill = "#3a4f6a" if sx <= x <= ex else "#2a303a"
            c.create_line(x, 8, x, h - 8, fill=fill)

        # Selection border top/bottom
        if ex > sx:
            c.create_line(sx, 0, ex, 0,     fill="#2a5898")
            c.create_line(sx, h-1, ex, h-1, fill="#2a5898")

        # Handles
        cy = h // 2
        for x in [sx, ex]:
            c.create_line(x, 0, x, h, fill=ACCENT, width=2)
            c.create_rectangle(x - 4, cy - 8, x + 4, cy + 8,
                                fill=ACCENT, outline="")

    def _update_scale(self):
        dur = self._duration
        for i, lbl in enumerate(self._scale_lbls):
            sec = int(dur * i / 4) if dur else 0
            lbl.configure(text=self._fmt_time(sec))
            lbl.place(relx=i / 4, anchor="n" if i < 4 else "ne")

    @staticmethod
    def _parse(s: str) -> float:
        try:
            parts = [int(p) for p in s.strip().split(":")]
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
            return float(parts[0])
        except Exception:
            return 0.0

    @staticmethod
    def _fmt_time(sec: int) -> str:
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ── job row ───────────────────────────────────────────────────────────────────

class JobRow(tk.Frame):
    THUMB_W, THUMB_H = 76, 44

    def __init__(self, parent, job_id, url, thumb_url="", title="", on_cancel=None, bg=BG_PANEL):
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0)
        self._bg = bg
        self._on_cancel = on_cancel
        self._thumb_photo = None
        self.columnconfigure(0, minsize=_C_ID)
        self.columnconfigure(1, minsize=_C_THUMB)
        self.columnconfigure(2, weight=1)
        self.columnconfigure(3, minsize=_C_STAT)
        self.columnconfigure(4, minsize=_C_PROG)
        self.columnconfigure(5, minsize=_C_CNCL)
        self._build(job_id, url, thumb_url, title, bg)

    def _build(self, job_id, url, thumb_url, title, bg):
        # ID
        tk.Label(self, text=job_id, fg=FG_FAINT, bg=bg,
                 font=(MONO, 10), anchor="w"
                 ).grid(row=0, column=0, rowspan=2, sticky="nsew",
                        padx=(10, 4), pady=10)

        # Thumbnail
        self._tc = tk.Canvas(self, width=self.THUMB_W, height=self.THUMB_H,
                              bg="#1a2030", highlightthickness=1, highlightbackground=BD)
        self._tc.grid(row=0, column=1, rowspan=2, padx=(0, 8), pady=10, sticky="w")
        self._draw_placeholder()
        if thumb_url and _PIL:
            self._load_thumb_async(thumb_url)

        # Title + meta
        wrap = Frame(self, bg=bg)
        wrap.grid(row=0, column=2, sticky="nsew", padx=(0, 8), pady=(10, 2))
        wrap.columnconfigure(0, weight=1)
        display = (title or url.replace("https://", "").replace("http://", ""))[:80]
        self._title = tk.Label(wrap, text=display, fg=FG, bg=bg,
                                font=(UI, 11, "bold"), anchor="w",
                                wraplength=1, justify="left")
        self._title.grid(row=0, column=0, sticky="ew")
        self._meta = tk.Label(wrap, text=url.replace("https://", "")[:72],
                               fg=FG_DIM, bg=bg, font=(MONO, 10), anchor="w")
        self._meta.grid(row=1, column=0, sticky="ew")
        wrap.bind("<Configure>", lambda e: self._title.configure(wraplength=e.width - 4))

        # Badge (status chip)
        self._badge = Badge(self, "Starting…")
        self._badge.grid(row=0, column=3, padx=(0, 8), pady=10, sticky="w")

        # Progress
        pf = Frame(self, bg=bg)
        pf.grid(row=0, column=4, padx=(0, 8), pady=10, sticky="ew")
        self._prog_lbl = tk.Label(pf, text="", fg=FG_MUTED, bg=bg,
                                   font=(MONO, 10), anchor="w")
        self._prog_lbl.pack(fill="x")
        self._pbar = ProgressBar(pf, bg=bg)
        self._pbar.pack(fill="x", pady=(3, 0))
        self._pbar.set(0)

        # Cancel
        self._cancel = tk.Button(
            self, text="✕", command=self._on_cancel,
            bg=bg, fg=FG_DIM, activebackground="#2b1a1c", activeforeground=ERR,
            relief="flat", bd=0, highlightthickness=0,
            padx=4, pady=4, font=(MONO, 11), cursor="hand2",
        )
        self._cancel.grid(row=0, column=5, rowspan=2, pady=10, sticky="ns")

    def _draw_placeholder(self):
        cx, cy = self.THUMB_W // 2, self.THUMB_H // 2
        self._tc.create_polygon(
            cx - 12, cy - 9, cx - 12, cy + 9, cx + 14, cy,
            fill="#ffffff", outline="",
        )

    def _load_thumb_async(self, url: str):
        def _go():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    raw = resp.read()
                img = Image.open(io.BytesIO(raw)).convert("RGB")
                img = img.resize((self.THUMB_W, self.THUMB_H), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.after(0, self._set_thumb, photo)
            except Exception:
                pass
        threading.Thread(target=_go, daemon=True).start()

    def _set_thumb(self, photo):
        self._thumb_photo = photo
        self._tc.delete("all")
        self._tc.create_image(0, 0, anchor="nw", image=photo)

    def update_status(self, raw: str):
        status = self._classify(raw)
        self._badge.set_status(status)
        mode = {"Done": "done", "Cancelled": "cancel",
                "Recording": "record", "Failed": "error",
                "Error": "error"}.get(status, "download")

        if "[download]" in raw and "%" in raw:
            try:
                pct = float(raw.split("%")[0].split()[-1]) / 100.0
                self._pbar.set(pct, mode=mode)
                self._prog_lbl.configure(text=_fmt_progress(raw), fg=FG_MUTED)
            except Exception:
                pass
        elif status == "Done":
            self._pbar.set(1.0, mode="done")
        elif status in ("Failed", "Error"):
            self._pbar.set(1.0, mode="error")
            self._prog_lbl.configure(text=raw[:60], fg=ERR)
        elif status == "Trimming…":
            self._prog_lbl.configure(text="trimming with ffmpeg…", fg=FG_DIM)
        elif status == "Cancelled":
            self._prog_lbl.configure(text="")

    @property
    def status_text(self) -> str:
        return self._badge._lbl.cget("text").lower()

    def disable_cancel(self):
        self._cancel.configure(state="disabled", fg=FG_FAINT)

    def _classify(self, raw):
        if raw in ("Done", "Cancelled", "Recording", "Downloading",
                   "Starting…", "Running", "Trimming…"):
            return raw
        r = raw.lower()
        if raw.startswith("Error") or "error" in r or "failed" in r:
            return "Failed"
        if "[download]" in r:
            return "Downloading"
        if "live" in r or "recording" in r:
            return "Recording"
        if "merg" in r or "trim" in r or "convert" in r:
            return "Running"
        return "Running"


# ── main tab ──────────────────────────────────────────────────────────────────

class DownloadTab(tk.Frame):
    def __init__(self, master, scheduler: RecordingScheduler,
                 default_output_dir: callable):
        super().__init__(master, bg=BG_PANEL, bd=0, highlightthickness=0)
        self._get_output_dir = default_output_dir
        self._scheduler = scheduler
        self._jobs: dict[str, dict] = {}
        self._thumb_idx = 0
        self._selected_fmt = DEFAULT_FORMAT
        self._chip_btns: dict[str, tk.Button] = {}
        self._meta_cache: dict[str, dict] = {}
        self._debounce_id = None
        self._build()

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        top = Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        self._build_source(top)

        self._build_job_section()

    def _build_source(self, parent):
        # ── section label ──
        SectionHeader(parent, "SOURCE URL",
                      hint="youtube.com · youtu.be · live streams"
                      ).pack(anchor="w", padx=14, pady=(10, 6))

        # ── URL row ──
        url_row = Frame(parent)
        url_row.pack(fill="x", padx=14, pady=(0, 6))
        url_row.columnconfigure(0, weight=1)

        self._url_var = tk.StringVar()
        self._url_var.trace_add("write", self._on_url_change)
        url_e = Entry(url_row, textvariable=self._url_var, mono_font=True)
        url_e.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=4)
        url_e.bind("<Return>", self._on_url_enter)

        Button(url_row, "↓  Download", command=self._on_download, primary=True,
               ).grid(row=0, column=1, padx=(0, 6))
        Button(url_row, "⏺  Record Live", command=self._on_record,
               ).grid(row=0, column=2)

        # Inline fetch-status (shown during loading, hidden otherwise)
        self._fetch_lbl = tk.Label(
            parent, text="", fg=FG_DIM, bg=BG_PANEL,
            font=(MONO, 10), anchor="w",
        )
        self._fetch_lbl.pack(fill="x", padx=14, pady=(0, 4))

        # Container always stays in pack order; VideoCard packs inside it
        _card_host = tk.Frame(parent, bg=BG_PANEL, bd=0, highlightthickness=0)
        _card_host.pack(fill="x")
        self._video_card = VideoCard(_card_host)

        Sep(parent, bg=BD_SUBTLE).pack(fill="x", pady=(6, 0))

        # ── Format + Clip (side-by-side) ──
        fc = Frame(parent)
        fc.pack(fill="x", padx=14, pady=(8, 10))
        fc.columnconfigure(0, weight=1)
        fc.columnconfigure(1, weight=1)

        # Format chips
        fmt_f = Frame(fc)
        fmt_f.grid(row=0, column=0, sticky="nsew", padx=(0, 20))
        SectionHeader(fmt_f, "FORMAT", hint="container · codec"
                      ).pack(anchor="w", pady=(0, 6))
        chips = Frame(fmt_f)
        chips.pack(anchor="w")
        for fmt in FORMATS:
            active = fmt == self._selected_fmt
            btn = tk.Button(
                chips, text=fmt,
                bg="#0e1f38" if active else BG_INPUT,
                fg=INFO if active else FG_MUTED,
                activebackground=BG_ELEV, activeforeground=FG,
                relief="flat", bd=0, highlightthickness=1,
                highlightbackground=ACCENT if active else BD,
                padx=8, pady=3, font=(MONO, 10), cursor="hand2",
                command=lambda f=fmt: self._select_fmt(f),
            )
            btn.pack(side="left", padx=(0, 4))
            self._chip_btns[fmt] = btn

        # Clip range
        clip_f = Frame(fc)
        clip_f.grid(row=0, column=1, sticky="nsew")
        SectionHeader(clip_f, "CLIP RANGE",
                      hint="leave empty for full video").pack(anchor="w", pady=(0, 6))

        inp_row = Frame(clip_f)
        inp_row.pack(anchor="w", pady=(0, 6))
        tk.Label(inp_row, text="FROM", fg=FG_DIM, bg=BG_PANEL,
                 font=(MONO, 10)).pack(side="left", padx=(0, 4))
        self._clip_start = Entry(inp_row, mono_font=True, width=10)
        self._clip_start.pack(side="left", padx=(0, 8), ipady=3)
        tk.Label(inp_row, text="→", fg=FG_FAINT, bg=BG_PANEL,
                 font=(MONO, 11)).pack(side="left")
        tk.Label(inp_row, text="TO", fg=FG_DIM, bg=BG_PANEL,
                 font=(MONO, 10)).pack(side="left", padx=(8, 4))
        self._clip_end = Entry(inp_row, mono_font=True, width=10)
        self._clip_end.pack(side="left", ipady=3)

        self._clip_bar = ClipBar(clip_f, on_change=self._on_clipbar_drag)
        self._clip_bar.pack(fill="x", pady=(0, 4))

        # Update clip bar when time fields change
        for e in (self._clip_start, self._clip_end):
            e.bind("<KeyRelease>", self._on_clip_change)

        Sep(parent, bg=BD_SUBTLE).pack(fill="x")

    def _build_job_section(self):
        # Stats bar
        stats_bg = "#0d1116"
        sb = tk.Frame(self, bg=stats_bg, bd=0, highlightthickness=0)
        sb.grid(row=1, column=0, sticky="new")

        inner = tk.Frame(sb, bg=stats_bg)
        inner.pack(fill="x", padx=14, pady=6)
        self._stat_vars: dict[str, tk.StringVar] = {}
        for key, col in [("Queue", FG), ("Active", INFO),
                          ("Scheduled", WARN), ("Done", OK), ("Failed", ERR)]:
            f = tk.Frame(inner, bg=stats_bg)
            f.pack(side="left", padx=(0, 20))
            tk.Label(f, text=key.upper(), bg=stats_bg, fg=FG_DIM,
                     font=(MONO, 9, "bold")).pack(side="left", padx=(0, 5))
            var = tk.StringVar(value="0")
            self._stat_vars[key] = var
            tk.Label(f, textvariable=var, bg=stats_bg, fg=col,
                     font=(MONO, 12, "bold")).pack(side="left")
        Sep(sb, bg=BD_SUBTLE).pack(fill="x")
        Sep(self, bg=BD_SUBTLE).grid(row=2, column=0, sticky="ew")

        # Scroll frame with single unified grid
        self.grid_rowconfigure(3, weight=1)
        self._scroll = ScrollFrame(self)
        self._scroll.grid(row=3, column=0, sticky="nsew")

        # Configure columns on the inner grid (shared by header + all job rows)
        g = self._scroll.inner
        g.columnconfigure(0, minsize=_C_ID)
        g.columnconfigure(1, minsize=_C_THUMB)
        g.columnconfigure(2, weight=1)
        g.columnconfigure(3, minsize=_C_STAT)
        g.columnconfigure(4, minsize=_C_PROG)
        g.columnconfigure(5, minsize=_C_PCT)
        g.columnconfigure(6, minsize=_C_CNCL)

        # Header row (row 0) - use nsew sticky so bg fills entire cell
        tk.Label(g, text="ID", bg=stats_bg, fg=FG_DIM,
                 font=(MONO, 9, "bold"), anchor="w", padx=10, pady=5
                 ).grid(row=0, column=0, sticky="nsew")
        tk.Label(g, text="", bg=stats_bg).grid(row=0, column=1, sticky="nsew")
        tk.Label(g, text="TITLE / URL", bg=stats_bg, fg=FG_DIM,
                 font=(MONO, 9, "bold"), anchor="w", padx=4, pady=5
                 ).grid(row=0, column=2, sticky="nsew")
        tk.Label(g, text="STATUS", bg=stats_bg, fg=FG_DIM,
                 font=(MONO, 9, "bold"), anchor="w", padx=4, pady=5
                 ).grid(row=0, column=3, sticky="nsew")
        tk.Label(g, text="PROGRESS", bg=stats_bg, fg=FG_DIM,
                 font=(MONO, 9, "bold"), anchor="w", padx=4, pady=5
                 ).grid(row=0, column=4, columnspan=2, sticky="nsew")
        tk.Label(g, text="", bg=stats_bg).grid(row=0, column=6, sticky="nsew")

        # Separator after header
        Sep(g, bg=BD_SUBTLE).grid(row=1, column=0, columnspan=7, sticky="ew")

        self._next_job_row = 2  # job rows start at row 2

    # ── URL auto-resolve ──────────────────────────────────────────────────────

    def _on_url_enter(self, _event=None):
        if self._debounce_id:
            self.after_cancel(self._debounce_id)
            self._debounce_id = None
        url = self._url_var.get().strip()
        if url.startswith("http://") or url.startswith("https://"):
            self._video_card.hide()
            self._fetch_lbl.configure(text="⟳  Resolving metadata…")
            self._do_fetch(url)

    def _on_url_change(self, *_):
        if self._debounce_id:
            self.after_cancel(self._debounce_id)
            self._debounce_id = None
        url = self._url_var.get().strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            self._video_card.hide()
            self._fetch_lbl.configure(text="")
            return
        self._video_card.hide()
        self._fetch_lbl.configure(text="⟳  Resolving metadata…")
        self._debounce_id = self.after(900, self._do_fetch, url)

    def _do_fetch(self, url: str):
        if url in self._meta_cache:
            self._fetch_lbl.configure(text="")
            self._apply_meta(self._meta_cache[url])
            return
        def _go():
            data = _fetch_info(url)
            self.after(0, self._on_fetch_done, url, data)
        threading.Thread(target=_go, daemon=True).start()

    def _on_fetch_done(self, url: str, data: dict | None):
        if self._url_var.get().strip() != url:
            return
        self._fetch_lbl.configure(text="")
        if data:
            self._meta_cache[url] = data
            self._apply_meta(data)
        else:
            self._video_card.show_error()

    def _apply_meta(self, data: dict):
        self._video_card.show_data(data)
        dur = int(data.get("duration") or 0)
        self._clip_bar.set_duration(dur)
        # Auto-fill FROM / TO with full video range
        if dur:
            end_str = ClipBar._fmt_time(dur)
            self._clip_start.delete(0, tk.END)
            self._clip_start.insert(0, "00:00:00")
            self._clip_end.delete(0, tk.END)
            self._clip_end.insert(0, end_str)
            self._clip_bar.set_range("00:00:00", end_str)

    # ── clip bar update ───────────────────────────────────────────────────────

    def _on_clip_change(self, _event=None):
        s = self._clip_start.get().strip()
        e = self._clip_end.get().strip()
        if s or e:
            self._clip_bar.set_range(s or "00:00:00", e or "00:00:00")

    def _on_clipbar_drag(self, start_str: str, end_str: str):
        """Sync entry fields when user drags clip handles."""
        self._clip_start.delete(0, tk.END)
        self._clip_start.insert(0, start_str)
        self._clip_end.delete(0, tk.END)
        self._clip_end.insert(0, end_str)

    # ── actions ───────────────────────────────────────────────────────────────

    def _select_fmt(self, fmt: str):
        self._selected_fmt = fmt
        for f, btn in self._chip_btns.items():
            on = f == fmt
            btn.configure(bg="#0e1f38" if on else BG_INPUT,
                          fg=INFO if on else FG_MUTED,
                          highlightbackground=ACCENT if on else BD)

    def _on_download(self):
        url = self._url_var.get().strip()
        if not url:
            return
        if url in self._meta_cache:
            meta = self._meta_cache[url]
            self._start_job(url, is_live=bool(meta.get("is_live") or meta.get("was_live")))
        else:
            self._fetch_then_start(url, is_live=False)

    def _on_record(self):
        url = self._url_var.get().strip()
        if url:
            self._start_job(url, is_live=True)

    def _fetch_then_start(self, url: str, is_live: bool):
        if self._debounce_id:
            self.after_cancel(self._debounce_id)
            self._debounce_id = None
        self._video_card.hide()
        self._fetch_lbl.configure(text="⟳  Resolving metadata…")
        def _go():
            data = _fetch_info(url)
            self.after(0, self._on_fetched_for_download, url, data, is_live)
        threading.Thread(target=_go, daemon=True).start()

    def _on_fetched_for_download(self, url: str, data: dict | None, is_live: bool):
        self._fetch_lbl.configure(text="")
        if data:
            self._meta_cache[url] = data
            self._apply_meta(data)
            is_live = bool(data.get("is_live") or data.get("was_live"))
        self._start_job(url, is_live=is_live)

    def _start_job(self, url: str, is_live: bool):
        job_id = str(uuid.uuid4())[:8]
        clip_start = self._clip_start.get().strip() or None
        clip_end   = self._clip_end.get().strip() or None
        # Don't clip if range covers the whole video
        dur = self._video_card.duration_sec
        if dur and clip_start and clip_end:
            s = ClipBar._parse(clip_start)
            e = ClipBar._parse(clip_end)
            if s <= 0 and e >= dur:
                clip_start = clip_end = None
        output_dir = self._get_output_dir()

        self._add_row(job_id, url)

        def _on_status(jid, status):
            self.after(0, self._update_job_status, jid, status)
            self.after(0, self._refresh_stats)

        job = DownloadJob(job_id, url, output_dir, is_live, _on_status,
                          format_key=self._selected_fmt,
                          clip_start=clip_start, clip_end=clip_end)
        self._jobs[job_id]["job"] = job
        job.start()
        self._refresh_stats()

    def _add_row(self, job_id: str, url: str):
        meta = self._meta_cache.get(url) or {}
        thumb_url = meta.get("thumbnail") or ""
        title = (meta.get("title") or "")[:80]

        g = self._scroll.inner
        r = self._next_job_row
        self._next_job_row += 2  # +2 for row + separator

        bg = BG_PANEL
        cell_pady = 12
        cell_padx = 10

        widgets = []  # Track all widgets for cleanup

        # Column 0: ID
        id_lbl = tk.Label(g, text=job_id[:8], fg=FG_FAINT, bg=bg,
                          font=(MONO, 10), anchor="w")
        id_lbl.grid(row=r, column=0, sticky="w", padx=(14, cell_padx), pady=cell_pady)
        widgets.append(id_lbl)

        # Column 1: Thumbnail
        tc = tk.Canvas(g, width=76, height=44, bg="#1a2030",
                       highlightthickness=1, highlightbackground=BD)
        tc.grid(row=r, column=1, padx=(0, cell_padx), pady=cell_pady, sticky="w")
        cx, cy = 38, 22
        tc.create_polygon(cx-12, cy-9, cx-12, cy+9, cx+14, cy, fill="#fff", outline="")
        widgets.append(tc)
        if thumb_url and _PIL:
            self._load_thumb_async(tc, thumb_url)

        # Column 2: Title + meta
        wrap = Frame(g, bg=bg)
        wrap.grid(row=r, column=2, sticky="ew", padx=(0, cell_padx), pady=cell_pady)
        wrap.columnconfigure(0, weight=1)
        widgets.append(wrap)
        display = (title or url.replace("https://", "").replace("http://", ""))[:80]
        title_lbl = tk.Label(wrap, text=display, fg=FG, bg=bg,
                              font=(UI, 11, "bold"), anchor="w")
        title_lbl.grid(row=0, column=0, sticky="ew")
        meta_lbl = tk.Label(wrap, text=url.replace("https://", "")[:72],
                             fg=FG_DIM, bg=bg, font=(MONO, 10), anchor="w")
        meta_lbl.grid(row=1, column=0, sticky="ew")

        # Column 3: Badge
        badge = Badge(g, "Starting…")
        badge.grid(row=r, column=3, padx=(0, cell_padx), pady=cell_pady, sticky="w")
        widgets.append(badge)

        # Column 4: Progress bar
        pbar = ProgressBar(g, bg=bg, width=_C_PROG)
        pbar.grid(row=r, column=4, padx=(0, cell_padx), pady=cell_pady, sticky="w")
        widgets.append(pbar)

        # Column 5: Percentage
        prog_lbl = tk.Label(g, text="", fg=FG_MUTED, bg=bg,
                             font=(MONO, 10), anchor="w")
        prog_lbl.grid(row=r, column=5, padx=(0, cell_padx), pady=cell_pady, sticky="w")
        widgets.append(prog_lbl)

        # Column 6: Cancel button
        cancel_btn = tk.Button(
            g, text="✕", command=lambda jid=job_id: self._on_cancel(jid),
            bg=bg, fg=FG_DIM, activebackground="#2b1a1c", activeforeground=ERR,
            relief="flat", bd=0, highlightthickness=0,
            padx=6, pady=6, font=(MONO, 11), cursor="hand2",
        )
        cancel_btn.grid(row=r, column=6, padx=(0, 10), pady=cell_pady)
        widgets.append(cancel_btn)

        # Separator
        sep = Sep(g, bg=BD_SUBTLE)
        sep.grid(row=r+1, column=0, columnspan=7, sticky="ew")
        widgets.append(sep)

        # Store references for updates
        self._jobs[job_id] = {
            "job": None,
            "badge": badge,
            "prog_lbl": prog_lbl,
            "pbar": pbar,
            "cancel_btn": cancel_btn,
            "status": "starting",
            "widgets": widgets,
        }

    def _load_thumb_async(self, canvas, url: str):
        def _go():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    raw = resp.read()
                img = Image.open(io.BytesIO(raw)).convert("RGB")
                img = img.resize((76, 44), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                canvas.after(0, lambda: self._set_thumb(canvas, photo))
            except Exception:
                pass
        threading.Thread(target=_go, daemon=True).start()

    def _set_thumb(self, canvas, photo):
        canvas._photo = photo  # prevent GC
        canvas.delete("all")
        canvas.create_image(0, 0, anchor="nw", image=photo)

    def _on_cancel(self, job_id: str):
        e = self._jobs.get(job_id)
        if not e:
            return
        status = e.get("status", "")
        if status in ("done", "cancelled", "failed", "error"):
            self._remove_row(job_id)
            return
        job = e.get("job")
        if job:
            job.cancel()
        else:
            self._scheduler.cancel(job_id)
        e["cancel_btn"].configure(state="disabled", fg=FG_FAINT)
        self._refresh_stats()

    def _remove_row(self, job_id: str):
        e = self._jobs.pop(job_id, None)
        if not e:
            return
        for w in e.get("widgets", []):
            try:
                w.destroy()
            except Exception:
                pass
        self._refresh_stats()

    def _update_job_status(self, job_id: str, raw: str):
        e = self._jobs.get(job_id)
        if not e:
            return
        prev_status = e.get("status", "starting")
        status = self._classify_status(raw, prev_status)
        e["badge"].set_status(status)
        e["status"] = status.lower()
        mode = {"Done": "done", "Cancelled": "cancel",
                "Recording": "record", "Failed": "error",
                "Error": "error"}.get(status, "download")

        if "[download]" in raw and "%" in raw:
            try:
                pct = float(raw.split("%")[0].split()[-1]) / 100.0
                e["pbar"].set(pct, mode=mode)
                e["prog_lbl"].configure(text=_fmt_progress(raw), fg=FG_MUTED)
            except Exception:
                pass
        elif status == "Done":
            e["pbar"].set(1.0, mode="done")
            e["prog_lbl"].configure(text="")
        elif status in ("Failed", "Error"):
            e["pbar"].set(1.0, mode="error")
            e["prog_lbl"].configure(text=raw[:60], fg=ERR)
        elif status == "Trimming…":
            e["prog_lbl"].configure(text="trimming with ffmpeg…", fg=FG_DIM)
        elif status == "Cancelled":
            e["prog_lbl"].configure(text="")

    def _classify_status(self, raw, prev_status="starting"):
        # Terminal states - always honor these
        if raw in ("Done", "Cancelled"):
            return raw
        if raw.startswith("Error") or "error" in raw.lower() or "failed" in raw.lower():
            return "Failed"

        # Explicit status strings
        if raw in ("Recording", "Downloading", "Starting…", "Running", "Trimming…"):
            return raw

        r = raw.lower()

        # Detect new status from output
        if "[download]" in r and "%" in r:
            return "Downloading"
        if "live" in r or "recording" in r:
            return "Recording"
        if "merg" in r or "trim" in r or "convert" in r:
            return "Trimming…"

        # Sticky: stay in Downloading/Recording once entered (until terminal)
        if prev_status in ("downloading", "recording"):
            return prev_status.capitalize()

        # Pre-download yt-dlp chatter → show as Downloading
        if "[youtube]" in r or "[info]" in r or "downloading" in r:
            return "Downloading"

        return "Running"

    def _refresh_stats(self):
        statuses = [e.get("status", "starting") for e in self._jobs.values()]
        self._stat_vars["Queue"].set(str(len(self._jobs)))
        self._stat_vars["Active"].set(
            str(sum(1 for s in statuses if s in ("downloading", "recording", "running"))))
        self._stat_vars["Scheduled"].set(
            str(sum(1 for s in statuses if s == "scheduled")))
        self._stat_vars["Done"].set(str(sum(1 for s in statuses if s == "done")))
        self._stat_vars["Failed"].set(
            str(sum(1 for s in statuses if s in ("failed", "error"))))

    def get_output_dir(self) -> str:
        return self._get_output_dir()

    def on_scheduled_job_trigger(self, job_id: str, url: str, output_dir: str):
        def _start():
            if job_id not in self._jobs:
                self._add_row(job_id, url)

            def _on_status(jid, status):
                self.after(0, self._update_job_status, jid, status)
                self.after(0, self._refresh_stats)

            job = DownloadJob(job_id, url, output_dir, is_live=True, on_status=_on_status)
            if job_id in self._jobs:
                self._jobs[job_id]["job"] = job
            job.start()
            self._refresh_stats()
        self.after(0, _start)
