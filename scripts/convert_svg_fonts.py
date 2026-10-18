#!/usr/bin/env python3
"""Replace dvisvgm's legacy SVG fonts with self-contained WOFF fonts.

Run once on existing exports: python3 scripts/convert_svg_fonts.py pgf/standalone/*.svg
Requires fonttools. Text, explicit kerning positions and SMIL animations stay intact.
"""
import argparse
import base64
import hashlib
from io import BytesIO
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.svgLib.path import parse_path


SVG_FONT = re.compile(r'<font\b[^>]*>.*?</font>', re.S)


def woff_font(font):
    """Keep the SVG font's cubic outlines, advances, Unicode map and metrics."""
    if any(child.tag not in ('font-face', 'glyph') for child in font):
        raise ValueError('unsupported SVG font element')
    face = font.find('font-face')
    family = face.attrib['font-family']
    units = int(face.attrib['units-per-em'])
    ascent, descent = int(face.attrib['ascent']), int(face.attrib['descent'])
    default_width = int(font.attrib['horiz-adv-x'])
    charstrings, metrics, cmap = {}, {}, {}
    pen = T2CharStringPen(default_width, None)
    charstrings['.notdef'] = pen.getCharString()
    metrics['.notdef'] = (default_width, 0)
    for glyph in font.findall('glyph'):
        char = glyph.attrib['unicode']
        if len(char) != 1 or ord(char) in cmap:
            raise ValueError('unsupported ligature or duplicate Unicode glyph')
        name = f'uni{ord(char):04X}'
        width = int(glyph.get('horiz-adv-x', default_width))
        path = glyph.get('d', '')
        pen = T2CharStringPen(width, None)
        bounds = BoundsPen(None)
        parse_path(path, pen)
        parse_path(path, bounds)
        charstrings[name] = pen.getCharString()
        metrics[name] = (width, round(bounds.bounds[0]) if bounds.bounds else 0)
        cmap[ord(char)] = name

    builder = FontBuilder(units, isTTF=False)
    builder.setupGlyphOrder(list(charstrings))
    builder.setupCharacterMap(cmap)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=ascent, descent=-descent)
    # A distinct internal name avoids font-cache collisions between SVG files.
    identity = 'TikzSvg' + hashlib.sha256(ET.tostring(font)).hexdigest()[:16]
    builder.setupNameTable(dict(familyName=family, styleName='Regular',
                               uniqueFontIdentifier=identity, fullName=identity, psName=identity))
    builder.setupOS2(sTypoAscender=ascent, sTypoDescender=-descent,
                     usWinAscent=ascent, usWinDescent=descent)
    builder.setupPost()
    builder.setupCFF(identity, {}, charstrings, {})
    # Fixed timestamps make repeated conversions byte-for-byte reproducible.
    builder.font['head'].created = builder.font['head'].modified = 2082844800
    builder.font.recalcTimestamp = False
    builder.font.flavor = 'woff'
    output = BytesIO()
    builder.font.save(output)
    return family, output.getvalue()


def convert(source):
    rules = []

    def replace(match):
        family, data = woff_font(ET.fromstring(match[0]))
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', family):
            raise ValueError('unsupported SVG font family name')
        encoded = base64.b64encode(data).decode('ascii')
        rules.append(f'@font-face{{font-family:{family};src:url(data:font/woff;base64,{encoded}) format("woff")}}')
        return ''

    converted = SVG_FONT.sub(replace, source)
    if not rules:
        return source
    css = '<style type="text/css"><![CDATA[\n' + '\n'.join(rules) + '\n]]></style>'
    # Keep existing style rules, IDs, text/tspan positions and animation markup.
    if converted.count('</defs>') != 1:
        raise ValueError('expected one SVG definitions block')
    return converted.replace('</defs>', css + '\n</defs>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    args = parser.parse_args()
    changed = 0
    before = after = 0
    for path in args.files:
        source = path.read_text()
        converted = convert(source)
        if converted != source:
            path.write_text(converted)
            changed += 1
            before += len(source.encode())
            after += len(converted.encode())
    print(f'Converted {changed} SVGs: {before:,} -> {after:,} bytes')


if __name__ == '__main__':
    main()
