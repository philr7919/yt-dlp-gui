#!/usr/bin/env bash
# yt-dlp GUI — macOS launcher
# Double-click in Finder, or run from Terminal.
# Bootstraps a standalone Python if needed, then launches gui.py.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Config ────────────────────────────────────────────────────────────────────
# PBS_TAG / PBS_PY_VER: using a recent release whose bundled Tk is compatible
# with macOS 26 Tahoe and later. Update these when new PBS releases are available.
PBS_TAG="20250702"
PBS_PY_VER="3.13.5"
PBS_BASE="https://github.com/indygreg/python-build-standalone/releases/download/${PBS_TAG}"
EMBED_DIR="${SCRIPT_DIR}/python_embedded"
GUI="${SCRIPT_DIR}/gui.py"

# ── Keep Terminal open on error (Finder double-click) ────────────────────────
trap 'echo ""; echo "  Press Enter to close…"; read -r' ERR

# ── Helpers ───────────────────────────────────────────────────────────────────
info()    { echo "  [Launcher] $*"; }
success() { echo "  [OK]       $*"; }
warn()    { echo "  [WARN]     $*" >&2; }
err()     { echo "  [ERROR]    $*" >&2; }

# ── Detect architecture ───────────────────────────────────────────────────────
detect_arch() {
    local m
    m="$(uname -m)"
    case "$m" in
        x86_64)        echo "x86_64" ;;
        arm64|aarch64) echo "aarch64" ;;
        *)             echo "$m" ;;
    esac
}

# ── Build PBS asset filename for macOS ───────────────────────────────────────
pbs_filename() {
    local arch
    arch="$(detect_arch)"
    # python-build-standalone uses 'aarch64' not 'arm64' in asset names
    echo "cpython-${PBS_PY_VER}+${PBS_TAG}-${arch}-apple-darwin-install_only.tar.gz"
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
        err "curl not found (unexpected on macOS). Install Xcode Command Line Tools:"
        err "  xcode-select --install"
        exit 1
    fi
    echo ""
}

# ── Find embedded Python ──────────────────────────────────────────────────────
embedded_python() {
    local candidates=(
        "${EMBED_DIR}/python/bin/python3"
        "${EMBED_DIR}/python/bin/python${PBS_PY_VER:0:4}"
        "${EMBED_DIR}/python/bin/python3.13"
        "${EMBED_DIR}/python/bin/python3.12"
    )
    for c in "${candidates[@]}"; do
        if [[ -x "$c" ]]; then echo "$c"; return 0; fi
    done
    return 1
}

# ── Check if a Python interpreter is usable (3.8+ with working Tk) ───────────
#
# IMPORTANT: We do a real Tk() instantiation, not just `import tkinter`.
# Just importing tkinter succeeds even when the bundled Tk framework is built
# for a different macOS version — the crash only happens when Tk actually
# tries to connect to the window server, e.g.:
#   "macOS 26 (2603) or later required, have instead 16 (1603)"
#
# We also hard-skip /usr/bin/python3 (Apple's Xcode stub) because it is
# permanently linked to the system Tk which is routinely mismatched on new
# macOS releases.
check_interpreter() {
    local exe="$1"

    # Skip Apple's stub unconditionally — its Tk is always suspect
    if [[ "$exe" == "/usr/bin/python3" ]]; then
        warn "Skipping /usr/bin/python3 (Apple stub — Tk version may be mismatched)"
        return 1
    fi

    # Smoke-test: actually instantiate a Tk root window (hidden).
    # Redirect stderr so the mismatch abort message doesn't appear to the user.
    TK_SILENCE_DEPRECATION=1 \
    "$exe" -c "
import sys
assert sys.version_info >= (3, 8), 'version too old'
import tkinter
root = tkinter.Tk()   # <-- this is where the macOS version crash surfaces
root.withdraw()
root.destroy()
print('ok')
" 2>/dev/null | grep -q "^ok$"
}

# ── Find system Python (skipping Apple stub) ──────────────────────────────────
find_system_python() {
    local candidates=(
        # Homebrew (Apple Silicon)
        /opt/homebrew/bin/python3.13
        /opt/homebrew/bin/python3.12
        /opt/homebrew/bin/python3.11
        /opt/homebrew/bin/python3.10
        /opt/homebrew/bin/python3
        # Homebrew (Intel)
        /usr/local/bin/python3.13
        /usr/local/bin/python3.12
        /usr/local/bin/python3.11
        /usr/local/bin/python3.10
        /usr/local/bin/python3
        # python.org framework installs
        /Library/Frameworks/Python.framework/Versions/3.13/bin/python3
        /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
        /Library/Frameworks/Python.framework/Versions/3.11/bin/python3
        /Library/Frameworks/Python.framework/Versions/3.10/bin/python3
        # PATH fallback (but NOT /usr/bin/python3 — handled in check_interpreter)
        python3.13
        python3.12
        python3.11
        python3.10
        python3.9
        python3.8
        python3
    )
    for c in "${candidates[@]}"; do
        local exe=""
        if [[ "$c" == /* ]]; then
            [[ -x "$c" ]] && exe="$c"
        else
            command -v "$c" &>/dev/null && exe="$(command -v "$c")"
        fi
        if [[ -n "$exe" ]]; then
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

    info "Downloading standalone Python ${PBS_PY_VER} for macOS ($(detect_arch))…"
    info "This only happens once (~30 MB)."
    echo ""

    mkdir -p "$EMBED_DIR"
    download_with_progress "$url" "$tmp_tar"

    info "Extracting archive…"
    tar -xzf "$tmp_tar" -C "$EMBED_DIR"
    rm -f "$tmp_tar"

    local exe
    if exe="$(embedded_python)"; then
        chmod +x "$exe"
        chmod +x "${EMBED_DIR}/python/bin/"* 2>/dev/null || true
        success "Standalone Python ready: $exe"
        echo "$exe"
    else
        err "Python binary not found after extraction in ${EMBED_DIR}"
        err "Contents of EMBED_DIR:"
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

# 1. Embedded already present? (may need re-download if macOS was upgraded)
if EMB="$(embedded_python 2>/dev/null)"; then
    if check_interpreter "$EMB"; then
        info "Using embedded Python: $EMB"
        CHOSEN_PY="$EMB"
    else
        warn "Embedded Python found but Tk test failed — clearing and re-downloading…"
        rm -rf "$EMBED_DIR"
    fi
fi

# 2. System Python (Homebrew / python.org installer, NOT Apple stub)
if [[ -z "$CHOSEN_PY" ]]; then
    info "Checking for system Python 3.8+ with working Tk…"
    if SYS="$(find_system_python 2>/dev/null)"; then
        info "Using system Python: $SYS"
        CHOSEN_PY="$SYS"
    else
        info "No suitable system Python found — will download standalone Python."
    fi
fi

# 3. Download python-build-standalone
if [[ -z "$CHOSEN_PY" ]]; then
    CHOSEN_PY="$(install_embedded_python)"
fi

# ── macOS env tweaks ──────────────────────────────────────────────────────────
export TK_SILENCE_DEPRECATION=1
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}"

# ── Launch GUI ────────────────────────────────────────────────────────────────
info "Starting yt-dlp GUI…"
echo ""
exec "$CHOSEN_PY" "$GUI" "$@"
