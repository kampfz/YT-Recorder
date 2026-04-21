"""
Shown on first run when yt-dlp or ffmpeg are missing.
Downloads binaries in a background thread and calls on_done() when complete.
"""
import threading

import customtkinter as ctk

from utils.auto_download import ensure_binaries, needs_download


class SetupWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("YT Recorder — First-run Setup")
        self.geometry("480x180")
        self.resizable(False, False)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._success = False

        ctk.CTkLabel(self, text="Downloading required tools…", font=ctk.CTkFont(size=14)).pack(pady=(20, 6))

        self._status = ctk.CTkLabel(self, text="Starting…", text_color="gray")
        self._status.pack()

        self._bar = ctk.CTkProgressBar(self, width=420)
        self._bar.set(0)
        self._bar.pack(pady=12)

        self._error_label = ctk.CTkLabel(self, text="", text_color="red", wraplength=440)
        self._error_label.pack()

        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            ensure_binaries(self._on_progress)
            self._success = True
            self.after(400, self.destroy)
        except Exception as exc:
            self.after(0, self._show_error, str(exc))

    def _on_progress(self, message: str, fraction: float):
        self.after(0, self._update_ui, message, fraction)

    def _update_ui(self, message: str, fraction: float):
        self._status.configure(text=message)
        self._bar.set(max(0.0, min(1.0, fraction)))

    def _show_error(self, msg: str):
        self._error_label.configure(text=f"Error: {msg}")
        ctk.CTkButton(self, text="Quit", command=self.destroy).pack(pady=6)

    @property
    def success(self) -> bool:
        return self._success


def run_setup_if_needed() -> bool:
    """
    Show setup window if any binary is missing.
    Returns True if all binaries are present (either already were, or just downloaded).
    """
    if not needs_download():
        return True

    win = SetupWindow()
    win.mainloop()
    return win.success
