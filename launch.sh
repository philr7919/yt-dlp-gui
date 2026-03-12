#!/usr/bin/env bash
# yt-dlp GUI — Linux launcher
# Bootstraps a standalone Python if needed, then launches gui.py.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Config ────────────────────────────────────────────────────────────────────
PBS_TAG="20240107"
PBS_PY_VER="3.12.1"
PBS_BASE="https://github.com/indygreg/python-build-standalone/releases/download/${PBS_TAG}"
EMBED_DIR="${SCRIPT_DIR}/python_embedded"
GUI="${SCRIPT_DIR}/gui.py"
BOOTSTRAP="${SCRIPT_DIR}/bootstrap.py"

# ── Helpers ───────────────────────────────────────────────────────────────────
info()    { echo "  [Launcher] $*"; }
success() { echo "  [OK]       $*"; }
warn()    { echo "  [WARN]     $*" >&2; }
err()     { echo "  [ERROR]    $*" >&2; }

draw_bar() {
    # draw_bar <pct 0-100> <downloaded_bytes> <total_bytes>
    local pct=$1 dl=$2 tot=$3
    local filled=$(( pct / 2 ))
    local empty=$(( 50 - filled ))
    local bar
    bar="$(printf '█%.0s' $(seq 1 $filled 2>/dev/null))$(printf '░%.0s' $(seq 1 $empty 2>/dev/null))"
    local dl_mb tot_mb
    dl_mb=$(echo "scale=1; $dl/1048576" | bc 2>/dev/null || echo "?")
    tot_mb=$(echo "scale=1; $tot/1048576" | bc 2>/dev/null || echo "?")
    printf "\r  [%s] %3d%%  %s / %s MB" "$bar" "$pct" "$dl_mb" "$tot_mb"
}

# ── Download with progress bar ────────────────────────────────────────────────
download_with_progress() {
    local url="$1" dest="$2"
    info "URL  : $url"
    info "Dest : $dest"
    echo ""

    if command -v curl &>/dev/null; then
        curl -L --progress-bar -o "$dest" "$url"
    elif command -v wget &>/dev/null; then
        wget --progress=bar:force -O "$dest" "$url" 2>&1
    else
        err "Neither curl nor wget found. Install one and retry."
        err "  sudo apt install curl   OR   sudo apt install wget"
        exit 1
    fi
    echo ""
}

# ── Detect architecture ───────────────────────────────────────────────────────
detect_arch() {
    local m
    m="$(uname -m)"
    case "$m" in
        x86_64|amd64)  echo "x86_64" ;;
        aarch64|arm64) echo "aarch64" ;;
        *)             echo "$m" ;;
    esac
}

# ── Detect libc ───────────────────────────────────────────────────────────────
detect_libc() {
    if ldd --version 2>&1 | grep -qi musl; then
        echo "musl"
    else
        echo "gnu"
    fi
}

# ── Build PBS asset filename ──────────────────────────────────────────────────
pbs_filename() {
    local arch libc
    arch="$(detect_arch)"
    libc="$(detect_libc)"
    echo "cpython-${PBS_PY_VER}+${PBS_TAG}-${arch}-unknown-linux-${libc}-install_only.tar.gz"
}

# ── Find embedded Python ──────────────────────────────────────────────────────
embedded_python() {
    local candidates=(
        "${EMBED_DIR}/python/bin/python3"
        "${EMBED_DIR}/python/bin/python${PBS_PY_VER:0:4}"
        "${EMBED_DIR}/python/bin/python3.12"
    )
    for c in "${candidates[@]}"; do
        if [[ -x "$c" ]]; then echo "$c"; return 0; fi
    done
    return 1
}

# ── Check if a Python interpreter is usable (3.8+ with tkinter) ──────────────
check_interpreter() {
    local exe="$1"
    "$exe" -c "
import sys, tkinter
assert sys.version_info >= (3, 8), 'too old'
print('ok')
" 2>/dev/null | grep -q "^ok$"
}

# ── Find system Python ────────────────────────────────────────────────────────
find_system_python() {
    local candidates=(python3 python python3.12 python3.11 python3.10 python3.9 python3.8)
    for c in "${candidates[@]}"; do
        if command -v "$c" &>/dev/null; then
            local exe
            exe="$(command -v "$c")"
            if check_interpreter "$exe"; then
                echo "$exe"
                return 0
            fi
        fi
    done
    return 1
}

# ── Download + install python-build-standalone ────────────────────────────────
install_embedded_python() {
    local fname url tmp_tar
    fname="$(pbs_filename)"
    url="${PBS_BASE}/${fname}"
    tmp_tar="${EMBED_DIR}/_python_download.tar.gz"

    info "Downloading standalone Python ${PBS_PY_VER} ($(detect_arch)/$(detect_libc))…"
    info "This only happens once."
    echo ""

    mkdir -p "$EMBED_DIR"
    download_with_progress "$url" "$tmp_tar"

    info "Extracting archive…"
    tar -xzf "$tmp_tar" -C "$EMBED_DIR"
    rm -f "$tmp_tar"

    local exe
    if exe="$(embedded_python)"; then
        chmod +x "$exe"
        success "Standalone Python ready: $exe"
        echo "$exe"
    else
        err "Python binary not found after extraction in ${EMBED_DIR}"
        err "Contents:"
        ls -la "$EMBED_DIR" >&2 || true
        exit 1
    fi
}

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║           yt-dlp GUI  Launcher           ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# ── Bootstrap logic ───────────────────────────────────────────────────────────
CHOSEN_PY=""

# 1. Embedded already present?
if EMB="$(embedded_python 2>/dev/null)"; then
    if check_interpreter "$EMB"; then
        info "Using embedded Python: $EMB"
        CHOSEN_PY="$EMB"
    else
        warn "Embedded Python found but unusable — re-downloading…"
        rm -rf "$EMBED_DIR"
    fi
fi

# 2. System Python?
if [[ -z "$CHOSEN_PY" ]]; then
    info "Checking for system Python 3.8+ with tkinter…"
    if SYS="$(find_system_python 2>/dev/null)"; then
        info "Using system Python: $SYS"
        CHOSEN_PY="$SYS"
    else
        info "No suitable system Python found."
    fi
fi

# 3. Download embedded Python
if [[ -z "$CHOSEN_PY" ]]; then
    CHOSEN_PY="$(install_embedded_python)"
fi

# ── Launch GUI ────────────────────────────────────────────────────────────────
info "Starting yt-dlp GUI…"
echo ""
exec "$CHOSEN_PY" "$GUI" "$@"
