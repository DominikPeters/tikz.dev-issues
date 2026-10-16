"""Compare real lwarp output with and without the local parser optimization."""
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SHARED = Path(__file__).resolve().parents[1] / "shared"
DOCUMENT = r"""
\documentclass{article}
\usepackage[warpHTML,mathjax,BaseJobname=main,HomeHTMLFilename=home]{lwarp}
\MathJaxFilename{mathjax.txt}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{tikz}
\setcounter{FileDepth}{1}
\boolfalse{CombineHigherDepths}
PRELOAD
OPTIMIZATION
\begin{document}
\section{First \textbf{bold} $x$ section}\label{first}
\InlineClass{outer}{outer \textcolor{blue}{blue \textbf{bold} text} end}
Outside \textcolor{red}{red}, \ref{missing}, \ref{missing}, and \ref{second}; \hyperref[first]{back}.
\InlineClass{test}{\begin{minipage}[b][1cm][t]{2cm}mini\end{minipage}}
\InlineClass{test}{\begin{BlockClass}[color:red](note){test}block\end{BlockClass}}
\InlineClass{test}{\begin{LWR@BlockClassWP}{one}{two}(note){test}wp\end{LWR@BlockClassWP}}
\begin{minipage}{2cm}Outside minipage.\end{minipage}
\section{Second \textit{italic} section}\label{second}
\begin{tikzpicture}\draw[blue] (0,0)--(1,1);\end{tikzpicture}
\makeatletter
\expandafter\def\csname r@formatted@lwarp\endcsname{{Formatted}{2}{\textbf{Fancy}}{}{}}
Formatted file: \LWR@htmlrefsectionfilename{formatted}.
\begingroup
\renewcommand\HTMLFilename{prefix-}
Prefixed file: \LWR@htmlrefsectionfilename{first}.
\endgroup
\makeatother
\ref{first}, $a+b$, and \InlineClass[font-style:italic]{final}{last}.
\end{document}
"""


@unittest.skipUnless(shutil.which("lualatex") and shutil.which("pdftotext"),
                     "requires LuaLaTeX, lwarp and Poppler")
class FastLwarpTests(unittest.TestCase):
    def compare(self, preload="", fallback=False):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = []
            env = os.environ.copy()
            env["TEXINPUTS"] = str(SHARED) + "//:" + env.get("TEXINPUTS", "")
            for optimized in (False, True):
                path = Path(tmp) / str(optimized)
                path.mkdir()
                (path / "mathjax.txt").write_text("// fixture\n")
                source = DOCUMENT.replace("PRELOAD", preload).replace(
                    "OPTIMIZATION", r"\usepackage{tikz-dev-fast-lwarp}" if optimized else "")
                (path / "main_html.tex").write_text(source)
                for _ in range(3):
                    result = subprocess.run(
                        ["lualatex", "-halt-on-error", "-interaction=nonstopmode", "main_html.tex"],
                        cwd=path, env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout[-5000:])
                subprocess.run(["pdftotext", "-enc", "UTF-8", "-nopgbrk", "-layout",
                                "main_html.pdf", "output.html"], cwd=path, check=True)
                outputs.append(tuple((path / name).read_bytes() for name in
                                     ("output.html", "main_html.aux", "main-images.txt")))
                if optimized:
                    log = " ".join((path / "main_html.log").read_text().split())
                    if fallback:
                        self.assertIn("Unrecognized span setup; using stock lwarp", log)
                        self.assertRegex(log, r"Unrecognized filename setup; using stock l\s*warp", "filename fallback warning missing")
                        self.assertRegex(log, r"Unrecognized link setup; using stock l\s*warp", "link fallback warning missing")
                    else:
                        self.assertIn("Reusing span argument parsers", log)
                        self.assertIn("Reusing filename argument parsers", log)
                        self.assertIn("Using plain filename links", log)
                        self.assertNotIn("Unrecognized", log)
            self.assertEqual(outputs[0], outputs[1])

    @unittest.skipUnless(shutil.which("latexmk"), "requires latexmk")
    def test_image_scratch_counter_does_not_force_an_extra_pass(self):
        runs = []
        outputs = []
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["TEXINPUTS"] = str(SHARED) + "//:" + env.get("TEXINPUTS", "")
            for optimized in (False, True):
                path = Path(tmp) / str(optimized)
                path.mkdir()
                (path / "main_html.tex").write_text(r"""
\documentclass{article}
\usepackage[warpHTML,BaseJobname=main,HomeHTMLFilename=home]{lwarp}
\usepackage{tikz}
OPTIMIZATION
\begin{document}
\include{chapter}
\end{document}
""".replace("OPTIMIZATION", r"\usepackage{tikz-dev-fast-lwarp}" if optimized else ""))
                (path / "chapter.tex").write_text(r"""
\section{Example}\label{example}
\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}
""")
                result = subprocess.run(
                    ["latexmk", "-lualatex", "-interaction=nonstopmode", "-halt-on-error", "main_html.tex"],
                    cwd=path, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-1000:])
                runs.append(len(re.findall(r"Run number \d+ of rule 'lualatex'", result.stdout)))
                subprocess.run(["pdftotext", "-enc", "UTF-8", "-nopgbrk", "-layout",
                                "main_html.pdf", "output.html"], cwd=path, check=True)
                aux = {p.name: re.sub(rb"(?m)^\\setcounter\{LWR@LIpage\}[^\n]*\n", b"", p.read_bytes())
                       for p in path.glob("*.aux")}
                outputs.append(((path / "output.html").read_bytes(),
                                (path / "main-images.txt").read_bytes(), aux))
            self.assertGreater(runs[0], runs[1], f"stock/optimized pass counts: {runs}")
            self.assertEqual(outputs[0], outputs[1])

    def test_html_references_and_images_unchanged(self):
        self.compare()

    def test_unrecognized_lwarp_uses_original_implementations(self):
        self.compare(r"""
\makeatletter
\let\originalnestspan\LWR@nestspan
\def\LWR@nestspan{\originalnestspan}
\let\originalnullfonts\LWR@nullfonts
\def\LWR@nullfonts{\originalnullfonts}
\let\originalrefsectionfilename\LWR@htmlrefsectionfilename
\def\LWR@htmlrefsectionfilename#1{\originalrefsectionfilename{#1}}
\makeatother
""", fallback=True)
