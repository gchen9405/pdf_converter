#!/usr/bin/env python3
"""Pre-download Docling model weights into a local folder for offline bundling.

Run INSIDE the build venv (build.py does this automatically):

    python prefetch_models.py --out <dir> [--ocr]

Downloads only what the default PDF->text pipeline needs (document layout +
table-structure recognition). With --ocr it also fetches the EasyOCR weights so
scanned/image-only PDFs can be converted fully offline.
"""
import argparse
from pathlib import Path

# Make HTTPS verification use the OS (Windows/macOS) trust store instead of the
# bundled certifi list. On corporate networks that do TLS inspection, the proxy
# re-signs traffic with a corporate root CA that lives in the OS trust store
# (the same one your browser and pip already trust) but NOT in certifi -- so
# without this, model downloads from the HuggingFace Hub fail with
# "SSL: CERTIFICATE_VERIFY_FAILED". No-op if truststore isn't installed.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-download Docling model weights.")
    ap.add_argument("--out", required=True, type=Path,
                    help="Destination directory for the model weights.")
    ap.add_argument("--ocr", action="store_true",
                    help="Also download EasyOCR weights (for scanned PDFs).")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    # Imported here so a missing/old install gives a clear error instead of a
    # module-level ImportError before argparse can show usage.
    from docling.utils.model_downloader import download_models

    print("Downloading Docling models into:\n   %s\n" % args.out.resolve(), flush=True)
    download_models(
        output_dir=args.out,
        progress=True,
        force=False,
        with_layout=True,            # always needed (page layout + reading order)
        with_tableformer=True,       # table-structure recognition (default pipeline)
        with_code_formula=False,     # enrichment models -- off by default, skip
        with_picture_classifier=False,
        with_rapidocr=False,         # we use EasyOCR for the optional OCR path
        with_easyocr=args.ocr,       # only when an OCR build is requested
    )

    print("\nDone. Model folder now contains:")
    for child in sorted(args.out.iterdir()):
        kind = "dir " if child.is_dir() else "file"
        print("   [%s] %s" % (kind, child.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
