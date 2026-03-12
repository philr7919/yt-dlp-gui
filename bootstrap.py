#!/usr/bin/env python3
"""
bootstrap.py — Stage-2 bootstrapper for yt-dlp GUI
Runs with ANY Python 3.x (even 3.6+, uses only stdlib).
Responsible for:
  1. Downloading an embedded Python if needed (Windows only path used here
     for the .bat → python bootstrap.py flow; unix launchers handle their own)
  2. Verifying tkinter is available in the chosen interpreter
  3. Re-exec'ing gui.py with the best interpreter found
"""

import os
import sys
import json
import platform
import stat
import struct
import subprocess
import tarfile
import zipfile
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

SCRIPT_DIR = Path(__file__).parent.resolve()
EMBED_DIR  = SCRIPT_DIR / "python_embedded"
GUI        = SCRIPT_DIR / "gui.py"

SYSTEM = platform.system()   # Windows / Darwin / Linux
ARCH   = platform.machine()  # x86_64 / AMD64 / arm64 / aarch64

# ── python-build-standalone release tag ───────────────────────────────────────
# Check https://github.com/indygreg/python-build-standalone/releases for updates
PBS_TAG     = "20240107"
PBS_PY_VER  = "3.12.1"
PBS_BASE    = (
    "https://github.com/indygreg/python-build-standalone/releases/download"
    f"/{PBS_TAG}"
)

# ── Windows: use python-build-standalone (includes tkinter unlike embeddable zip)
# The official python.org embeddable zip deliberately strips tkinter out.
WIN_PBS_TAG = "20250702"
WIN_PY_VER  = "3.13.5"


def _arch_tag():
    """Normalise machine string."""
    m = ARCH.lower()
    if m in ("x86_64", "amd64"):
        return "x86_64"
    if m in ("arm64", "aarch64"):
        return "aarch64"
    return m


def _pbs_filename():
    """Return the python-build-standalone asset filename for this OS/arch."""
    arch = _arch_tag()
    if SYSTEM == "Darwin":
        # macOS universal2 covers both Intel and Apple Silicon
        return (
            f"cpython-{PBS_PY_VER}+{PBS_TAG}-"
            f"{'aarch64' if arch == 'aarch64' else 'x86_64'}-apple-darwin"
            f"-install_only.tar.gz"
        )
    if SYSTEM == "Linux":
        libc = "musl" if _is_musl() else "gnu"
        return (
            f"cpython-{PBS_PY_VER}+{PBS_TAG}-"
            f"{arch}-unknown-linux-{libc}"
            f"-install_only.tar.gz"
        )
    return None   # Windows handled separately


def _is_musl():
    """Best-effort musl detection on Linux."""
    try:
        out = subprocess.check_output(["ldd", "--version"],
                                      stderr=subprocess.STDOUT).decode()
        return "musl" in out.lower()
    except Exception:
        return False


def _win_embed_url():
    arch = _arch_tag()
    # python-build-standalone Windows asset names
    msvc_arch = "aarch64-pc-windows-msvc" if arch == "aarch64" else "x86_64-pc-windows-msvc"
    return (
        f"{PBS_BASE}/{WIN_PBS_TAG}"
        f"/cpython-{WIN_PY_VER}+{WIN_PBS_TAG}-{msvc_arch}-install_only.tar.gz"
    )


# ── Progress-bar download ──────────────────────────────────────────────────────

def _download(url: str, dest: Path):
    """Download url → dest with a live terminal progress bar."""
    print(f"  URL  : {url}")
    print(f"  Dest : {dest}")

    req = Request(url, headers={"User-Agent": "yt-dlp-gui-bootstrap/1.0"})
    with urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 65536   # 64 KB
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct  = downloaded / total * 100
                    done = int(pct / 2)        # 50-char bar
                    bar  = "█" * done + "░" * (50 - done)
                    mb_d = downloaded / 1_048_576
                    mb_t = total      / 1_048_576
                    print(f"\r  [{bar}] {pct:5.1f}%  {mb_d:.1f}/{mb_t:.1f} MB",
                          end="", flush=True)
                else:
                    mb_d = downloaded / 1_048_576
                    print(f"\r  Downloaded {mb_d:.1f} MB…", end="", flush=True)
    print()   # newline after bar


# ── Extraction helpers ─────────────────────────────────────────────────────────

def _extract_targz(src: Path, dst: Path):
    dst.mkdir(parents=True, exist_ok=True)
    print(f"  Extracting {src.name}…")
    with tarfile.open(src, "r:gz") as tar:
        tar.extractall(dst)
    src.unlink()


def _extract_zip(src: Path, dst: Path):
    dst.mkdir(parents=True, exist_ok=True)
    print(f"  Extracting {src.name}…")
    with zipfile.ZipFile(src) as zf:
        zf.extractall(dst)
    src.unlink()


def _make_exec(path: Path):
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


# ── Locate embedded interpreter ───────────────────────────────────────────────

def _embedded_python_exe() -> Path | None:
    """Return path to embedded Python exe if it exists, else None."""
    if SYSTEM == "Windows":
        # python-build-standalone extracts to <EMBED_DIR>/python/python.exe
        exe = EMBED_DIR / "python" / "python.exe"
        return exe if exe.exists() else None
    else:
        # python-build-standalone extracts to <EMBED_DIR>/python/bin/python3
        for candidate in (
            EMBED_DIR / "python" / "bin" / "python3",
            EMBED_DIR / "python" / "bin" / f"python{PBS_PY_VER[:4]}",
        ):
            if candidate.exists():
                return candidate
        return None


# ── System Python check ───────────────────────────────────────────────────────

def _check_interpreter(exe: str) -> bool:
    """Return True if exe is Python 3.8+ with tkinter."""
    try:
        out = subprocess.check_output(
            [exe, "-c",
             "import sys,tkinter; "
             "assert sys.version_info>=(3,8); "
             "print('ok')"],
            stderr=subprocess.DEVNULL, timeout=10
        ).decode().strip()
        return out == "ok"
    except Exception:
        return False


def _find_system_python() -> str | None:
    """Return path to a usable system Python, or None."""
    candidates = ["python3", "python", "python3.12", "python3.11",
                  "python3.10", "python3.9", "python3.8"]
    for c in candidates:
        try:
            exe = subprocess.check_output(
                ["which" if SYSTEM != "Windows" else "where", c],
                stderr=subprocess.DEVNULL
            ).decode().splitlines()[0].strip()
            if exe and _check_interpreter(exe):
                return exe
        except Exception:
            continue
    return None


# ── Download + install embedded Python ────────────────────────────────────────

def install_embedded_python():
    EMBED_DIR.mkdir(parents=True, exist_ok=True)
    tmp = EMBED_DIR / "_download_tmp"

    if SYSTEM == "Windows":
        url  = _win_embed_url()
        dest = tmp.with_suffix(".tar.gz")
        print(f"\n[Bootstrap] Downloading Python {WIN_PY_VER} for Windows (python-build-standalone)…")
        _download(url, dest)
        _extract_targz(dest, EMBED_DIR)
        # PBS extracts to <EMBED_DIR>/python/python.exe
        exe = EMBED_DIR / "python" / "python.exe"
        if not exe.exists():
            raise RuntimeError(f"python.exe not found after extraction in {EMBED_DIR}")
        print(f"[Bootstrap] Embedded Python ready: {exe}")
        return str(exe)

    else:
        fname = _pbs_filename()
        if not fname:
            raise RuntimeError(f"No python-build-standalone asset for {SYSTEM}/{ARCH}")
        url  = f"{PBS_BASE}/{fname}"
        dest = tmp.with_suffix(".tar.gz")
        print(f"\n[Bootstrap] Downloading standalone Python {PBS_PY_VER} for {SYSTEM}/{_arch_tag()}…")
        _download(url, dest)
        _extract_targz(dest, EMBED_DIR)
        exe = _embedded_python_exe()
        if not exe:
            raise RuntimeError(f"Python binary not found after extraction in {EMBED_DIR}")
        _make_exec(exe)
        print(f"[Bootstrap] Standalone Python ready: {exe}")
        return str(exe)


# ── Main bootstrap logic ───────────────────────────────────────────────────────

def bootstrap() -> str:
    """
    Returns path to the best Python interpreter to use.
    Order:
      1. Already-embedded Python in ./python_embedded/
      2. System Python 3.8+ with tkinter
      3. Download embedded Python → return its path
    """
    # 1. Embedded already present?
    emb = _embedded_python_exe()
    if emb and _check_interpreter(str(emb)):
        print(f"[Bootstrap] Using embedded Python: {emb}")
        return str(emb)

    # 2. System Python?
    sys_py = _find_system_python()
    if sys_py:
        print(f"[Bootstrap] Using system Python: {sys_py}")
        return sys_py

    # 3. Download embedded
    print("[Bootstrap] No suitable Python found — downloading embedded Python…")
    return install_embedded_python()


if __name__ == "__main__":
    # Called from Windows launch.bat as:
    #   python bootstrap.py --run-gui
    # Or tested standalone.
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-gui", action="store_true",
                        help="After bootstrapping, exec gui.py")
    parser.add_argument("--print-exe", action="store_true",
                        help="Print chosen interpreter path and exit")
    args = parser.parse_args()

    try:
        chosen = bootstrap()
    except Exception as e:
        print(f"\n[Bootstrap] FATAL: {e}", file=sys.stderr)
        if SYSTEM == "Windows":
            input("\nPress Enter to close…")
        sys.exit(1)

    if args.print_exe:
        print(chosen)
        sys.exit(0)

    if args.run_gui:
        os.execv(chosen, [chosen, str(GUI)])
