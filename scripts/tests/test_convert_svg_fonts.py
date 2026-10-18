"""Keep glyph metrics, text layout and animation targets when replacing SVG fonts."""
import base64
from io import BytesIO
from pathlib import Path
import re
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import convert_svg_fonts as fonts
    from fontTools.ttLib import TTFont
except ImportError:
    fonts = None


FIXTURE = '''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<defs><font id="nf0" horiz-adv-x="549">
<font-face font-family="nf0" units-per-em="1000" ascent="1127" descent="290"/>
<glyph unicode="o" horiz-adv-x="500" d="M28 0L471 0L471 448L28 448Z"/>
<glyph unicode="ﬀ" d="M10 0L400 0L400 600L10 600Z"/>
</font></defs>
<style>text.f0 {font-family:nf0;font-size:9.96264px}</style>
<g id="moving"><text class="f0" x="35.7" y="35.7">Mo<tspan x="50.1">on</tspan></text></g>
<animateMotion xlink:href="#moving" dur="2s" path="M0 0L10 0"/>
</svg>'''


@unittest.skipUnless(fonts, 'requires fonttools')
class ConversionTests(unittest.TestCase):
    def test_font_metrics_unicode_and_outlines_survive(self):
        converted = fonts.convert(FIXTURE)
        encoded = re.search(r'data:font/woff;base64,([^)]*)', converted)[1]
        with TTFont(BytesIO(base64.b64decode(encoded))) as font:
            self.assertEqual(font.flavor, 'woff')
            self.assertEqual(font['head'].unitsPerEm, 1000)
            self.assertEqual(font['hhea'].ascent, 1127)
            self.assertEqual(font['hhea'].descent, -290)
            cmap = font.getBestCmap()
            self.assertEqual(set(cmap), {ord('o'), ord('ﬀ')})
            self.assertEqual(font['hmtx'][cmap[ord('o')]], (500, 28))
            self.assertEqual(font['hmtx'][cmap[ord('ﬀ')]], (549, 10))
            from fontTools.pens.boundsPen import BoundsPen
            pen = BoundsPen(font.getGlyphSet())
            font.getGlyphSet()[cmap[ord('o')]].draw(pen)
            self.assertEqual(pen.bounds, (28, 0, 471, 448))

    def test_text_positions_styles_and_smil_are_unchanged(self):
        converted = fonts.convert(FIXTURE)
        ns = {'s': 'http://www.w3.org/2000/svg'}
        before, after = ET.fromstring(FIXTURE), ET.fromstring(converted)
        for tag in ('text', 'tspan', 'g', 'animateMotion'):
            self.assertEqual([ET.tostring(e) for e in before.findall('.//s:' + tag, ns)],
                             [ET.tostring(e) for e in after.findall('.//s:' + tag, ns)])
        self.assertIsNone(after.find('.//s:font', ns))
        self.assertIn('text.f0 {font-family:nf0;font-size:9.96264px}', converted)

    def test_conversion_is_reproducible_and_idempotent(self):
        result = fonts.convert(FIXTURE)
        self.assertEqual(fonts.convert(FIXTURE), result)
        self.assertEqual(fonts.convert(result), result)
        self.assertEqual(fonts.convert('<svg/>'), '<svg/>')

    def test_unsupported_font_features_fail_instead_of_losing_spacing(self):
        unsupported = FIXTURE.replace('</font>', '<hkern u1="o" u2="o" k="20"/></font>')
        with self.assertRaisesRegex(ValueError, 'unsupported SVG font element'):
            fonts.convert(unsupported)


class PublishedFontTests(unittest.TestCase):
    def test_standalone_exports_no_longer_depend_on_svg_fonts(self):
        directory = Path(__file__).resolve().parents[2] / 'pgf/standalone'
        count = 0
        for path in directory.glob('*.svg'):
            source = path.read_text()
            self.assertNotRegex(source, r'<(?:font|font-face)\b', path.name)
            for encoded in re.findall(r'data:font/woff;base64,([^)]*)', source):
                self.assertEqual(base64.b64decode(encoded)[:4], b'wOFF', path.name)
                count += 1
        self.assertGreater(count, 0)


if __name__ == '__main__':
    unittest.main()
