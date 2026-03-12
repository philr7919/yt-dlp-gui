#!/usr/bin/env python3
"""
yt-dlp GUI - A modern, portable frontend for yt-dlp
Supports Windows, macOS, and Linux
"""

import os
import sys
import json
import platform
import subprocess
import threading
import time
import re
import stat
import queue
from pathlib import Path
from urllib.request import urlretrieve, urlopen
from urllib.error import URLError
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont

# ─── Constants ────────────────────────────────────────────────────────────────

APP_NAME    = "yt-dlp GUI"
APP_VERSION = "1.0.0"
GITHUB_API  = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"

BIN_DIR   = Path(__file__).parent / "bin"
CONF_FILE = Path(__file__).parent / "config.json"

SYSTEM = platform.system()  # 'Windows', 'Darwin', 'Linux'

if SYSTEM == "Windows":
    BIN_NAME = "yt-dlp.exe"
elif SYSTEM == "Darwin":
    BIN_NAME = "yt-dlp_macos"
else:
    BIN_NAME = "yt-dlp_linux"

BIN_PATH = BIN_DIR / BIN_NAME

# ffmpeg — bundled alongside yt-dlp in bin/
# We use yt-dlp/FFmpeg-Builds which provides static single-file binaries.
FFMPEG_BUILDS_API = "https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest"

if SYSTEM == "Windows":
    FFMPEG_NAME  = "ffmpeg.exe"
    FFPROBE_NAME = "ffprobe.exe"
else:
    FFMPEG_NAME  = "ffmpeg"
    FFPROBE_NAME = "ffprobe"

FFMPEG_PATH  = BIN_DIR / FFMPEG_NAME
FFPROBE_PATH = BIN_DIR / FFPROBE_NAME

# ─── Colour palette ───────────────────────────────────────────────────────────
C = {
    "bg":        "#0d0d0f",
    "bg2":       "#14141a",
    "bg3":       "#1c1c26",
    "panel":     "#181820",
    "border":    "#2a2a3a",
    "accent":    "#00f5c4",
    "accent2":   "#7b5ea7",
    "accent3":   "#e040fb",
    "text":      "#e8e8f0",
    "text_dim":  "#6e6e8a",
    "text_mid":  "#a0a0b8",
    "success":   "#00e676",
    "warning":   "#ffea00",
    "error":     "#ff1744",
    "progress":  "#00f5c4",
}

# ─── Config helpers ────────────────────────────────────────────────────────────

def load_config():
    defaults = {
        "save_dir":      str(Path.home() / "Downloads"),
        "format":        "bestvideo+bestaudio/best",
        "subtitles":     True,
        "thumbnail":     True,
        "embed_subs":    True,
        "embed_thumb":   True,
        "preferred_ext": "mp4",
        "audio_only":    False,
        "audio_format":  "mp3",
        "ytdlp_version": None,
    }
    if CONF_FILE.exists():
        try:
            with open(CONF_FILE) as f:
                saved = json.load(f)
            defaults.update(saved)
        except Exception:
            pass
    return defaults

def save_config(cfg):
    try:
        with open(CONF_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

# ─── yt-dlp binary management ─────────────────────────────────────────────────

def get_ytdlp_asset_name():
    if SYSTEM == "Windows":
        return "yt-dlp.exe"
    elif SYSTEM == "Darwin":
        return "yt-dlp_macos"
    else:
        return "yt-dlp_linux"

def fetch_latest_release_info():
    try:
        with urlopen(GITHUB_API, timeout=15) as r:
            data = json.loads(r.read().decode())
        tag     = data["tag_name"]
        assets  = {a["name"]: a["browser_download_url"] for a in data["assets"]}
        return tag, assets
    except Exception as e:
        return None, {}

def download_ytdlp(progress_cb=None):
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    tag, assets = fetch_latest_release_info()
    if not tag:
        return False, "Could not reach GitHub API"

    asset_name = get_ytdlp_asset_name()
    url = assets.get(asset_name)
    if not url:
        return False, f"Asset '{asset_name}' not found in release {tag}"

    dest = BIN_DIR / asset_name

    def _reporthook(block, block_size, total):
        if progress_cb and total > 0:
            progress_cb(block * block_size / total)

    try:
        urlretrieve(url, dest, _reporthook)
    except Exception as e:
        return False, str(e)

    # Make executable on unix
    if SYSTEM in ("Darwin", "Linux"):
        dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return True, tag

def download_ffmpeg():
    """
    Download static ffmpeg + ffprobe binaries.
    - Windows : yt-dlp/FFmpeg-Builds via GitHub API (asset name pattern matched
                carefully) with gyan.dev essentials zip as fallback
    - macOS   : evermeet.cx static builds
    - Linux   : yt-dlp/FFmpeg-Builds via GitHub API
    Returns (ok: bool, message: str).
    """
    if SYSTEM == "Darwin":
        return _download_ffmpeg_macos()
    if SYSTEM == "Windows":
        return _download_ffmpeg_windows()
    return _download_ffmpeg_linux()


def _download_ffmpeg_windows():
    """Download ffmpeg for Windows. Tries two sources in order."""
    import zipfile, tempfile

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    machine = platform.machine().lower()
    is_arm  = machine in ("arm64", "aarch64")

    # ── Source 1: yt-dlp/FFmpeg-Builds GitHub API ─────────────────────────────
    # Real asset names look like:
    #   ffmpeg-n7.1-latest-win64-lgpl-7.1.zip
    #   ffmpeg-n7.1-latest-win64-lgpl-shared-7.1.zip  <- skip shared
    # We want: win64 (or arm64), lgpl, .zip, NOT shared
    try:
        with urlopen(FFMPEG_BUILDS_API, timeout=20) as r:
            data = json.loads(r.read().decode())
        assets = data.get("assets", [])
        arch_tag = "arm64" if is_arm else "win64"
        chosen = None
        for a in assets:
            n = a["name"].lower()
            if (arch_tag in n and n.endswith(".zip")
                    and "lgpl" in n and "shared" not in n):
                chosen = a
                break
        if chosen:
            ok, msg = _extract_ffmpeg_zip_url(
                chosen["browser_download_url"], chosen["name"])
            if ok:
                return True, "ok"
    except Exception as e:
        pass  # fall through to source 2

    # ── Source 2: gyan.dev essentials build (stable direct URL) ───────────────
    # This URL is stable and maintained specifically for scripts/tools.
    # Only available for x86_64; skip for ARM.
    if not is_arm:
        try:
            url  = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            ok, msg = _extract_ffmpeg_zip_url(url, "ffmpeg-release-essentials.zip")
            if ok:
                return True, "ok"
        except Exception as e:
            return False, f"Both ffmpeg sources failed. Last error: {e}"

    return False, (
        "Could not download ffmpeg automatically for this platform. "
        "Please download ffmpeg manually from https://ffmpeg.org/download.html "
        "and place ffmpeg.exe and ffprobe.exe in the 'bin' folder."
    )


def _extract_ffmpeg_zip_url(url: str, filename: str):
    """Download a zip from url and extract ffmpeg.exe / ffprobe.exe into BIN_DIR."""
    import zipfile, tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / filename
        urlretrieve(url, tmp_path)
        with zipfile.ZipFile(tmp_path) as zf:
            found = []
            for member in zf.namelist():
                fname = Path(member).name.lower()
                if fname in ("ffmpeg.exe", "ffprobe.exe"):
                    dest = BIN_DIR / Path(member).name
                    dest.write_bytes(zf.read(member))
                    found.append(fname)
            if "ffmpeg.exe" not in found:
                return False, "ffmpeg.exe not found in zip"
    return True, "ok"


def _download_ffmpeg_linux():
    """Download ffmpeg for Linux via yt-dlp/FFmpeg-Builds."""
    import tarfile, tempfile

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    machine = platform.machine().lower()
    is_arm  = machine in ("arm64", "aarch64")
    arch_tag = "aarch64" if is_arm else "linux64"

    try:
        with urlopen(FFMPEG_BUILDS_API, timeout=20) as r:
            data = json.loads(r.read().decode())
        assets = data.get("assets", [])
        chosen = None
        for a in assets:
            n = a["name"].lower()
            if (arch_tag in n and n.endswith(".tar.xz")
                    and "lgpl" in n and "shared" not in n):
                chosen = a
                break
        if not chosen:
            return False, f"No Linux ffmpeg asset found for arch={arch_tag}"

        url  = chosen["browser_download_url"]
        name = chosen["name"]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / name
            urlretrieve(url, tmp_path)
            with tarfile.open(tmp_path, "r:xz") as tf:
                for member in tf.getmembers():
                    fname = Path(member.name).name
                    if fname in (FFMPEG_NAME, FFPROBE_NAME):
                        extracted = tf.extractfile(member)
                        if extracted:
                            dest = BIN_DIR / fname
                            dest.write_bytes(extracted.read())
                            dest.chmod(dest.stat().st_mode | 0o111)
    except Exception as e:
        return False, str(e)

    if not FFMPEG_PATH.exists():
        return False, "ffmpeg binary not found after extraction"
    return True, "ok"


def _download_ffmpeg_macos():
    """Download ffmpeg static build for macOS from evermeet.cx."""
    import zipfile, tempfile

    machine  = platform.machine().lower()
    is_arm   = machine in ("arm64", "aarch64")
    arch_tag = "arm64" if is_arm else "x86_64"

    # evermeet.cx provides separate ffmpeg and ffprobe zip downloads
    urls = {
        FFMPEG_NAME:  f"https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
        FFPROBE_NAME: f"https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip",
    }

    for binary_name, url in urls.items():
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_zip = Path(tmp) / f"{binary_name}.zip"
                # evermeet.cx returns a redirect — urlretrieve follows it
                urlretrieve(url, tmp_zip)
                with zipfile.ZipFile(tmp_zip) as zf:
                    for member in zf.namelist():
                        if Path(member).name == binary_name:
                            dest = BIN_DIR / binary_name
                            dest.write_bytes(zf.read(member))
                            dest.chmod(dest.stat().st_mode | 0o111)
                            break
        except Exception as e:
            return False, f"Failed to download {binary_name}: {e}"

    if not FFMPEG_PATH.exists():
        return False, "ffmpeg binary not found after macOS download"
    return True, "ok"


def ytdlp_needs_update(current_tag):
    """Returns (needs_update: bool, latest_tag: str)"""
    tag, _ = fetch_latest_release_info()
    if tag and tag != current_tag:
        return True, tag
    return False, tag

# ─── Format fetching ──────────────────────────────────────────────────────────

def fetch_formats(url):
    """Run yt-dlp -J to get JSON metadata; returns (info_dict, error_str)"""
    try:
        result = subprocess.run(
            [str(BIN_PATH), "-J", "--no-playlist", url],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return None, result.stderr.strip() or "Unknown error"
        info = json.loads(result.stdout)
        return info, None
    except subprocess.TimeoutExpired:
        return None, "Timed out fetching formats (60s)"
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"
    except Exception as e:
        return None, str(e)

def build_format_rows(info):
    """Returns a list of dicts describing available formats, best first."""
    formats = info.get("formats", [])
    rows = []
    for f in formats:
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        has_v  = vcodec and vcodec != "none"
        has_a  = acodec and acodec != "none"

        kind = "video+audio" if (has_v and has_a) else ("video" if has_v else "audio")

        resolution = f.get("resolution") or (
            f"{f['width']}x{f['height']}" if f.get("width") and f.get("height") else
            f"{f.get('height', '?')}p" if f.get("height") else "N/A"
        )

        fps    = f"{f['fps']:.0f}fps" if f.get("fps") else ""
        size   = f.get("filesize") or f.get("filesize_approx")
        size_s = f"{size/1_048_576:.1f} MB" if size else "?"
        tbr    = f"{f['tbr']:.0f}k" if f.get("tbr") else ""
        ext    = f.get("ext", "?")
        fmt_id = f.get("format_id", "?")
        note   = f.get("format_note", "")

        rows.append({
            "id":         fmt_id,
            "ext":        ext,
            "kind":       kind,
            "resolution": resolution,
            "fps":        fps,
            "size":       size_s,
            "tbr":        tbr,
            "vcodec":     vcodec if has_v else "-",
            "acodec":     acodec if has_a else "-",
            "note":       note,
        })

    # Sort: video+audio first, then by tbr desc
    def sort_key(r):
        kind_order = {"video+audio": 0, "video": 1, "audio": 2}
        tbr_val = float(r["tbr"].rstrip("k")) if r["tbr"] else 0
        return (kind_order.get(r["kind"], 9), -tbr_val)

    rows.sort(key=sort_key)
    return rows

# ─── Download execution ───────────────────────────────────────────────────────

def build_cmd(url, save_dir, fmt_id, cfg, audio_only=False):
    cmd = [str(BIN_PATH)]

    # Tell yt-dlp exactly where our bundled ffmpeg lives so it never
    # falls back to a system ffmpeg (or fails with "ffmpeg not found").
    if FFMPEG_PATH.exists():
        cmd += ["--ffmpeg-location", str(BIN_DIR)]

    if audio_only:
        cmd += ["-x", "--audio-format", cfg.get("audio_format", "mp3")]
    else:
        if fmt_id and fmt_id not in ("best", "bestvideo+bestaudio/best"):
            # If user picked a video-only format, merge with best audio
            cmd += ["-f", f"{fmt_id}+bestaudio/best/{fmt_id}"]
        else:
            cmd += ["-f", "bestvideo+bestaudio/best"]
        cmd += ["--merge-output-format", cfg.get("preferred_ext", "mp4")]

    if cfg.get("subtitles"):
        cmd += ["--write-subs", "--write-auto-subs", "--sub-langs", "en,en-orig"]
    if cfg.get("embed_subs") and not audio_only:
        cmd += ["--embed-subs"]
    if cfg.get("thumbnail"):
        cmd += ["--write-thumbnail"]
    if cfg.get("embed_thumb"):
        cmd += ["--embed-thumbnail"]

    cmd += [
        "--no-playlist",
        "--progress",
        "--newline",
        "-o", str(Path(save_dir) / "%(title)s.%(ext)s"),
        url
    ]
    return cmd

# ─── Main Application ─────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg       = load_config()
        self.queue_items = []          # list of QueueItem widgets
        self.dl_thread   = None
        self.dl_queue    = queue.Queue()
        self.log_queue   = queue.Queue()

        self._setup_window()
        self._setup_fonts()
        self._setup_styles()
        self._build_ui()
        self._check_ytdlp_on_start()
        self._poll_log()

    # ── Window setup ─────────────────────────────────────────────────────────

    def _setup_window(self):
        self.title(APP_NAME)
        self.configure(bg=C["bg"])
        self.minsize(900, 640)
        w, h = 1060, 740
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_fonts(self):
        avail = list(tkfont.families())
        mono_candidates  = ["JetBrains Mono", "Fira Code", "Cascadia Code",
                            "Consolas", "Source Code Pro", "Courier New", "monospace"]
        title_candidates = ["Exo 2", "Rajdhani", "Orbitron", "Segoe UI",
                            "Helvetica Neue", "Arial", "sans-serif"]
        body_candidates  = ["Inter", "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"]

        def pick(candidates):
            for c in candidates:
                if c in avail:
                    return c
            return candidates[-1]

        mono  = pick(mono_candidates)
        title = pick(title_candidates)
        body  = pick(body_candidates)

        self.font_title   = tkfont.Font(family=title, size=18, weight="bold")
        self.font_heading = tkfont.Font(family=body,  size=11, weight="bold")
        self.font_body    = tkfont.Font(family=body,  size=10)
        self.font_small   = tkfont.Font(family=body,  size=9)
        self.font_mono    = tkfont.Font(family=mono,  size=9)
        self.font_mono_sm = tkfont.Font(family=mono,  size=8)

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".",
            background=C["bg"], foreground=C["text"],
            fieldbackground=C["bg3"], troughcolor=C["bg2"],
            bordercolor=C["border"], darkcolor=C["bg2"],
            lightcolor=C["bg3"], selectbackground=C["accent2"],
            selectforeground=C["text"], font=self.font_body)

        style.configure("TFrame", background=C["bg"])
        style.configure("Panel.TFrame", background=C["panel"])

        style.configure("TLabel",
            background=C["bg"], foreground=C["text"])
        style.configure("Panel.TLabel",
            background=C["panel"], foreground=C["text"])
        style.configure("Dim.TLabel",
            background=C["panel"], foreground=C["text_dim"])

        style.configure("Accent.TButton",
            background=C["accent"], foreground=C["bg"],
            borderwidth=0, focusthickness=0, font=self.font_heading)
        style.map("Accent.TButton",
            background=[("active", "#00ddb0"), ("disabled", C["border"])],
            foreground=[("disabled", C["text_dim"])])

        style.configure("Ghost.TButton",
            background=C["bg3"], foreground=C["text"],
            borderwidth=1, font=self.font_body)
        style.map("Ghost.TButton",
            background=[("active", C["border"])])

        style.configure("Treeview",
            background=C["bg2"], foreground=C["text"],
            fieldbackground=C["bg2"], rowheight=26,
            borderwidth=0, font=self.font_mono_sm)
        style.configure("Treeview.Heading",
            background=C["bg3"], foreground=C["accent"],
            borderwidth=0, font=self.font_small)
        style.map("Treeview",
            background=[("selected", C["accent2"])],
            foreground=[("selected", C["text"])])

        style.configure("green.Horizontal.TProgressbar",
            troughcolor=C["bg3"], background=C["accent"],
            borderwidth=0, thickness=6)

        style.configure("TNotebook",
            background=C["bg"], borderwidth=0)
        style.configure("TNotebook.Tab",
            background=C["bg2"], foreground=C["text_dim"],
            padding=[14, 6], font=self.font_body)
        style.map("TNotebook.Tab",
            background=[("selected", C["bg3"])],
            foreground=[("selected", C["accent"])])

        style.configure("TCheckbutton",
            background=C["panel"], foreground=C["text"],
            indicatorcolor=C["bg3"], selectcolor=C["accent"])
        style.map("TCheckbutton",
            background=[("active", C["panel"])])

        style.configure("TCombobox",
            fieldbackground=C["bg3"], background=C["bg3"],
            foreground=C["text"], arrowcolor=C["accent"],
            bordercolor=C["border"])

        style.configure("TScrollbar",
            background=C["bg2"], troughcolor=C["bg"],
            borderwidth=0, arrowcolor=C["text_dim"])

    # ── UI Building ───────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ─────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=C["bg2"], height=56)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="◈", bg=C["bg2"], fg=C["accent"],
                 font=("Arial", 22)).pack(side="left", padx=(18,6), pady=8)
        tk.Label(hdr, text=APP_NAME, bg=C["bg2"], fg=C["text"],
                 font=self.font_title).pack(side="left", pady=8)
        tk.Label(hdr, text=f"v{APP_VERSION}", bg=C["bg2"], fg=C["text_dim"],
                 font=self.font_small).pack(side="left", padx=6, pady=12)

        self.lbl_ytdlp_ver = tk.Label(hdr, text="yt-dlp: checking…",
            bg=C["bg2"], fg=C["text_dim"], font=self.font_small)
        self.lbl_ytdlp_ver.pack(side="right", padx=18)

        ttk.Button(hdr, text="⟳ Update yt-dlp", style="Ghost.TButton",
                   command=self._manual_update).pack(side="right", padx=4)

        # ── Main notebook ───────────────────────────────────────────────────
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=0, pady=0)

        self.tab_dl  = ttk.Frame(nb, style="TFrame")
        self.tab_cfg = ttk.Frame(nb, style="TFrame")
        self.tab_log = ttk.Frame(nb, style="TFrame")

        nb.add(self.tab_dl,  text="  ⬇  Download  ")
        nb.add(self.tab_cfg, text="  ⚙  Settings  ")
        nb.add(self.tab_log, text="  ⌨  Log  ")

        self._build_download_tab()
        self._build_settings_tab()
        self._build_log_tab()

        # ── Status bar ──────────────────────────────────────────────────────
        bar = tk.Frame(self, bg=C["bg2"], height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.lbl_status = tk.Label(bar, text="Ready.", bg=C["bg2"],
                                   fg=C["text_dim"], font=self.font_small)
        self.lbl_status.pack(side="left", padx=12)

    # ── Download tab ─────────────────────────────────────────────────────────

    def _build_download_tab(self):
        tab = self.tab_dl
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(2, weight=1)

        # URL + Fetch row
        url_frame = tk.Frame(tab, bg=C["panel"], pady=12, padx=14)
        url_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10,0))
        url_frame.columnconfigure(1, weight=1)

        tk.Label(url_frame, text="URL", bg=C["panel"], fg=C["text_dim"],
                 font=self.font_small).grid(row=0, column=0, sticky="w", padx=(0,8))

        self.entry_url = tk.Entry(url_frame, bg=C["bg3"], fg=C["text"],
                                  insertbackground=C["accent"], relief="flat",
                                  font=self.font_body, bd=6)
        self.entry_url.grid(row=0, column=1, sticky="ew", ipady=5)
        self.entry_url.bind("<Return>", lambda e: self._fetch_formats())

        self.btn_fetch = ttk.Button(url_frame, text="Fetch Formats",
                                    style="Accent.TButton", command=self._fetch_formats)
        self.btn_fetch.grid(row=0, column=2, padx=(8,0), ipadx=6)

        ttk.Button(url_frame, text="+ Add to Queue", style="Ghost.TButton",
                   command=self._add_to_queue_from_url).grid(row=0, column=3, padx=(6,0))

        # Save dir row
        dir_frame = tk.Frame(tab, bg=C["panel"], pady=8, padx=14)
        dir_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(2,0))
        dir_frame.columnconfigure(1, weight=1)

        tk.Label(dir_frame, text="Save to", bg=C["panel"], fg=C["text_dim"],
                 font=self.font_small).grid(row=0, column=0, sticky="w", padx=(0,8))

        self.var_savedir = tk.StringVar(value=self.cfg["save_dir"])
        tk.Entry(dir_frame, textvariable=self.var_savedir, bg=C["bg3"],
                 fg=C["text"], insertbackground=C["accent"], relief="flat",
                 font=self.font_body, bd=6).grid(row=0, column=1, sticky="ew", ipady=4)

        ttk.Button(dir_frame, text="Browse…", style="Ghost.TButton",
                   command=self._browse_dir).grid(row=0, column=2, padx=(8,0))

        # ── Formats + queue pane ────────────────────────────────────────────
        paned = tk.PanedWindow(tab, orient="horizontal", bg=C["bg"],
                                sashwidth=4, sashrelief="flat")
        paned.grid(row=2, column=0, sticky="nsew", padx=10, pady=8)

        # Left: format selector
        left = tk.Frame(paned, bg=C["panel"])
        self._build_format_panel(left)
        paned.add(left, minsize=420)

        # Right: download queue
        right = tk.Frame(paned, bg=C["panel"])
        self._build_queue_panel(right)
        paned.add(right, minsize=280)

    def _build_format_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        hdr = tk.Frame(parent, bg=C["bg3"])
        hdr.grid(row=0, column=0, sticky="ew")

        tk.Label(hdr, text="  Available Formats", bg=C["bg3"], fg=C["accent"],
                 font=self.font_heading, pady=7).pack(side="left")

        self.lbl_title = tk.Label(hdr, text="", bg=C["bg3"], fg=C["text_dim"],
                                  font=self.font_small)
        self.lbl_title.pack(side="right", padx=10)

        # Thumbnail label
        self.lbl_thumb_info = tk.Label(parent, text="Paste a URL and click Fetch Formats",
            bg=C["panel"], fg=C["text_dim"], font=self.font_small, pady=4)
        self.lbl_thumb_info.grid(row=1, column=0, sticky="ew", padx=8)

        # Treeview
        cols = ("id","ext","kind","resolution","fps","size","tbr","note")
        self.tree = ttk.Treeview(parent, columns=cols, show="headings",
                                 selectmode="browse")
        col_cfg = [
            ("id",         "ID",         60,  False),
            ("ext",        "Ext",        45,  False),
            ("kind",       "Type",       90,  False),
            ("resolution", "Resolution", 90,  False),
            ("fps",        "FPS",        50,  False),
            ("size",       "Size",       65,  False),
            ("tbr",        "Bitrate",    60,  False),
            ("note",       "Note",       120, True),
        ]
        for cid, hdr_txt, w, stretch in col_cfg:
            self.tree.heading(cid, text=hdr_txt)
            self.tree.column(cid, width=w, stretch=stretch, anchor="center")
        self.tree.column("note", anchor="w")

        vsb = ttk.Scrollbar(parent, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=2, column=0, sticky="nsew", padx=(8,0), pady=(4,0))
        vsb.grid(row=2, column=1, sticky="ns",  pady=(4,0))
        hsb.grid(row=3, column=0, sticky="ew",  padx=(8,0))
        parent.rowconfigure(2, weight=1)

        # Bottom row: options + download button
        bot = tk.Frame(parent, bg=C["panel"], pady=8)
        bot.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8)

        self.var_audio_only = tk.BooleanVar(value=self.cfg.get("audio_only", False))
        tk.Checkbutton(bot, text="Audio only", variable=self.var_audio_only,
                       bg=C["panel"], fg=C["text"], selectcolor=C["bg3"],
                       activebackground=C["panel"], font=self.font_small,
                       command=self._toggle_audio_only).pack(side="left", padx=(0,8))

        tk.Label(bot, text="Format:", bg=C["panel"], fg=C["text_dim"],
                 font=self.font_small).pack(side="left")
        self.var_ext = tk.StringVar(value=self.cfg.get("preferred_ext","mp4"))
        ext_cb = ttk.Combobox(bot, textvariable=self.var_ext, width=6,
                              values=["mp4","mkv","webm","mp3","m4a","flac","opus"],
                              state="readonly")
        ext_cb.pack(side="left", padx=4)

        self.btn_dl = ttk.Button(bot, text="⬇  Download Selected",
                                 style="Accent.TButton", command=self._download_selected)
        self.btn_dl.pack(side="right", ipadx=8)

        ttk.Button(bot, text="+ Queue Selected", style="Ghost.TButton",
                   command=self._queue_selected).pack(side="right", padx=6)

    def _build_queue_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        hdr = tk.Frame(parent, bg=C["bg3"])
        hdr.grid(row=0, column=0, sticky="ew")
        tk.Label(hdr, text="  Download Queue", bg=C["bg3"], fg=C["accent"],
                 font=self.font_heading, pady=7).pack(side="left")

        self.lbl_q_count = tk.Label(hdr, text="0 items", bg=C["bg3"],
                                    fg=C["text_dim"], font=self.font_small)
        self.lbl_q_count.pack(side="right", padx=10)

        # Scrollable queue list
        self.queue_canvas = tk.Canvas(parent, bg=C["panel"], highlightthickness=0)
        qsb = ttk.Scrollbar(parent, orient="vertical",
                            command=self.queue_canvas.yview)
        self.queue_canvas.configure(yscrollcommand=qsb.set)
        self.queue_canvas.grid(row=1, column=0, sticky="nsew")
        qsb.grid(row=1, column=1, sticky="ns")

        self.queue_inner = tk.Frame(self.queue_canvas, bg=C["panel"])
        self.queue_canvas.create_window((0,0), window=self.queue_inner, anchor="nw")
        self.queue_inner.bind("<Configure>",
            lambda e: self.queue_canvas.configure(
                scrollregion=self.queue_canvas.bbox("all")))

        # Buttons
        bot = tk.Frame(parent, bg=C["panel"], pady=6)
        bot.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8)

        self.btn_start_q = ttk.Button(bot, text="▶  Start Queue",
                                      style="Accent.TButton",
                                      command=self._start_queue)
        self.btn_start_q.pack(side="left", ipadx=6)

        ttk.Button(bot, text="✕ Clear Done", style="Ghost.TButton",
                   command=self._clear_done_queue).pack(side="left", padx=6)

        ttk.Button(bot, text="✕ Clear All", style="Ghost.TButton",
                   command=self._clear_all_queue).pack(side="right")

    def _build_settings_tab(self):
        tab = self.tab_cfg
        tab.columnconfigure(0, weight=1)

        canvas = tk.Canvas(tab, bg=C["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        inner = tk.Frame(canvas, bg=C["bg"])
        canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        inner.columnconfigure(1, weight=1)

        self._add_section(inner, 0, "Download Options")
        row = 1

        # Default save dir
        row = self._add_cfg_row(inner, row, "Default Save Directory",
            widget_factory=lambda p: self._make_dir_row(p))

        self._add_section(inner, row, "Video Options")
        row += 1

        self.var_cfg_ext = tk.StringVar(value=self.cfg.get("preferred_ext","mp4"))
        self.var_cfg_ext.trace_add("write", self._autosave_settings)
        row = self._add_cfg_row(inner, row, "Preferred container",
            widget_factory=lambda p: self._make_combo(p, self.var_cfg_ext,
                ["mp4","mkv","webm"]))

        self.var_embed_subs = tk.BooleanVar(value=self.cfg.get("embed_subs", True))
        self.var_embed_subs.trace_add("write", self._autosave_settings)
        row = self._add_cfg_row(inner, row, "Embed subtitles into file",
            widget_factory=lambda p: self._make_check(p, self.var_embed_subs))

        self.var_embed_thumb = tk.BooleanVar(value=self.cfg.get("embed_thumb", True))
        self.var_embed_thumb.trace_add("write", self._autosave_settings)
        row = self._add_cfg_row(inner, row, "Embed thumbnail into file",
            widget_factory=lambda p: self._make_check(p, self.var_embed_thumb))

        self._add_section(inner, row, "Subtitle Options")
        row += 1

        self.var_subtitles = tk.BooleanVar(value=self.cfg.get("subtitles", True))
        self.var_subtitles.trace_add("write", self._autosave_settings)
        row = self._add_cfg_row(inner, row, "Download subtitles",
            widget_factory=lambda p: self._make_check(p, self.var_subtitles))

        self._add_section(inner, row, "Thumbnail Options")
        row += 1

        self.var_thumbnail = tk.BooleanVar(value=self.cfg.get("thumbnail", True))
        self.var_thumbnail.trace_add("write", self._autosave_settings)
        row = self._add_cfg_row(inner, row, "Save thumbnail file",
            widget_factory=lambda p: self._make_check(p, self.var_thumbnail))

        self._add_section(inner, row, "Audio Options")
        row += 1

        self.var_cfg_audio_fmt = tk.StringVar(value=self.cfg.get("audio_format","mp3"))
        self.var_cfg_audio_fmt.trace_add("write", self._autosave_settings)
        row = self._add_cfg_row(inner, row, "Default audio format",
            widget_factory=lambda p: self._make_combo(p, self.var_cfg_audio_fmt,
                ["mp3","m4a","flac","opus","wav"]))

        self._add_section(inner, row, "yt-dlp Binary")
        row += 1

        self.lbl_bin_path = tk.Label(inner, text=str(BIN_PATH),
            bg=C["bg"], fg=C["text_dim"], font=self.font_mono_sm)
        self.lbl_bin_path.grid(row=row, column=0, columnspan=2, sticky="w",
                               padx=22, pady=4)
        row += 1

        btn_row = tk.Frame(inner, bg=C["bg"])
        btn_row.grid(row=row, column=0, columnspan=2, sticky="w", padx=18, pady=8)
        ttk.Button(btn_row, text="⟳ Check for yt-dlp Update",
                   style="Ghost.TButton", command=self._manual_update).pack(side="left")
        ttk.Button(btn_row, text="↓ Force Re-download",
                   style="Ghost.TButton", command=self._force_redownload).pack(side="left", padx=8)
        row += 1

        # Save button
        tk.Frame(inner, bg=C["border"], height=1).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=18, pady=16)
        row += 1
        ttk.Button(inner, text="  Save Settings  ", style="Accent.TButton",
                   command=self._save_settings).grid(row=row, column=0,
                   columnspan=2, pady=(0,24), ipadx=10)

    def _build_log_tab(self):
        tab = self.tab_log
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        self.log_text = tk.Text(tab, bg=C["bg"], fg=C["text_mid"],
                                font=self.font_mono, state="disabled",
                                relief="flat", bd=0, wrap="none",
                                insertbackground=C["accent"])

        vsb = ttk.Scrollbar(tab, orient="vertical",   command=self.log_text.yview)
        hsb = ttk.Scrollbar(tab, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.log_text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.log_text.tag_configure("accent",  foreground=C["accent"])
        self.log_text.tag_configure("success", foreground=C["success"])
        self.log_text.tag_configure("warning", foreground=C["warning"])
        self.log_text.tag_configure("error",   foreground=C["error"])
        self.log_text.tag_configure("dim",     foreground=C["text_dim"])

        bot = tk.Frame(tab, bg=C["bg2"], pady=5)
        bot.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(bot, text="Clear Log", style="Ghost.TButton",
                   command=self._clear_log).pack(side="right", padx=8)

    # ── Settings helpers ──────────────────────────────────────────────────────

    def _add_section(self, parent, row, title):
        f = tk.Frame(parent, bg=C["bg"])
        f.grid(row=row, column=0, columnspan=2, sticky="ew", padx=14, pady=(18,4))
        tk.Label(f, text=title, bg=C["bg"], fg=C["accent"],
                 font=self.font_heading).pack(side="left")
        tk.Frame(f, bg=C["border"], height=1).pack(side="left", fill="x",
                                                    expand=True, padx=8)

    def _add_cfg_row(self, parent, row, label, widget_factory):
        tk.Label(parent, text=label, bg=C["bg"], fg=C["text"],
                 font=self.font_body).grid(row=row, column=0, sticky="w",
                 padx=(28,12), pady=5)
        w = widget_factory(parent)
        if w:
            w.grid(row=row, column=1, sticky="w", padx=(0,18), pady=5)
        return row + 1

    def _make_dir_row(self, parent):
        f = tk.Frame(parent, bg=C["bg"])
        self.var_cfg_savedir = tk.StringVar(value=self.cfg["save_dir"])
        self.var_cfg_savedir.trace_add("write", self._autosave_settings)
        e = tk.Entry(f, textvariable=self.var_cfg_savedir, width=36,
                     bg=C["bg3"], fg=C["text"], insertbackground=C["accent"],
                     relief="flat", font=self.font_body, bd=4)
        e.pack(side="left", ipady=3)
        ttk.Button(f, text="Browse…", style="Ghost.TButton",
                   command=lambda: self.var_cfg_savedir.set(
                       filedialog.askdirectory() or self.var_cfg_savedir.get())
                   ).pack(side="left", padx=6)
        return f

    def _make_combo(self, parent, var, values):
        # tk.OptionMenu is backed directly by the StringVar and always renders
        # the current value immediately — no readonly/set() timing issues.
        om = tk.OptionMenu(parent, var, *values)
        om.configure(
            bg=C["bg3"], fg=C["text"], activebackground=C["accent2"],
            activeforeground=C["text"], highlightthickness=0,
            relief="flat", bd=0, width=8,
            indicatoron=True,
        )
        om["menu"].configure(
            bg=C["bg3"], fg=C["text"],
            activebackground=C["accent2"], activeforeground=C["text"],
            borderwidth=0,
        )
        return om

    def _make_check(self, parent, var):
        f = tk.Frame(parent, bg=C["bg"])
        tk.Checkbutton(f, variable=var, bg=C["bg"], fg=C["text"],
                       selectcolor=C["bg3"], activebackground=C["bg"],
                       relief="flat").pack(side="left")
        return f

    def _collect_settings(self):
        """Pull every settings-tab tk variable into self.cfg."""
        self.cfg["save_dir"]      = self.var_cfg_savedir.get()
        self.cfg["preferred_ext"] = self.var_cfg_ext.get()
        self.cfg["embed_subs"]    = self.var_embed_subs.get()
        self.cfg["embed_thumb"]   = self.var_embed_thumb.get()
        self.cfg["subtitles"]     = self.var_subtitles.get()
        self.cfg["thumbnail"]     = self.var_thumbnail.get()
        self.cfg["audio_format"]  = self.var_cfg_audio_fmt.get()
        # Keep the download-tab save-dir entry in sync
        self.var_savedir.set(self.cfg["save_dir"])

    def _save_settings(self):
        """Called by the Save Settings button — collect, persist, notify."""
        self._collect_settings()
        save_config(self.cfg)
        self._set_status("Settings saved.", C["success"])

    def _autosave_settings(self, *_):
        """Called automatically whenever any settings widget changes.
        Guarded so it silently no-ops if called before all vars are ready
        (e.g. during the StringVar trace fired by cb.set() at build time)."""
        try:
            self._collect_settings()
            save_config(self.cfg)
        except AttributeError:
            pass  # Not all settings widgets built yet — ignore

    # ── yt-dlp management ─────────────────────────────────────────────────────

    def _check_ytdlp_on_start(self):
        def _work():
            if not BIN_PATH.exists():
                self._log("yt-dlp binary not found — downloading…", "warning")
                self.after(0, lambda: self.lbl_ytdlp_ver.configure(
                    text="yt-dlp: downloading…", fg=C["warning"]))
                ok, result = download_ytdlp(progress_cb=None)
                if ok:
                    self.cfg["ytdlp_version"] = result
                    save_config(self.cfg)
                    self._log(f"yt-dlp downloaded: {result}", "success")
                    self.after(0, lambda: self.lbl_ytdlp_ver.configure(
                        text=f"yt-dlp {result}", fg=C["success"]))
                else:
                    self._log(f"Download failed: {result}", "error")
                    self.after(0, lambda: self.lbl_ytdlp_ver.configure(
                        text="yt-dlp: FAILED", fg=C["error"]))
            else:
                ver = self.cfg.get("ytdlp_version") or "installed"
                self.after(0, lambda: self.lbl_ytdlp_ver.configure(
                    text=f"yt-dlp {ver}", fg=C["accent"]))
                self._log(f"yt-dlp binary found ({ver})", "dim")

            # ── Also ensure ffmpeg is present ────────────────────────────
            if not FFMPEG_PATH.exists():
                self._log("ffmpeg not found — downloading…", "warning")
                self.after(0, lambda: self._set_status(
                    "Downloading ffmpeg…", C["warning"]))
                ok, msg = download_ffmpeg()
                if ok:
                    self._log("ffmpeg downloaded successfully.", "success")
                    self.after(0, lambda: self._set_status(
                        "ffmpeg ready.", C["success"]))
                else:
                    self._log(f"ffmpeg download failed: {msg}", "error")
                    self.after(0, lambda: self._set_status(
                        "ffmpeg missing — merging disabled.", C["warning"]))
            else:
                self._log("ffmpeg found.", "dim")
        threading.Thread(target=_work, daemon=True).start()

    def _manual_update(self):
        def _work():
            self._log("Checking for yt-dlp update…", "accent")
            self.after(0, lambda: self.lbl_ytdlp_ver.configure(
                text="yt-dlp: checking…", fg=C["text_dim"]))
            ok, result = download_ytdlp()
            if ok:
                self.cfg["ytdlp_version"] = result
                save_config(self.cfg)
                self._log(f"yt-dlp updated to {result}", "success")
                self.after(0, lambda: self.lbl_ytdlp_ver.configure(
                    text=f"yt-dlp {result}", fg=C["success"]))
            else:
                self._log(f"Update failed: {result}", "error")
                self.after(0, lambda: self.lbl_ytdlp_ver.configure(
                    text="yt-dlp: update failed", fg=C["error"]))
        threading.Thread(target=_work, daemon=True).start()

    def _force_redownload(self):
        if BIN_PATH.exists():
            BIN_PATH.unlink()
        self._manual_update()

    # ── Format fetching ───────────────────────────────────────────────────────

    def _fetch_formats(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Please enter a video URL.")
            return
        if not BIN_PATH.exists():
            messagebox.showerror("yt-dlp missing", "yt-dlp binary not found.")
            return

        self.btn_fetch.configure(state="disabled")
        self.lbl_thumb_info.configure(text="Fetching formats…", fg=C["warning"])
        self._clear_tree()

        def _work():
            self._log(f"Fetching formats for: {url}", "accent")
            info, err = fetch_formats(url)
            if err:
                self._log(f"Error: {err}", "error")
                self.after(0, lambda: [
                    self.lbl_thumb_info.configure(text=f"Error: {err}", fg=C["error"]),
                    self.btn_fetch.configure(state="normal")
                ])
                return
            rows = build_format_rows(info)
            title = info.get("title","Unknown")
            self._log(f"Found {len(rows)} formats for: {title}", "success")
            self.after(0, lambda: self._populate_tree(rows, title, url))

        threading.Thread(target=_work, daemon=True).start()

    def _clear_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _populate_tree(self, rows, title, url):
        self._clear_tree()
        self._current_url   = url
        self._current_rows  = rows
        self.lbl_title.configure(text=title[:48] + ("…" if len(title)>48 else ""))
        self.lbl_thumb_info.configure(
            text=f"{len(rows)} formats available — select one below",
            fg=C["text_mid"])

        for r in rows:
            tag = r["kind"].replace("+","_")
            self.tree.insert("", "end", iid=r["id"], values=(
                r["id"], r["ext"], r["kind"], r["resolution"],
                r["fps"], r["size"], r["tbr"], r["note"]
            ), tags=(tag,))

        self.tree.tag_configure("video_audio", foreground=C["accent"])
        self.tree.tag_configure("video",       foreground=C["text"])
        self.tree.tag_configure("audio",       foreground=C["text_dim"])

        if rows:
            self.tree.selection_set(rows[0]["id"])
            self.tree.focus(rows[0]["id"])

        self.btn_fetch.configure(state="normal")

    def _get_selected_fmt(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return sel[0]

    # ── Queue management ──────────────────────────────────────────────────────

    def _make_queue_item_widget(self, url, fmt_id, title=""):
        item_frame = tk.Frame(self.queue_inner, bg=C["bg3"],
                               highlightbackground=C["border"],
                               highlightthickness=1)
        item_frame.pack(fill="x", padx=4, pady=2)

        top = tk.Frame(item_frame, bg=C["bg3"])
        top.pack(fill="x", padx=8, pady=(4,2))

        lbl = tk.Label(top, text=(title or url)[:60],
                       bg=C["bg3"], fg=C["text"], font=self.font_small,
                       anchor="w")
        lbl.pack(side="left", fill="x", expand=True)

        def remove():
            item_frame.destroy()
            self.queue_items = [i for i in self.queue_items if i["frame"] is not item_frame]
            self._update_queue_count()

        ttk.Button(top, text="✕", style="Ghost.TButton",
                   command=remove).pack(side="right")

        bot = tk.Frame(item_frame, bg=C["bg3"])
        bot.pack(fill="x", padx=8, pady=(0,4))

        fmt_lbl = tk.Label(bot, text=f"fmt: {fmt_id}",
                           bg=C["bg3"], fg=C["text_dim"], font=self.font_mono_sm)
        fmt_lbl.pack(side="left")

        status_lbl = tk.Label(bot, text="queued",
                              bg=C["bg3"], fg=C["text_dim"], font=self.font_small)
        status_lbl.pack(side="left", padx=10)

        prog = ttk.Progressbar(bot, style="green.Horizontal.TProgressbar",
                               length=100, maximum=100)
        prog.pack(side="right")

        item = {"frame": item_frame, "url": url, "fmt_id": fmt_id,
                "title": title, "status_lbl": status_lbl, "prog": prog,
                "done": False}
        self.queue_items.append(item)
        self._update_queue_count()
        return item

    def _update_queue_count(self):
        n = len(self.queue_items)
        self.lbl_q_count.configure(text=f"{n} item{'s' if n!=1 else ''}")

    def _queue_selected(self):
        url = getattr(self, "_current_url", None) or self.entry_url.get().strip()
        fmt_id = self._get_selected_fmt() or "bestvideo+bestaudio/best"
        if not url:
            messagebox.showwarning("No URL", "Fetch formats first or enter a URL.")
            return
        title = self.lbl_title.cget("text")
        self._make_queue_item_widget(url, fmt_id, title)
        self._log(f"Queued: {url} [fmt:{fmt_id}]", "dim")

    def _add_to_queue_from_url(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Enter a URL first.")
            return
        self._make_queue_item_widget(url, "bestvideo+bestaudio/best", url)
        self._log(f"Added to queue: {url}", "dim")

    def _clear_done_queue(self):
        to_remove = [i for i in self.queue_items if i["done"]]
        for i in to_remove:
            i["frame"].destroy()
        self.queue_items = [i for i in self.queue_items if not i["done"]]
        self._update_queue_count()

    def _clear_all_queue(self):
        for i in self.queue_items:
            i["frame"].destroy()
        self.queue_items.clear()
        self._update_queue_count()

    def _start_queue(self):
        pending = [i for i in self.queue_items if not i["done"]]
        if not pending:
            messagebox.showinfo("Queue empty", "No pending items in queue.")
            return
        self.btn_start_q.configure(state="disabled")
        save_dir = self.var_savedir.get()

        def _run_queue():
            for item in pending:
                self.after(0, lambda i=item: i["status_lbl"].configure(
                    text="downloading…", fg=C["warning"]))
                cmd = build_cmd(item["url"], save_dir, item["fmt_id"],
                                self.cfg, self.var_audio_only.get())
                self._log(f"Starting: {item['url']}", "accent")
                self._run_cmd_with_progress(cmd, item)
            self.after(0, lambda: self.btn_start_q.configure(state="normal"))
            self._log("Queue complete.", "success")

        threading.Thread(target=_run_queue, daemon=True).start()

    # ── Download single ───────────────────────────────────────────────────────

    def _download_selected(self):
        url = getattr(self, "_current_url", None) or self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Enter a URL and fetch formats first.")
            return
        fmt_id = self._get_selected_fmt() or "bestvideo+bestaudio/best"
        save_dir = self.var_savedir.get()

        self.cfg["save_dir"]      = save_dir
        self.cfg["audio_only"]    = self.var_audio_only.get()
        self.cfg["preferred_ext"] = self.var_ext.get()

        cmd = build_cmd(url, save_dir, fmt_id, self.cfg, self.var_audio_only.get())
        self._log(f"Download cmd: {' '.join(str(x) for x in cmd)}", "dim")

        # Create a temporary queue item for progress tracking
        title = self.lbl_title.cget("text") or url
        item = self._make_queue_item_widget(url, fmt_id, title)
        self.btn_dl.configure(state="disabled")

        def _work():
            self._run_cmd_with_progress(cmd, item)
            self.after(0, lambda: self.btn_dl.configure(state="normal"))

        threading.Thread(target=_work, daemon=True).start()

    def _run_cmd_with_progress(self, cmd, queue_item):
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    bufsize=1)
            saw_100pct  = False   # saw "[download] 100%"
            saw_merger  = False   # saw "[Merger]" line (ffmpeg merge succeeded)
            saw_already = False   # "has already been downloaded"
            for line in proc.stdout:
                line = line.rstrip()
                self._log(line, "dim")
                # Track meaningful success signals
                if "[Merger]" in line or "[merger]" in line:
                    saw_merger = True
                if "has already been downloaded" in line:
                    saw_already = True
                # Parse download progress
                m = re.search(r'\[download\]\s+(\d+(?:\.\d+)?)%', line)
                if m:
                    pct = float(m.group(1))
                    if pct >= 99.9:
                        saw_100pct = True
                    self.after(0, lambda p=pct, qi=queue_item:
                        qi["prog"].configure(value=p))
                    self.after(0, lambda p=pct, qi=queue_item:
                        qi["status_lbl"].configure(
                            text=f"{p:.1f}%", fg=C["accent"]))
            proc.wait()
            rc = proc.returncode
            # yt-dlp exits 0 on clean success, but occasionally exits 1 even
            # after a fully successful download+merge (e.g. a post-processing
            # warning or a subtitle that couldn't be embedded).  We consider
            # the download successful if we saw 100% progress OR the output
            # contains a "[Merger]" or "has already been downloaded" line.
            actually_done = (
                rc == 0
                or saw_100pct
                or saw_merger
                or saw_already
            )
            if actually_done:
                self.after(0, lambda qi=queue_item: [
                    qi["status_lbl"].configure(text="✓ done", fg=C["success"]),
                    qi["prog"].configure(value=100),
                    qi.update({"done": True}),
                ])
                self._log("Download complete.", "success")
            else:
                self.after(0, lambda qi=queue_item:
                    qi["status_lbl"].configure(text="✗ error", fg=C["error"]))
                self._log(f"Process exited with code {rc}", "error")
        except Exception as e:
            self._log(f"Exception: {e}", "error")
            self.after(0, lambda qi=queue_item:
                qi["status_lbl"].configure(text="✗ exception", fg=C["error"]))

    # ── Misc helpers ──────────────────────────────────────────────────────────

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.var_savedir.get())
        if d:
            self.var_savedir.set(d)
            self.cfg["save_dir"] = d
            save_config(self.cfg)

    def _toggle_audio_only(self):
        self.cfg["audio_only"] = self.var_audio_only.get()

    def _set_status(self, msg, color=None):
        self.lbl_status.configure(text=msg, fg=color or C["text_dim"])

    def _log(self, msg, tag=""):
        self.log_queue.put((msg, tag))

    def _poll_log(self):
        try:
            while True:
                msg, tag = self.log_queue.get_nowait()
                ts = time.strftime("%H:%M:%S")
                self.log_text.configure(state="normal")
                self.log_text.insert("end", f"[{ts}] ", "dim")
                self.log_text.insert("end", msg + "\n", tag or "")
                self.log_text.configure(state="disabled")
                self.log_text.see("end")
                self.lbl_status.configure(text=msg[:80], fg=C["text_dim"])
        except queue.Empty:
            pass
        self.after(80, self._poll_log)

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _on_close(self):
        # Flush any unsaved settings changes before quitting
        try:
            self._collect_settings()
        except Exception:
            pass
        save_config(self.cfg)
        self.destroy()

# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
