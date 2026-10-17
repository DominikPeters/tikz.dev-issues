"""Archive pins must reproduce sources and reject changed or unsafe inputs."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import archive_upstream as source
import prepare


@unittest.skipUnless(shutil.which('dpkg-deb'), 'dpkg-deb is needed for source archives')
class ArchiveUpstreamTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.addCleanup(patch.stopall)
        patch.object(source, 'ROOT', self.root).start()
        patch.object(prepare, 'ROOT', str(self.root)).start()
        package = self.root / 'manual'
        package.mkdir()
        tree = self.root / 'deb-tree'
        (tree / 'DEBIAN').mkdir(parents=True)
        (tree / 'DEBIAN').chmod(0o755)
        (tree / 'DEBIAN/control').write_text('Package: manual-fixture\nVersion: 1\nArchitecture: all\nMaintainer: Test <test@example.org>\nDescription: source archive test\n')
        docs = tree / 'usr/share/doc/manual'
        docs.mkdir(parents=True)
        (docs / 'manual.tex.gz').write_bytes(gzip.compress(b'Original documentation\n'))
        (docs / 'manual.sty').write_text('Original package\n')
        (docs / 'unrelated.txt').write_text('Do not extract')
        archive = self.root / 'source.deb'
        subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(tree), str(archive)],
                       check=True, capture_output=True)
        digest = source.sha256(archive)
        cache = self.root / '.upstream/archive-cache'
        cache.mkdir(parents=True)
        shutil.copy2(archive, cache / (digest + '.deb'))
        manifest = {'version': '1', 'archives': [{
            'url': 'https://example.invalid/source.deb', 'sha256': digest,
            'files': {'usr/share/doc/manual/manual.tex.gz': 'manual.tex',
                      'usr/share/doc/manual/manual.sty': 'tex/manual.sty'}}]}
        path = package / 'upstream.json'
        path.write_text(json.dumps(manifest))
        self.revision = hashlib.sha256(path.read_bytes()).hexdigest()
        (package / 'upstream.lock').write_text(
            'source=archives\nmanifest=upstream.json\ncommit=' + self.revision + '\ndocdir=.\n')
        self.archive = archive

    def test_verified_sources_can_be_prepared_without_git_or_network(self):
        with patch.object(source.urllib.request, 'urlopen', side_effect=AssertionError('Unexpected network')):
            source.fetch('manual')
            source.fetch('manual', self.revision)
        destination = self.root / 'prepared'
        prepare.export_upstream('manual', str(destination))
        self.assertEqual((destination / 'manual.tex').read_text(), 'Original documentation\n')
        self.assertEqual((destination / 'tex/manual.sty').read_text(), 'Original package\n')
        self.assertEqual(sorted(str(p.relative_to(destination)) for p in destination.rglob('*') if p.is_file()),
                         ['manual.tex', 'tex/manual.sty'])

    def test_changed_manifest_snapshot_and_cache_are_rejected(self):
        source.fetch('manual')
        (self.root / '.upstream/manual/manual.tex').write_text('Changed')
        with self.assertRaisesRegex(ValueError, 'snapshot changed'):
            source.fetch('manual')
        with self.assertRaisesRegex(ValueError, 'pinned'):
            (self.root / 'manual/upstream.json').write_text('{}')
            source.manifest('manual')
        cache = self.root / 'bad-cache'
        cache.mkdir()
        digest = source.sha256(self.archive)
        (cache / (digest + '.deb')).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            source.download({'sha256': digest}, cache)

    def test_unsafe_destinations_and_missing_source_members_are_rejected(self):
        destination = self.root / 'extract'
        destination.mkdir()
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            source.extract_deb(self.archive, {'file': '../escape'}, destination)
        with self.assertRaisesRegex(ValueError, 'Missing source'):
            source.extract_deb(self.archive, {'missing.tex': 'manual.tex'}, destination)
        self.assertFalse((self.root / 'escape').exists())

    def test_advancing_the_pin_replaces_only_a_verified_snapshot(self):
        source.fetch('manual')
        path = self.root / 'manual/upstream.json'
        data = json.loads(path.read_text())
        data['version'] = '2'
        path.write_text(json.dumps(data))
        revision = source.sha256(path)
        lock = self.root / 'manual/upstream.lock'
        lock.write_text(lock.read_text().replace(self.revision, revision))
        source.fetch('manual')
        directory = self.root / '.upstream/manual'
        self.assertEqual((directory / '.source-ref').read_text().strip(), revision)
        self.assertEqual((directory / 'manual.tex').read_text(), 'Original documentation\n')


if __name__ == '__main__':
    unittest.main()
