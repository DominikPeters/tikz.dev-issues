"""Shared documentation overlays and root-level upstream manual patches."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import prepare


class PrepareTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.shared = self.root / 'shared'
        self.group = self.shared / 'pgfmanual'
        self.group.mkdir(parents=True)
        (self.group / 'helper.sty').write_text('shared documentation')
        (self.shared / 'utility.py').write_text('common tool')
        self.package = self.root / 'manual'
        self.package.mkdir()
        self.lock = self.package / 'upstream.lock'
        self.lock.write_text('docdir=.\ndocumentation=pgf\n')
        self.tree = self.root / 'tree'
        self.tree.mkdir()
        self.addCleanup(patch.stopall)
        patch.object(prepare, 'ROOT', str(self.root)).start()
        patch.object(prepare, 'SHARED', str(self.shared)).start()

    def test_opted_in_documentation_is_flattened_without_copying_the_group_directory(self):
        prepare.overlay('manual', str(self.tree), '.')
        self.assertEqual((self.tree / 'helper.sty').read_text(), 'shared documentation')
        self.assertEqual((self.tree / 'utility.py').read_text(), 'common tool')
        self.assertFalse((self.tree / 'pgfmanual').exists())

    def test_other_manuals_do_not_receive_pgf_helpers_and_package_overrides_win(self):
        self.lock.write_text('docdir=.\n')
        prepare.overlay('manual', str(self.tree), '.')
        self.assertFalse((self.tree / 'helper.sty').exists())
        self.lock.write_text('docdir=.\ndocumentation=pgf\n')
        (self.package / 'helper.sty').write_text('package-specific override')
        prepare.overlay('manual', str(self.tree), '.')
        self.assertEqual((self.tree / 'helper.sty').read_text(), 'package-specific override')

    def test_refresh_can_record_and_apply_a_root_manual_patch(self):
        edited = self.root / 'edited'
        edited.mkdir()
        (edited / 'manual.tex').write_text('after\n')

        def export(pkg, dest):
            Path(dest).mkdir()
            (Path(dest) / 'manual.tex').write_text('before\n')

        with patch.object(prepare, 'export_upstream', side_effect=export), \
             patch.object(prepare, 'preprocess'):
            prepare.refresh_patches('manual', str(edited))
        result = self.package / 'patches/manual.tex.patch'
        self.assertTrue(result.is_file())
        self.assertIn('+after', result.read_text())
        (self.tree / 'manual.tex').write_text('before\n')
        prepare.apply_patches('manual', str(self.tree))
        self.assertEqual((self.tree / 'manual.tex').read_text(), 'after\n')


if __name__ == '__main__':
    unittest.main()
