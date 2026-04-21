# YT Recorder

A Windows desktop app for downloading YouTube videos and live streams with scheduling support.

**Version:** 0.7.2

## Features

- **Download videos** — Multiple formats (MP4, WebM, MKV, audio-only) with video metadata preview
- **Record live streams** — Captures from start with automatic retry
- **Schedule downloads** — Queue jobs for specific dates and times
- **GIF converter** — Convert local videos or YouTube URLs to GIFs with customizable FPS, width, and trim points
- **Clip trimming** — Extract segments with start/end timestamps
- **Settings** — Configurable output directories, filename templates, quality presets, concurrent downloads, and desktop notifications

## Requirements

- Windows 10/11
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [ffmpeg](https://ffmpeg.org/) (setup wizard downloads these automatically)

## Installation

```bash
pip install -r requirements.txt
python main.py
```

Or build a standalone executable:

```bash
pyinstaller build.spec
```

## Dependencies

- customtkinter — Modern dark UI
- apscheduler — Scheduled download jobs
- Pillow — Thumbnail and GIF preview
- pyinstaller — Standalone .exe builds

## Supported Formats

| Format     | Description              |
|------------|--------------------------|
| mp4 4k     | Up to 2160p              |
| mp4 1080p  | H.264 video + AAC audio  |
| mp4 720p   | H.264 video + AAC audio  |
| webm vp9   | VP9 video + Opus audio   |
| mkv 4k     | Up to 2160p              |
| m4a audio  | Audio only (M4A)         |
| mp3 192k   | Audio only (MP3)         |

## License

MIT
