import os
import re
import subprocess
import threading
from typing import Callable, Optional
from utils.binaries import get_binary_path

FORMAT_MAP = {
    "mp4 1080p": ("bestvideo[height<=1080]+bestaudio/best", "mp4",  []),
    "mp4 720p":  ("bestvideo[height<=720]+bestaudio/best",  "mp4",  []),
    "webm vp9":  ("bestvideo[vcodec^=vp9]+bestaudio/best",  "webm", []),
    "mkv 4k":    ("bestvideo[height<=2160]+bestaudio/best", "mkv",  []),
    "m4a audio": ("bestaudio[ext=m4a]/bestaudio",           "m4a",  []),
    "mp3 192k":  ("bestaudio",                              None,
                  ["-x", "--audio-format", "mp3", "--audio-quality", "192K"]),
}
DEFAULT_FORMAT = "mp4 1080p"


def extract_available_formats(data: dict) -> list[dict]:
    """Extract available formats from yt-dlp metadata.

    Returns list of dicts with keys: label, format_spec, merge_format, extra_args
    """
    formats = data.get("formats") or []
    if not formats:
        return list(FORMAT_MAP.keys())

    # Collect unique resolutions and codecs
    resolutions = set()
    has_vp9 = False
    has_audio = False
    best_height = 0

    for f in formats:
        height = f.get("height")
        vcodec = f.get("vcodec") or ""
        acodec = f.get("acodec") or ""

        if height and vcodec != "none":
            resolutions.add(height)
            best_height = max(best_height, height)
        if "vp9" in vcodec.lower():
            has_vp9 = True
        if acodec and acodec != "none":
            has_audio = True

    # Build format list based on what's available
    available = []

    # Video formats - only show resolutions that exist
    if best_height >= 2160:
        available.append({
            "label": "mp4 4k",
            "format_spec": "bestvideo[height<=2160]+bestaudio/best",
            "merge_format": "mp4",
            "extra_args": [],
        })
    if best_height >= 1080 or 1080 in resolutions:
        available.append({
            "label": "mp4 1080p",
            "format_spec": "bestvideo[height<=1080]+bestaudio/best",
            "merge_format": "mp4",
            "extra_args": [],
        })
    if best_height >= 720 or 720 in resolutions:
        available.append({
            "label": "mp4 720p",
            "format_spec": "bestvideo[height<=720]+bestaudio/best",
            "merge_format": "mp4",
            "extra_args": [],
        })
    if best_height >= 480 or 480 in resolutions:
        available.append({
            "label": "mp4 480p",
            "format_spec": "bestvideo[height<=480]+bestaudio/best",
            "merge_format": "mp4",
            "extra_args": [],
        })

    # VP9 if available
    if has_vp9:
        available.append({
            "label": "webm vp9",
            "format_spec": "bestvideo[vcodec^=vp9]+bestaudio/best",
            "merge_format": "webm",
            "extra_args": [],
        })

    # Audio formats
    if has_audio:
        available.append({
            "label": "m4a audio",
            "format_spec": "bestaudio[ext=m4a]/bestaudio",
            "merge_format": "m4a",
            "extra_args": [],
        })
        available.append({
            "label": "mp3 192k",
            "format_spec": "bestaudio",
            "merge_format": None,
            "extra_args": ["-x", "--audio-format", "mp3", "--audio-quality", "192K"],
        })

    return available if available else list(FORMAT_MAP.keys())


def _is_live_stream(url: str) -> bool:
    ytdlp = get_binary_path("yt-dlp.exe")
    try:
        result = subprocess.run(
            [ytdlp, "--print", "is_live", url],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout.strip().lower() == "true"
    except Exception:
        return False


def detect_stream_type(url: str) -> str:
    return "live" if _is_live_stream(url) else "video"


def _build_command(
    url: str,
    output_dir: str,
    is_live: bool,
    format_key: str = DEFAULT_FORMAT,
    format_info: dict = None,
    suffix: str = "",
) -> list[str]:
    ytdlp = get_binary_path("yt-dlp.exe")
    output_template = f"{output_dir}/%(title)s{suffix}.%(ext)s"

    # Use format_info dict if provided, otherwise lookup by key
    if format_info:
        fmt = format_info.get("format_spec", "bestvideo+bestaudio/best")
        merge_fmt = format_info.get("merge_format")
        extra = format_info.get("extra_args", [])
    else:
        fmt, merge_fmt, extra = FORMAT_MAP.get(format_key, FORMAT_MAP[DEFAULT_FORMAT])

    cmd = [ytdlp, "-f", fmt, "--newline", "--no-overwrites"]
    if merge_fmt:
        cmd += ["--merge-output-format", merge_fmt]
        cmd += ["--postprocessor-args", "Merger+ffmpeg:-c:a aac -b:a 192k"]
    cmd += extra
    cmd += ["-o", output_template]

    if is_live:
        cmd += ["--live-from-start", "--wait-for-video", "30"]

    cmd.append(url)
    return cmd


_ALREADY_DL_RE = re.compile(r'\[download\] (.+) has already been downloaded')


class DownloadJob:
    def __init__(
        self,
        job_id: str,
        url: str,
        output_dir: str,
        is_live: bool,
        on_status: Callable[[str, str], None],
        format_key: str = DEFAULT_FORMAT,
        format_info: dict = None,
        clip_start: Optional[str] = None,
        clip_end: Optional[str] = None,
        end_time: Optional[str] = None,
        duration_minutes: Optional[int] = None,
        auto_stop: bool = True,
    ):
        self.job_id = job_id
        self.url = url
        self.output_dir = output_dir
        self.is_live = is_live
        self.on_status = on_status
        self.format_key = format_key
        self.format_info = format_info
        self.clip_start = clip_start
        self.clip_end = clip_end
        self.end_time = end_time
        self.duration_minutes = duration_minutes
        self.auto_stop = auto_stop
        self.process: subprocess.Popen | None = None
        self.cancelled = False
        self._thread: threading.Thread | None = None
        self._stop_timer: threading.Timer | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._schedule_stop_timer()

    def _schedule_stop_timer(self):
        if self.duration_minutes and self.duration_minutes > 0:
            delay = self.duration_minutes * 60
            self._stop_timer = threading.Timer(delay, self._timed_stop)
            self._stop_timer.daemon = True
            self._stop_timer.start()
        elif self.end_time:
            from datetime import datetime
            try:
                end_dt = datetime.fromisoformat(self.end_time)
                now = datetime.now()
                delay = (end_dt - now).total_seconds()
                if delay > 0:
                    self._stop_timer = threading.Timer(delay, self._timed_stop)
                    self._stop_timer.daemon = True
                    self._stop_timer.start()
            except Exception:
                pass

    def _timed_stop(self):
        if not self.cancelled and self.process and self.process.poll() is None:
            self.on_status(self.job_id, "Stopping (end time reached)")
            self.process.terminate()

    def cancel(self):
        self.cancelled = True
        if self._stop_timer:
            self._stop_timer.cancel()
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def _run(self):
        for attempt in range(1, 12):
            suffix = f" ({attempt})" if attempt > 1 else ""
            cmd = _build_command(
                self.url, self.output_dir, self.is_live,
                self.format_key, self.format_info, suffix
            )
            downloaded_file = None
            conflict = False
            try:
                self.process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                )
                self.on_status(self.job_id, "Recording" if self.is_live else "Downloading")
                buf = ""
                while True:
                    chunk = self.process.stdout.read(256)
                    if not chunk:
                        break
                    buf += chunk
                    parts = re.split(r"[\r\n]", buf)
                    buf = parts[-1]
                    for line in parts[:-1]:
                        line = line.strip()
                        if line:
                            self.on_status(self.job_id, line)
                            path = _parse_dest(line)
                            if path:
                                downloaded_file = path
                            if _ALREADY_DL_RE.search(line):
                                conflict = True
                    if self.cancelled:
                        break
                self.process.wait()
            except Exception as exc:
                self.on_status(self.job_id, f"Error: {exc}")
                return

            if self.cancelled:
                if self._stop_timer:
                    self._stop_timer.cancel()
                self.on_status(self.job_id, "Cancelled")
                return

            if conflict:
                continue

            if self._stop_timer:
                self._stop_timer.cancel()

            if self.process.returncode == 0:
                if (self.clip_start and self.clip_end
                        and downloaded_file and os.path.isfile(downloaded_file)):
                    self._trim(downloaded_file)
                else:
                    self.on_status(self.job_id, "Done")
            else:
                self.on_status(self.job_id, f"Error (exit {self.process.returncode})")
            return

        self.on_status(self.job_id, "Error: too many duplicate filenames")

    def _trim(self, source: str):
        self.on_status(self.job_id, "Trimming…")
        base, ext = os.path.splitext(source)
        s_label = self.clip_start.replace(":", "-")
        e_label = self.clip_end.replace(":", "-")
        output = f"{base} [{s_label}–{e_label}]{ext}"
        ffmpeg = get_binary_path("ffmpeg.exe")
        cmd = [
            ffmpeg, "-y",
            "-i", source,
            "-ss", self.clip_start,
            "-to", self.clip_end,
            "-c", "copy",
            output,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if r.returncode == 0 and os.path.isfile(output):
                os.remove(source)
                self.on_status(self.job_id, "Done")
            else:
                self.on_status(self.job_id, f"Trim error: {r.stderr.strip()[-120:]}")
        except Exception as exc:
            self.on_status(self.job_id, f"Error trimming: {exc}")


def _parse_dest(line: str) -> Optional[str]:
    """Extract output file path from yt-dlp progress lines."""
    for pattern in (
        r'\[download\] Destination: (.+)',
        r'\[Merger\] Merging formats into "(.+)"',
        r'\[VideoConvertor\] Converting video from \S+ to \S+; Destination: (.+)',
        r'\[ExtractAudio\] Destination: (.+)',
    ):
        m = re.search(pattern, line)
        if m:
            return m.group(1).strip()
    return None
