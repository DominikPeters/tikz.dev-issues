"""PDF feature detection and PGF's optimized-size image policy."""
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, BooleanObject, DecodedStreamObject,
                           DictionaryObject, FloatObject, NameObject, NumberObject)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shared'))
import illustration_formats as formats


def dictionary(**values):
    return DictionaryObject({NameObject('/' + key): value for key, value in values.items()})


def stream(data, **values):
    obj = DecodedStreamObject()
    obj.set_data(data.encode())
    obj.update(dictionary(**values))
    return obj


class FormatTests(unittest.TestCase):
    def fixture(self, content, resources, **values):
        writer = PdfWriter()
        page = writer.add_blank_page(100, 100)
        page.update(dictionary(Contents=stream(content), Resources=resources, **values))
        result = BytesIO()
        writer.write(result)
        return PdfReader(result).pages[0]

    def test_smaller_format_wins_with_svg_on_ties(self):
        self.assertEqual(formats.choose_format(100, 101, []), ('svg', 'smaller-svg'))
        self.assertEqual(formats.choose_format(100, 100, []), ('svg', 'smaller-svg'))
        self.assertEqual(formats.choose_format(101, 100, []), ('png', 'smaller-png'))
        self.assertEqual(formats.choose_format(1, 1000, ['knockout-group']), ('png', 'pdf-feature'))

    def test_ordinary_opacity_gradients_and_supported_blends_are_safe(self):
        for mode in formats.SVG_BLEND_MODES:
            with self.subTest(mode=mode):
                page = self.fixture('/safe gs /gradient sh', dictionary(
                    ExtGState=dictionary(safe=dictionary(ca=FloatObject(.5), BM=NameObject(mode))),
                    Shading=dictionary(gradient=dictionary(ShadingType=NumberObject(2)))))
                features, risks = formats.pdf_features(page)
                self.assertIn('opacity', features)
                self.assertIn('shading:2', features)
                self.assertEqual(risks, [])

    def test_unused_advanced_resources_do_not_force_png(self):
        page = self.fixture('0 0 10 10 re f', dictionary(
            ExtGState=dictionary(unused=dictionary(BM=NameObject('/Overlay'))),
            Shading=dictionary(unused=dictionary(ShadingType=NumberObject(1))),
            XObject=dictionary(unused=stream('', Subtype=NameObject('/Form'),
                Group=dictionary(S=NameObject('/Transparency'), K=BooleanObject(True))))))
        self.assertEqual(formats.pdf_features(page), ([], []))

    def test_blend_alternatives_use_the_first_supported_pdf_mode(self):
        page = self.fixture('/blend gs', dictionary(ExtGState=dictionary(blend=dictionary(
            BM=ArrayObject([NameObject('/Unknown'), NameObject('/Multiply'), NameObject('/Overlay')])))))
        self.assertEqual(formats.pdf_features(page), (['blend-mode:Multiply'], []))

    def test_bitmap_alpha_does_not_force_a_raster_fallback(self):
        bitmap = stream('', Subtype=NameObject('/Image'), SMask=stream(''))
        page = self.fixture('/image Do', dictionary(XObject=dictionary(image=bitmap)))
        self.assertEqual(formats.pdf_features(page), ([], []))

    def test_knockout_detection_in_nested_form_and_page_groups(self):
        for knockout in (False, True):
            group = dictionary(S=NameObject('/Transparency'), K=BooleanObject(knockout))
            resources = dictionary(XObject=dictionary(form=stream(
                '', Subtype=NameObject('/Form'), Group=group)))
            for page in (self.fixture('/form Do', resources), self.fixture('', dictionary(), Group=group)):
                _, risks = formats.pdf_features(page)
                self.assertEqual(risks, ['knockout-group'] if knockout else [])

    def test_luminosity_masks_and_transfer_functions_force_png(self):
        for kind, transfer, expected in (
                ('/Luminosity', '/Identity', True), ('/Alpha', '/Identity', False),
                ('/Alpha', '/CustomTransfer', True)):
            with self.subTest(kind=kind, transfer=transfer):
                mask = dictionary(S=NameObject(kind), TR=NameObject(transfer), G=stream(''))
                page = self.fixture('/masked gs /reset gs', dictionary(ExtGState=dictionary(
                    masked=dictionary(SMask=mask), reset=dictionary(SMask=NameObject('/None')))))
                _, risks = formats.pdf_features(page)
                self.assertEqual(risks, ['rasterized-soft-mask'] if expected else [])

    def test_risky_blends_and_shadings_inside_patterns_are_detected(self):
        pattern = stream('/blend gs /mesh sh', PatternType=NumberObject(1), Resources=dictionary(
            ExtGState=dictionary(blend=dictionary(BM=NameObject('/Overlay'))),
            Shading=dictionary(mesh=dictionary(ShadingType=NumberObject(6)))))
        page = self.fixture('/Pattern cs /p scn', dictionary(Pattern=dictionary(p=pattern)))
        features, risks = formats.pdf_features(page)
        self.assertIn('tiling-pattern', features)
        self.assertEqual(risks, ['rasterized-blend:Overlay', 'rasterized-shading:6'])

    def test_recursive_form_resources_terminate(self):
        form = stream('/self Do', Subtype=NameObject('/Form'))
        writer = PdfWriter()
        ref = writer._add_object(form)
        form[NameObject('/Resources')] = dictionary(XObject=dictionary(self=ref))
        page = writer.add_blank_page(100, 100)
        page.update(dictionary(Contents=stream('/self Do'), Resources=form['/Resources']))
        result = BytesIO()
        writer.write(result)
        self.assertEqual(formats.pdf_features(PdfReader(result).pages[0]), ([], []))

    def test_reports_use_cached_original_pages_and_current_file_sizes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'manual.pdf'
            writer = PdfWriter()
            writer.add_blank_page(100, 100)
            writer.write(source)
            manifest = root / 'images.txt'
            manifest.write_text('|1|false|image-1|\n|end|end|end|\n')
            key = 'a' * 64 + '-1'
            cache = source.with_suffix('.render-cache')
            cache.mkdir()
            original = PdfWriter()
            original.add_page(self.fixture('', dictionary(), Group=dictionary(
                S=NameObject('/Transparency'), K=BooleanObject(True))))
            original.write(cache / f'{key}.pdf')
            source.with_suffix('.render-cache-used.jsonl').write_text(
                json.dumps({'name': 'image-1', 'key': key}) + '\n')
            (root / 'image-1.svg').write_bytes(b'svg')
            (root / 'image-1.png').write_bytes(b'larger png')
            report = root / 'formats.json'
            entry = formats.select_formats(source, manifest, root, report)['image-1']
            self.assertEqual(entry['format'], 'png')
            self.assertEqual(entry['svg_risks'], ['knockout-group'])
            self.assertEqual(entry['svg_bytes'], 3)
            self.assertEqual(json.loads(report.read_text())['images']['image-1'], entry)
            # An invalid output must not replace a successful report.
            previous = report.read_bytes()
            (root / 'image-1.png').write_bytes(b'')
            with self.assertRaisesRegex(ValueError, 'Empty illustration'):
                formats.select_formats(source, manifest, root, report)
            self.assertEqual(report.read_bytes(), previous)

    def test_html_policy_preserves_overrides_and_unrelated_assets(self):
        choices = {'image-1': {'format': 'png'}}
        src = 'pgfmanual-images/image-1.svg'
        self.assertEqual(formats.image_format(src, choices), 'pgfmanual-images/image-1.png')
        self.assertEqual(formats.image_format(src, choices, force_svg=True), src)
        self.assertEqual(formats.image_format('standalone/diagram.svg', choices), 'standalone/diagram.svg')
        with self.assertRaises(KeyError):
            formats.image_format('pgfmanual-images/missing.svg', choices)


if __name__ == '__main__':
    unittest.main()
