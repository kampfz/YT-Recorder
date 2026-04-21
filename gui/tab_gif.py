import json
import os
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from services.gif_converter import convert_to_gif, download_and_convert_to_gif
from gui.theme import (
    BG_PANEL, BG_ELEV, BG_INPUT, BD, BD_SUBTLE,
    FG, FG_MUTED, FG_DIM, FG_FAINT,
    ACCENT, OK, ERR, INFO, MONO, UI,
)
from gui.widgets import (
    Frame, Sep, SectionHeader, Label, MonoLabel,
    Entry, Button, ProgressBar, ScrollFrame,
)
from gui.tab_download import ClipBar, VideoCard
from utils.binaries import get_binary_path


def _fieldset(parent, title, sub=""):
    outer = tk.Frame(parent, bg=BG_ELEV, bd=0,
                     highlightthickness=1, highlightbackground=BD_SUBTLE)
    outer.pack(fill="x", pady=(0, 10))
    hdr = Frame(outer, bg=BG_ELEV)
    hdr.pack(fill="x", padx=14, pady=(10, 8))
    tk.Label(hdr, text=title, fg=FG_MUTED, bg=BG_ELEV,
             font=(MONO, 10, "bold")).pack(side="left")
    if sub:
        tk.Label(hdr, text=sub, fg=FG_FAINT, bg=BG_ELEV,
                 font=(MONO, 10)).pack(side="left", padx=(8, 0))
    return outer


class GifTab(tk.Frame):
    def __init__(self, master, get_output_dir: callable = None):
        super().__init__(master, bg=BG_PANEL, bd=0, highlightthickness=0)
        self._get_output_dir = get_output_dir or (lambda: os.path.expanduser("~/Videos"))
        self._source_mode = "local"
        self._debounce_id = None
        self._build()

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_source()
        Sep(self, bg=BD_SUBTLE).grid(row=1, column=0, sticky="ew")
        self._build_controls()

    # ── source section ────────────────────────────────────────────────────────

    def _build_source(self):
        sec = Frame(self)
        sec.grid(row=0, column=0, sticky="ew")
        sec.grid_columnconfigure(0, weight=1)

        SectionHeader(sec, "SOURCE",
                      hint="local video file or YouTube URL"
                      ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))

        inp = Frame(sec)
        inp.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        inp.grid_columnconfigure(1, weight=1)

        # Segmented toggle
        seg_box = tk.Frame(inp, bg=BG_INPUT, bd=0,
                           highlightthickness=1, highlightbackground=BD)
        seg_box.grid(row=0, column=0, padx=(0, 8))

        self._local_btn = tk.Button(
            seg_box, text="📁  Local file", bg=BG_INPUT, fg=FG_DIM,
            activebackground=BG_ELEV, activeforeground=FG,
            relief="flat", bd=0, highlightthickness=0,
            padx=10, pady=4, font=(UI, 11), cursor="hand2",
            command=self._set_local,
        )
        self._local_btn.pack(side="left")

        tk.Frame(seg_box, bg=BD_SUBTLE, width=1).pack(side="left", fill="y", pady=4)

        self._url_btn = tk.Button(
            seg_box, text="▶  YouTube URL", bg=BG_INPUT, fg=FG_DIM,
            activebackground=BG_ELEV, activeforeground=FG,
            relief="flat", bd=0, highlightthickness=0,
            padx=10, pady=4, font=(UI, 11), cursor="hand2",
            command=self._set_url,
        )
        self._url_btn.pack(side="left")

        self._src_var = tk.StringVar()
        self._src_var.trace_add("write", self._on_src_change)
        self._src_entry = Entry(inp, textvariable=self._src_var, mono_font=True)
        self._src_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), ipady=4)

        self._action_btn = Button(inp, "Browse", command=self._src_action)
        self._action_btn.grid(row=0, column=2)

        self._fetch_lbl = tk.Label(sec, text="", fg=FG_DIM, bg=BG_PANEL,
                                    font=(MONO, 10), anchor="w")
        self._fetch_lbl.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 4))

        _card_host = tk.Frame(sec, bg=BG_PANEL, bd=0, highlightthickness=0)
        _card_host.grid(row=3, column=0, sticky="ew")
        self._video_card = VideoCard(_card_host)

        self._set_local()

    def _set_local(self):
        self._source_mode = "local"
        self._local_btn.configure(bg="#0e1f38", fg=INFO)
        self._url_btn.configure(bg=BG_INPUT, fg=FG_DIM)
        self._action_btn.configure(text="Browse")
        self._src_var.set("")
        self._reset_clip_bar()
        if hasattr(self, "_video_card"):
            self._video_card.hide()
            self._fetch_lbl.configure(text="")

    def _set_url(self):
        self._source_mode = "url"
        self._url_btn.configure(bg="#0e1f38", fg=INFO)
        self._local_btn.configure(bg=BG_INPUT, fg=FG_DIM)
        self._action_btn.configure(text="Paste")
        self._src_var.set("")
        self._reset_clip_bar()
        if hasattr(self, "_video_card"):
            self._video_card.hide()
            self._fetch_lbl.configure(text="")

    def _src_action(self):
        if self._source_mode == "local":
            path = filedialog.askopenfilename(
                filetypes=[("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv"),
                           ("All files", "*.*")]
            )
            if path:
                self._src_var.set(path)
                self._probe_local_duration(path)
        else:
            try:
                text = self.clipboard_get()
                if text.strip():
                    self._src_var.set(text.strip())
            except Exception:
                pass

    # ── source change / duration detection ───────────────────────────────────

    def _on_src_change(self, *_):
        if self._source_mode != "url":
            return
        if self._debounce_id:
            self.after_cancel(self._debounce_id)
        val = self._src_var.get().strip()
        if val.startswith("http://") or val.startswith("https://"):
            self._video_card.hide()
            self._fetch_lbl.configure(text="⟳  Resolving metadata…")
            self._debounce_id = self.after(900, self._fetch_url_metadata, val)
        else:
            self._video_card.hide()
            self._fetch_lbl.configure(text="")
            self._reset_clip_bar()

    def _fetch_url_metadata(self, url: str):
        def _go():
            try:
                r = subprocess.run(
                    [get_binary_path("yt-dlp.exe"),
                     "--dump-json", "--no-download", "--no-playlist", url],
                    capture_output=True, text=True, timeout=30,
                )
                if r.returncode == 0 and r.stdout.strip():
                    data = json.loads(r.stdout.strip())
                    self.after(0, self._on_metadata_done, url, data)
                else:
                    self.after(0, self._on_metadata_done, url, None)
            except Exception:
                self.after(0, self._on_metadata_done, url, None)
        threading.Thread(target=_go, daemon=True).start()

    def _on_metadata_done(self, url: str, data: dict | None):
        if self._src_var.get().strip() != url:
            return
        self._fetch_lbl.configure(text="")
        if data:
            self._video_card.show_data(data)
            dur = int(data.get("duration") or 0)
            if dur:
                self._apply_duration(dur)
            # Extract available video widths from formats
            widths = set()
            for fmt in data.get("formats") or []:
                w = fmt.get("width")
                if w and isinstance(w, int) and w >= 240:
                    widths.add(w)
            if widths:
                sorted_widths = sorted(widths)
                self._width_combo["values"] = [str(w) for w in sorted_widths]
        else:
            self._video_card.show_error()

    def _probe_local_duration(self, path: str):
        def _go():
            try:
                r = subprocess.run(
                    [get_binary_path("ffprobe.exe"),
                     "-v", "quiet", "-show_entries", "format=duration",
                     "-of", "csv=p=0", path],
                    capture_output=True, text=True, timeout=15,
                )
                dur = int(float(r.stdout.strip())) if r.stdout.strip() else 0
                if dur:
                    self.after(0, self._apply_duration, dur)
            except Exception:
                pass
        threading.Thread(target=_go, daemon=True).start()

    def _apply_duration(self, dur: int):
        self._clip_bar.set_duration(dur)
        default_end = min(dur, 10)  # Default to 10 seconds or video length if shorter
        end_str = ClipBar._fmt_time(default_end)
        self._clip_start.delete(0, tk.END)
        self._clip_start.insert(0, "00:00:00")
        self._clip_end.delete(0, tk.END)
        self._clip_end.insert(0, end_str)
        self._clip_bar.set_range("00:00:00", end_str)

    def _reset_clip_bar(self):
        if hasattr(self, "_clip_bar"):
            self._clip_bar.set_duration(0)
            self._clip_start.delete(0, tk.END)
            self._clip_start.insert(0, "00:00:00")
            self._clip_end.delete(0, tk.END)
            self._clip_end.insert(0, "00:00:10")

    # ── controls section ──────────────────────────────────────────────────────

    def _build_controls(self):
        outer = Frame(self)
        outer.grid(row=2, column=0, sticky="nsew", padx=14, pady=10)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_columnconfigure(1, weight=1)
        outer.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_left(outer)
        self._build_right(outer)

    def _build_left(self, parent):
        col = Frame(parent)
        col.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        col.grid_rowconfigure(99, weight=1)

        # ── Clip Range ──
        SectionHeader(col, "CLIP RANGE",
                      hint="leave empty for full video").pack(anchor="w", pady=(0, 6))

        inp_row = Frame(col)
        inp_row.pack(anchor="w", pady=(0, 6))
        tk.Label(inp_row, text="FROM", fg=FG_DIM, bg=BG_PANEL,
                 font=(MONO, 10)).pack(side="left", padx=(0, 4))
        self._clip_start = Entry(inp_row, mono_font=True, width=10)
        self._clip_start.pack(side="left", padx=(0, 8), ipady=3)
        self._clip_start.insert(0, "00:00:00")
        tk.Label(inp_row, text="→", fg=FG_FAINT, bg=BG_PANEL,
                 font=(MONO, 11)).pack(side="left")
        tk.Label(inp_row, text="TO", fg=FG_DIM, bg=BG_PANEL,
                 font=(MONO, 10)).pack(side="left", padx=(8, 4))
        self._clip_end = Entry(inp_row, mono_font=True, width=10)
        self._clip_end.pack(side="left", ipady=3)
        self._clip_end.insert(0, "00:00:10")

        self._clip_bar = ClipBar(col, on_change=self._on_clipbar_drag)
        self._clip_bar.pack(fill="x", pady=(0, 10))

        for e in (self._clip_start, self._clip_end):
            e.bind("<KeyRelease>", self._on_clip_change)

        # ── Output fieldset ──
        of = _fieldset(col, "OUTPUT", "ffmpeg gif")
        og = Frame(of, bg=BG_ELEV)
        og.pack(fill="x", padx=14, pady=(0, 14))

        # FPS
        tk.Label(og, text="FPS", fg=FG_MUTED, bg=BG_ELEV,
                 font=(UI, 12), width=8, anchor="w").grid(row=0, column=0, pady=5)
        fps_row = Frame(og, bg=BG_ELEV)
        fps_row.grid(row=0, column=1, sticky="w")
        self._fps_var = tk.StringVar(value="15")
        Entry(fps_row, textvariable=self._fps_var, mono_font=True, width=5
              ).pack(side="left", ipady=3)
        tk.Label(fps_row, text="frames/sec", fg=FG_DIM, bg=BG_ELEV,
                 font=(MONO, 10)).pack(side="left", padx=(8, 0))

        # Width
        tk.Label(og, text="Width", fg=FG_MUTED, bg=BG_ELEV,
                 font=(UI, 12), width=8, anchor="w").grid(row=1, column=0, pady=5)
        w_row = Frame(og, bg=BG_ELEV)
        w_row.grid(row=1, column=1, sticky="w")
        self._width_var = tk.StringVar(value="480")
        self._width_combo = ttk.Combobox(
            w_row, textvariable=self._width_var, width=6,
            values=["320", "480", "640", "720", "960", "1280"],
            font=(MONO, 11),
        )
        self._width_combo.pack(side="left")
        tk.Label(w_row, text="px · height auto", fg=FG_DIM, bg=BG_ELEV,
                 font=(MONO, 10)).pack(side="left", padx=(8, 0))

        # Quality slider
        tk.Label(og, text="Quality", fg=FG_MUTED, bg=BG_ELEV,
                 font=(UI, 12), width=8, anchor="w").grid(row=2, column=0, pady=5)
        q_row = Frame(og, bg=BG_ELEV)
        q_row.grid(row=2, column=1, sticky="ew")
        self._quality_var = tk.IntVar(value=7)
        self._quality_lbl = tk.Label(q_row, text="7", fg=FG, bg=BG_INPUT,
                                      font=(MONO, 12, "bold"), width=3,
                                      highlightthickness=1, highlightbackground=BD)
        slider = tk.Scale(
            q_row, from_=1, to=10, orient="horizontal",
            variable=self._quality_var, showvalue=False,
            bg=BG_ELEV, fg=FG_DIM, troughcolor=BG_INPUT,
            activebackground=ACCENT, highlightthickness=0,
            sliderrelief="flat", sliderlength=14, width=6,
            length=140, bd=0, relief="flat",
            command=lambda v: self._quality_lbl.configure(text=str(int(float(v)))),
        )
        slider.pack(side="left")
        self._quality_lbl.pack(side="left", padx=(8, 0), ipady=3, ipadx=4)

        # Buttons
        btn_row = Frame(col)
        btn_row.pack(anchor="w", pady=(8, 0))
        self._convert_btn = Button(btn_row, "▶  Convert to GIF", command=self._on_convert, primary=True)
        self._convert_btn.pack(side="left", padx=(0, 8))
        Button(btn_row, "Reset", command=self._on_reset, ghost=True).pack(side="left")

    def _build_right(self, parent):
        col = Frame(parent)
        col.grid(row=0, column=1, sticky="nsew")

        # Preview header
        prev_hdr = Frame(col)
        prev_hdr.pack(fill="x", pady=(0, 6))
        tk.Label(prev_hdr, text="PREVIEW", fg=FG_MUTED, bg=BG_PANEL,
                 font=(MONO, 10, "bold")).pack(side="left")
        self._prev_info_lbl = tk.Label(prev_hdr, text="480 × 270 · 15 fps · q7",
                                        fg=FG_FAINT, bg=BG_PANEL, font=(MONO, 10))
        self._prev_info_lbl.pack(side="left", padx=(8, 0))

        # Striped preview canvas (16:9)
        self._prev_canvas = tk.Canvas(col, bg="#1a2030", bd=0,
                                       highlightthickness=1, highlightbackground=BD)
        self._prev_canvas.pack(fill="x")
        self._prev_canvas.bind("<Configure>", self._redraw_preview)

        # Status
        tk.Label(col, text="STATUS", fg=FG_MUTED, bg=BG_PANEL,
                 font=(MONO, 10, "bold")).pack(anchor="w", pady=(12, 4))

        status_box = tk.Frame(col, bg=BG_INPUT, bd=0,
                               highlightthickness=1, highlightbackground=BD_SUBTLE)
        status_box.pack(fill="x")
        status_inner = Frame(status_box, bg=BG_INPUT)
        status_inner.pack(fill="x", padx=10, pady=8)

        self._enc_tag = tk.Label(status_inner, text="READY", fg=INFO, bg=BG_INPUT,
                                  font=(MONO, 10, "bold"))
        self._enc_tag.pack(side="left")
        self._status_lbl = tk.Label(status_inner, text="Select a source file to begin",
                                     fg=FG_MUTED, bg=BG_INPUT, font=(MONO, 11), anchor="w",
                                     width=1)
        self._status_lbl.pack(side="left", padx=(8, 0), fill="x", expand=True)

        self._prog_bar = ProgressBar(col, mode="download", bg=BG_PANEL)
        self._prog_bar.pack(fill="x", pady=(6, 0))
        self._prog_bar.set(0)

    def _redraw_preview(self, event=None):
        w = self._prev_canvas.winfo_width() or 400
        h = max(int(w * 9 / 16), 1)
        self._prev_canvas.configure(height=h)
        self._prev_canvas.delete("all")
        for i in range(0, w, 16):
            c = "#141820" if (i // 16) % 2 == 0 else "#11151c"
            self._prev_canvas.create_rectangle(i, 0, i + 16, h, fill=c, outline="")
        cx, cy = w // 2, h // 2
        self._prev_canvas.create_polygon(cx - 14, cy - 9, cx - 14, cy + 9,
                                          cx + 14, cy, fill="white", outline="")

    # ── clip bar sync ─────────────────────────────────────────────────────────

    def _on_clip_change(self, _event=None):
        s = self._clip_start.get().strip()
        e = self._clip_end.get().strip()
        if s or e:
            self._clip_bar.set_range(s or "00:00:00", e or "00:00:00")

    def _on_clipbar_drag(self, start_str: str, end_str: str):
        self._clip_start.delete(0, tk.END)
        self._clip_start.insert(0, start_str)
        self._clip_end.delete(0, tk.END)
        self._clip_end.insert(0, end_str)

    # ── actions ───────────────────────────────────────────────────────────────

    def _on_convert(self):
        src = self._src_var.get().strip()
        if not src:
            self._set_status("No source selected.", ERR)
            return
        try:
            fps   = int(self._fps_var.get())
            width = int(self._width_var.get())
        except ValueError:
            self._set_status("FPS and width must be integers.", ERR)
            return

        start   = self._clip_start.get().strip() or "00:00:00"
        end     = self._clip_end.get().strip() or "00:00:10"
        quality = self._quality_var.get()

        h = int(width * 9 / 16)
        self._prev_info_lbl.configure(text=f"{width} × {h} · {fps} fps · q{quality}")
        self._prog_bar.set(0)
        self._convert_btn.configure(state="disabled")

        cb = lambda msg: self.after(0, self._on_progress, msg)

        if self._source_mode == "url":
            if not (src.startswith("http://") or src.startswith("https://")):
                self._set_status("Enter a valid YouTube URL.", ERR)
                self._convert_btn.configure(state="normal")
                return
            self._enc_tag.configure(text="DOWNLOADING")
            self._set_status("Starting download…", INFO)
            download_and_convert_to_gif(
                url=src, start=start, end=end,
                fps=fps, width=width, quality=quality,
                output_dir=self._get_output_dir(),
                on_progress=cb,
            )
        else:
            if not os.path.isfile(src):
                self._set_status(f"File not found: {src}", ERR)
                self._convert_btn.configure(state="normal")
                return
            self._enc_tag.configure(text="ENCODING")
            self._set_status("Starting…", INFO)
            convert_to_gif(
                input_path=src, start=start, end=end,
                fps=fps, width=width, quality=quality,
                on_progress=cb,
            )

    def _on_progress(self, msg: str):
        if msg.startswith("Done"):
            self._enc_tag.configure(text="DONE")
            self._prog_bar.set(1.0, mode="done")
            self._set_status(msg, OK)
            self._convert_btn.configure(state="normal")
        elif "Downloading video" in msg:
            self._prog_bar.set(0.05)
            self._set_status(msg, INFO)
        elif "[download]" in msg and "%" in msg:
            try:
                pct = float(msg.split("%")[0].split()[-1]) / 100.0
                self._prog_bar.set(pct * 0.4)
            except Exception:
                pass
            self._set_status(msg, FG_MUTED)
        elif "Pass 1" in msg:
            self._prog_bar.set(0.5)
            self._set_status(msg, INFO)
        elif "Pass 2" in msg:
            self._prog_bar.set(0.75)
            self._set_status(msg, INFO)
        elif "error" in msg.lower():
            self._enc_tag.configure(text="ERROR")
            self._prog_bar.set(1.0, mode="error")
            self._set_status(msg, ERR)
            self._convert_btn.configure(state="normal")
        else:
            self._set_status(msg, FG_MUTED)

    def _set_status(self, text: str, color=None):
        self._status_lbl.configure(text=text[-120:], fg=color or FG_MUTED)

    def _on_reset(self):
        self._src_var.set("")
        self._clip_start.delete(0, tk.END)
        self._clip_start.insert(0, "00:00:00")
        self._clip_end.delete(0, tk.END)
        self._clip_end.insert(0, "00:00:10")
        self._clip_bar.set_duration(0)
        self._fps_var.set("15")
        self._width_var.set("480")
        self._quality_var.set(7)
        self._prog_bar.set(0)
        self._enc_tag.configure(text="READY")
        self._convert_btn.configure(state="normal")
        self._set_status("Select a source file to begin.", FG_MUTED)
