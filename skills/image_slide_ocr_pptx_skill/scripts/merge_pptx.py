#!/usr/bin/env python3
"""Merge PPTX files in order.

Requires pptxcompose for robust slide relationship copying:
    pip install pptxcompose
"""
import argparse
from pathlib import Path

from pptx import Presentation
try:
    from pptxcompose.composer import Composer
except Exception as exc:  # pragma: no cover
    raise SystemExit("Please install pptxcompose: pip install pptxcompose") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", help="Merged PPTX output path")
    parser.add_argument("inputs", nargs="+", help="Input PPTX files in order")
    args = parser.parse_args()

    if not args.inputs:
        raise SystemExit("No input PPTX files")

    master = Presentation(args.inputs[0])
    composer = Composer(master)
    for path in args.inputs[1:]:
        composer.append(Presentation(path))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    composer.save(output)
    print(output)


if __name__ == "__main__":
    main()
