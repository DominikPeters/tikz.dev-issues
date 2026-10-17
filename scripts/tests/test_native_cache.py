"""Compiled output is reusable only for the same native inputs and toolchain."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import native_cache as native
import archive_upstream


class NativeCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'manual').mkdir()
        (self.root / 'manual/upstream.lock').write_text('source=archives\ndocdir=.\n')
        (self.root / '.upstream/manual').mkdir(parents=True)
        (self.root / '.upstream/manual/.source-ref').write_text('a' * 64)
        (self.root / 'shared').mkdir()
        (self.root / 'scripts').mkdir()
        for name in ['prepare.py', 'illustration_audit.py', 'native_cache.py', 'build.sh']:
            (self.root / 'scripts' / name).write_text('native tool')
        (self.root / 'shared/style.css').write_text('style')
        (self.root / 'shared/helper.sty').write_text('native helper')
        (self.root / 'manual/postprocessing.py').write_text('HTML tool')
        self.addCleanup(patch.stopall)
        patch.object(native, 'ROOT', self.root).start()
        patch.object(native, 'toolchain', return_value={'engine': 'test-1'}).start()
        patch.object(archive_upstream, 'validate_snapshot').start()
        patch.dict(os.environ, {'TIKZ_COMPILED_CACHE': str(self.root / 'cache'),
                                'TEXINPUTS': '', 'LUAINPUTS': ''}).start()

    def test_frontend_changes_keep_key_and_native_changes_invalidate(self):
        original = native.key('manual')
        (self.root / 'shared/style.css').write_text('new style')
        (self.root / 'manual/postprocessing.py').write_text('new footer')
        self.assertEqual(native.key('manual'), original)
        (self.root / 'shared/helper.sty').write_text('changed TeX')
        self.assertNotEqual(native.key('manual'), original)
        (self.root / 'shared/helper.sty').write_text('native helper')
        (self.root / '.upstream/manual/.source-ref').write_text('b' * 64)
        self.assertNotEqual(native.key('manual'), original)
        (self.root / '.upstream/manual/.source-ref').write_text('a' * 64)
        with patch.object(native, 'toolchain', return_value={'engine': 'test-2'}):
            self.assertNotEqual(native.key('manual'), original)

    def test_cached_raw_inputs_restore_and_corruption_becomes_a_miss(self):
        source = self.root / 'build/manual/src'
        source.mkdir(parents=True)
        (source / 'index.html').write_text('raw native HTML')
        (source / 'processed').mkdir()
        (source / 'processed/index.html').write_text('obsolete final HTML')
        identity = native.key('manual')
        native.save('manual', identity)
        (source / 'index.html').write_text('changed in disposable build tree')
        self.assertTrue(native.restore('manual', identity))
        self.assertEqual((source / 'index.html').read_text(), 'raw native HTML')
        self.assertFalse((source / 'processed').exists())
        (native.cache('manual').directory(identity) / 'image.tar').write_bytes(b'broken')
        self.assertFalse(native.restore('manual', identity))
        self.assertEqual((source / 'index.html').read_text(), 'raw native HTML')

    def test_python_manual_images_and_aux_files_restore_together(self):
        (self.root / 'manual/convert.py').write_text('converter')
        for name in ['tex', 'images']:
            directory = self.root / 'manual/build' / name
            directory.mkdir(parents=True)
            (directory / 'native.data').write_text(name)
        identity = native.key('manual')
        native.save('manual', identity)
        (self.root / 'manual/build/tex/native.data').unlink()
        self.assertTrue(native.restore('manual', identity))
        self.assertEqual((self.root / 'manual/build/tex/native.data').read_text(), 'tex')
        self.assertEqual((self.root / 'manual/build/images/native.data').read_text(), 'images')

    def test_custom_external_search_paths_fail_closed(self):
        with patch.dict(os.environ, {'TEXINPUTS': '/custom/libraries//:'}):
            with self.assertRaisesRegex(ValueError, 'custom TeX search'):
                native.key('manual')

    def test_python_frontend_rebuild_uses_html_mode_and_current_upstream(self):
        (self.root / 'manual/convert.py').write_text('converter')
        script = self.root / 'manual/build.sh'
        script.write_text('#!/bin/bash\nset -eu\n[[ $1 == html ]]\nprintf "%s" "$UPSTREAM" > "' +
                          str(self.root / 'html-upstream') + '"\n')
        script.chmod(0o755)
        native.html('manual')
        self.assertEqual((self.root / 'html-upstream').read_text(), str(self.root / '.upstream/manual'))

    def test_python_dirty_checkout_disables_compiled_cache(self):
        (self.root / 'manual/upstream.lock').write_text('repo=git\ndocdir=.\n')
        (self.root / 'manual/convert.py').write_text('converter')
        with patch.object(native.subprocess, 'check_output', side_effect=['a' * 40, ' M source.tex\n']):
            with self.assertRaisesRegex(ValueError, 'modified upstream'):
                native.key('manual')

    def test_archive_epoch_uses_release_date(self):
        (self.root / 'manual/upstream.lock').write_text('source=archives\nmanifest=upstream.json\ndocdir=.\n')
        (self.root / 'manual/upstream.json').write_text('{"version":"manual 2.0 (2026-04-19)"}')
        self.assertEqual(native.source_epoch('manual'), '1776556800')
        (self.root / 'manual/upstream.json').write_text('{"version":"manual 2.0"}')
        with self.assertRaisesRegex(ValueError, 'release date'):
            native.source_epoch('manual')


if __name__ == '__main__':
    unittest.main()
