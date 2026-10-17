"""Real LuaLaTeX integration coverage for the audited illustration cache."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
CACHE_ID = "a" * 64

DOCUMENT = r"""
\documentclass{article}
\usepackage[warpHTML,mathjax,BaseJobname=main,HomeHTMLFilename=home]{lwarp}
\MathJaxFilename{mathjax.txt}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{tikz}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usepackage{tikz-dev-fast-lwarp}
\usepackage{tikz-dev-illustration-cache}
\newcount\outsideeffects
\newcount\uncachedruns
\makeatletter
\newcommand\CurrentPictureID{\the\pgf@picture@serial@count}
\let\code@pre\@empty
\let\code@post\@empty
% Exercise the same raw-source path used by PGF's codeexample execution:
% the render-cache key wraps code@pre, which inspects \code@temp before the
% source is retokenized with \scantokens.
\def\code@pre{%
  \global\advance\outsideeffects by 1\relax
  \typeout{CACHE-PRE=\the\outsideeffects}%
}
\def\code@post{%
  \global\advance\outsideeffects by 1\relax
  \typeout{CACHE-POST=\the\outsideeffects}%
}
\newcommand\RunCachedExample[2]{%
  \begingroup
  \pgfkeys{/codeexample/render cache=#1}%
  \edef\code@temp{\detokenize{#2}}%
  \code@pre\expandafter\scantokens\expandafter{\code@temp}\code@post
  \endgroup
}
\makeatother
\begin{document}
\section{Cache integration}\label{cache-section}
\begin{itemize}
\item
\RunCachedExample{KEY}{\begin{tikzpicture}[draw=blue]
  \draw (0,0) -- (1,1);
  \begin{tikzpicture}
    \draw[red] (0,0) circle[radius=2pt];
  \end{tikzpicture}
\end{tikzpicture}\typeout{CACHE-PGFID-A=\CurrentPictureID}}
\end{itemize}
\RunCachedExample{KEY}{\begin {tikzpicture}
  \fill[green] (0,0) rectangle (1,1);
\end {tikzpicture}\typeout{CACHE-PGFID-B=\CurrentPictureID}}
% PGFplots reads this inline table while changing catcodes inside axis.
\RunCachedExample{KEY}{\begin{tikzpicture}
  \begin{axis}[width=3cm,height=2cm]
    \addplot table[row sep=\\] {
      x y\\
      0 0\\
      1 1\\
      2 1.5\\
    };
  \end{axis}
\end{tikzpicture}}
\begin{tikzpicture}[alt={visible-alt-sentinel}]
  \draw[purple] (0,0) -- (1,0);
\end{tikzpicture}
\begin{tikzpicture}
  \global\advance\uncachedruns by 1
  \pgfmathrandominteger{\uncachedrandom}{1}{9999}
  \typeout{UNCACHED-RUN=\the\uncachedruns}
  \typeout{UNCACHED-RNG=\uncachedrandom}
  \node {\label{uncached-drawing-label}uncached drawing};
\end{tikzpicture}
\typeout{UNCACHED-PGFID=\CurrentPictureID}
\end{document}
"""


def available_tools():
    required = ("lualatex", "pdftotext", "python3")
    return all(shutil.which(tool) for tool in required)


@unittest.skipUnless(available_tools(), "requires LuaLaTeX, Python and Poppler")
class IllustrationCacheIntegrationTests(unittest.TestCase):
    def setUp(self):
        try:
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest("requires pypdf")

    def environment(self, cache_enabled, minimum_seconds="0"):
        env = os.environ.copy()
        env["TEXINPUTS"] = str(SHARED) + "//:" + env.get("TEXINPUTS", "")
        env["LUAINPUTS"] = str(SHARED) + "//:" + env.get("LUAINPUTS", "")
        pythonpath = [str(SHARED)]
        if env.get("PYTHONPATH"):
            pythonpath.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(pythonpath)
        env["TIKZ_RENDER_CACHE"] = "1" if cache_enabled else "0"
        env["TIKZ_RENDER_CACHE_MIN_SECONDS"] = str(minimum_seconds)
        return env

    def run_variant(self, directory, cache_enabled, minimum_seconds="0", inline_prose=False):
        directory.mkdir()
        (directory / "mathjax.txt").write_text("// fixture\n")
        source = DOCUMENT.replace("KEY", CACHE_ID)
        if inline_prose:
            source = source.replace(r"\end {tikzpicture}\typeout{CACHE-PGFID-B=",
                                    r"\end {tikzpicture}right of picture.\typeout{CACHE-PGFID-B=")
        (directory / "main_html.tex").write_text(source)
        env = self.environment(cache_enabled, minimum_seconds)
        first_pdf = None
        first_pending = None
        logs = []
        pass_aux = []
        for pass_number in range(1, 4):
            result = subprocess.run(
                [
                    sys.executable,
                    str(SHARED / "render_cache.py"),
                    "-halt-on-error",
                    "-interaction=nonstopmode",
                    "main_html.tex",
                ],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"pass {pass_number} failed\n{result.stdout[-7000:]}\n{result.stderr[-3000:]}",
            )
            logs.append((directory / "main_html.log").read_text(errors="replace"))
            pass_aux.append((directory / "main_html.aux").read_bytes())
            if pass_number == 1:
                first_pdf = directory / "first-pass.pdf"
                shutil.copyfile(directory / "main_html.pdf", first_pdf)
                pending = directory / "main_html.render-cache-pending.jsonl"
                first_pending = pending.read_text()

        subprocess.run(
            [
                "pdftotext",
                "-enc",
                "UTF-8",
                "-nopgbrk",
                "-layout",
                "main_html.pdf",
                "output.html",
            ],
            cwd=directory,
            check=True,
            capture_output=True,
            text=True,
        )
        cache_log = " ".join(logs[-1].split())
        return {
            "html": (directory / "output.html").read_bytes(),
            "aux": (directory / "main_html.aux").read_bytes(),
            "manifest": (directory / "main-images.txt").read_bytes(),
            "logs": logs,
            "pass_aux": pass_aux,
            "cache_log": cache_log,
            "first_pdf": first_pdf,
            "first_pending": first_pending,
            "pending_final": (directory / "main_html.render-cache-pending.jsonl").read_text(),
            "used_final": (directory / "main_html.render-cache-used.jsonl").read_text(),
            "cache_dir": directory / "main_html.render-cache",
            "directory": directory,
        }

    def test_cached_picture_bodies_match_three_stock_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stock = self.run_variant(root / "stock", cache_enabled=False)
            cached = self.run_variant(root / "cached", cache_enabled=True)

            self.assertEqual(stock["html"], cached["html"])
            self.assertEqual(stock["aux"], cached["aux"])
            self.assertEqual(stock["manifest"], cached["manifest"])
            self.assertIn(b"visible-alt-sentinel", stock["html"])
            self.assertIn(b"visible-alt-sentinel", cached["html"])

            # Three outer pictures share one ID; the nested picture is
            # absorbed into the first image and gets no independent key.
            pending = [json.loads(line) for line in cached["first_pending"].splitlines()]
            self.assertEqual(len(pending), 3, pending)
            self.assertEqual([entry["key"] for entry in pending],
                             [f"{CACHE_ID}-1", f"{CACHE_ID}-2", f"{CACHE_ID}-3"])
            self.assertEqual(cached["pending_final"], "")
            self.assertRegex(cached["cache_log"], r"Illustration drawing cache: [1-9][0-9]* reused")
            for log in cached["logs"]:
                self.assertNotRegex(
                    log,
                    r"Overfull \\hbox \([0-9]{4,}(?:\.\d+)?pt too wide\)",
                )

            # Uncached global effects, labels and random calls must still run on
            # each of the three passes. Hooks around the cached pictures do too.
            for variant in (stock, cached):
                for log in variant["logs"]:
                    for marker in ("CACHE-PRE=1", "CACHE-POST=2", "CACHE-PRE=3",
                                   "CACHE-POST=4", "CACHE-PRE=5", "CACHE-POST=6"):
                        self.assertIn(marker, log)
                    self.assertIn("UNCACHED-RUN=1", log)
                    self.assertRegex(log, r"UNCACHED-RNG=\d+")
                for aux in variant["pass_aux"]:
                    self.assertIn(b"uncached-drawing-label", aux)
            for label in ("CACHE-PGFID-A", "CACHE-PGFID-B", "UNCACHED-PGFID"):
                stock_values = [re.findall(rf"{label}=([^\s]+)", log)[-1]
                                for log in stock["logs"]]
                cached_values = [re.findall(rf"{label}=([^\s]+)", log)[-1]
                                 for log in cached["logs"]]
                self.assertEqual(stock_values, cached_values, label)

            # The converter helper must select each saved original page, and
            # those pages must match the physical pages from the first render.
            sys.path.insert(0, str(SHARED))
            try:
                import convert_illustrations
            finally:
                sys.path.remove(str(SHARED))
            from pypdf import PdfReader

            manifest_entries = convert_illustrations.read_manifest(
                cached["directory"] / "main-images.txt"
            )
            used_contents, used, cache_info = convert_illustrations.read_render_cache_used(
                cached["directory"] / "main_html.pdf", manifest_entries
            )
            self.assertTrue(used_contents)
            self.assertEqual(len(used), 3)
            original_reader = PdfReader(str(cached["first_pdf"]))
            cached_pdf_reader = PdfReader(str(cached["directory"] / "main_html.pdf"))
            for entry in pending:
                cached_page = PdfReader(str(cache_info["paths"][
                    next(name for name, key in used.items() if key == entry["key"])
                ])).pages[0]
                self.assertEqual(
                    convert_illustrations.page_bytes(cached_page),
                    convert_illustrations.page_bytes(original_reader.pages[entry["page"] - 1]),
                )
                self.assertGreater(len(cached_pdf_reader.pages), 0)


    def test_high_threshold_keeps_all_pictures_live_with_identical_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stock = self.run_variant(root / "stock", cache_enabled=False, inline_prose=True)
            high_threshold = self.run_variant(
                root / "high-threshold", cache_enabled=True, minimum_seconds="1000000", inline_prose=True
            )

            self.assertEqual(stock["html"], high_threshold["html"])
            self.assertEqual(stock["aux"], high_threshold["aux"])
            self.assertEqual(stock["manifest"], high_threshold["manifest"])
            self.assertEqual(high_threshold["first_pending"], "")
            self.assertEqual(high_threshold["pending_final"], "")
            self.assertEqual(high_threshold["used_final"], "")
            self.assertRegex(
                high_threshold["cache_log"],
                r"Illustration drawing cache: 0 reused, 0 recorded",
            )
            self.assertEqual(
                list(high_threshold["cache_dir"].glob("*.pdf")), []
            )
            self.assertEqual(
                list(high_threshold["cache_dir"].glob("*.tex")), []
            )

    def test_invalid_minimum_seconds_fails_with_clear_error(self):
        invalid_values = ("not-a-number", "-0.01", "nan", "inf")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, value in enumerate(invalid_values):
                with self.subTest(value=value):
                    directory = root / f"invalid-{index}"
                    directory.mkdir()
                    (directory / "mathjax.txt").write_text("// fixture\n")
                    (directory / "main_html.tex").write_text(
                        DOCUMENT.replace("KEY", CACHE_ID)
                    )
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(SHARED / "render_cache.py"),
                            "-halt-on-error",
                            "-interaction=nonstopmode",
                            "main_html.tex",
                        ],
                        cwd=directory,
                        env=self.environment(True, value),
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    log = (directory / "main_html.log").read_text(errors="replace")
                    # TeX wraps log lines mid-word; unwrap without inserting
                    # whitespace so the actual diagnostic stays recognizable.
                    self.assertIn(
                        "TIKZ_RENDER_CACHE_MIN_SECONDS must be a finite nonnegative number",
                        "".join(log.splitlines()),
                    )


if __name__ == "__main__":
    unittest.main()
