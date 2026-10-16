#!/usr/bin/env python3
"""Turn the pages shipped out by tcbhtml.sty into cropped PNG/SVG images.

Usage: extract_images.py <pdf> <htmlimages log> <output dir>

Every image is produced both as SVG (MuPDF, then svgo if available) and as a
300dpi PNG (pdftocairo, then pngquant if available). Unlike tikz.dev, the SVG
is preferred: it stays sharp when zoomed and, as served gzipped, is smaller
than the PNG for most images. The PNG is used instead when

* the SVG does not render like the PDF (checked for every image by comparing
  rasterizations, see verify_svgs; MuPDF's SVG output gets a few shadings and
  soft masks wrong), or
* the gzipped SVG is more than SVG_MAX_FACTOR times larger (photos, ...).

pdftocairo's SVG output is not used: it renders most pages up to ~1% too
narrow. Writes dims.json with the display size of every image
(1pt = 4/3 CSS px) and the measured SVG difference.
"""
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

SVG_MAX_FACTOR = 2
SVG_MAX_BLOCK_DIFF = 60
MARGIN = 1  # pt, as in tikz.dev


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def verify_svgs(cropped, svgs, tmp):
    """For every SVG, the largest colour difference (0-255) between an 8x8
    pixel block of the SVG, rasterized by librsvg, and the same block of the
    PDF page rasterized by MuPDF, at 192dpi. Correct SVGs stay below ~40
    (anti-aliasing); broken shadings or soft masks give 100+. Returns None
    entries if rsvg-convert, numpy or Pillow are not available."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        np = None
    if np is None or not shutil.which("rsvg-convert"):
        print("warning: SVGs not verified (needs rsvg-convert, numpy, Pillow)")
        return [None] * len(svgs)
    refdir = os.path.join(tmp, "ref")
    os.makedirs(refdir)
    run(["mutool", "draw", "-q", "-r", "192", "-c", "rgb", "-o", os.path.join(refdir, "%d.png"), cropped])

    def one(n_svg):
        n, svg = n_svg
        ref = np.asarray(Image.open(os.path.join(refdir, f"{n}.png")).convert("RGB"), dtype=np.float32)
        h, w = ref.shape[0] // 8, ref.shape[1] // 8
        if h == 0 or w == 0:
            return 0.0
        out = os.path.join(refdir, f"svg-{n}.png")
        run(["rsvg-convert", "-w", str(ref.shape[1]), "-h", str(ref.shape[0]), "-b", "white", "-o", out, svg])
        got = np.asarray(Image.open(out).convert("RGB"), dtype=np.float32)
        d = (ref[:h * 8, :w * 8] - got[:h * 8, :w * 8]).reshape(h, 8, w, 8, 3).mean(axis=(1, 3))
        return float(np.abs(d).mean(axis=2).max())

    with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
        return list(pool.map(one, enumerate(svgs, 1)))


def main():
    pdf, log, outdir = sys.argv[1:4]
    entries = []
    seen = set()
    with open(log) as f:
        for line in f:
            parts = line.split()
            if len(parts) != 2 or parts[0] in seen:
                continue
            seen.add(parts[0])
            entries.append((parts[0], int(parts[1])))
    print(f"{len(entries)} images")
    if os.path.isdir(outdir):
        shutil.rmtree(outdir)
    os.makedirs(outdir)
    with tempfile.TemporaryDirectory() as tmp:
        # 1. collect the image pages into one PDF
        sel = os.path.join(tmp, "selected.pdf")
        pages = ",".join(str(p) for _, p in entries)
        run(["mutool", "merge", "-o", sel, pdf, pages])
        # 2. bounding boxes (to detect empty images)
        res = subprocess.run(["gs", "-q", "-dBATCH", "-dNOPAUSE", "-sDEVICE=bbox", sel],
                             capture_output=True, text=True)
        bboxes = re.findall(r"%%HiResBoundingBox: ([\d.\-]+) ([\d.\-]+) ([\d.\-]+) ([\d.\-]+)", res.stderr)
        assert len(bboxes) == len(entries), (len(bboxes), len(entries))
        keep = []
        for (image_id, _), bb in zip(entries, bboxes):
            x0, y0, x1, y1 = map(float, bb)
            if x1 - x0 < 0.5 or y1 - y0 < 0.5:
                continue
            keep.append((image_id, len(keep) + 1, x1 - x0 + 2 * MARGIN, y1 - y0 + 2 * MARGIN,
                         entries.index((image_id, _)) + 1))
        print(f"{len(entries) - len(keep)} empty images skipped")
        nonempty = os.path.join(tmp, "nonempty.pdf")
        run(["mutool", "merge", "-o", nonempty, sel, ",".join(str(k[4]) for k in keep)])
        # 3. crop
        cropped = os.path.join(tmp, "cropped.pdf")
        run(["pdfcrop", "--hires", "--margins", str(MARGIN), nonempty, cropped])
        # 4. PNGs (pdftocairo) and SVGs (MuPDF), each in one go
        run(["pdftocairo", "-png", "-transp", "-r", "300", cropped, os.path.join(tmp, "p")])
        digits = len(str(len(keep)))
        svgdir = os.path.join(tmp, "svg")
        os.makedirs(svgdir)
        run(["mutool", "draw", "-q", "-F", "svg", "-o", os.path.join(svgdir, "s-%d.svg"), cropped])
        svgs = [os.path.join(svgdir, f"s-{k[1]}.svg") for k in keep]
        if shutil.which("svgo"):
            run(["svgo", "--quiet", "--multipass", "-f", svgdir])
        pngs = []
        for k in keep:
            png = os.path.join(tmp, f"p-{k[1]:0{digits}d}.png")
            if not os.path.exists(png):
                png = os.path.join(tmp, f"p-{k[1]}.png")
            pngs.append(png)
        if shutil.which("pngquant"):
            with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
                list(pool.map(lambda p: subprocess.run(
                    ["pngquant", "--force", "--skip-if-larger", "--quality", "70-95", "--ext", ".png", p],
                    capture_output=True), pngs))
        # 5. check every SVG against a raster of the PDF page
        diffs = verify_svgs(cropped, svgs, tmp)
        dims = {}
        rejected = []
        for k, png, svg, diff in zip(keep, pngs, svgs, diffs):
            image_id, _, w_pt, h_pt, _ = k
            with open(svg, "rb") as f:
                svg_transfer = len(gzip.compress(f.read()))
            if diff is not None and diff > SVG_MAX_BLOCK_DIFF:
                rejected.append(f"{image_id} ({diff:.0f})")
                use_svg = False
            else:
                use_svg = svg_transfer <= SVG_MAX_FACTOR * os.path.getsize(png)
            name = image_id + (".svg" if use_svg else ".png")
            shutil.copy(svg if use_svg else png, os.path.join(outdir, name))
            dims[image_id] = {"file": name, "width": w_pt * 4 / 3, "height": h_pt * 4 / 3}
            if diff is not None:
                dims[image_id]["svgdiff"] = round(diff, 1)
        if rejected:
            print(f"{len(rejected)} SVGs differ from the PDF, using PNG: {', '.join(rejected)}")
    with open(os.path.join(outdir, "dims.json"), "w") as f:
        json.dump(dims, f, indent=0)
    print(f"Wrote {len(dims)} images to {outdir}")


if __name__ == "__main__":
    main()
