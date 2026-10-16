#!/usr/bin/env python3
"""Crop a lwarp image, keeping blank transport pages small enough to render."""
import subprocess
import sys


def crop(source, destination):
    command = ["pdfcrop", "--margins", "1", "--hires", source, destination]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        sys.stderr.write(result.stdout + result.stderr)
        return result.returncode
    if "Empty Bounding Box" in result.stdout + result.stderr:
        # pdfcrop otherwise keeps the enormous lwarp transport page, which
        # exceeds Cairo's raster size limit even though there is no ink.
        print(f"Blank image: {source}; using a minimal canvas", file=sys.stderr)
        result = subprocess.run(
            ["pdfcrop", "--bbox", "0 0 1 1", "--margins", "1", source, destination],
            capture_output=True, text=True,
        )
        if result.returncode:
            sys.stderr.write(result.stdout + result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(crop(*sys.argv[1:]))
