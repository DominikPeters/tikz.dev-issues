#!/usr/bin/env python3
"""Adapt wheelchart's print presentation while preserving its examples."""
from pathlib import Path
import re
import sys


def prepare(tree):
    path = tree / 'wheelchart.tex'
    source = path.read_text()
    source = source.replace(r'\documentclass', r'\PassOptionsToPackage{nomulticol,nohyperref}{doc}'
                            + '\n' + r'\documentclass', 1)
    end = re.search(r'\\documentclass[^\n]*', source).end()
    source = source[:end] + r'''
\usepackage[latexmk,mathjax,IndexRef=nameref,HomeHTMLFilename=index]{lwarp}
\usepackage{tikz-dev-fast-lwarp}
\CSSFilename{style.css}
\setcounter{FileDepth}{1}
\boolfalse{CombineHigherDepths}
''' + source[end:]
    source = source.replace(r'\usepackage{codehigh}', r'\usepackage{listings}')
    source = source.replace(r'\usepackage{tikzlings}', r'''% TikZlings declares a fading in the preamble. It is a PDF resource,
% not a document illustration, so keep lwarp's picture hooks nested here.
\begin{warpHTML}
\setcounter{LWR@lateximagedepth}{1}
\end{warpHTML}
\usepackage{tikzlings}
\begin{warpHTML}
\setcounter{LWR@lateximagedepth}{0}
\end{warpHTML}''', 1)
    source = source.replace(r'\input{pgfmanual-en-macros.tex}', r'\usepackage{hyperref}'
                            + '\n' + r'\input{pgfmanual-en-macros.tex}', 1)
    source = re.sub(r'\\usepackage\{fancyhdr\}.*?(?=\\usepackage\{etoc\})',
                    lambda _: '\\usepackage{fancyhdr}\n% Print header and footer omitted.\n',
                    source, count=1, flags=re.S)
    source = re.sub(r'\\iftotalpages%\n\\newsavebox.*?\\fi%\n', '', source, count=1, flags=re.S)
    source = source.replace(r'\thispagestyle{fancy}', '')
    source = re.sub(r'^\\f@nch@setoffs[^\n]*\n', '', source, flags=re.M)
    source = source.replace(r'\indexsetup{othercode={\thispagestyle{fancy}}}', '')
    source = source.replace(r'\section*{\contentsname}', r'\subsection*{\contentsname}')
    # The slice-arc comparison table contains native graphics and math. Its
    # row-generating macro must be parsed in the same native context.
    source = re.sub(r'\\begin\{center\}(.*?)\\end\{center\}',
                    lambda m: '\\begin{lateximage}[Slice arc comparison]\n' + m[0]
                    + '\n\\end{lateximage}', source, flags=re.S)
    for title, slug in [('Usage', 'usage'), ('The main macro', 'main-macro'),
                        ('Additional macros', 'additional-macros'), ('Keys', 'keys'),
                        ('Additional examples', 'examples'), ('Version history', 'version-history'),
                        ('The source code', 'source-code')]:
        source = source.replace(r'\section{' + title + '}', r'\section[' + slug + ']{' + title + '}')
    source = source.replace(r'\begin{thebibliography}', r'\ForceHTMLPage' + '\n' + r'\begin{thebibliography}')
    source = source.replace(r'\printindex', r'\ForceHTMLPage' + '\n' + r'\printindex')
    source = source.replace(r'\dochighinput[language=latex/latex3]{wheelchart.sty}',
                            r'\begin{BlockClass}{example-code}' + '\n'
                            + r'\lstinputlisting[language={[LaTeX]TeX},basicstyle=\small\ttfamily,columns=fullflexible,keepspaces=true,breaklines=true]{wheelchart.sty}'
                            + '\n' + r'\end{BlockClass}')
    source = source.replace(r'\begin{document}', r'\usepackage{wheelchart-html}'
                            + '\n' + r'\begin{document}', 1)
    path.write_text(source)


if __name__ == '__main__':
    prepare(Path(sys.argv[1]))
