# YT Recorder

A Windows desktop app for downloading YouTube videos and live streams with scheduling support.

## Features

- **Download videos** — Multiple formats (MP4, WebM, MKV, audio-only)
- **Record live streams** — Captures from start with automatic retry
- **Schedule downloads** — Queue jobs for specific times
- **GIF converter** — Convert video clips to GIFs using ffmpeg
- **Clip trimming** — Extract segments with start/end timestamps

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

## Supported Formats

| Format     | Description              |
|------------|--------------------------|
| mp4 1080p  | H.264 video + AAC audio  |
| mp4 720p   | H.264 video + AAC audio  |
| webm vp9   | VP9 video + Opus audio   |
| mkv 4k     | Up to 2160p              |
| m4a audio  | Audio only (M4A)         |
| mp3 192k   | Audio only (MP3)         |

## License

MIT
