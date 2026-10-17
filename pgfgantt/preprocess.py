#!/usr/bin/env python3
"""Unwrap the documented source for lwarp, keeping executable examples intact."""
from pathlib import Path
import re
import sys


def documentation(source):
    """Extract docstrip prose and retain implementation as verbatim listings."""
    source = source.split('%</driver>', 1)[1]
    source = re.sub(r'^\s*% \\fi\s*\n', '', source, count=1)
    lines = []
    in_code = False
    source = re.sub(r'% \\iffalse\n%<[^\n]+>\n% \\fi\n', '', source)
    for line in source.splitlines(keepends=True):
        if line.strip() == r'% \Finale':
            break
        if re.match(r'%\s+\\begin\{macrocode\}', line):
            if in_code:
                raise ValueError('Nested macrocode block')
            in_code = True
            lines.append('\\begin{implementationcode}\n')
        elif re.match(r'%\s+\\end\{macrocode\}', line):
            if not in_code:
                raise ValueError('Unexpected end of macrocode')
            in_code = False
            lines.append('\\end{implementationcode}\n')
        elif in_code:
            lines.append(line)
        elif line.startswith('%<'):
            continue
        elif line.startswith('%'):
            lines.append(re.sub(r'^% ?', '', line))
        elif line.strip():
            raise ValueError('Executable source outside macrocode: ' + line.strip())
    if in_code:
        raise ValueError('Unclosed macrocode block')
    return ''.join(lines)


def prepare(tree):
    source = (tree / 'pgfgantt.dtx').read_text()
    body = documentation(source)
    body = body.replace(r'\GetFileInfo{pgfgantt.sty}', '')
    body = body.replace(r'\StopEventually{\PrintIndex}', '')
    body = body.replace(r'\lstDeleteShortInline|', '').replace(r'\MakeShortVerb{\|}', '')
    body = body.replace(r'\Finale', '')
    body = re.sub(r'\\shorthand(?:on|off)\{"\}', '', body)
    # Parse setup definitions with native math catcodes too: custom link
    # paths contain TikZ's ($...$) syntax before the chart starts.
    pieces = re.split(r'(\\begin\{(?:texcode|implementationcode)\}.*?\\end\{(?:texcode|implementationcode)\})',
                      body, flags=re.S)
    for i in range(0, len(pieces), 2):
        pieces[i] = re.sub(r'\\begin\{center\}(.*?)\\end\{center\}',
            lambda m: ('\\begin{lateximage}[Gantt chart example]\n' + m[0]
                       + '\n\\end{lateximage}') if re.search(r'\\begin\{(?:ganttchart|tikzpicture)\}', m[1]) else m[0],
            pieces[i], flags=re.S)
    body = ''.join(pieces)
    for title, slug in [('Introduction', 'introduction'), ('User Guide', 'user-guide'),
                        ('Implementation', 'implementation')]:
        body = body.replace(r'\section{' + title + '}', r'\section[' + slug + ']{' + title + '}')
    # Remove docstrip's outer comment guard, not example or implementation code.
    body = re.sub(r'^\\DoNotIndex\{[^\n]*\}\n', '', body, flags=re.M)
    version = re.search(r'\\ProvidesPackage\{pgfgantt\}\[(\S+) (\S+)', source)
    preamble = r'''\PassOptionsToPackage{dvipsnames}{xcolor}
\PassOptionsToPackage{nomulticol,nohyperref}{doc}
\documentclass{ltxdoc}
\usepackage[latexmk,mathjax,IndexRef=nameref,HomeHTMLFilename=index]{lwarp}
\usepackage{tikz-dev-fast-lwarp}
\CSSFilename{style.css}
\setcounter{FileDepth}{1}
\boolfalse{CombineHigherDepths}
\usepackage{pgfgantt}
\usetikzlibrary{shadows,shadings,decorations.pathmorphing,shapes.misc}
\usepackage{array,booktabs,listings,multicol,makeidx}
\usepackage{hyperref}
\input{pgfmanual-en-macros.tex}
\usepackage{pgfgantt-html}
'''
    preamble += '\\def\\filedate{' + version[1] + '}\n\\def\\fileversion{' + version[2] + '}\n'
    (tree / 'pgfgantt-manual.tex').write_text(preamble + '\\begin{document}\n' + body
        + '\n\\ForceHTMLPage\n\\printindex\n\\end{document}\n')


if __name__ == '__main__':
    prepare(Path(sys.argv[1]))
