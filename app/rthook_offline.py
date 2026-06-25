# PyInstaller runtime hook -- runs BEFORE any of the app's own imports.
#
# This guarantees Docling/torch/huggingface_hub see the offline + bundled-model
# settings from the very first import (these env vars are read at import time,
# so setting them inside pdf2txt.py after `import docling` would be too late).
import os
import sys

_base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
_models = os.path.join(_base, "models")

if os.path.isdir(_models):
    os.environ.setdefault("DOCLING_ARTIFACTS_PATH", _models)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

# Avoid the "OMP: Error #15 ... libiomp5 already initialized" crash.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
