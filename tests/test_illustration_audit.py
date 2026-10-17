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

    def test_screening_separates_live_setup_from_skipped_picture(self):
        example = {"options": r"pre={\gdef\setup{live}},preamble={\usetikzlibrary{calc}}",
                   "body": r"\global\advance\outside by1\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}"}
        screen = audit.screen_example(example)
        self.assertEqual(screen["status"], "review")
        self.assertEqual(screen["drawing_hazards"], [])
        self.assertIn("global_definition_or_declaration", screen["option_hazards"])
        # No lexical hazard is never itself an eligibility decision.
        self.assertNotEqual(screen["status"], "eligible")

    def test_screening_finds_nested_picture_hazards_and_ignores_comments(self):
        body = (r"\begin{tikzpicture}\draw (0,0)--(1,1);" + "\n" +
                r"% \end{tikzpicture}\input{commented}" + "\n" +
                r"\begin{tikzpicture}\pgfmathparse{rnd}\end{tikzpicture}\end{tikzpicture}")
        screen = audit.screen_example({"options": "", "body": body})
        self.assertEqual(screen["drawing_hazards"], ["random_state"])
        self.assertNotIn("file_io_or_input", screen["drawing_hazards"])

    def test_loop_around_picture_stays_live_but_loop_inside_picture_can_be_reviewed(self):
        picture = r"\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}"
        outer = {"options": "", "body": r"\foreach \level in {0,1,2}{" + picture + "}"}
        inner = {"options": "", "body": r"\begin{tikzpicture}\foreach \x in {1,2}{\draw (0,0)--(\x,1);}\end{tikzpicture}"}
        self.assertEqual(audit.screen_example(outer)["status"], "live")
        self.assertEqual(audit.screen_example(inner)["status"], "review")

    def test_raw_picture_markers_in_comments_stay_live(self):
        source = ("\\begin{codeexample}\n"
                  "% \\begin{tikzpicture}\n"
                  "\\begin{tikzpicture}\\draw;\\end{tikzpicture}\n"
                  "\\end{codeexample}\n")
        path = self.write(source)
        example = next(audit.parse_file(path, self.root))
        self.assertEqual(example["screening"]["status"], "live")
        manifest = self.make_eligible_manifest(path)
        self.assertEqual(audit.apply_cache_tags(self.root, manifest)["tagged"], 0)
        self.assertEqual(path.read_text(), source)

    def test_adjacent_pictures_without_blank_line_stay_live(self):
        first = r"\begin{tikzpicture}\draw;\end{tikzpicture}"
        second = r"\begin{tikzpicture}\fill;\end{tikzpicture}"
        for separator in ("", "\n", "\n  "):
            with self.subTest(separator=separator):
                path = self.write("\\begin{codeexample}\n" + first + separator + second +
                                  "\n\\end{codeexample}\n")
                example = next(audit.parse_file(path, self.root))
                self.assertEqual(example["screening"]["status"], "live")
                manifest = self.make_eligible_manifest(path)
                self.assertEqual(audit.apply_cache_tags(self.root, manifest)["tagged"], 0)

        path = self.write("\\begin{codeexample}\n" + first + "\n\n  " + second +
                          "\n\\end{codeexample}\n")
        example = next(audit.parse_file(path, self.root))
        self.assertEqual(example["screening"]["status"], "review")

    def test_external_plot_data_and_indirect_random_hints(self):
        for source in (r"\addplot table {measurements.dat};",
                       r"\addplot3 gnuplot {sin(x)};",
                       r"\addplot shell {awk data.dat};",
                       r"\addplot table [x index=0] shell {cat data.dat};",
                       r"\draw plot[id=test] function {sin(x)};",
                       r"\addplot[contour lua] {x*y};",
                       r"\pgfplotstableread{data.csv}\loaded"):
            with self.subTest(source=source):
                self.assertIn("external_plot_or_data", audit.hazard_tags("", source))
        for source in (r"\pgfmathparse{rnd}", "decorate,decoration={random steps}",
                       r"\pgfmathdeclarerandomlist{a}{{1}{2}}",
                       r"\node[starburst] {burst};",
                       r"\node[shape=starburst] {burst};",
                       r"\tikzset{burst/.style={starburst}}\node[burst] {burst};"):
            with self.subTest(source=source):
                self.assertIn("random_state", audit.hazard_tags("", source))
        self.assertIn("external_image", audit.hazard_tags("", r"\includegraphics{changed.png}"))
        self.assertIn("persistent_layer_state", audit.hazard_tags("", r"\pgfsetlayers{pre main,main}"))
        self.assertIn("file_io_or_input", audit.hazard_tags("", r"\immediate\write18{touch file}"))

    def test_unsupported_execution_paths_and_unbalanced_pictures_stay_live(self):
        picture = r"\begin{tikzpicture}\draw;\end{tikzpicture}"
        for options, body in (("code only", picture), ("setup code", picture), ("leave comments", picture),
                              ("execute code=false", picture), ("imagesource=x.svg", picture),
                              ("from file=foo.tex", picture), ("render instead={x}", picture),
                              (r"pre={\begin{lateximage}},post={\end{lateximage}}", picture),
                              ("", picture + "right of picture."),
                              ("", r"\begin{tikzpicture}\draw;"), ("", r"\tikz\draw;")):
            with self.subTest(options=options, body=body):
                self.assertEqual(audit.screen_example({"options": options, "body": body})["status"], "live")

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
        return {"context_sha256": audit.context_fingerprint(self.root),
                "examples": [{key: example[key] for key in
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
        manifest = {"context_sha256": audit.context_fingerprint(self.root), "examples": records}
        self.assertEqual(audit.apply_cache_tags(self.root, manifest)["tagged"], 0)
        original = path.read_text()
        changed = records[-1] | {"source_span_sha256": "0" * 64}
        counts = audit.apply_cache_tags(self.root, manifest | {"examples": [changed]})
        self.assertEqual(counts["stale"], 1)
        self.assertEqual(path.read_text(), original)
        # A changed source-file hash also prevents activation.
        changed_file = records[0] | {"status": "eligible", "source_sha256": "f" * 64}
        self.assertEqual(audit.apply_cache_tags(self.root, manifest | {"examples": [changed_file]})["stale"], 1)
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

    def test_conflicting_review_never_enables_cache_regardless_of_order(self):
        path = self.write("\\begin{codeexample}\n\\begin{tikzpicture}x\\end{tikzpicture}\n\\end{codeexample}\n")
        manifest = self.make_eligible_manifest(path)
        eligible = manifest["examples"][0]
        unsafe = eligible | {"status": "unsafe", "reason": "cross-picture state"}
        original = path.read_bytes()
        for records in ([eligible, unsafe], [unsafe, eligible]):
            self.assertEqual(audit.apply_cache_tags(
                self.root, manifest | {"examples": records})["tagged"], 0)
            self.assertEqual(path.read_bytes(), original)

    def test_review_cannot_enable_listing_or_malformed_picture(self):
        for source in (r"\begin{codeexample}[code only]\begin{tikzpicture}x\end{tikzpicture}\end{codeexample}",
                       r"\begin{codeexample}\begin{tikzpicture}x\end{codeexample}"):
            path = self.write(source)
            manifest = self.make_eligible_manifest(path)
            self.assertEqual(audit.apply_cache_tags(self.root, manifest)["tagged"], 0)
            self.assertEqual(path.read_text(), source)

    def test_reviewed_spaced_picture_boundaries_match_runtime_scanner(self):
        path = self.write(r"\begin{codeexample}\begin {tikzpicture}x\end {tikzpicture}\end{codeexample}")
        manifest = self.make_eligible_manifest(path)
        self.assertEqual(audit.apply_cache_tags(self.root, manifest)["tagged"], 1)

    def test_review_merge_checks_fingerprints_and_keeps_unreviewed_live(self):
        path = self.write("\\begin{codeexample}\n\\begin{tikzpicture}x\\end{tikzpicture}\n\\end{codeexample}\n")
        inventory = audit.build_inventory("pgf", self.root)
        review = self.make_eligible_manifest(path) | {"package": "pgf"}
        merged = audit.merge_reviews(inventory, [review], "a" * 40)
        self.assertEqual(merged["summary"], {"eligible": 1})
        self.assertEqual(audit.merge_reviews(inventory, [], "a" * 40)["summary"], {"unreviewed": 1})
        stale = review | {"examples": [review["examples"][0] | {"source_sha256": "b" * 64}]}
        with self.assertRaisesRegex(ValueError, "stale or unknown"):
            audit.merge_reviews(inventory, [stale], "a" * 40)
        with self.assertRaisesRegex(ValueError, "package"):
            audit.merge_reviews(inventory, [review | {"package": "other"}], "a" * 40)

    def test_missing_context_fails_closed_for_positive_reviews_and_tagging(self):
        path = self.write("\\begin{codeexample}\n\\begin{tikzpicture}x\\end{tikzpicture}\n\\end{codeexample}\n")
        inventory = audit.build_inventory("pgf", self.root)
        review = self.make_eligible_manifest(path) | {"package": "pgf"}
        original = path.read_text()

        missing_context = review | {"context_sha256": None}
        with self.assertRaisesRegex(ValueError, "matching context_sha256"):
            audit.merge_reviews(inventory, [missing_context], "a" * 40)
        self.assertEqual(audit.apply_cache_tags(self.root, missing_context)["tagged"], 0)
        self.assertEqual(path.read_text(), original)

        # Legacy negative-only decisions remain safe to merge without context.
        negative = missing_context | {"examples": [review["examples"][0] | {
            "status": "unsafe", "reason": "known side effect"}]}
        self.assertEqual(
            audit.merge_reviews(inventory, [negative], "a" * 40)["summary"],
            {"unsafe": 1},
        )

    def test_editing_shared_source_context_disables_otherwise_unchanged_examples(self):
        path = self.write("\\begin{codeexample}\n\\begin{tikzpicture}x\\end{tikzpicture}\n\\end{codeexample}\n")
        helper = self.root / "preamble.tex"
        helper.write_text(r"\def\helper{safe}")
        inventory = audit.build_inventory("pgf", self.root)
        review = self.make_eligible_manifest(path) | {"package": "pgf"}
        manifest = audit.merge_reviews(inventory, [review], "a" * 40)
        original = path.read_bytes()
        helper.write_text(r"\def\helper{\global\advance\state by1}")
        self.assertEqual(audit.apply_cache_tags(self.root, manifest)["tagged"], 0)
        self.assertEqual(path.read_bytes(), original)
        changed_inventory = audit.build_inventory("pgf", self.root)
        with self.assertRaisesRegex(ValueError, "stale review context"):
            audit.merge_reviews(changed_inventory, [manifest], "a" * 40)
        helper.write_text(r"\def\helper{safe}")
        self.assertEqual(audit.apply_cache_tags(self.root, manifest)["tagged"], 1)

    def test_review_merge_preserves_negative_findings_and_rejects_invalid_status(self):
        path = self.write("\\begin{codeexample}\n\\begin{tikzpicture}x\\end{tikzpicture}\n\\end{codeexample}\n")
        inventory = audit.build_inventory("pgf", self.root)
        positive = self.make_eligible_manifest(path) | {"package": "pgf"}
        negative = positive | {"examples": [positive["examples"][0] | {"status": "unsafe"}]}
        for reviews in ([positive, negative], [negative, positive]):
            self.assertEqual(audit.merge_reviews(inventory, reviews, "a" * 40)["summary"], {"unsafe": 1})
        invalid = positive | {"examples": [positive["examples"][0] | {"status": "probably_safe"}]}
        with self.assertRaisesRegex(ValueError, "status and reason"):
            audit.merge_reviews(inventory, [invalid], "a" * 40)


if __name__ == "__main__":
    unittest.main()
