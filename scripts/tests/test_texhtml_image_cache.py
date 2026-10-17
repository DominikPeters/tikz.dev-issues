"""Persistent captures survive page renumbering and repair damaged entries."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'shared'))
from texhtml import extract_images as images


class CaptureCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pdf = self.root / 'input.pdf'
        self.log = self.root / 'input.htmlimages'
        self.out = self.root / 'images'
        self.cache = self.root / 'cache'
        self.write_pdf(['first', 'second'])
        self.log.write_text('example-1 1\nexample-2 2\n')

    def write_pdf(self, contents):
        writer = PdfWriter()
        for content in contents:
            page = writer.add_blank_page(100, 100)
            stream = DecodedStreamObject()
            stream.set_data(content.encode())
            page[NameObject('/Contents')] = writer._add_object(stream)
        writer.write(self.pdf)

    def batch(self, pdf, entries, outdir):
        out = Path(outdir)
        out.mkdir()
        result = {}
        for name, page in entries:
            for suffix in ['.png', '.svg']:
                (out / (name + suffix)).write_bytes((name + suffix).encode())
            result[name] = {'file': name + '.svg', 'width': 100, 'height': 80, 'svgdiff': 0.0}
        return result

    def convert(self, signature=b'tools-v1', batch=None):
        with patch.object(images, 'conversion_signature', return_value=signature), \
             patch.object(images, 'convert_uncached', side_effect=batch or self.batch):
            return images.convert(self.pdf, self.log, self.out, self.cache)

    def test_warm_cache_does_not_render_and_renumbering_keeps_hits(self):
        self.assertEqual(self.convert()['converted'], 2)
        first = (self.out / 'example-1.svg').read_bytes()
        self.write_pdf(['unrelated new page', 'first', 'second'])
        self.log.write_text('renamed-1 2\nrenamed-2 3\n')
        result = self.convert(batch=lambda *a: self.fail('Unchanged captures rendered again'))
        self.assertEqual(result['cached'], 2)
        self.assertEqual((self.out / 'renamed-1.svg').read_bytes(), first)
        self.assertFalse((self.out / 'example-1.svg').exists())

    def test_only_changed_or_corrupt_images_are_rebuilt(self):
        self.convert()
        self.write_pdf(['changed', 'second'])
        self.assertEqual(self.convert()['converted'], 1)
        key = (self.out / 'example-1.svg').read_text().removesuffix('.svg')
        (self.cache / 'objects' / key[:2] / key / 'image.png').write_bytes(b'corrupt')
        self.assertEqual(self.convert()['converted'], 1)
        used = list(self.cache.glob('objects/*/*/image.svg'))
        for path in used:
            path.unlink()
        self.assertEqual(self.convert()['converted'], 2)
        self.assertEqual(self.convert(signature=b'tools-v2')['converted'], 2)

    def test_empty_captures_are_cached_but_never_published(self):
        result = self.convert(batch=lambda pdf, entries, out: (Path(out).mkdir() or {}))
        self.assertEqual(result['converted'], 2)
        self.assertEqual(list(self.out.glob('*.svg')), [])
        self.assertEqual(self.convert(batch=lambda *a: self.fail('Empty capture rendered again'))['cached'], 2)

    def test_failed_render_keeps_previous_output(self):
        self.convert()
        before = (self.out / 'example-1.svg').read_bytes()
        self.write_pdf(['changed', 'second'])
        with self.assertRaisesRegex(RuntimeError, 'render failed'):
            self.convert(batch=lambda *a: (_ for _ in ()).throw(RuntimeError('render failed')))
        self.assertEqual((self.out / 'example-1.svg').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
