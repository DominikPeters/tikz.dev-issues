"""Command names in prose must follow TeX's control-word spacing rules."""
from pathlib import Path
import sys
import unittest

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'shared'))
from texhtml.core import Context, Converter, Page


class SymbolSpacingTests(unittest.TestCase):
    def convert(self, text):
        converter = Converter(Context(), text, 'test', page=Page('test', 'test', '', '1'))
        return converter.render(converter.items(0, len(text)))

    def test_chemfig_command_names_have_no_delimiter_space(self):
        source = r'\section{The \texttt{\textbackslash chemfig} macro}'
        html = self.convert(source)
        self.assertIn(r'<span class="texttt">\chemfig</span>', html)
        self.assertNotIn(r'\ chemfig', html)
        for source in [r'\texttt{\textbackslash CFhash}', '\\texttt{\\textbackslash\n  merge}']:
            with self.subTest(source=source):
                text = BeautifulSoup(self.convert(source), 'html.parser').get_text()
                self.assertNotRegex(text, r'\\\s+\w')

    def test_explicit_group_and_control_space_remain_visible(self):
        for source in [r'\textbackslash{} name', r'\textbackslash\ name']:
            with self.subTest(source=source):
                text = BeautifulSoup(self.convert(source), 'html.parser').get_text()
                self.assertEqual(text.strip(), '\\ name')

    def test_consuming_a_delimiter_does_not_consume_a_paragraph_break(self):
        html = self.convert('Copyright \\copyright\n\nNext paragraph.')
        soup = BeautifulSoup(html, 'html.parser')
        self.assertEqual(len(soup.find_all('p')), 2)

    def test_page_references_to_examples_use_the_containing_section(self):
        context = Context()
        context.add_label('exercise', slug='listings', anchor='exercise', text='17.1',
                          kind='label', containing_section='17.11')
        source = r'Example~\ref{exercise} on page~\pageref{exercise}.'
        converter = Converter(context, source, 'options')
        html = converter.render(converter.items(0, len(source)))
        soup = BeautifulSoup(html, 'html.parser')
        self.assertEqual([a.get_text() for a in soup.find_all('a')], ['17.1', '17.11'])
        self.assertEqual({a['href'] for a in soup.find_all('a')}, {'listings#exercise'})


if __name__ == '__main__':
    unittest.main()
