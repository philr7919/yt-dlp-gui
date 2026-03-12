# yt-dlp GUI

A modern, portable graphical frontend for [yt-dlp](https://github.com/yt-dlp/yt-dlp).  
Supports **Windows**, **macOS**, and **Linux** — **no pre-installed Python required**.

---

## Zero-Dependency Setup

On first launch, the launchers:

1. Check if **system Python 3.8+** with tkinter is already installed → use it (fastest)
2. If not found → **automatically download a standalone embedded Python** for your OS/arch
3. Then download the latest **yt-dlp binary**
4. Launch the GUI — every subsequent launch is instant

You only need an **internet connection** on first run.

| OS      | Embedded Python source                          | Size   |
|---------|-------------------------------------------------|--------|
| Windows | python.org embeddable zip (no installer needed) | ~10 MB |
| macOS   | python-build-standalone (Intel + Apple Silicon) | ~30 MB |
| Linux   | python-build-standalone (glibc or musl)         | ~30 MB |

---

## How to Launch

### Windows
Double-click **`launch.bat`**

No Python? No problem — it uses PowerShell (built into Windows) to download  
the embeddable Python zip automatically, then launches the GUI.

### macOS
```bash
chmod +x launch.command
```
Then double-click **`launch.command`** in Finder.  
*(If blocked: right-click → Open → Open)*

### Linux
```bash
chmod +x launch.sh
./launch.sh
```

---

## Features

- **Auto-downloads yt-dlp** on first launch for your OS
- **Fetch & browse all available formats** — every quality, codec, bitrate, file size
- **Download video or audio only** with format selection  
- **Subtitles** — auto-download and embed English subtitles
- **Thumbnails** — download and embed cover art
- **Download queue** — add multiple URLs, download in sequence
- **Save location picker** — choose exactly where files go
- **Live progress bars** per queue item + full log tab
- **Settings** — persistent preferences saved to `config.json`
- **Dark/neon theme**

---

## Usage

1. Run your OS launcher → Python + yt-dlp bootstrap on first run
2. Paste a URL → click **Fetch Formats**
3. Select a format from the table
4. Pick your **save location**
5. Click **⬇ Download Selected** — or **+ Queue Selected** for batch
6. Monitor progress in the queue panel or the **Log** tab

### Batch / Queue Mode
- **"+ Add to Queue"** — adds URL with best-quality auto-selection
- **"+ Queue Selected"** — queues a specific format from the format table
- **"▶ Start Queue"** — downloads all pending items in sequence
- **"✕ Clear Done"** — removes completed items

---

## File Structure

```
yt-dlp-gui/
├── gui.py                ← Main GUI application
├── bootstrap.py          ← Shared Python bootstrap helper
├── launch.bat            ← Windows launcher (no Python needed)
├── launch.sh             ← Linux launcher
├── launch.command        ← macOS launcher (Finder double-clickable)
├── config.json           ← Auto-created (your settings)
├── README.md
├── bin/
│   └── yt-dlp[.exe]      ← Auto-downloaded on first run
└── python_embedded/      ← Auto-created if no system Python found
    └── python/           ← Standalone Python lives here
```

---

## Updating yt-dlp

Click **"⟳ Update yt-dlp"** in the app header, or go to **Settings → Force Re-download**.

To update embedded Python: delete the `python_embedded/` folder and relaunch.

---

## Supported Sites

YouTube, Vimeo, Twitter/X, TikTok, Instagram, Twitch, SoundCloud, Reddit, and 1000+ more.  
Full list: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md

---

## Troubleshooting

**Download fails with ffmpeg error**  
Some formats (best video + best audio merged) require ffmpeg:
- Linux: `sudo apt install ffmpeg`
- macOS: `brew install ffmpeg`
- Windows: [ffmpeg.org/download.html](https://ffmpeg.org/download.html)

**macOS Gatekeeper blocks launch.command**  
Right-click → Open → Open (only needed once)

**Embedded Python download fails**  
Check your internet connection. The launchers pull from:
- python.org (Windows)
- github.com/indygreg/python-build-standalone (macOS/Linux)

---

## License

GUI: MIT License  
yt-dlp: Unlicense — https://github.com/yt-dlp/yt-dlp  
python-build-standalone: PSF License
