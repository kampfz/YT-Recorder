import tkinter as tk
import customtkinter as ctk

from gui.tabbar import TabBar
from gui.tab_download import DownloadTab
from gui.tab_schedule import ScheduleTab
from gui.tab_gif import GifTab
from gui.tab_settings import SettingsTab
from services.scheduler import RecordingScheduler
from gui.theme import BG_PANEL, BD_SUBTLE, FG_DIM, OK, WARN, MONO, UI

VERSION = "0.7.2"
_STATUSBAR_BG = "#0b0e12"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("YT Recorder")
        self.geometry("960x700")
        self.minsize(800, 560)
        ctk.set_appearance_mode("dark")
        self.configure(fg_color=BG_PANEL)

        self._scheduler = RecordingScheduler(on_job_trigger=self._on_scheduled_trigger)
        self._panels: dict[str, tk.Frame] = {}

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_tabbar()
        self._build_panels()
        self._build_statusbar()

        self._scheduler.start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Show first tab
        self._tabbar.activate("Download")

    # ────────────────────────── build ────────────────────────────────────────

    def _build_tabbar(self):
        self._tabbar = TabBar(
            self,
            tabs=["Download", "Schedule", "GIF Converter", "Settings"],
            on_switch=self._switch_panel,
        )
        self._tabbar.grid(row=0, column=0, sticky="ew")

    def _build_panels(self):
        container = tk.Frame(self, bg=BG_PANEL, bd=0, highlightthickness=0)
        container.grid(row=1, column=0, sticky="nsew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)
        self._container = container

        self._settings_tab = SettingsTab(container, on_output_dir_change=lambda d: None)
        self._download_tab = DownloadTab(container, self._scheduler,
                                          self._settings_tab.get_output_dir)
        self._schedule_tab = ScheduleTab(container, self._scheduler,
                                          self._settings_tab.get_output_dir)
        self._gif_tab      = GifTab(container, self._settings_tab.get_output_dir)

        for name, widget in [
            ("Download",      self._download_tab),
            ("Schedule",      self._schedule_tab),
            ("GIF Converter", self._gif_tab),
            ("Settings",      self._settings_tab),
        ]:
            widget.place(x=0, y=0, relwidth=1, relheight=1)
            widget.lower()
            self._panels[name] = widget

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=_STATUSBAR_BG, height=24, bd=0,
                       highlightthickness=1, highlightbackground=BD_SUBTLE)
        bar.grid(row=2, column=0, sticky="ew")
        bar.pack_propagate(False)

        # Green dot + label
        dot = tk.Canvas(bar, width=8, height=8, bg=_STATUSBAR_BG,
                        highlightthickness=0)
        dot.pack(side="left", padx=(14, 4), pady=8)
        dot.create_oval(1, 1, 7, 7, fill=OK, outline="")
        tk.Label(bar, text="scheduler running", bg=_STATUSBAR_BG, fg=FG_DIM,
                 font=(MONO, 10)).pack(side="left", padx=(0, 10))

        self._pending_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self._pending_var, bg=_STATUSBAR_BG,
                 fg=WARN, font=(MONO, 10)).pack(side="left")

        # Right: versions
        for text in [f"v{VERSION}", "·", "ffmpeg", "·", "yt-dlp"]:
            fg = BD_SUBTLE if text == "·" else FG_DIM
            tk.Label(bar, text=text, bg=_STATUSBAR_BG, fg=fg,
                     font=(MONO, 10)).pack(side="right", padx=(0, 6 if text == f"v{VERSION}" else 2))

        self._tick_statusbar()

    def _tick_statusbar(self):
        n = len(self._scheduler.get_scheduled())
        self._pending_var.set(f"· {n} job{'s' if n != 1 else ''} pending" if n else "")
        self._tabbar.set_badge("Schedule", n)
        self.after(5000, self._tick_statusbar)

    # ────────────────────────── tab switching ─────────────────────────────────

    def _switch_panel(self, name: str):
        for n, panel in self._panels.items():
            if n == name:
                panel.lift()
            else:
                panel.lower()

    # ────────────────────────── callbacks ─────────────────────────────────────

    def _on_scheduled_trigger(self, job_id: str, url: str, output_dir: str):
        self._download_tab.on_scheduled_job_trigger(job_id, url, output_dir)

    def _on_close(self):
        self._scheduler.shutdown()
        self.destroy()
