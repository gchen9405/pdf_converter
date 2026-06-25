#!/usr/bin/env bash
# One-shot builder for macOS / Linux.
#
#   ./build.sh                # digital PDFs
#   ./build.sh --with-ocr     # also handles scanned PDFs
#
# Produces a NATIVE executable for THIS OS/arch (a mac build runs only on mac,
# etc.). Handy for testing the recipe locally; the Windows deliverable is built
# with build.bat on the Windows machine.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
export KMP_DUPLICATE_LIB_OK=TRUE
export PYTHONUTF8=1

PY=""
for cand in python3.12 python3.11 python3.10; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ] && command -v python3 >/dev/null 2>&1; then
    if python3 -c 'import sys; raise SystemExit(0 if (3,10)<=sys.version_info[:2]<(3,13) else 1)'; then
        PY=python3
    fi
fi
if [ -z "$PY" ]; then
    echo "ERROR: need Python 3.10-3.12 to build Docling. Install one and retry." >&2
    exit 1
fi

echo "Using interpreter: $("$PY" --version)"
exec "$PY" "$HERE/build.py" "$@"
