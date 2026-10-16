"""Cache correctness and failure behavior without requiring TeX/rendering tools.

Run: python3 -m unittest discover -s tests
"""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, FloatObject, NameObject, NumberObject

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shared'))
import convert_illustrations as images


class IllustrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'input.pdf'
        self.manifest = self.root / 'images.txt'
        self.output = self.root / 'images'
        self.cache = self.root / 'cache'
        self.write_pdf()
        self.manifest.write_text('|1|false|image-1|\n|end|end|end|\n')

    def write_pdf(self, color='1 0 0', metadata='first', resource=1, insert=False):
        writer = PdfWriter()
        if insert:
            writer.add_blank_page(100, 100)
        page = writer.add_blank_page(100, 100)
        stream = DecodedStreamObject()
        stream.set_data(f'q {color} rg 10 10 20 20 re f Q'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Test'): NumberObject(resource)})
        writer.add_metadata({'/CreationDate': metadata})
        writer.write(self.source)

    def write_single_pdf(self, path, color):
        writer = PdfWriter()
        page = writer.add_blank_page(100, 100)
        stream = DecodedStreamObject()
        stream.set_data(f'q {color} rg 10 10 20 20 re f Q'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
        writer.write(path)

    @staticmethod
    def fake_batch(pdf, items, directory, cache, magick):
        for _, key in items:
            stem = directory / key
            for suffix in cache.suffixes:
                Path(str(stem) + suffix).write_bytes((key + suffix).encode())
            cache.store(key, stem)
        return len(items)

    def convert(self, signature='tools-v1', **options):
        with patch.object(images, 'conversion_signature', return_value=signature), \
             patch.object(images, 'convert_batch', side_effect=self.fake_batch), \
             redirect_stdout(StringIO()):
            return images.convert(self.source, self.manifest, self.output, self.cache, **options)

    def test_metadata_and_page_numbers_do_not_invalidate_content(self):
        self.assertEqual(self.convert()['converted'], 1)
        original = (self.output / 'image-1.png').read_bytes()
        self.assertEqual((self.output / 'image-1.png').stat().st_mode & 0o777, 0o644)
        self.write_pdf(metadata='different date', insert=True)
        self.manifest.write_text('|2|false|renamed|\n|end|end|end|\n')
        result = self.convert()
        self.assertEqual(result['cached'], 1)
        self.assertEqual((self.output / 'renamed.png').read_bytes(), original)

    def test_resource_matrix_precision_is_preserved(self):
        writer = PdfWriter()
        page = writer.add_blank_page(100, 100)
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/TestMatrix'): FloatObject('0.1234567890123456')})
        self.assertIn(b'0.1234567890123456', images.page_bytes(page))

    def test_bounding_boxes_use_separate_ghostscript_processes(self):
        log = self.root / 'calls'
        executable = self.root / 'fake-gs'
        executable.write_text(
            '#!/usr/bin/env python3\nimport os, sys\n'
            f'with open({str(log)!r}, "a") as f:\n'
            '    f.write(str(os.getpid()) + " " + sys.argv[-1] + "\\n")\n'
            'raise SystemExit(9 if "broken" in sys.argv[-1] else 0)\n')
        executable.chmod(0o755)
        pages = [self.root / 'first.pdf', self.root / 'second.pdf']
        wrapper = images.ghostscript_wrapper(self.root, pages, executable)
        subprocess.run([str(wrapper), '-sDEVICE=bbox', '-f', 'batch.pdf'], check=True)
        calls = [line.split() for line in log.read_text().splitlines()]
        self.assertEqual([call[1] for call in calls], list(map(str, pages)))
        self.assertNotEqual(calls[0][0], calls[1][0])
        wrapper = images.ghostscript_wrapper(self.root, [self.root / 'broken.pdf'], executable)
        self.assertEqual(subprocess.run([str(wrapper), '-sDEVICE=bbox', 'batch.pdf']).returncode, 9)

    def test_drawing_resources_and_toolchain_each_invalidate(self):
        self.convert()
        self.write_pdf(color='0 1 0')
        self.assertEqual(self.convert()['converted'], 1)
        self.write_pdf(color='0 1 0', resource=2)
        self.assertEqual(self.convert()['converted'], 1)
        self.assertEqual(self.convert(signature='tools-v2')['converted'], 1)

    def test_partial_or_corrupt_cache_entry_is_rebuilt(self):
        self.convert()
        cached_png = next((self.cache / 'objects').rglob('image.png'))
        cached_png.write_bytes(b'corruption')
        self.assertEqual(self.convert()['converted'], 1)
        cached_png.unlink()
        self.assertEqual(self.convert()['converted'], 1)
        (self.output / 'image-1.svg').write_bytes(b'old placeholder')
        self.assertEqual(self.convert()['cached'], 1)
        self.assertNotEqual((self.output / 'image-1.svg').read_bytes(), b'old placeholder')

    def test_worker_failure_does_not_publish_partial_outputs(self):
        self.output.mkdir()
        existing = self.output / 'image-1.svg'
        existing.write_bytes(b'previous successful image')
        with patch.object(images, 'conversion_signature', return_value='tools'), \
             patch.object(images, 'convert_batch', side_effect=RuntimeError('renderer failed')), \
             redirect_stdout(StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'renderer failed'):
                images.convert(self.source, self.manifest, self.output, self.cache)
        self.assertEqual(existing.read_bytes(), b'previous successful image')
        self.assertFalse((self.output / 'image-1.png').exists())
        self.assertFalse(list(self.cache.glob('documents/*.json')))

    def test_magick_fallback_is_part_of_cache_completeness(self):
        self.assertEqual(self.convert(magick=True)['converted'], 1)
        fallback = next((self.cache / 'objects').rglob('image.magick.png'))
        fallback.unlink()
        self.assertEqual(self.convert(magick=True)['converted'], 1)
        self.assertTrue((self.output / 'image-1.magick.png').stat().st_size)

    def test_used_render_cache_page_replaces_placeholder_for_fingerprint_and_batch(self):
        key = 'a' * 64 + '-1'
        render_cache = self.source.with_suffix('.render-cache')
        render_cache.mkdir()
        cached_pdf = render_cache / f'{key}.pdf'
        self.write_single_pdf(cached_pdf, '0 1 0')
        self.source.with_suffix('.render-cache-used.jsonl').write_text(
            f'{{"name":"image-1","key":"{key}"}}\n')
        batch_pages = []
        expected_key = images.digest(
            b'tools-v1' + images.page_bytes(images.PdfReader(cached_pdf).pages[0]))

        def inspect_batch(pdf, items, directory, cache, magick):
            batch_pages.append(images.page_bytes(images.PdfReader(pdf).pages[0]))
            return self.fake_batch(pdf, items, directory, cache, magick)

        with patch.object(images, 'conversion_signature', return_value='tools-v1'), \
             patch.object(images, 'convert_batch', side_effect=inspect_batch), \
             redirect_stdout(StringIO()):
            result = images.convert(self.source, self.manifest, self.output, self.cache)

        self.assertEqual(result['converted'], 1)
        self.assertEqual(batch_pages, [images.page_bytes(images.PdfReader(cached_pdf).pages[0])])
        self.assertTrue((self.cache / 'objects' / expected_key[:2] / expected_key).is_dir())

    def test_invalid_used_map_and_missing_payload_are_fatal(self):
        map_path = self.source.with_suffix('.render-cache-used.jsonl')
        invalid_lines = (
            '{"name":"image-1","key":"not-a-key"}\n',
            '{"name":"unknown","key":"' + 'a' * 64 + '-1"}\n',
            '{"name":"image-1","key":"' + 'a' * 64 + '-1","extra":true}\n',
            '{"name":"image-1","name":"image-1","key":"' + 'a' * 64 + '-1"}\n',
            '{"name":"image-1","key":"' + 'a' * 64 + '-1","key":"' + 'a' * 64 + '-1"}\n',
            '{"name":"image-1","key":"' + 'a' * 64 + '-1"}\n'
            '{"name":"image-1","key":"' + 'b' * 64 + '-1"}\n',
        )
        for contents in invalid_lines:
            with self.subTest(contents=contents):
                map_path.write_text(contents)
                with patch.object(images, 'conversion_signature', return_value='tools-v1'), \
                     redirect_stdout(StringIO()):
                    with self.assertRaises(ValueError):
                        images.convert(self.source, self.manifest, self.output, self.cache)

        key = 'b' * 64 + '-2'
        map_path.write_text(f'{{"name":"image-1","key":"{key}"}}\n')
        with patch.object(images, 'conversion_signature', return_value='tools-v1'), \
             redirect_stdout(StringIO()):
            with self.assertRaisesRegex(ValueError, 'PDF is missing'):
                images.convert(self.source, self.manifest, self.output, self.cache)

        render_cache = self.source.with_suffix('.render-cache')
        render_cache.mkdir(exist_ok=True)
        writer = PdfWriter()
        writer.add_blank_page(100, 100)
        writer.add_blank_page(100, 100)
        two_page_pdf = render_cache / f'{key}.pdf'
        with two_page_pdf.open('wb') as stream:
            writer.write(stream)
        with patch.object(images, 'conversion_signature', return_value='tools-v1'), \
             redirect_stdout(StringIO()):
            with self.assertRaisesRegex(ValueError, 'exactly one page'):
                images.convert(self.source, self.manifest, self.output, self.cache)

    def test_invalid_or_incomplete_manifest_is_rejected(self):
        for text in ('|0|false|image-1|\n|end|end|end|\n',
                     '|1|false|image-1|\n',
                     '|1|false|../escape|\n|end|end|end|\n',
                     '|1|false|image-1|\n|2|false|image-1|\n|end|end|end|\n'):
            with self.subTest(text=text):
                self.manifest.write_text(text)
                with self.assertRaises(ValueError):
                    images.read_manifest(self.manifest)
        self.manifest.write_text('|1|true|hash|\n|2|true|hash|\n')
        self.assertEqual(images.read_manifest(self.manifest, allow_missing_end=True), {'hash': 1})


if __name__ == '__main__':
    unittest.main()
