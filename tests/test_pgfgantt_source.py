"""Docstrip extraction must preserve examples and implementation tokens."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('pgfgantt_source',
    Path(__file__).resolve().parents[1] / 'pgfgantt/preprocess.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class PgfganttSourceTests(unittest.TestCase):
    def test_unwraps_docstrip_without_executing_or_rewriting_implementation(self):
        code = '\\iftrue\n  \\def\\example#1{#1}% retain comment\n\\fi\n'
        text = r'''%<*driver>
\documentclass{ltxdoc}
%</driver>
% \fi
% \section{Guide}
% \begin{texcode}
% \iftrue \ganttbar{A}{1}{2}\fi
% \end{texcode}
% \iffalse
%<*package>
% \fi
%    \begin{macrocode}
''' + code + r'''%    \end{macrocode}
% \Finale
\endinput
'''
        result = source.documentation(text)
        self.assertIn(code, result)
        self.assertIn(r'\iftrue \ganttbar{A}{1}{2}\fi', result)
        self.assertIn('\\begin{implementationcode}\n' + code + '\\end{implementationcode}', result)
        self.assertNotIn('\\endinput', result)
        self.assertNotIn('%<', result)
        self.assertFalse(result.startswith('\\fi'))

    def test_rejects_unexpected_executable_source(self):
        with self.assertRaisesRegex(ValueError, 'outside macrocode'):
            source.documentation('%</driver>\n\\unexpected\n')
        with self.assertRaisesRegex(ValueError, 'Unclosed'):
            source.documentation('%</driver>\n% \\begin{macrocode}\n')


if __name__ == '__main__':
    unittest.main()
