import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SHARED = Path(__file__).resolve().parents[2] / "shared"
SPEC = importlib.util.spec_from_file_location("render_cache", SHARED / "render_cache.py")
render_cache = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = render_cache
SPEC.loader.exec_module(render_cache)


KEY = "a" * 64 + "-0"


def make_pdf(path: Path, sizes):
    from pypdf import PdfWriter
    from pypdf.generic import _base as pypdf_base

    pypdf_base.FLOAT_WRITE_PRECISION = 16
    writer = PdfWriter()
    for width, height in sizes:
        writer.add_blank_page(width=width, height=height)
    with path.open("wb") as output:
        writer.write(output)


class RenderCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.job = self.root / "sample"
        self.cache_dir = self.root / "sample.render-cache"
        self.pending = Path(f"{self.job}.render-cache-pending.jsonl")

    def tearDown(self):
        self.temporary.cleanup()

    def write_records(self, *records):
        self.pending.write_text("".join(json.dumps(record) + "\n" for record in records))

    def record(self, key=KEY, page=1, pgf_ids=7):
        return {"key": key, "page": page, "pgf_ids": pgf_ids}

    def test_empty_pending_manifest_creates_cache_dir_without_pypdf(self):
        self.pending.write_text("")
        with mock.patch.dict(sys.modules, {"pypdf": None}):
            self.assertEqual(render_cache.extract_pending_pages(self.job), 0)
        self.assertTrue(self.cache_dir.is_dir())

    def test_missing_pending_manifest_creates_cache_dir(self):
        self.assertEqual(render_cache.extract_pending_pages(self.job), 0)
        self.assertTrue(self.cache_dir.is_dir())

    def test_rejects_malformed_json(self):
        self.pending.write_text('{"key":\n')
        with self.assertRaisesRegex(render_cache.RenderCacheError, "malformed JSON"):
            render_cache.extract_pending_pages(self.job)

    def test_rejects_unexpected_or_missing_fields(self):
        self.write_records({"key": KEY, "page": 1})
        with self.assertRaisesRegex(render_cache.RenderCacheError, "exactly key, page, and pgf_ids"):
            render_cache.extract_pending_pages(self.job)

    def test_rejects_invalid_cache_key(self):
        for key in ("../" + KEY, "A" * 64 + "-0", "a" * 63 + "-0", "a" * 64):
            with self.subTest(key=key):
                self.write_records(self.record(key=key))
                with self.assertRaisesRegex(render_cache.RenderCacheError, "invalid cache key"):
                    render_cache.extract_pending_pages(self.job)

    def test_rejects_invalid_page_and_pgf_ids(self):
        for field, value, message in (
            ("page", 0, "page must be a positive integer"),
            ("page", "1", "page must be a positive integer"),
            ("pgf_ids", 0, "pgf_ids must be a positive integer"),
            ("pgf_ids", True, "pgf_ids must be a positive integer"),
        ):
            with self.subTest(field=field, value=value):
                self.write_records(self.record(**{field: value}))
                with self.assertRaisesRegex(render_cache.RenderCacheError, message):
                    render_cache.extract_pending_pages(self.job)

    def test_missing_source_pdf_fails_and_keeps_manifest(self):
        self.write_records(self.record())
        with self.assertRaisesRegex(render_cache.RenderCacheError, "source PDF .* is missing"):
            render_cache.extract_pending_pages(self.job)
        self.assertTrue(self.pending.exists())

    def test_rejects_page_out_of_bounds(self):
        self.write_records(self.record(page=2))
        make_pdf(Path(f"{self.job}.pdf"), [(72, 36)])
        with self.assertRaisesRegex(render_cache.RenderCacheError, "outside the PDF"):
            render_cache.extract_pending_pages(self.job)
        self.assertTrue(self.pending.exists())

    def test_extracts_full_original_page_and_writes_minimal_metadata(self):
        self.write_records(self.record())
        make_pdf(Path(f"{self.job}.pdf"), [(72.1234567890123, 36.9876543210987), (10, 10)])
        self.assertEqual(render_cache.extract_pending_pages(self.job), 1)

        from pypdf import PdfReader

        cached_pdf = self.cache_dir / f"{KEY}.pdf"
        cached_tex = self.cache_dir / f"{KEY}.tex"
        page = PdfReader(str(cached_pdf), strict=True).pages[0]
        self.assertEqual(len(PdfReader(str(cached_pdf)).pages), 1)
        self.assertAlmostEqual(float(page.mediabox.width), 72.1234567890123, places=10)
        self.assertAlmostEqual(float(page.mediabox.height), 36.9876543210987, places=10)
        self.assertEqual(
            cached_tex.read_bytes(),
            b"\\expandafter\\def\\csname TDC@pgfids\\endcsname{7}",
        )
        self.assertEqual(cached_pdf.stat().st_mode & 0o777, 0o644)
        self.assertEqual(cached_tex.stat().st_mode & 0o777, 0o644)
        self.assertFalse(self.pending.exists())

    def test_jobname_derivation(self):
        cwd = self.root
        self.assertEqual(
            render_cache._job_from_args(["-halt-on-error", "-jobname", "named", "source.tex"], cwd),
            cwd / "named",
        )
        self.assertEqual(
            render_cache._job_from_args(["-jobname=chosen.v2", "source.tex"], cwd),
            cwd / "chosen.v2",
        )
        self.assertEqual(
            render_cache._job_from_args(
                ["-output-directory=build", "-jobname=chosen", "source.tex"], cwd
            ),
            cwd / "build" / "chosen",
        )
        self.assertEqual(
            render_cache._job_from_args(["-interaction=nonstopmode", "docs/source.tex"], cwd),
            cwd / "source",
        )
        self.assertEqual(render_cache._job_from_args(["source"], cwd), cwd / "source")

    def test_main_preserves_engine_arguments(self):
        args = [f"-jobname={self.job}", "-halt-on-error", "-interaction=nonstopmode", "source.tex"]
        with mock.patch.object(render_cache, "extract_pending_pages", return_value=0) as extract, \
                mock.patch.object(render_cache.subprocess, "call", return_value=13) as call:
            self.assertEqual(render_cache.main(args), 13)
        extract.assert_called_once_with(self.job)
        call.assert_called_once_with(["lualatex", *args])


if __name__ == "__main__":
    unittest.main()
