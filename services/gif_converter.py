import os
import re
import subprocess
import sys
import tempfile
import threading
from typing import Callable, Optional
from utils.binaries import get_binary_path


def _quality_to_bayer_scale(quality: int) -> int:
    return round((quality - 1) / 9 * 5)


def _parse_secs(t: str) -> float:
    parts = [float(p) for p in t.strip().split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]


def convert_to_gif(
    input_path: str,
    start: str,
    end: str,
    fps: int,
    width: int,
    quality: int,
    on_progress: Callable[[str], None],
):
    thread = threading.Thread(
        target=_run_conversion,
        args=(input_path, start, end, fps, width, quality, on_progress),
        daemon=True,
    )
    thread.start()


def download_and_convert_to_gif(
    url: str,
    start: str,
    end: str,
    fps: int,
    width: int,
    quality: int,
    output_dir: str,
    on_progress: Callable[[str], None],
):
    thread = threading.Thread(
        target=_run_download_and_conversion,
        args=(url, start, end, fps, width, quality, output_dir, on_progress),
        daemon=True,
    )
    thread.start()


def _parse_dl_dest(line: str) -> Optional[str]:
    for pattern in (
        r'\[download\] Destination: (.+)',
        r'\[Merger\] Merging formats into "(.+)"',
        r'\[VideoConvertor\] Converting video from \S+ to \S+; Destination: (.+)',
    ):
        m = re.search(pattern, line)
        if m:
            return m.group(1).strip()
    return None


def _run_download_and_conversion(url, start, end, fps, width, quality, output_dir, on_progress):
    ytdlp = get_binary_path("yt-dlp.exe")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        on_progress("Downloading video…")
        dl_template = os.path.join(tmp, "%(title).80s.%(ext)s")
        # Request resolution close to target GIF width, prefer h264 over av1 for faster decoding
        # Use width as max_height - for 16:9 this gives us more source width than needed
        max_height = max(width, 360)
        fmt = (
            f"bestvideo[height<={max_height}][vcodec^=avc]+bestaudio/"  # h264 preferred
            f"bestvideo[height<={max_height}]+bestaudio/"               # fallback to any codec
            f"best[height<={max_height}]/best"
        )
        cmd = [
            ytdlp,
            "-f", fmt,
            "--merge-output-format", "mp4",
            "--newline", "-o", dl_template, url,
        ]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        downloaded_file = None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                on_progress(line[:120])
                path = _parse_dl_dest(line)
                if path:
                    downloaded_file = path
        proc.wait()
        if proc.returncode != 0:
            on_progress(f"Download error (exit {proc.returncode})")
            return
        if not downloaded_file or not os.path.isfile(downloaded_file):
            candidates = [
                os.path.join(tmp, f) for f in os.listdir(tmp)
                if not f.endswith(".part") and os.path.isfile(os.path.join(tmp, f))
            ]
            if candidates:
                downloaded_file = max(candidates, key=os.path.getsize)
        if not downloaded_file or not os.path.isfile(downloaded_file):
            on_progress("Error: downloaded file not found")
            return
        base = os.path.splitext(os.path.basename(downloaded_file))[0]
        output_path = os.path.join(output_dir, f"{base}.gif")
        _run_conversion(downloaded_file, start, end, fps, width, quality, on_progress,
                        output_path=output_path)


def _run_conversion(input_path, start, end, fps, width, quality, on_progress, output_path=None):
    ffmpeg = get_binary_path("ffmpeg.exe")
    bayer_scale = _quality_to_bayer_scale(quality)
    if output_path is None:
        out_dir = os.path.dirname(input_path)
        base = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(out_dir, f"{base}.gif")

    duration = _parse_secs(end) - _parse_secs(start)
    if duration <= 0:
        on_progress("Error: end time must be after start time")
        return

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        palette_path = os.path.join(tmp, "palette.png")

        # Pass 1 — generate palette
        # -ss before -i = fast input seek; -t is output duration (more portable than -to as input option)
        pass1 = [
            ffmpeg, "-y",
            "-ss", start,
            "-i", input_path,
            "-t", str(duration),
            "-an",  # skip audio
            "-threads", "0",  # use all CPU cores
            "-vf", f"fps={fps},scale={width}:-1:flags=bilinear,palettegen=stats_mode=diff",
            palette_path,
        ]
        on_progress("Pass 1: generating palette…")
        ok = _run_ffmpeg(ffmpeg, pass1, on_progress)
        if not ok:
            return

        # Pass 2 — render GIF
        # -filter_complex required when referencing multiple input streams ([0:v] + [1:v])
        pass2 = [
            ffmpeg, "-y",
            "-ss", start,
            "-i", input_path,
            "-i", palette_path,
            "-t", str(duration),
            "-an",
            "-threads", "0",
            "-filter_complex", (
                f"[0:v]fps={fps},scale={width}:-1:flags=bilinear[x];"
                f"[x][1:v]paletteuse=dither=bayer:bayer_scale={bayer_scale}"
            ),
            output_path,
        ]
        on_progress("Pass 2: rendering GIF…")
        ok = _run_ffmpeg(ffmpeg, pass2, on_progress)
        if ok:
            on_progress(f"Done → {output_path}")


def _run_ffmpeg(ffmpeg: str, cmd: list[str], on_progress: Callable[[str], None]) -> bool:
    # -hwaccel auto lets ffmpeg pick the best available GPU decoder (NVDEC, QSV, D3D11VA, etc.)
    cmd = cmd[:1] + ["-nostdin", "-hwaccel", "auto", "-stats_period", "0.5"] + cmd[1:]
    print(f"[gif] {' '.join(cmd)}", file=sys.stderr, flush=True)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        error_lines: list[str] = []

        def read_stdout():
            proc.stdout.read()

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stdout_thread.start()

        # Read stderr byte-by-byte to handle \r progress updates
        buf = b""
        last_progress = ""
        while True:
            chunk = proc.stderr.read(256)
            if not chunk:
                break
            buf += chunk
            # Split on \r or \n to get progress lines
            while b'\r' in buf or b'\n' in buf:
                idx_r = buf.find(b'\r')
                idx_n = buf.find(b'\n')
                if idx_r == -1:
                    idx = idx_n
                elif idx_n == -1:
                    idx = idx_r
                else:
                    idx = min(idx_r, idx_n)
                line = buf[:idx].decode("utf-8", errors="replace").strip()
                buf = buf[idx + 1:]
                if line:
                    print(f"  {line}", file=sys.stderr, flush=True)
                    # Parse frame progress
                    m = re.search(r'frame=\s*(\d+)', line)
                    if m:
                        progress = f"Processing frame {m.group(1)}..."
                        if progress != last_progress:
                            on_progress(progress)
                            last_progress = progress
                    if any(kw in line.lower() for kw in
                           ("error", "invalid", "no such", "cannot", "failed", "unable")):
                        error_lines.append(line)

        proc.wait()
        stdout_thread.join(timeout=2)

        if proc.returncode != 0:
            detail = error_lines[-1] if error_lines else f"exit {proc.returncode}"
            on_progress(f"ffmpeg error: {detail}")
            return False
        return True
    except Exception as exc:
        on_progress(f"Error: {exc}")
        return False
