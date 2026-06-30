#!/usr/bin/env python3
"""Render a PPTX to PDF and PNG pages for visual QA."""
import argparse
import shutil
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx")
    parser.add_argument("outdir")
    args = parser.parse_args()

    pptx = Path(args.pptx).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    libreoffice = shutil.which("libreoffice") or shutil.which("soffice")
    if not libreoffice:
        raise SystemExit("LibreOffice/soffice not found")

    subprocess.run([
        libreoffice, "--headless", "--convert-to", "pdf", "--outdir", str(outdir), str(pptx)
    ], check=True)

    pdf = outdir / (pptx.stem + ".pdf")
    if shutil.which("pdftoppm") and pdf.exists():
        subprocess.run(["pdftoppm", "-png", str(pdf), str(outdir / "slide")], check=True)

    print(f"Rendered to {outdir}")


if __name__ == "__main__":
    main()
