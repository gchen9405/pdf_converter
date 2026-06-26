#!/usr/bin/env python3
"""pdf2txt -- batch-convert every PDF in a folder to .txt using IBM Docling.

Each input PDF produces one UTF-8 file with the same basename and a .txt
extension (report.pdf -> report.txt). By default the file CONTENT is Docling
**Markdown** (export_to_markdown), which preserves headings and tables, written
directly into the .txt file -- no intermediate .md file is created or renamed.
The .txt extension is intentional: downstream tools (e.g. a GraphRAG text
reader, which treats file contents as opaque) accept .txt only, and
markdown-inside-a-.txt ingests fine. Use --plain for plain text instead.

The frozen executable runs FULLY OFFLINE: all Docling model weights are bundled
inside it, so nothing is ever downloaded at run time.

Typical use (with the shipped executable):
    1. Put your PDFs in the `input` folder next to pdf2txt(.exe)
    2. Run pdf2txt(.exe)
    3. Collect the `.txt` files (Markdown content) from the `output` folder

CLI:
    pdf2txt [-i INPUT] [-o OUTPUT] [--recursive] [--ocr] [--plain]
            [--parser {pypdfium2,docling-parse}] [--skip-existing] [files ...]
"""
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Environment MUST be configured before importing docling / torch, because
# huggingface_hub and transformers read these variables at import time.
# (A PyInstaller runtime hook also sets these for the frozen exe; doing it here
# as well keeps `python pdf2txt.py` working when run from source.)
# ---------------------------------------------------------------------------
def _resolve_models_dir() -> Path:
    """Locate the bundled/pre-downloaded Docling model weights."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
        return base / "models"
    here = Path(__file__).resolve().parent
    for cand in (here / "models", here.parent / "models"):
        if cand.is_dir():
            return cand
    return here.parent / "models"  # default location (may not exist yet)


_MODELS_DIR = _resolve_models_dir()

# Guard against the "OMP: Error #15 ... libiomp5 already initialized" abort that
# happens when torch's bundled OpenMP collides with numpy/MKL's. Harmless if not.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

if _MODELS_DIR.is_dir():
    # Use the bundled weights and forbid any network access at run time.
    os.environ.setdefault("DOCLING_ARTIFACTS_PATH", str(_MODELS_DIR))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import argparse  # noqa: E402  (after env setup, intentionally)
import time  # noqa: E402
import traceback  # noqa: E402

__version__ = "1.0.0"


def _program_dir() -> Path:
    """Folder that holds the executable (for default input/output locations)."""
    if getattr(sys, "frozen", False):
        return Path(os.path.dirname(sys.executable))
    return Path.cwd()


def _find_pdfs(folder: Path, recursive: bool):
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(p for p in folder.glob(pattern) if p.is_file())


def _build_converter(use_ocr: bool, parser: str = "pypdfium2"):
    """Construct a Docling DocumentConverter wired to the local model weights."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.settings import settings
    from docling.document_converter import DocumentConverter, PdfFormatOption

    # Process one page at a time: caps peak memory (helps on modest RAM) and is
    # cheap insurance against the docling-parse memory growth that can throw
    # std::bad_alloc on large PDFs (docling issues #3671 / #3345).
    settings.perf.page_batch_size = 1

    artifacts = _MODELS_DIR if _MODELS_DIR.is_dir() else None

    opts = PdfPipelineOptions(do_ocr=use_ocr)
    if artifacts is not None:
        opts.artifacts_path = artifacts  # parent dir holding the model subfolders

    if use_ocr:
        from docling.datamodel.pipeline_options import EasyOcrOptions
        easy = EasyOcrOptions(lang=["en"], download_enabled=False)
        if artifacts is not None:
            easy.model_storage_directory = str(artifacts / "EasyOcr")
        opts.ocr_options = easy

    if parser == "docling-parse":
        # Higher-fidelity text cells, but its C++ parser can crash (std::bad_alloc)
        # on large/complex PDFs. Use only if pypdfium2 output is insufficient.
        fmt = PdfFormatOption(pipeline_options=opts)
    else:
        # Default: pypdfium2 backend -- robust on heavy PDFs, no std::bad_alloc,
        # and the layout/table ML models (headings, tables) run regardless.
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
        fmt = PdfFormatOption(pipeline_options=opts, backend=PyPdfiumDocumentBackend)

    return DocumentConverter(format_options={InputFormat.PDF: fmt})


def _gather_inputs(args):
    """Return (list_of_pdfs, base_dir_or_None) honoring positional paths/--input."""
    if args.paths:
        pdfs = []
        for path in args.paths:
            if path.is_dir():
                pdfs += _find_pdfs(path, args.recursive)
            elif path.is_file() and path.suffix.lower() == ".pdf":
                pdfs.append(path)
            else:
                print("[warn] skipping (not a PDF): %s" % path, file=sys.stderr)
        return pdfs, None

    if not args.input.exists():
        args.input.mkdir(parents=True, exist_ok=True)
        print("Created input folder:\n   %s" % args.input.resolve())
        print("Put your PDF files in there, then run this program again.")
        return [], args.input
    return _find_pdfs(args.input, args.recursive), args.input


def _output_path(pdf: Path, base_dir, out_root: Path, ext: str) -> Path:
    """Mirror the input subfolder layout under the output root when possible."""
    if base_dir is not None:
        try:
            rel = pdf.relative_to(base_dir)
            return (out_root / rel).with_suffix(ext)
        except ValueError:
            pass
    return out_root / (pdf.stem + ext)


def main(argv=None) -> int:
    program_dir = _program_dir()
    p = argparse.ArgumentParser(
        prog="pdf2txt",
        description="Convert every PDF in a folder to .txt using IBM Docling (offline).",
    )
    p.add_argument("-i", "--input", type=Path, default=program_dir / "input",
                   help="Folder containing PDFs (default: ./input next to the program).")
    p.add_argument("-o", "--output", type=Path, default=program_dir / "output",
                   help="Folder for the .txt files (default: ./output next to the program).")
    p.add_argument("paths", nargs="*", type=Path,
                   help="Optional explicit PDF files/folders (overrides --input).")
    p.add_argument("-r", "--recursive", action="store_true",
                   help="Also convert PDFs in subfolders.")
    p.add_argument("--ocr", action="store_true",
                   help="Run OCR on scanned/image-only PDFs (needs an OCR-enabled build).")
    p.add_argument("--plain", action="store_true",
                   help="Write plain text instead of the default Docling Markdown "
                        "(output always keeps the .txt extension either way).")
    p.add_argument("--parser", choices=["pypdfium2", "docling-parse"],
                   default="pypdfium2",
                   help="PDF parser backend. 'pypdfium2' (default) is robust on "
                        "large/complex PDFs. 'docling-parse' gives slightly richer "
                        "text cells but can crash (std::bad_alloc) on heavy PDFs.")
    p.add_argument("--skip-existing", action="store_true",
                   help="Skip PDFs whose output file already exists.")
    p.add_argument("--verbose", action="store_true",
                   help="Print full tracebacks for files that fail.")
    p.add_argument("--version", action="version", version="pdf2txt %s" % __version__)
    args = p.parse_args(argv)

    ocr_available = (_MODELS_DIR / "EasyOcr").is_dir()
    use_ocr = bool(args.ocr and ocr_available)
    if args.ocr and not ocr_available:
        print("[warn] --ocr requested, but this build has no OCR model bundled; "
              "continuing WITHOUT OCR. Rebuild with --with-ocr to enable it.",
              file=sys.stderr)

    pdfs, base_dir = _gather_inputs(args)
    if not pdfs:
        where = ", ".join(map(str, args.paths)) if args.paths else str(args.input)
        print("No PDF files found in: %s" % where)
        return 0

    args.output.mkdir(parents=True, exist_ok=True)
    # Always .txt: downstream accepts only .txt. Markdown content lives INSIDE
    # the .txt file -- no intermediate .md file is ever written.
    ext = ".txt"

    print("pdf2txt %s" % __version__)
    print("  PDFs to convert : %d" % len(pdfs))
    print("  Output folder   : %s" % args.output.resolve())
    print("  OCR             : %s" % ("on" if use_ocr else "off"))
    print("  Parser          : %s" % args.parser)
    print("  Content         : %s (written to .txt files)"
          % ("plain text" if args.plain else "Docling Markdown"))
    print("Loading Docling models (the first run can take ~10-30s) ...", flush=True)

    t0 = time.time()
    converter = _build_converter(use_ocr, args.parser)
    print("Models loaded in %.1fs.\n" % (time.time() - t0), flush=True)

    ok = skipped = 0
    failures = []
    for idx, pdf in enumerate(pdfs, 1):
        out_path = _output_path(pdf, base_dir, args.output, ext)
        if args.skip_existing and out_path.exists():
            skipped += 1
            print("[%d/%d] skip (exists): %s" % (idx, len(pdfs), pdf.name))
            continue
        print("[%d/%d] %s ... " % (idx, len(pdfs), pdf.name), end="", flush=True)
        t = time.time()
        try:
            result = converter.convert(str(pdf))
            doc = result.document
            # Markdown by default (keeps headings/tables); --plain for plain text.
            # The string is written straight into the .txt file as-is.
            text = doc.export_to_text() if args.plain else doc.export_to_markdown()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text, encoding="utf-8")
            ok += 1
            print("done (%.1fs, %d chars)" % (time.time() - t, len(text)))
        except Exception as exc:  # one bad PDF must not stop the batch
            failures.append((pdf, exc))
            print("FAILED: %s" % exc)
            if args.verbose:
                traceback.print_exc(file=sys.stderr)

    print("\nSummary: %d converted, %d skipped, %d failed (of %d)."
          % (ok, skipped, len(failures), len(pdfs)))
    if failures:
        print("Failed files:")
        for pdf, exc in failures:
            print("  - %s: %s" % (pdf.name, exc))
    return 0 if not failures else 1


if __name__ == "__main__":
    # MUST be the first thing in the main guard. Inside a PyInstaller-frozen
    # app, worker/spawned processes re-launch the executable with internal
    # interpreter flags (e.g. -B -S -I -c ...); freeze_support() intercepts
    # those so they run as multiprocessing workers instead of hitting argparse
    # (which otherwise errors with "unrecognized arguments: -B -S -I -c").
    import multiprocessing
    multiprocessing.freeze_support()
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
