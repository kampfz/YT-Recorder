import json
import subprocess
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from tkcalendar import DateEntry

from services.scheduler import RecordingScheduler, COMMON_TIMEZONES, DEFAULT_GRACE_MINUTES
from services.recorder import FORMAT_MAP, DEFAULT_FORMAT, extract_available_formats
from gui.tab_download import VideoCard
from utils.binaries import get_binary_path
from gui.theme import (
    BG_PANEL, BG_ELEV, BG_INPUT, BD, BD_SUBTLE,
    FG, FG_MUTED, FG_DIM, FG_FAINT,
    ACCENT, OK, WARN, ERR, INFO, MONO, UI,
)
from gui.widgets import (
    Frame, Sep, Label, MonoLabel, SectionHeader, FlowFrame,
    Entry, Button, Badge, ProgressBar, Thumbnail, Pill,
    ScrollFrame,
)


FORMATS = list(FORMAT_MAP.keys())


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


class ScheduleRow(tk.Frame):
    def __init__(self, parent, job_data: dict, on_cancel, bg=BG_PANEL):
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0)
        self.columnconfigure(2, weight=1)
        self._build(job_data, on_cancel, bg)

    def _build(self, job_data: dict, on_cancel, bg):
        job_id = job_data["job_id"]
        url = job_data["url"]
        run_at_iso = job_data["run_at"]
        format_key = job_data.get("format_key", DEFAULT_FORMAT)
        end_time = job_data.get("end_time")

        MonoLabel(self, text=job_id, fg=FG_FAINT, bg=bg, size=10
                  ).grid(row=0, column=0, rowspan=2, sticky="ns",
                         padx=(10, 6), pady=10)

        Thumbnail(self, idx=2, mode="soon", width=76, height=44, bg=bg
                  ).grid(row=0, column=1, rowspan=2, padx=(0, 8), pady=10)

        wrap = Frame(self, bg=bg)
        wrap.grid(row=0, column=2, sticky="ew", padx=(0, 8), pady=(10, 2))
        wrap.columnconfigure(0, weight=1)
        short = url.replace("https://", "")[:60]
        tk.Label(wrap, text=short, fg=FG, bg=bg,
                 font=(UI, 11, "bold"), anchor="w").grid(row=0, column=0, sticky="ew")
        meta_text = f"{format_key}"
        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time)
                meta_text += f" · ends {end_dt.strftime('%H:%M')}"
            except Exception:
                pass
        tk.Label(wrap, text=meta_text,
                 fg=FG_DIM, bg=bg, font=(MONO, 9), anchor="w"
                 ).grid(row=1, column=0, sticky="ew")

        try:
            dt = datetime.fromisoformat(run_at_iso)
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M")
        except Exception:
            date_str, time_str = run_at_iso[:10], run_at_iso[11:16]

        time_f = Frame(self, bg=bg)
        time_f.grid(row=0, column=3, padx=(0, 8), pady=10, sticky="w")
        tk.Label(time_f, text=date_str, fg=FG, bg=bg,
                 font=(MONO, 10)).pack(anchor="w")
        tk.Label(time_f, text=time_str, fg=FG_MUTED, bg=bg,
                 font=(MONO, 9)).pack(anchor="w")

        prog_f = Frame(self, bg=bg)
        prog_f.grid(row=0, column=4, padx=(0, 8), pady=10, sticky="ew")
        self.columnconfigure(4, minsize=160)
        tk.Label(prog_f, text="armed", fg=WARN, bg=bg,
                 font=(MONO, 9), anchor="w").pack(fill="x")
        bar = ProgressBar(prog_f, mode="warn", bg=bg)
        bar.pack(fill="x", pady=(3, 0))
        bar.set(0.85, mode="warn")

        tk.Button(
            self, text="✕", command=on_cancel,
            bg=bg, fg=FG_DIM, activebackground="#2b1a1c", activeforeground=ERR,
            relief="flat", bd=0, highlightthickness=1, highlightbackground="black",
            padx=5, pady=4, font=(MONO, 11), cursor="hand2",
        ).grid(row=0, column=5, rowspan=2, padx=(0, 10), pady=10)


def _setup_combobox_style(root=None):
    style = ttk.Style()
    style.theme_use('clam')
    # Combobox style
    style.configure("Dark.TCombobox",
                    fieldbackground=BG_INPUT,
                    background=BG_INPUT,
                    foreground=FG,
                    arrowcolor=FG_DIM,
                    bordercolor=BD,
                    lightcolor=BG_INPUT,
                    darkcolor=BG_INPUT,
                    selectbackground=ACCENT,
                    selectforeground=FG,
                    font=(MONO, 10))
    style.map("Dark.TCombobox",
              fieldbackground=[("readonly", BG_INPUT)],
              background=[("readonly", BG_INPUT)],
              foreground=[("readonly", FG)])
    # DateEntry style (must end with .TEntry to inherit properly)
    style.configure("Dark.TEntry",
                    fieldbackground=BG_INPUT,
                    background=BG_INPUT,
                    foreground=FG,
                    bordercolor=BD,
                    lightcolor=BD,
                    darkcolor=BD,
                    insertcolor=FG,
                    padding=2)
    style.map("Dark.TEntry",
              fieldbackground=[("readonly", BG_INPUT), ("disabled", BG_INPUT), ("focus", BG_INPUT), ("!disabled", BG_INPUT)],
              background=[("readonly", BG_INPUT), ("!disabled", BG_INPUT)],
              foreground=[("readonly", FG), ("disabled", FG_DIM), ("!disabled", FG)])
    # Style the dropdown listbox via option database
    if root:
        root.option_add("*TCombobox*Listbox.background", BG_INPUT)
        root.option_add("*TCombobox*Listbox.foreground", FG)
        root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        root.option_add("*TCombobox*Listbox.selectForeground", FG)


class ScheduleTab(tk.Frame):
    def __init__(self, master, scheduler: RecordingScheduler,
                 default_output_dir: callable):
        super().__init__(master, bg=BG_PANEL, bd=0, highlightthickness=0)
        self._scheduler = scheduler
        self._get_output_dir = default_output_dir
        self._rows: dict[str, ScheduleRow] = {}
        self._selected_fmt = DEFAULT_FORMAT
        self._chip_btns: dict[str, tk.Button] = {}
        self._meta_cache: dict[str, dict] = {}
        self._debounce_id = None
        self._selected_tz = tk.StringVar(value="Local")
        self._grace_var = tk.StringVar(value=str(DEFAULT_GRACE_MINUTES))
        self._auto_stop_var = tk.BooleanVar(value=True)
        self._start_ampm = tk.StringVar(value="AM")
        self._end_ampm = tk.StringVar(value="PM")
        _setup_combobox_style(self.winfo_toplevel())
        self._build()
        self._load_existing()

    def _build(self):
        self.grid_rowconfigure(4, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build_form()
        self._build_stats()
        self._build_joblist()

    def _build_form(self):
        sec = Frame(self)
        sec.grid(row=0, column=0, sticky="ew")
        sec.grid_columnconfigure(0, weight=1)

        SectionHeader(sec, "NEW SCHEDULED RECORDING",
                      hint="fires at given datetime · records live stream"
                      ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))

        inp = Frame(sec)
        inp.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))
        inp.grid_columnconfigure(0, weight=1)

        self._url_var = tk.StringVar()
        self._url_var.trace_add("write", self._on_url_change)
        self._url_e = Entry(inp, textvariable=self._url_var, mono_font=True)
        self._url_e.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=4)

        Button(inp, "⏱  Schedule", command=self._on_schedule, primary=True,
               ).grid(row=0, column=1)

        card_host = tk.Frame(sec, bg=BG_PANEL, bd=0, highlightthickness=0)
        card_host.grid(row=2, column=0, sticky="ew")
        self._video_card = VideoCard(card_host)

        opts = Frame(sec)
        opts.grid(row=3, column=0, sticky="ew", padx=14, pady=(6, 10))
        opts.columnconfigure(6, weight=1)

        # Start date (calendar picker)
        tk.Label(opts, text="START", fg=FG_DIM, bg=BG_PANEL,
                 font=(MONO, 9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 6))
        start_box = tk.Frame(opts, bg=BG_PANEL, bd=0)
        start_box.grid(row=0, column=1, padx=(0, 6))
        self._start_date = DateEntry(
            start_box, width=10, date_pattern="yyyy-mm-dd",
            background=BG_ELEV, foreground=FG,
            headersbackground=BG_ELEV, headersforeground=FG,
            selectbackground=ACCENT, selectforeground=FG,
            normalbackground=BG_INPUT, normalforeground=FG,
            weekendbackground=BG_INPUT, weekendforeground=FG_MUTED,
            othermonthbackground="#0a0d11", othermonthforeground=FG_FAINT,
            othermonthwebackground="#0a0d11", othermonthweforeground=FG_FAINT,
            bordercolor=BD,
            font=(MONO, 10),
        )
        self._start_date.configure(style="Dark.TEntry")
        self._start_date.pack(side="left")

        # Start time (12hr format)
        time_box = tk.Frame(opts, bg=BG_INPUT, bd=0,
                            highlightthickness=1, highlightbackground=BD)
        time_box.grid(row=0, column=2, padx=(0, 12))
        self._start_time = tk.Entry(time_box, bg=BG_INPUT, fg=FG,
                                     insertbackground=FG,
                                     relief="flat", bd=0, highlightthickness=0,
                                     font=(MONO, 10), width=5)
        now = datetime.now()
        hr12 = now.hour % 12 or 12
        self._start_time.insert(0, f"{hr12}:{now.strftime('%M')}")
        self._start_time.pack(side="left", padx=(6, 2), pady=2)
        self._start_ampm.set("PM" if now.hour >= 12 else "AM")
        start_ampm_cb = ttk.Combobox(time_box, textvariable=self._start_ampm,
                                      values=["AM", "PM"], width=3,
                                      state="readonly", style="Dark.TCombobox")
        start_ampm_cb.pack(side="left", padx=(0, 4), pady=2)

        # End date (calendar picker)
        tk.Label(opts, text="END", fg=FG_DIM, bg=BG_PANEL,
                 font=(MONO, 9, "bold")).grid(row=0, column=3, sticky="w", padx=(0, 6))
        end_box = tk.Frame(opts, bg=BG_PANEL, bd=0)
        end_box.grid(row=0, column=4, padx=(0, 6))
        self._end_date = DateEntry(
            end_box, width=10, date_pattern="yyyy-mm-dd",
            background=BG_ELEV, foreground=FG,
            headersbackground=BG_ELEV, headersforeground=FG,
            selectbackground=ACCENT, selectforeground=FG,
            normalbackground=BG_INPUT, normalforeground=FG,
            weekendbackground=BG_INPUT, weekendforeground=FG_MUTED,
            othermonthbackground="#0a0d11", othermonthforeground=FG_FAINT,
            othermonthwebackground="#0a0d11", othermonthweforeground=FG_FAINT,
            bordercolor=BD,
            font=(MONO, 10),
        )
        self._end_date.configure(style="Dark.TEntry")
        self._end_date.pack(side="left")
        self._end_date.delete(0, "end")

        # End time (12hr format)
        self._end_time_box = tk.Frame(opts, bg=BG_INPUT, bd=0,
                                       highlightthickness=1, highlightbackground=BD)
        self._end_time_box.grid(row=0, column=5, padx=(0, 12))
        self._end_time = tk.Entry(self._end_time_box, bg=BG_INPUT, fg=FG,
                                   insertbackground=FG,
                                   relief="flat", bd=0, highlightthickness=0,
                                   font=(MONO, 10), width=5)
        self._end_time.pack(side="left", padx=(6, 2), pady=2)
        self._end_ampm_cb = ttk.Combobox(self._end_time_box, textvariable=self._end_ampm,
                                          values=["AM", "PM"], width=3,
                                          state="readonly", style="Dark.TCombobox")
        self._end_ampm_cb.pack(side="left", padx=(0, 4), pady=2)

        # Auto-stop checkbox
        auto_f = tk.Frame(opts, bg=BG_PANEL)
        auto_f.grid(row=0, column=6, sticky="w", padx=(0, 12))
        self._auto_cb = tk.Checkbutton(
            auto_f, text="Auto-stop", variable=self._auto_stop_var,
            bg=BG_PANEL, fg=FG_MUTED, selectcolor=BG_INPUT,
            activebackground=BG_PANEL, activeforeground=FG,
            font=(UI, 10), anchor="w", command=self._toggle_end_fields,
        )
        self._auto_cb.pack(side="left")

        # Initially disable end fields since auto-stop is checked by default
        self._toggle_end_fields()

        Sep(sec, bg=BD_SUBTLE).grid(row=4, column=0, sticky="ew")

        # Format + Settings row
        settings_row = Frame(sec)
        settings_row.grid(row=5, column=0, sticky="ew", padx=14, pady=(8, 10))

        # Format chips (dynamically updated based on video metadata)
        fmt_f = Frame(settings_row)
        fmt_f.pack(side="left", fill="x", expand=True, padx=(0, 24))
        tk.Label(fmt_f, text="FORMAT", fg=FG_DIM, bg=BG_PANEL,
                 font=(MONO, 9, "bold")).pack(anchor="w")
        self._chips_frame = FlowFrame(fmt_f, padx=3, pady=3)
        self._chips_frame.pack(fill="x", expand=True)
        self._available_formats: list[dict] = []
        self._rebuild_format_chips(FORMATS)

        # Timezone
        tz_f = Frame(settings_row)
        tz_f.pack(side="left", padx=(0, 16))
        tk.Label(tz_f, text="TZ", fg=FG_DIM, bg=BG_PANEL,
                 font=(MONO, 9, "bold")).pack(side="left", padx=(0, 6))
        tz_combo = ttk.Combobox(tz_f, textvariable=self._selected_tz,
                                 values=COMMON_TIMEZONES, width=14,
                                 state="readonly", style="Dark.TCombobox")
        tz_combo.pack(side="left")

        # Grace period
        grace_f = Frame(settings_row)
        grace_f.pack(side="left", padx=(0, 16))
        tk.Label(grace_f, text="GRACE", fg=FG_DIM, bg=BG_PANEL,
                 font=(MONO, 9, "bold")).pack(side="left", padx=(0, 6))
        grace_box = tk.Frame(grace_f, bg=BG_INPUT, bd=0,
                              highlightthickness=1, highlightbackground=BD)
        grace_box.pack(side="left")
        self._grace_e = tk.Entry(grace_box, textvariable=self._grace_var,
                                  bg=BG_INPUT, fg=FG,
                                  insertbackground=FG,
                                  relief="flat", bd=0, highlightthickness=0,
                                  font=(MONO, 10), width=3)
        self._grace_e.pack(side="left", padx=(6, 2), pady=2)
        tk.Label(grace_box, text="min", fg=FG_DIM, bg=BG_INPUT,
                 font=(MONO, 9)).pack(side="left", padx=(0, 6), pady=2)

        self._err_lbl = tk.Label(settings_row, text="", fg=ERR, bg=BG_PANEL,
                                  font=(MONO, 10))
        self._err_lbl.pack(side="right", padx=(10, 0))

    def _build_stats(self):
        bar = tk.Frame(self, bg="#0d1116", bd=0, highlightthickness=0)
        bar.grid(row=1, column=0, sticky="ew")

        inner = Frame(bar, bg="#0d1116")
        inner.pack(fill="x", padx=14, pady=6)

        self._stat_sched = tk.StringVar(value="0")
        self._stat_next = tk.StringVar(value="—")

        for label, var, col in [("Scheduled", self._stat_sched, WARN),
                                  ("Next Fire", self._stat_next, FG)]:
            f = tk.Frame(inner, bg="#0d1116")
            f.pack(side="left", padx=(0, 20))
            tk.Label(f, text=label.upper(), bg="#0d1116", fg=FG_DIM,
                     font=(MONO, 9, "bold")).pack(side="left", padx=(0, 5))
            tk.Label(f, textvariable=var, bg="#0d1116", fg=col,
                     font=(MONO, 11, "bold")).pack(side="left")

        tk.Label(inner, text="Persisted:", bg="#0d1116", fg=FG_DIM,
                 font=(MONO, 9)).pack(side="right", padx=(0, 4))
        tk.Label(inner, text="jobs.json", bg="#0d1116", fg=FG_MUTED,
                 font=(MONO, 10)).pack(side="right")

        Sep(self, bg=BD_SUBTLE).grid(row=2, column=0, sticky="ew")

    def _build_joblist(self):
        hdr = tk.Frame(self, bg="#0d1116", bd=0, highlightthickness=0)
        hdr.grid(row=3, column=0, sticky="new")
        for text, pad in [("ID", (12, 0)), ("", (84, 0)),
                           ("URL / FORMAT", (8, 0)), ("FIRES", (8, 0)),
                           ("STATUS", (8, 0))]:
            tk.Label(hdr, text=text, bg="#0d1116", fg=FG_DIM,
                     font=(MONO, 9, "bold"), anchor="w"
                     ).pack(side="left", padx=pad, pady=5)
        Sep(hdr, bg=BD_SUBTLE).pack(fill="x", side="bottom")

        self.grid_rowconfigure(4, weight=1)
        self._scroll = ScrollFrame(self)
        self._scroll.grid(row=4, column=0, sticky="nsew")
        self._scroll.inner.grid_columnconfigure(0, weight=1)

    def _on_url_change(self, *_):
        if self._debounce_id:
            self.after_cancel(self._debounce_id)
            self._debounce_id = None
        url = self._url_var.get().strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            self._video_card.hide()
            return
        self._video_card.show_loading()
        self._debounce_id = self.after(900, self._do_fetch, url)

    def _do_fetch(self, url: str):
        if url in self._meta_cache:
            data = self._meta_cache[url]
            self._video_card.show_data(data)
            available = extract_available_formats(data)
            self._rebuild_format_chips(available)
            return

        def _go():
            data = _fetch_info(url)
            self.after(0, self._on_fetch_done, url, data)
        threading.Thread(target=_go, daemon=True).start()

    def _on_fetch_done(self, url: str, data: dict | None):
        if self._url_var.get().strip() != url:
            return
        if data:
            self._meta_cache[url] = data
            self._video_card.show_data(data)
            available = extract_available_formats(data)
            self._rebuild_format_chips(available)
        else:
            self._video_card.show_error()

    def _toggle_end_fields(self):
        if self._auto_stop_var.get():
            # Auto-stop enabled: disable end time fields
            self._end_date.configure(state="disabled")
            self._end_time.configure(state="disabled", bg="#1a1d22", fg=FG_FAINT)
            self._end_ampm_cb.configure(state="disabled")
            self._end_time_box.configure(highlightbackground=BD_SUBTLE)
        else:
            # Manual end time: enable end time fields
            self._end_date.configure(state="normal")
            self._end_time.configure(state="normal", bg=BG_INPUT, fg=FG)
            self._end_ampm_cb.configure(state="readonly")
            self._end_time_box.configure(highlightbackground=BD)

    def _rebuild_format_chips(self, formats):
        """Rebuild format chip buttons based on available formats."""
        self._chips_frame.clear()
        self._chip_btns.clear()

        if formats and isinstance(formats[0], dict):
            self._available_formats = formats
            format_labels = [f["label"] for f in formats]
        else:
            self._available_formats = []
            format_labels = list(formats)

        if self._selected_fmt not in format_labels and format_labels:
            self._selected_fmt = format_labels[0]

        for fmt in format_labels:
            active = fmt == self._selected_fmt
            btn = tk.Button(
                self._chips_frame, text=fmt,
                bg="#0e1f38" if active else BG_INPUT,
                fg=INFO if active else FG_MUTED,
                activebackground=BG_ELEV, activeforeground=FG,
                relief="flat", bd=0, highlightthickness=1,
                highlightbackground=ACCENT if active else BD,
                padx=6, pady=2, font=(MONO, 9), cursor="hand2",
                command=lambda f=fmt: self._select_fmt(f),
            )
            self._chips_frame.add_widget(btn)
            self._chip_btns[fmt] = btn

    def _select_fmt(self, fmt: str):
        self._selected_fmt = fmt
        for f, btn in self._chip_btns.items():
            on = f == fmt
            btn.configure(bg="#0e1f38" if on else BG_INPUT,
                          fg=INFO if on else FG_MUTED,
                          highlightbackground=ACCENT if on else BD)

    def _parse_12hr_time(self, time_str: str, ampm: str) -> str:
        """Convert 12hr time (h:MM or hh:MM) + AM/PM to 24hr HH:MM."""
        parts = time_str.strip().split(":")
        if len(parts) != 2:
            raise ValueError("Invalid time format")
        hr = int(parts[0])
        mn = int(parts[1])
        if hr < 1 or hr > 12 or mn < 0 or mn > 59:
            raise ValueError("Invalid time")
        if ampm == "AM":
            hr24 = 0 if hr == 12 else hr
        else:
            hr24 = 12 if hr == 12 else hr + 12
        return f"{hr24:02d}:{mn:02d}"

    def _on_schedule(self):
        url = self._url_var.get().strip()
        start_date_str = self._start_date.get().strip()
        start_time_str = self._start_time.get().strip()
        start_ampm = self._start_ampm.get()
        auto_stop = self._auto_stop_var.get()

        if not url or not start_date_str or not start_time_str:
            self._err_lbl.configure(text="URL and start date/time required")
            return
        try:
            start_time_24 = self._parse_12hr_time(start_time_str, start_ampm)
            run_at = datetime.strptime(f"{start_date_str} {start_time_24}", "%Y-%m-%d %H:%M")
        except ValueError:
            self._err_lbl.configure(text="Invalid start time (use h:MM)")
            return

        end_time = None
        duration_minutes = None
        if not auto_stop:
            end_date_str = self._end_date.get().strip()
            end_time_str = self._end_time.get().strip()
            end_ampm = self._end_ampm.get()
            if end_date_str and end_time_str:
                try:
                    end_time_24 = self._parse_12hr_time(end_time_str, end_ampm)
                    end_time = datetime.strptime(f"{end_date_str} {end_time_24}", "%Y-%m-%d %H:%M")
                    if end_time <= run_at:
                        self._err_lbl.configure(text="End time must be after start")
                        return
                except ValueError:
                    self._err_lbl.configure(text="Invalid end time (use h:MM)")
                    return
            elif end_time_str and not end_date_str:
                try:
                    duration_minutes = int(end_time_str)
                except ValueError:
                    self._err_lbl.configure(text="End time: select date or enter minutes")
                return

        try:
            grace = int(self._grace_var.get())
            self._scheduler.set_grace_minutes(grace)
        except ValueError:
            pass

        self._err_lbl.configure(text="")
        job_id = self._scheduler.schedule(
            url=url,
            run_at=run_at,
            output_dir=self._get_output_dir(),
            format_key=self._selected_fmt,
            end_time=end_time,
            duration_minutes=duration_minutes,
            timezone=self._selected_tz.get(),
        )
        job_data = {
            "job_id": job_id,
            "url": url,
            "run_at": run_at.isoformat(),
            "format_key": self._selected_fmt,
            "end_time": end_time.isoformat() if end_time else None,
        }
        self._add_row(job_data)
        self._refresh()

    def _on_cancel(self, job_id: str):
        self._scheduler.cancel(job_id)
        row = self._rows.pop(job_id, None)
        if row:
            row.destroy()
        self._refresh()

    def _add_row(self, job_data: dict):
        job_id = job_data["job_id"]
        row = ScheduleRow(
            self._scroll.inner, job_data,
            on_cancel=lambda jid=job_id: self._on_cancel(jid),
        )
        row.grid(sticky="ew")
        Sep(self._scroll.inner, bg=BD_SUBTLE).grid(sticky="ew")
        self._rows[job_id] = row

    def _load_existing(self):
        for job in self._scheduler.get_scheduled():
            self._add_row(job)
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
