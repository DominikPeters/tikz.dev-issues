"""Source inventory tests; no TeX engine is invoked."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import illustration_audit as audit


class IllustrationAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, text):
        path = self.root / "manual.tex"
        path.write_text(text, encoding="utf-8")
        return path

    def test_ignores_commented_environment_markers_and_preserves_body(self):
        path = self.write(
            "% \\begin{codeexample} fake\n"
            "\\begin{codeexample}[code only]\n"
            "\\node {visible}; % \\end{codeexample}\n"
            "\\end{codeexample}\n"
            "% \\end{codeexample}\n")
        examples = list(audit.parse_file(path, self.root))
        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0]["line"], 2)
        self.assertIn("% \\end{codeexample}", examples[0]["body"])
        self.assertIn("code_only_execution_uncertain", examples[0]["hazard_tags"])
        self.assertEqual(examples[0]["status"], "unreviewed")

    def test_nested_brackets_inside_option_braces_do_not_end_options(self):
        path = self.write(
            r"\begin{codeexample}[pre={\foo[abc]},render={x[y]}]" "\n"
            r"\tikz \draw;" "\n"
            r"\end{codeexample}" "\n")
        example = next(audit.parse_file(path, self.root))
        self.assertEqual(example["options"], r"pre={\foo[abc]},render={x[y]}")
        self.assertEqual(example["body"], "\n" + r"\tikz \draw;" + "\n")

    def test_comment_between_begin_and_options_is_skipped(self):
        path = self.write(
            "\\begin{codeexample}% comment out the rest of this line\n"
            r"[pre={\foo[x]},width=2cm] body" + "\n"
            r"\end{codeexample}" + "\n")
        example = next(audit.parse_file(path, self.root))
        self.assertTrue(example["has_options"])
        self.assertEqual(example["options"], r"pre={\foo[x]},width=2cm")
        self.assertEqual(example["body"], " body\n")

    def test_same_line_examples_after_comment_are_both_found(self):
        path = self.write(
            "% commented \\begin{codeexample} must be ignored\n"
            r"\begin{codeexample}first\end{codeexample} \begin{codeexample}second\end{codeexample}" + "\n")
        examples = list(audit.parse_file(path, self.root))
        self.assertEqual([example["ordinal"] for example in examples], [1, 2])
        self.assertEqual([example["body"].strip() for example in examples], ["first", "second"])

    def test_hazards_are_lexical_and_execute_false_is_marked(self):
        examples = list(audit.parse_file(self.write(
            r"\begin{codeexample}[execute=false]" "\n"
            r"% \pgfmathrandom\label{fake}" "\n"
            r"\pgfmathsetseed{2}\write\foo{data}" "\n"
            r"\end{codeexample}" "\n"), self.root))
        tags = examples[0]["hazard_tags"]
        self.assertIn("execute_false", tags)
        self.assertIn("random_state", tags)
        self.assertIn("file_io_or_input", tags)
        self.assertNotIn("auxiliary_or_reference", tags)

    def test_exact_span_and_file_hashes_are_stable_and_invalidate_on_edit(self):
        source = "before\n\\begin{codeexample}[x]\n body \n\\end{codeexample}\nafter\n"
        path = self.write(source)
        example = next(audit.parse_file(path, self.root))
        span = "\\begin{codeexample}[x]\n body \n\\end{codeexample}"
        self.assertEqual(example["source_span_sha256"], hashlib.sha256(span.encode()).hexdigest())
        self.assertEqual(example["source_sha256"], hashlib.sha256(source.encode()).hexdigest())
        repeated = next(audit.parse_file(path, self.root))
        self.assertEqual(example["source_span_sha256"], repeated["source_span_sha256"])
        path.write_text(source.replace("body", "changed"), encoding="utf-8")
        changed = next(audit.parse_file(path, self.root))
        self.assertNotEqual(example["source_span_sha256"], changed["source_span_sha256"])
        self.assertNotEqual(example["source_sha256"], changed["source_sha256"])

    def test_file_enumeration_is_sorted_and_relative(self):
        (self.root / "b.tex").write_text("\\begin{codeexample}b\\end{codeexample}")
        sub = self.root / "a"
        sub.mkdir()
        (sub / "one.tex").write_text("\\begin{codeexample}a\\end{codeexample}")
        self.assertEqual([ex["file"] for ex in audit.enumerate_examples(self.root)],
                         ["a/one.tex", "b.tex"])

    def make_eligible_manifest(self, path, status="eligible"):
        example = next(audit.parse_file(path, self.root))
        return {"examples": [{key: example[key] for key in
                              ("file", "line", "source_sha256", "source_span_sha256")}
                             | {"status": status, "reason": "reviewed"}]}

    def test_eligible_example_gets_deterministic_tag_and_balanced_options_survive(self):
        source = (r"lead" + "\n" +
                  r"\begin{codeexample}[pre={\foo[x]},width=2cm]" + "\n" +
                  r"\begin{tikzpicture}\draw;\end{tikzpicture}" + "\n" +
                  r"\end{codeexample}" + "\n")
        path = self.write(source)
        manifest = self.make_eligible_manifest(path)
        expected_id = audit.cache_id(manifest["examples"][0])
        counts = audit.apply_cache_tags(self.root, manifest)
        self.assertEqual(counts["tagged"], 1)
        example = next(audit.parse_file(path, self.root))
        self.assertIn(",render cache=", example["options"])
        self.assertIn(r"pre={\foo[x]},width=2cm", example["options"])
        self.assertIn("render cache=" + expected_id, example["options"])
        self.assertEqual(path.read_text(), source.replace(
            "width=2cm]", "width=2cm,render cache=" + expected_id + "]"))

    def test_eligible_example_without_options_gets_new_brackets_after_begin(self):
        path = self.write("\\begin{codeexample}\n\\begin{tikzpicture}x\\end{tikzpicture}\n\\end{codeexample}\n")
        manifest = self.make_eligible_manifest(path)
        expected_id = audit.cache_id(manifest["examples"][0])
        counts = audit.apply_cache_tags(self.root, manifest)
        self.assertEqual(counts["tagged"], 1)
        self.assertTrue(path.read_text().startswith("\\begin{codeexample}[render cache=" + expected_id + "]\n"))

    def test_noneligible_missing_tikz_and_stale_hashes_do_not_mutate(self):
        path = self.write(
            "\\begin{codeexample}[x]\n\\begin{tikzpicture}x\\end{tikzpicture}\n\\end{codeexample}\n"
            "\\begin{codeexample}\n\\begin{tikzpicture}y\\end{tikzpicture}\n\\end{codeexample}\n"
            "\\begin{codeexample}\n\\draw;\\end{codeexample}\n")
        examples = list(audit.parse_file(path, self.root))
        records = []
        for example, status in zip(examples, ("unsafe", "unreviewed", "eligible")):
            records.append({key: example[key] for key in
                            ("file", "line", "source_sha256", "source_span_sha256")}
                           | {"status": status})
        self.assertEqual(audit.apply_cache_tags(self.root, {"examples": records})["tagged"], 0)
        original = path.read_text()
        changed = records[-1] | {"source_span_sha256": "0" * 64}
        counts = audit.apply_cache_tags(self.root, {"examples": [changed]})
        self.assertEqual(counts["stale"], 1)
        self.assertEqual(path.read_text(), original)
        # A changed source-file hash also prevents activation.
        changed_file = records[0] | {"status": "eligible", "source_sha256": "f" * 64}
        self.assertEqual(audit.apply_cache_tags(self.root, {"examples": [changed_file]})["stale"], 1)
        self.assertEqual(path.read_text(), original)

    def test_moved_example_is_counted_stale_even_when_line_lookup_misses(self):
        path = self.write("\\begin{codeexample}\n\\begin{tikzpicture}x\\end{tikzpicture}\n\\end{codeexample}\n")
        manifest = self.make_eligible_manifest(path)
        path.write_text("% added line\n" + path.read_text(), encoding="utf-8")
        changed = path.read_text()
        counts = audit.apply_cache_tags(self.root, manifest)
        self.assertEqual(counts["tagged"], 0)
        self.assertEqual(counts["stale"], 1)
        self.assertEqual(path.read_text(), changed)


if __name__ == "__main__":
    unittest.main()
