import tkinter as tk
from datetime import datetime

from services.scheduler import RecordingScheduler
from gui.theme import (
    BG_PANEL, BG_ELEV, BG_INPUT, BD, BD_SUBTLE,
    FG, FG_MUTED, FG_DIM, FG_FAINT,
    ACCENT, OK, WARN, ERR, MONO, UI,
)
from gui.widgets import (
    Frame, Sep, Label, MonoLabel, SectionHeader,
    Entry, Button, Badge, ProgressBar, Thumbnail, Pill,
    ScrollFrame,
)


class ScheduleRow(tk.Frame):
    def __init__(self, parent, job_id, url, run_at_iso, on_cancel, bg=BG_PANEL):
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0)
        self.columnconfigure(2, weight=1)
        self._build(job_id, url, run_at_iso, on_cancel, bg)

    def _build(self, job_id, url, run_at_iso, on_cancel, bg):
        # ID
        MonoLabel(self, text=job_id, fg=FG_FAINT, bg=bg, size=10
                  ).grid(row=0, column=0, rowspan=2, sticky="ns",
                         padx=(10, 6), pady=10)

        # Thumbnail
        Thumbnail(self, idx=2, mode="soon", width=76, height=44, bg=bg
                  ).grid(row=0, column=1, rowspan=2, padx=(0, 8), pady=10)

        # Title + meta
        wrap = Frame(self, bg=bg)
        wrap.grid(row=0, column=2, sticky="ew", padx=(0, 8), pady=(10, 2))
        wrap.columnconfigure(0, weight=1)
        short = url.replace("https://", "")[:70]
        tk.Label(wrap, text=short, fg=FG, bg=bg,
                 font=(UI, 12, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        tk.Label(wrap, text="scheduled · live recording",
                 fg=FG_DIM, bg=bg, font=(MONO, 10), anchor="w"
                 ).grid(row=1, column=0, sticky="ew")

        # Fire time
        try:
            dt = datetime.fromisoformat(run_at_iso)
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M")
        except Exception:
            date_str, time_str = run_at_iso[:10], run_at_iso[11:16]

        time_f = Frame(self, bg=bg)
        time_f.grid(row=0, column=3, padx=(0, 8), pady=10, sticky="w")
        tk.Label(time_f, text=date_str, fg=FG, bg=bg,
                 font=(MONO, 11)).pack(anchor="w")
        tk.Label(time_f, text=time_str, fg=FG_MUTED, bg=bg,
                 font=(MONO, 10)).pack(anchor="w")

        # Countdown bar
        prog_f = Frame(self, bg=bg)
        prog_f.grid(row=0, column=4, padx=(0, 8), pady=10, sticky="ew")
        self.columnconfigure(4, minsize=185)
        tk.Label(prog_f, text="armed", fg=WARN, bg=bg,
                 font=(MONO, 10), anchor="w").pack(fill="x")
        bar = ProgressBar(prog_f, mode="warn", bg=bg)
        bar.pack(fill="x", pady=(3, 0))
        bar.set(0.85, mode="warn")

        # Cancel
        tk.Button(
            self, text="✕", command=on_cancel,
            bg=bg, fg=FG_DIM, activebackground="#2b1a1c", activeforeground=ERR,
            relief="flat", bd=0, highlightthickness=1, highlightbackground="black",
            padx=5, pady=4, font=(MONO, 11), cursor="hand2",
        ).grid(row=0, column=5, rowspan=2, padx=(0, 10), pady=10)


class ScheduleTab(tk.Frame):
    def __init__(self, master, scheduler: RecordingScheduler,
                 default_output_dir: callable):
        super().__init__(master, bg=BG_PANEL, bd=0, highlightthickness=0)
        self._scheduler = scheduler
        self._get_output_dir = default_output_dir
        self._rows: dict[str, ScheduleRow] = {}
        self._build()
        self._load_existing()

    def _build(self):
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_form()
        self._build_stats()
        self._build_joblist()

    # ── form ─────────────────────────────────────────────────────────────────

    def _build_form(self):
        sec = Frame(self)
        sec.grid(row=0, column=0, sticky="ew")
        sec.grid_columnconfigure(0, weight=1)

        SectionHeader(sec, "NEW SCHEDULED RECORDING",
                      hint="fires at given datetime · records until stream ends"
                      ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))

        inp = Frame(sec)
        inp.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))
        inp.grid_columnconfigure(0, weight=1)

        self._url_e = Entry(inp, mono_font=True)
        self._url_e.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=4)

        # Datetime box
        dt_box = tk.Frame(inp, bg=BG_INPUT, bd=0,
                          highlightthickness=1, highlightbackground=BD)
        dt_box.grid(row=0, column=1, padx=(0, 8))
        tk.Label(dt_box, text="📅", bg=BG_INPUT, fg=FG_DIM,
                 font=(UI, 11)).pack(side="left", padx=(8, 2), pady=3)
        self._dt_e = tk.Entry(dt_box, bg=BG_INPUT, fg=FG,
                               insertbackground=FG,
                               relief="flat", bd=0, highlightthickness=0,
                               font=(MONO, 11), width=14)
        self._dt_e.insert(0, datetime.now().strftime("%Y-%m-%d %H:%M"))
        self._dt_e.pack(side="left", padx=(2, 8), pady=3)

        Button(inp, "⏱  Schedule", command=self._on_schedule, primary=True,
               ).grid(row=0, column=2)

        # Options row
        opts = Frame(sec)
        opts.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 10))

        for k, v in [("TZ", "Local"), ("grace", "5 min misfire")]:
            p = tk.Frame(opts, bg="#0d1015", bd=0,
                         highlightthickness=1, highlightbackground=BD_SUBTLE)
            p.pack(side="left", padx=(0, 6))
            tk.Label(p, text=k, fg=FG_DIM, bg="#0d1015",
                     font=(MONO, 10)).pack(side="left", padx=(6, 3), pady=2)
            tk.Label(p, text=v, fg=FG, bg="#0d1015",
                     font=(MONO, 10)).pack(side="left", padx=(0, 6), pady=2)

        self._err_lbl = tk.Label(opts, text="", fg=ERR, bg=BG_PANEL,
                                  font=(MONO, 10))
        self._err_lbl.pack(side="left", padx=(10, 0))

        Sep(self, bg=BD_SUBTLE).grid(row=0, column=0, sticky="ew")

    # ── stats ────────────────────────────────────────────────────────────────

    def _build_stats(self):
        bar = tk.Frame(self, bg="#0d1116", bd=0, highlightthickness=0)
        bar.grid(row=1, column=0, sticky="ew")

        inner = Frame(bar, bg="#0d1116")
        inner.pack(fill="x", padx=14, pady=6)

        self._stat_sched = tk.StringVar(value="0")
        self._stat_next  = tk.StringVar(value="—")

        for label, var, col in [("Scheduled", self._stat_sched, WARN),
                                  ("Next Fire",  self._stat_next,  FG)]:
            f = tk.Frame(inner, bg="#0d1116")
            f.pack(side="left", padx=(0, 20))
            tk.Label(f, text=label.upper(), bg="#0d1116", fg=FG_DIM,
                     font=(MONO, 9, "bold")).pack(side="left", padx=(0, 5))
            tk.Label(f, textvariable=var, bg="#0d1116", fg=col,
                     font=(MONO, 12, "bold")).pack(side="left")

        tk.Label(inner, text="Persisted:", bg="#0d1116", fg=FG_DIM,
                 font=(MONO, 9)).pack(side="right", padx=(0, 4))
        tk.Label(inner, text="jobs.json", bg="#0d1116", fg=FG_MUTED,
                 font=(MONO, 10)).pack(side="right")

        Sep(self, bg=BD_SUBTLE).grid(row=2, column=0, sticky="ew")

    # ── job list ─────────────────────────────────────────────────────────────

    def _build_joblist(self):
        hdr = tk.Frame(self, bg="#0d1116", bd=0, highlightthickness=0)
        hdr.grid(row=3, column=0, sticky="new")
        for text, pad in [("ID", (12, 0)), ("", (84, 0)),
                           ("TITLE / URL", (8, 0)), ("FIRES", (8, 0)),
                           ("COUNTDOWN", (8, 0))]:
            tk.Label(hdr, text=text, bg="#0d1116", fg=FG_DIM,
                     font=(MONO, 9, "bold"), anchor="w"
                     ).pack(side="left", padx=pad, pady=5)
        Sep(self, bg=BD_SUBTLE).grid(row=4, column=0, sticky="ew")

        self.grid_rowconfigure(5, weight=1)
        self._scroll = ScrollFrame(self)
        self._scroll.grid(row=5, column=0, sticky="nsew")
        self._scroll.inner.grid_columnconfigure(0, weight=1)

    # ── actions ──────────────────────────────────────────────────────────────

    def _on_schedule(self):
        url = self._url_e.get().strip()
        dt_str = self._dt_e.get().strip()
        if not url or not dt_str:
            self._err_lbl.configure(text="URL and datetime required")
            return
        try:
            run_at = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        except ValueError:
            self._err_lbl.configure(text=f"Expected YYYY-MM-DD HH:MM")
            return
        self._err_lbl.configure(text="")
        job_id = self._scheduler.schedule(url, run_at, self._get_output_dir())
        self._add_row(job_id, url, run_at.isoformat())
        self._refresh()

    def _on_cancel(self, job_id: str):
        self._scheduler.cancel(job_id)
        row = self._rows.pop(job_id, None)
        if row:
            row.destroy()
        self._refresh()

    def _add_row(self, job_id, url, run_at_iso):
        row = ScheduleRow(
            self._scroll.inner, job_id, url, run_at_iso,
            on_cancel=lambda jid=job_id: self._on_cancel(jid),
        )
        row.grid(sticky="ew")
        Sep(self._scroll.inner, bg=BD_SUBTLE).grid(sticky="ew")
        self._rows[job_id] = row

    def _load_existing(self):
        for job in self._scheduler.get_scheduled():
            self._add_row(job["job_id"], job["url"], job["run_at"])
        self._refresh()

    def _refresh(self):
        jobs = self._scheduler.get_scheduled()
        self._stat_sched.set(str(len(jobs)))
        if jobs:
            nxt = min(jobs, key=lambda j: j["run_at"])
            try:
                dt = datetime.fromisoformat(nxt["run_at"])
                self._stat_next.set(dt.strftime("%b %d, %H:%M"))
            except Exception:
                self._stat_next.set(nxt["run_at"][:16])
        else:
            self._stat_next.set("—")
