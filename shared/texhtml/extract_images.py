#!/usr/bin/env python3
"""Turn the pages shipped out by tikzdev-capture.sty into cropped PNG/SVG images.

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
import argparse
import gzip
import hashlib
import importlib.metadata
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from convert_illustrations import Cache, page_bytes
from pypdf import PdfReader

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


def convert_uncached(pdf, entries, outdir):
    """Batch the missing PDF pages through the existing rendering pipeline."""
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
        if not keep:
            return {}
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
            # Cache both formats so publication can select one without exposing
            # placeholders or losing the SVG-verification decision.
            shutil.copy(svg, os.path.join(outdir, image_id + ".svg"))
            shutil.copy(png, os.path.join(outdir, image_id + ".png"))
            dims[image_id] = {"file": name, "width": w_pt * 4 / 3, "height": h_pt * 4 / 3}
            if diff is not None:
                dims[image_id]["svgdiff"] = round(diff, 1)
        if rejected:
            print(f"{len(rejected)} SVGs differ from the PDF, using PNG: {', '.join(rejected)}")
    with open(os.path.join(outdir, "dims.json"), "w") as f:
        json.dump(dims, f, indent=0)
    return dims


def conversion_signature():
    tools = {}
    for name, option in [("mutool", "-v"), ("gs", "--version"), ("pdfcrop", "--version"),
                         ("pdftex", "--version"), ("pdftocairo", "-v"), ("svgo", "--version"),
                         ("pngquant", "--version"), ("rsvg-convert", "--version")]:
        if shutil.which(name):
            result = subprocess.run([name, option], capture_output=True, text=True, check=False)
            tools[name] = result.stdout + result.stderr
        else:
            tools[name] = None
    versions = {}
    for name in ["pypdf", "numpy", "Pillow"]:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    material = {"pipeline": "texhtml-images-v1", "tools": tools, "python": versions,
                "source": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "margin": MARGIN, "max_factor": SVG_MAX_FACTOR, "max_diff": SVG_MAX_BLOCK_DIFF}
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).digest()


def read_entries(log):
    entries = {}
    for line in Path(log).read_text().splitlines():
        parts = line.split()
        if len(parts) != 2:
            if line.strip():
                raise ValueError("Invalid image record: " + line)
            continue
        name, number = parts
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in (".", "..") or not number.isdigit() or int(number) < 1:
            raise ValueError("Invalid image record: " + line)
        entries.setdefault(name, int(number))
    if not entries:
        raise ValueError("No captured images; refusing to replace existing output")
    return entries


def convert(pdf, log, outdir, cache_root):
    pdf, outdir, cache_root = Path(pdf), Path(outdir), Path(cache_root)
    if cache_root.resolve().is_relative_to(outdir.resolve()):
        raise ValueError("Image cache must be outside the published image directory")
    entries = read_entries(log)
    reader = PdfReader(pdf)
    signature = conversion_signature()
    cache = Cache(cache_root, (".json", ".svg", ".png"))
    keys = {}
    for name, number in entries.items():
        if number > len(reader.pages):
            raise ValueError(f"Missing PDF page {number} for {name}")
        keys[name] = hashlib.sha256(signature + page_bytes(reader.pages[number - 1])).hexdigest()
    valid = {key: cache.valid(key) for key in set(keys.values())}
    missing = {key: entries[name] for name, key in keys.items() if not valid[key]}
    print(f"Illustrations: {len(entries)} total, {sum(valid[k] for k in keys.values())} cached, "
          f"{len(missing)} unique pages to convert", flush=True)
    outdir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=outdir.parent) as tmp:
        tmp = Path(tmp)
        if missing:
            rendered = tmp / "rendered"
            dims = convert_uncached(str(pdf), list(missing.items()), str(rendered))
            for key in missing:
                info = dict(dims.get(key, {}))
                if info:
                    info["suffix"] = Path(info.pop("file")).suffix
                else:
                    info["empty"] = True
                    # Nonempty sentinels exist only inside the cache, never the
                    # published output. Empty captures remain absent as before.
                    (rendered / (key + ".svg")).write_bytes(b"empty capture")
                    (rendered / (key + ".png")).write_bytes(b"empty capture")
                (rendered / (key + ".json")).write_text(json.dumps(info))
                cache.store(key, rendered / key)
        staged = tmp / "images"
        staged.mkdir()
        restored = tmp / "restored"
        restored.mkdir()
        dims = {}
        for name, key in keys.items():
            cache.restore(key, restored, name)
            info = json.loads((restored / (name + ".json")).read_text())
            if info.pop("empty", False):
                continue
            suffix = info.pop("suffix")
            if suffix not in (".svg", ".png"):
                raise ValueError("Invalid cached image format")
            info["file"] = name + suffix
            shutil.copyfile(restored / info["file"], staged / info["file"])
            dims[name] = info
        (staged / "dims.json").write_text(json.dumps(dims, indent=0))
        previous = tmp / "previous"
        if outdir.exists():
            outdir.rename(previous)
        try:
            staged.rename(outdir)
        except BaseException:
            if previous.exists():
                previous.rename(outdir)
            raise
    print(f"Wrote {len(dims)} images to {outdir}")
    return {"total": len(entries), "converted": len(missing), "cached": len(entries) - sum(k in missing for k in keys.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("log", type=Path)
    parser.add_argument("outdir", type=Path)
    default = Path(os.environ.get("TIKZ_IMAGE_CACHE", Path(__file__).resolve().parents[2] / "build/image-cache")) / "texhtml"
    parser.add_argument("--cache", type=Path, default=default)
    args = parser.parse_args()
    convert(args.pdf, args.log, args.outdir, args.cache)


if __name__ == "__main__":
    main()
