"""
Downloads yt-dlp.exe and ffmpeg.exe into ~/.yt_recorder/bin/ if they are missing.
Provides a blocking `ensure_binaries(on_progress)` function; the GUI wraps it
in a thread so the progress window stays responsive.
"""
import io
import os
import urllib.request
import zipfile
from typing import Callable

BIN_DIR = os.path.join(os.path.expanduser("~"), ".yt_recorder", "bin")

YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
# BtbN GPL build — ~75 MB zip, contains bin/ffmpeg.exe
FFMPEG_ZIP_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)


def bin_dir() -> str:
    return BIN_DIR


def _dest(name: str) -> str:
    return os.path.join(BIN_DIR, name)


def needs_download() -> list[str]:
    """Return list of binary names that are missing."""
    missing = []
    for name in ("yt-dlp.exe", "ffmpeg.exe"):
        if not os.path.isfile(_dest(name)):
            missing.append(name)
    return missing


def ensure_binaries(on_progress: Callable[[str, float], None]):
    """
    Download any missing binaries to BIN_DIR.
    on_progress(message, fraction_0_to_1) is called from this thread.
    Raises on unrecoverable error.
    """
    os.makedirs(BIN_DIR, exist_ok=True)
    missing = needs_download()
    if not missing:
        return

    steps = len(missing)
    for idx, name in enumerate(missing):
        base_frac = idx / steps
        step_frac = 1 / steps

        if name == "yt-dlp.exe":
            _download_file(
                YTDLP_URL,
                _dest("yt-dlp.exe"),
                label="Downloading yt-dlp.exe",
                on_progress=lambda msg, f, bf=base_frac, sf=step_frac: on_progress(
                    msg, bf + f * sf
                ),
            )
        elif name == "ffmpeg.exe":
            _download_ffmpeg(
                base_frac=base_frac,
                step_frac=step_frac,
                on_progress=on_progress,
            )


def _download_file(
    url: str,
    dest: str,
    label: str,
    on_progress: Callable[[str, float], None],
):
    on_progress(f"{label}…", 0.0)
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(url) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk = 1 << 15  # 32 KB
            with open(tmp, "wb") as f:
                while True:
                    data = resp.read(chunk)
                    if not data:
                        break
                    f.write(data)
                    downloaded += len(data)
                    frac = (downloaded / total) if total else 0
                    mb = downloaded / (1 << 20)
                    on_progress(f"{label} — {mb:.1f} MB", frac)
        os.replace(tmp, dest)
        on_progress(f"{label} — done", 1.0)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _download_ffmpeg(
    base_frac: float,
    step_frac: float,
    on_progress: Callable[[str, float], None],
):
    def _prog(msg, f):
        on_progress(msg, base_frac + f * step_frac * 0.8)  # 80% for download

    zip_bytes = io.BytesIO()
    label = "Downloading ffmpeg"
    on_progress(f"{label}…", base_frac)
    with urllib.request.urlopen(FFMPEG_ZIP_URL) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk = 1 << 15
        while True:
            data = resp.read(chunk)
            if not data:
                break
            zip_bytes.write(data)
            downloaded += len(data)
            frac = (downloaded / total) if total else 0
            mb = downloaded / (1 << 20)
            _prog(f"{label} — {mb:.0f} MB", frac)

    on_progress("Extracting ffmpeg.exe…", base_frac + step_frac * 0.85)
    zip_bytes.seek(0)
    with zipfile.ZipFile(zip_bytes) as zf:
        # The zip contains e.g. ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe
        target = next(
            name for name in zf.namelist()
            if name.endswith("bin/ffmpeg.exe")
        )
        data = zf.read(target)

    with open(_dest("ffmpeg.exe"), "wb") as f:
        f.write(data)

    on_progress("ffmpeg.exe — done", base_frac + step_frac)
