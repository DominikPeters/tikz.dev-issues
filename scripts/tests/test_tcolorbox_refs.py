from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.texhtml.core import Context, Page
from tcolorbox.convert import TcbConverter


class RenderedExampleReferenceTests(unittest.TestCase):
    def make_converter(self, source, slug="library-theorems"):
        ctx = Context()
        page = Page(slug, slug, "libraries", "18")
        return TcbConverter(ctx, source, slug, file_stem=slug, page=page)

    def test_labels_from_rendered_tcolorbox_examples_are_anchored(self):
        source = r"""\newtcbtheorem{MyTheorem}{Theorem}
  {label type=theorem}{theo}
\begin{MyTheorem}{Mean value theorem}{meanvaluetheorem}
  Theorem content.
\end{MyTheorem}
\begin{texercise}{tabular_example}
  Exercise content.
\end{texercise}
\label{custom:example-label}"""
        converter = self.make_converter(source)
        converter.ctx._tcolorbox_native_label_numbers = {
            "theo:meanvaluetheorem": "18.3.5",
            "exe:tabular_example": "17.1",
            "custom:example-label": "18.3.5",
        }
        out = []
        converter._example(0, 0, len(source), out)
        html = "".join(item[1] for item in out)

        for label in ("theo:meanvaluetheorem", "exe:tabular_example", "custom:example-label"):
            with self.subTest(label=label):
                self.assertIn(f'id="{label}"', html)
                self.assertLess(html.index(f'id="{label}"'), html.index('<figure class="example">'))
                self.assertEqual(converter.ctx.href(label, converter.slug), f"#{label}")
        self.assertEqual(converter.ctx.labels["theo:meanvaluetheorem"]["text"], "18.3.5")
        self.assertEqual(converter.ctx.labels["exe:tabular_example"]["text"], "17.1")
        self.assertEqual(converter.ctx.labels["exe:tabular_example"]["containing_section"], "18")
        repeated = []
        converter.env_dispListing(0, 0, len(source), len(source), repeated)
        self.assertNotIn('id="exe:tabular_example"', "".join(item[1] for item in repeated))

    def test_labels_in_listings_that_produce_rendered_examples_are_anchored(self):
        source = r"\tcblistof[\subsection]{exam}{List of Exercises\label{listofexercises}}"
        converter = self.make_converter(source, slug="library-listings")
        converter.ctx._tcolorbox_native_label_numbers = {"listofexercises": "17.12"}
        out = []
        converter.env_dispListing(0, 0, len(source), len(source), out)
        html = "".join(item[1] for item in out)
        self.assertIn('id="listofexercises"', html)
        self.assertLess(html.index('id="listofexercises"'), html.index('<figure class="example">'))
        self.assertEqual(converter.ctx.href("listofexercises", converter.slug), "#listofexercises")
        self.assertEqual(converter.ctx.labels["listofexercises"]["text"], "17.12")

    def test_labels_in_macro_definitions_are_ignored_and_duplicate_ids_are_suppressed(self):
        source = r"""\newcommand{\demo}{\label{not-an-executed-label}}
\label{real:example-label}"""
        converter = self.make_converter(source)
        converter.ctx._tcolorbox_native_label_numbers = {"real:example-label": "18.1"}
        first = converter._register_rendered_labels(source)
        second = converter._register_rendered_labels(source)
        self.assertIn('id="real:example-label"', first)
        self.assertNotIn("not-an-executed-label", first)
        self.assertEqual(second, "")


if __name__ == "__main__":
    unittest.main()
