#!/usr/bin/env python3
"""Adapt wheelchart's print presentation while preserving its examples."""
from pathlib import Path
import re
import sys


def pdf_contents(pdf):
    """The sections of the printed manual with their pages: [(number, title,
    page)], and the page of the source code (the label Thesourcecode)."""
    from pypdf import PdfReader
    reader = PdfReader(pdf)
    entries, source_page = [], None
    for item in reader.outline:
        if isinstance(item, list):
            continue  # subsections
        page = reader.page_labels[reader.get_destination_page_number(item)]
        match = re.fullmatch(r'(?:(\d+|[A-Z]) )?(.+)', item.title)
        number, title = match[1] or '', match[2]
        if title == 'The source code':
            source_page = page
            break
        if title != 'Contents':  # the contents are not listed in themselves
            entries.append((number, title, page))
    if not entries or source_page is None:
        raise SystemExit(f'{pdf}: no sections or no source code in the bookmarks')
    return entries, source_page


def contents_setup(entries, source_page):
    """TeX code for the contents wheel: the table of contents and the page
    numbers of the PDF manual, which its picture shows (lwarp's own pages
    have nothing to do with the PDF's)."""
    lines = []
    for number, title, page in entries:
        title = re.sub(r'([&%#_$])', r'\\\1', title)
        name = rf'\numberline {{{number}}}{title}' if number else title
        anchor = f'section.{number}' if number else 'section*'
        lines.append(rf'\contentsline {{section}}{{{name}}}{{{page}}}{{{anchor}}}')
    return ('\\begin{warpHTML}\n\\makeatletter\n'
            '% the contents wheel shows the sections and pages of the PDF manual\n'
            '\\gdef\\WCHTMLexamplesetup{%\n'
            '  \\Etoc@toctoks{%\n    ' + '%\n    '.join(lines) + '}%\n'
            f'  \\def\\getpagerefnumber##1{{{source_page}}}}}\n'
            '\\makeatother\n\\end{warpHTML}\n')


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
    start = source.index(r'\begin{codeexample}', source.index(r'\subsection*{\contentsname}'))
    source = source[:start] + contents_setup(*pdf_contents(tree / 'wheelchart.pdf')) + source[start:]
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
