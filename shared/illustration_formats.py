#!/usr/bin/env python3
"""Choose PGF illustration formats after SVGO, accounting for PDF features."""
import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile

from pypdf import PdfReader
from pypdf.generic import ContentStream

from convert_illustrations import read_manifest, read_render_cache_used


# Cairo emits native SVG filters for these PDF blend modes. The other PDF
# blend modes fall back to bitmap fragments, with visible seams/coarse edges.
SVG_BLEND_MODES = {'/Normal', '/Compatible', '/Multiply', '/Screen', '/Darken', '/Lighten'}
PDF_BLEND_MODES = SVG_BLEND_MODES | {
    '/Overlay', '/ColorDodge', '/ColorBurn', '/HardLight', '/SoftLight',
    '/Difference', '/Exclusion', '/Hue', '/Saturation', '/Color', '/Luminosity'}


def pdf_features(page):
    """Inspect executed resources, including nested forms, patterns and masks.

    Testing every entry in /Resources would flag unused resources shared by
    many manual pages. Follow content operators instead. Do not treat ordinary
    opacity, axial/radial gradients, image alpha or simple shadows as failures.
    """
    features = set()
    risks = set()
    visited = set()

    def shading(obj):
        kind = int(obj.get_object()['/ShadingType'])
        features.add(f'shading:{kind}')
        if kind not in (2, 3):
            risks.add(f'rasterized-shading:{kind}')

    def walk(obj, inherited_resources):
        obj = obj.get_object()
        resources = obj.get('/Resources', inherited_resources).get_object()
        key = (id(obj), id(resources))
        if key in visited:
            return
        visited.add(key)
        group = obj['/Group'] if '/Group' in obj else {}
        if group.get('/S') == '/Transparency':
            features.add('transparency-group')
            # bool(BooleanObject(False)) is True in pypdf; inspect its value.
            if getattr(group.get('/K'), 'value', False):
                # In the manual's knockout example, SVG loses the gradient
                # along the border. PNG preserves the PDF compositing result.
                risks.add('knockout-group')
        if obj.get('/Subtype') == '/Image':
            # Embedded bitmap alpha is preserved in SVG's embedded PNGs.
            return
        stream = obj.get_contents() if hasattr(obj, 'get_contents') else obj
        if stream is None:
            return
        for operands, operator in ContentStream(stream, page.pdf).operations:
            if operator == b'gs':
                state = resources['/ExtGState'][operands[0]]
                if '/ca' in state or '/CA' in state:
                    features.add('opacity')
                if '/BM' in state:
                    modes = state['/BM']
                    # A PDF array lists alternatives in preference order;
                    # Cairo supports all standard PDF blend modes.
                    mode = (next((mode for mode in modes if mode in PDF_BLEND_MODES), '/Normal')
                            if isinstance(modes, list) else modes)
                    features.add(f'blend-mode:{str(mode).lstrip("/")}')
                    if mode not in SVG_BLEND_MODES:
                        risks.add(f'rasterized-blend:{str(mode).lstrip("/")}')
                mask = state.get('/SMask')
                if mask is not None:
                    mask = mask.get_object()
                    if mask != '/None':
                        kind = mask.get('/S')
                        features.add(f'soft-mask:{str(kind).lstrip("/")}')
                        # Poppler samples luminosity/transfer masks into a
                        # low-resolution bitmap even for vector SVG output.
                        if kind == '/Luminosity' or mask.get('/TR', '/Identity') != '/Identity':
                            risks.add('rasterized-soft-mask')
                        walk(mask['/G'], resources)
            elif operator == b'Do':
                walk(resources['/XObject'][operands[0]], resources)
            elif operator == b'sh':
                shading(resources['/Shading'][operands[0]])
            elif operator in (b'scn', b'SCN') and operands and str(operands[-1]).startswith('/'):
                pattern = resources['/Pattern'][operands[-1]]
                if pattern['/PatternType'] == 1:
                    features.add('tiling-pattern')
                    walk(pattern, resources)
                else:
                    shading(pattern['/Shading'])

    walk(page, page['/Resources'])
    return sorted(features), sorted(risks)


def choose_format(svg_bytes, png_bytes, risks):
    if risks:
        return 'png', 'pdf-feature'
    if svg_bytes <= png_bytes:
        return 'svg', 'smaller-svg'
    return 'png', 'smaller-png'


def image_format(src, choices, force_svg=False):
    """Apply a report entry; preserve manual SVG overrides and other assets."""
    path = Path(src)
    if path.parent.name != 'pgfmanual-images' or path.suffix != '.svg':
        return src
    choice = choices[path.stem]  # Missing entries must fail, not silently guess.
    if force_svg or choice['format'] == 'svg':
        return src
    return str(path.with_suffix('.png'))


def select_formats(source, manifest, images, report):
    entries = read_manifest(manifest)
    _, used, cached = read_render_cache_used(source, entries)
    reader = None
    choices = {}
    for name, number in entries.items():
        if name in used:
            # Cached drawings in the document are PDF imports. Inspect the
            # original drawing page, just as the image converter does.
            original = PdfReader(cached['paths'][name])
            page = original.pages[0]
        else:
            if reader is None:
                reader = PdfReader(source)
            page = reader.pages[number - 1]
        features, risks = pdf_features(page)
        svg_bytes = (images / f'{name}.svg').stat().st_size
        png_bytes = (images / f'{name}.png').stat().st_size
        if not svg_bytes or not png_bytes:
            raise ValueError(f'Empty illustration output: {name}')
        format_, reason = choose_format(svg_bytes, png_bytes, risks)
        choices[name] = {'format': format_, 'reason': reason, 'pdf_features': features,
                         'svg_risks': risks, 'svg_bytes': svg_bytes, 'png_bytes': png_bytes}
    # Keep the previous report intact if any page/resource/image is invalid.
    with tempfile.NamedTemporaryFile(mode='w', dir=report.parent, delete=False) as stream:
        json.dump({'version': 1, 'images': choices}, stream, indent=2, sort_keys=True)
        stream.write('\n')
        temporary = Path(stream.name)
    temporary.replace(report)
    counts = Counter(choice['reason'] for choice in choices.values())
    print(f'Illustration formats: {dict(counts)} (before manual SVG overrides)')
    return choices


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('images', type=Path, help='directory of SVGs already optimized by SVGO, plus PNGs')
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    select_formats(args.source, args.manifest, args.images, args.report)


if __name__ == '__main__':
    main()
