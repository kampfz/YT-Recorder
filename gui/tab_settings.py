import os
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog

from gui.theme import (
    BG_PANEL, BG_ELEV, BG_INPUT, BD, BD_SUBTLE,
    FG, FG_MUTED, FG_DIM, FG_FAINT,
    ACCENT, OK, ERR, MONO, UI,
)
from gui.widgets import Frame, Sep, Label, MonoLabel, Entry, Button, ScrollFrame
from utils.binaries import get_binary_path


class SettingsTab(tk.Frame):
    def __init__(self, master, on_output_dir_change: callable):
        super().__init__(master, bg=BG_PANEL, bd=0, highlightthickness=0)
        self._on_change = on_output_dir_change
        self._default_dir = os.path.join(os.path.expanduser("~"), "Videos")
        os.makedirs(self._default_dir, exist_ok=True)
        self._build()

    def _build(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        hdr = tk.Frame(self, bg="#0f1319", bd=0, highlightthickness=0)
        hdr.grid(row=0, column=0, sticky="ew")
        tk.Label(hdr, text="Settings", fg=FG, bg="#0f1319",
                 font=(UI, 13, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        tk.Label(hdr,
                 text="Configuration stored at  ~/.yt_recorder_settings.json",
                 fg=FG_DIM, bg="#0f1319", font=(MONO, 11)
                 ).pack(anchor="w", padx=16, pady=(0, 10))
        Sep(hdr, bg=BD_SUBTLE).pack(fill="x")

        scroll = ScrollFrame(self)
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.inner.grid_columnconfigure(0, weight=1)
        b = scroll.inner

        self._build_output_folder(b)
        Sep(b, bg=BD_SUBTLE).pack(fill="x")
        self._build_filename_template(b)
        Sep(b, bg=BD_SUBTLE).pack(fill="x")
        self._build_quality(b)
        Sep(b, bg=BD_SUBTLE).pack(fill="x")
        self._build_concurrency(b)
        Sep(b, bg=BD_SUBTLE).pack(fill="x")
        self._build_notifications(b)
        Sep(b, bg=BD_SUBTLE).pack(fill="x")
        self._build_launch(b)
        Sep(b, bg=BD_SUBTLE).pack(fill="x")
        self._build_binary_info(b)

    # ── row helpers ───────────────────────────────────────────────────────────

    def _row(self, parent, title, desc):
        """Returns (row_frame, ctrl_frame)."""
        row = tk.Frame(parent, bg=BG_PANEL, bd=0, highlightthickness=0)
        row.pack(fill="x", padx=0)

        left = tk.Frame(row, bg=BG_PANEL, width=230, bd=0, highlightthickness=0)
        left.pack(side="left", fill="y", padx=(16, 0), pady=14)
        left.pack_propagate(False)
        tk.Label(left, text=title, fg=FG, bg=BG_PANEL,
                 font=(UI, 12, "bold"), anchor="w", wraplength=220,
                 justify="left").pack(anchor="w")
        tk.Label(left, text=desc, fg=FG_DIM, bg=BG_PANEL,
                 font=(UI, 11), anchor="w", wraplength=220,
                 justify="left").pack(anchor="w", pady=(3, 0))

        ctrl = tk.Frame(row, bg=BG_PANEL, bd=0, highlightthickness=0)
        ctrl.pack(side="left", fill="both", expand=True, padx=(24, 16), pady=14)
        return row, ctrl

    # ── individual settings ───────────────────────────────────────────────────

    def _build_output_folder(self, parent):
        _, ctrl = self._row(parent, "Default output folder",
                            "Where finished videos and GIFs are saved.")
        path_row = Frame(ctrl)
        path_row.pack(fill="x")
        path_row.columnconfigure(0, weight=1)

        self._dir_var = tk.StringVar(value=self._default_dir)
        path_lbl = tk.Label(path_row, textvariable=self._dir_var,
                             fg=FG, bg=BG_INPUT, font=(MONO, 11), anchor="w",
                             highlightthickness=1, highlightbackground=BD,
                             padx=8, pady=4)
        path_lbl.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        Button(path_row, "Browse…", command=self._pick_folder, small=True,
               ).grid(row=0, column=1, padx=(0, 6))
        Button(path_row, "Open", command=self._open_folder, small=True, ghost=True,
               ).grid(row=0, column=2)

    def _build_filename_template(self, parent):
        _, ctrl = self._row(parent, "Filename template",
                            "yt-dlp output template. Supports %(title)s, %(id)s, %(uploader)s.")
        self._template_var = tk.StringVar(
            value="%(uploader)s - %(title).80s [%(id)s].%(ext)s")
        Entry(ctrl, textvariable=self._template_var, mono_font=True
              ).pack(fill="x", ipady=4)

    def _build_quality(self, parent):
        _, ctrl = self._row(parent, "Preferred quality",
                            "yt-dlp format selector. Falls back to next-best if unavailable.")
        q_row = Frame(ctrl)
        q_row.pack(fill="x", pady=(0, 8))

        for opts, default, w in [
            (["1080p (best)", "720p", "480p", "360p"], "1080p (best)", 16),
            (["mp4", "webm", "mkv", "m4a", "mp3"],    "mp4",           8),
        ]:
            var = tk.StringVar(value=default)
            om = tk.OptionMenu(q_row, var, *opts)
            om.configure(
                bg=BG_INPUT, fg=FG, activebackground=BG_ELEV, activeforeground=FG,
                relief="flat", bd=0, highlightthickness=1, highlightbackground=BD,
                font=(UI, 11), indicatoron=True, width=w,
            )
            om["menu"].configure(bg=BG_ELEV, fg=FG, activebackground=ACCENT,
                                  activeforeground="#fff", relief="flat")
            om.pack(side="left", padx=(0, 8))

        chk_row = Frame(ctrl)
        chk_row.pack(fill="x")
        self._embed_thumb = tk.BooleanVar(value=True)
        self._embed_subs  = tk.BooleanVar(value=True)
        self._keep_audio  = tk.BooleanVar(value=False)
        for text, var in [("Embed thumbnail", self._embed_thumb),
                           ("Embed subtitles (en)", self._embed_subs),
                           ("Keep separate audio", self._keep_audio)]:
            self._checkbox(chk_row, text, var)

    def _build_concurrency(self, parent):
        _, ctrl = self._row(parent, "Concurrent downloads",
                            "Max simultaneous jobs. Recordings count as one each.")
        row = Frame(ctrl)
        row.pack(anchor="w")
        self._conc_var = tk.IntVar(value=3)
        self._conc_lbl = tk.Label(row, text="3", fg=FG, bg=BG_INPUT,
                                   font=(MONO, 12, "bold"), width=3,
                                   highlightthickness=1, highlightbackground=BD)
        slider = tk.Scale(
            row, from_=1, to=8, orient="horizontal",
            variable=self._conc_var, showvalue=False,
            bg=BG_PANEL, fg=FG_DIM, troughcolor=BG_INPUT,
            activebackground=ACCENT, highlightthickness=0,
            sliderrelief="flat", sliderlength=14, width=6,
            length=200, bd=0,
            command=lambda v: self._conc_lbl.configure(text=str(int(float(v)))),
        )
        slider.pack(side="left")
        self._conc_lbl.pack(side="left", padx=(8, 0), ipady=3, ipadx=4)

    def _build_notifications(self, parent):
        _, ctrl = self._row(parent, "Notifications",
                            "System toast when a job finishes or fails.")
        row = Frame(ctrl)
        row.pack(anchor="w")
        self._notif_var = tk.BooleanVar(value=True)
        self._toggle(row, self._notif_var, "On completion and failure")

    def _build_launch(self, parent):
        _, ctrl = self._row(parent, "Launch at login",
                            "Starts minimized so the scheduler can fire while you're away.")
        row = Frame(ctrl)
        row.pack(anchor="w")
        self._launch_var = tk.BooleanVar(value=False)
        self._toggle(row, self._launch_var, "Off")

    def _build_binary_info(self, parent):
        _, ctrl = self._row(parent, "yt-dlp binary",
                            "Override the bundled binary. Leave blank to use built-in.")
        inp_row = Frame(ctrl)
        inp_row.pack(fill="x", pady=(0, 6))
        inp_row.columnconfigure(0, weight=1)
        self._ytdlp_override = Entry(inp_row, mono_font=True)
        self._ytdlp_override.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=4)
        Button(inp_row, "Check for update", command=self._check_update, small=True,
               ghost=True).grid(row=0, column=1)
        self._ver_lbl = tk.Label(ctrl, text="Checking…", fg=FG_DIM, bg=BG_PANEL,
                                  font=(MONO, 11), anchor="w")
        self._ver_lbl.pack(anchor="w")
        self._refresh_versions()

    # ── widget helpers ────────────────────────────────────────────────────────

    def _checkbox(self, parent, text, var):
        f = Frame(parent)
        f.pack(side="left", padx=(0, 16))
        cb = tk.Checkbutton(
            f, text=text, variable=var,
            bg=BG_PANEL, fg=FG_MUTED, selectcolor=ACCENT,
            activebackground=BG_PANEL, activeforeground=FG,
            font=(UI, 11), bd=0, highlightthickness=0, cursor="hand2",
        )
        cb.pack()
        return cb

    def _toggle(self, parent, var, label_text):
        """Simulated toggle switch using a Canvas."""
        W, H = 34, 18

        canvas = tk.Canvas(parent, width=W, height=H, bg=BG_PANEL,
                           highlightthickness=0, bd=0, cursor="hand2")
        canvas.pack(side="left")
        lbl = tk.Label(parent, text=label_text, fg=FG_MUTED, bg=BG_PANEL,
                       font=(UI, 12))
        lbl.pack(side="left", padx=(8, 0))

        def _draw():
            canvas.delete("all")
            on = var.get()
            track_col = ACCENT if on else "#1a1e25"
            canvas.create_rectangle(0, 3, W, H - 3, fill=track_col,
                                     outline=ACCENT if on else BD, width=1)
            x = W - 14 if on else 2
            canvas.create_rectangle(x, 1, x + 12, H - 1,
                                     fill=ACCENT if on else FG_DIM, outline="")

        def _toggle_click(e):
            var.set(not var.get())
            _draw()

        canvas.bind("<Button-1>", _toggle_click)
        lbl.bind("<Button-1>", _toggle_click)
        _draw()

    # ── folder / version actions ──────────────────────────────────────────────

    def _pick_folder(self):
        folder = filedialog.askdirectory(initialdir=self._dir_var.get())
        if folder:
            self._dir_var.set(folder)
            self._on_change(folder)

    def _open_folder(self):
        d = self._dir_var.get()
        if os.path.isdir(d):
            os.startfile(d)

    def _check_update(self):
        self._ver_lbl.configure(text="Checking…", fg=FG_DIM)
        def _go():
            try:
                r = subprocess.run([get_binary_path("yt-dlp.exe"), "--version"],
                                   capture_output=True, text=True, timeout=10)
                v = r.stdout.strip()
                self.after(0, self._ver_lbl.configure,
                           {"text": f"yt-dlp {v} · up to date", "fg": OK})
            except Exception as e:
                self.after(0, self._ver_lbl.configure,
                           {"text": str(e), "fg": ERR})
        threading.Thread(target=_go, daemon=True).start()

    def _refresh_versions(self):
        def _go():
            parts = []
            for name, binary, flag in [
                ("yt-dlp",  "yt-dlp.exe",  "--version"),
                ("ffmpeg",  "ffmpeg.exe",  "-version"),
            ]:
                try:
                    r = subprocess.run([get_binary_path(binary), flag],
                                       capture_output=True, text=True, timeout=8)
                    v = r.stdout.strip().splitlines()[0][:50]
                    parts.append(f"{name}: {v}")
                except Exception:
                    parts.append(f"{name}: not found")
            self.after(0, self._ver_lbl.configure,
                       {"text": "  ·  ".join(parts), "fg": FG_DIM})
        threading.Thread(target=_go, daemon=True).start()

    def get_output_dir(self) -> str:
        return self._dir_var.get()
