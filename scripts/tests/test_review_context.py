"""Prose edits carry existing decisions; executable changes fail closed."""
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import illustration_audit as audit


class ReviewContextTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'chapter.tex'
        self.original = ('These are the original words.\n\n'
                         r'\begin{codeexample}\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}\end{codeexample}' + '\n')
        self.path.write_text(self.original)
        example = next(audit.parse_file(self.path, self.root))
        manifest = {'context_sha256': audit.context_fingerprint(self.root),
                    'examples': [{k: example[k] for k in ('file', 'line', 'source_sha256', 'source_span_sha256')}
                                 | {'status': 'eligible', 'reason': 'previous review'}]}
        self.manifest = audit.upgrade_manifest(self.root, manifest, 'package-code')

    def apply(self):
        return audit.apply_cache_tags(self.root, self.manifest, 'package-code')

    def test_prose_and_line_shifts_keep_approval(self):
        self.path.write_text('% A new comment\n' + self.original.replace('original words', 'revised explanation'))
        self.assertEqual(self.apply()['tagged'], 1)

    def test_commands_in_prose_and_picture_edits_invalidate(self):
        for text in [self.original.replace('original words', r'\global\def\style{bad}'),
                     self.original.replace('(1,1)', '(2,2)')]:
            with self.subTest(source=text):
                self.path.write_text(text)
                self.assertEqual(self.apply()['tagged'], 0)

    def test_helpers_and_implementation_changes_invalidate(self):
        (self.root / 'helper.sty').write_text(r'\def\style{new}')
        self.assertEqual(self.apply()['tagged'], 0)
        (self.root / 'helper.sty').unlink()
        self.assertEqual(audit.apply_cache_tags(self.root, self.manifest, 'new-code')['tagged'], 0)

    def test_grouped_text_and_verbatim_data_remain_exact(self):
        for source in [r'\def\helper{' + '\n\nOriginal words.\n\n}',
                       '\\begin{filecontents}{data.tex}\n% data\n\\end{filecontents}',
                       '\\begin{verbatim}\nOriginal words.\n\\end{verbatim}']:
            changed = source.replace('Original', 'Changed').replace('% data', '% changed')
            self.assertNotEqual(audit.prose_independent_source(source), audit.prose_independent_source(changed))

    def test_comment_newline_semantics_are_preserved(self):
        a = '\\def\\helper{A% comment\nB}'
        b = '\\def\\helper{A\nB}'
        self.assertNotEqual(audit.prose_independent_source(a), audit.prose_independent_source(b))

    def test_migration_requires_original_exact_context(self):
        self.path.write_text(self.original + '% changed\n')
        with self.assertRaisesRegex(ValueError, 'exact original'):
            audit.upgrade_manifest(self.root, {'context_sha256': 'old'}, 'package-code')

    def test_identical_examples_keep_separate_reviews_and_cache_keys(self):
        self.path.write_text(self.original + self.original)
        inventory = audit.build_inventory('manual', self.root, audit.PROSE_POLICY, 'package-code')
        first, second = inventory['examples']
        self.assertEqual(first['source_span_sha256'], second['source_span_sha256'])
        self.assertNotEqual(audit.scoped_cache_id(first), audit.scoped_cache_id(second))
        review = dict(inventory, examples=[dict(first, status='eligible', reason='reviewed first occurrence')])
        manifest = audit.merge_reviews(inventory, [review], 'a' * 40)
        self.assertEqual(audit.apply_cache_tags(self.root, manifest, 'package-code')['tagged'], 1)
        self.assertEqual(self.path.read_text().count('render cache='), 1)
        self.path.write_text(self.original * 3)
        self.assertEqual(audit.apply_cache_tags(self.root, manifest, 'package-code')['tagged'], 0)

    def test_new_reviews_require_policy_and_implementation_metadata(self):
        inventory = audit.build_inventory('manual', self.root, audit.PROSE_POLICY, 'package-code')
        review = dict(inventory, examples=[dict(inventory['examples'][0], status='eligible', reason='safe drawing')])
        for changes in [{'context_policy': 'exact-v1'}, {'implementation_sha256': None},
                        {'implementation_sha256': 'changed-package'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                audit.merge_reviews(inventory, [dict(review, **changes)], 'a' * 40)
        manifest = audit.merge_reviews(inventory, [review], 'a' * 40)
        self.assertEqual(manifest['format'], 2)
        self.assertEqual(audit.apply_cache_tags(self.root, manifest)['tagged'], 0)
        self.assertEqual(audit.apply_cache_tags(self.root, manifest, 'package-code')['tagged'], 1)


if __name__ == '__main__':
    unittest.main()
