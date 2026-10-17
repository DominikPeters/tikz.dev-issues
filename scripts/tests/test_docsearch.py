"""Verify the search contract shared by the manual frontends."""
import ast
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared'))
from docsearch import add_docsearch
from assets import asset_url
from navbar import home_url, title_menu


def load_function(path, name, namespace):
    tree = ast.parse(path.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


class DocSearchTests(unittest.TestCase):
    def check_assets(self, soup):
        scripts = soup.select('script[src="https://cdn.jsdelivr.net/npm/@docsearch/js@3"]')
        self.assertEqual(len(scripts), 1)
        self.assertTrue(scripts[0].has_attr('defer'))
        self.assertIs(scripts[0].parent, soup.head)
        self.assertEqual(len(soup.select('link[href="https://cdn.jsdelivr.net/npm/@docsearch/css@3"]')), 1)
        self.assertEqual(len(soup.select('header #search')), 1)

    def test_pgf_and_pgfplots_headers_use_shared_assets(self):
        for package in ['pgf', 'pgfplots']:
            with self.subTest(package=package):
                namespace = dict(BeautifulSoup=BeautifulSoup, add_docsearch=add_docsearch,
                                 home_url=home_url, title_menu=title_menu,
                                 asset_url=lambda name: asset_url(name, ROOT / 'shared'))
                add_header = load_function(ROOT / package / 'postprocessing.py', 'add_header', namespace)
                soup = BeautifulSoup('<html><head></head><body><div class="bodyandsidetoc"></div></body></html>', 'html5lib')
                add_header(soup)
                self.check_assets(soup)
                soup.head.append(soup.new_tag('link', href='style.css', rel='stylesheet'))
                soup.head.append(soup.new_tag('script', src='pgfmanual.js'))
                version_assets = load_function(ROOT / package / 'postprocessing.py',
                                               'add_version_to_css_js', namespace)
                version_assets(soup)
                self.assertEqual(soup.select_one('script[src^="pgfmanual.js"]')['src'],
                                 asset_url('pgfmanual.js', ROOT / 'shared'))

    def test_converted_manual_shell_uses_shared_assets(self):
        # the page shell of the manuals converted with shared/texhtml (tcolorbox, ...)
        from texhtml.site import Manual, page_shell
        manual = Manual(package='tcolorbox', title='tcolorbox Manual', name_html='tcolorbox',
                        parts=[], notice='notice', footer_links=[], build_dir='', site_dir='',
                        img_dir='images')
        result = page_shell(manual, [], None, 'Manual', '<p>Content</p>', [], is_home=True)
        soup = BeautifulSoup(result, 'html5lib')
        self.check_assets(soup)
        button = soup.find(id='hamburger-button')
        self.assertEqual(button.name, 'button')
        self.assertEqual(button['type'], 'button')
        self.assertEqual(button['aria-controls'], 'chapter-toc-container')
        self.assertEqual(button['aria-expanded'], 'false')

    def test_references_are_in_the_converted_manual_navigation(self):
        from texhtml.core import Page
        from texhtml.site import Manual, page_shell
        manual = Manual(package='tcolorbox', title='tcolorbox Manual', name_html='tcolorbox',
                        parts=[], notice='notice', footer_links=[], build_dir='', site_dir='',
                        img_dir='images', has_references=True)
        for slug in ['introduction', 'references']:
            with self.subTest(slug=slug):
                page = Page(slug, slug, None, '')
                result = page_shell(manual, [], page, slug, '', [])
                soup = BeautifulSoup(result, 'html5lib')
                link = soup.select_one('#chapter-toc-container a[href="references"]')
                self.assertIsNotNone(link)
                self.assertEqual('current' in link.parent.get('class', []), slug == 'references')

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required to test browser configuration')
    def test_each_manual_searches_its_package_or_all_and_handles_missing_cdn(self):
        script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const cases = [];
for (const packageName of ['pgf', 'pgfplots', 'tcolorbox', 'tikz-cd', 'pgf-pie', 'tikz-feynman', 'wheelchart', 'pgfgantt', 'tkz-euclide', 'chemfig', 'forest', 'nicematrix', 'unknown']) {
  const calls = [];
  const sandbox = {
    document: {
      documentElement: {classList: ['pkg-' + packageName, 'pkg-pgf-contrib']},
      getElementById: () => ({}),
      addEventListener: () => {},
    },
    window: {docsearch: options => calls.push(options), addEventListener: () => {}},
  };
  vm.runInNewContext(source + '\ninitDocSearch();', sandbox);
  // The requests sent for this manual alone and for all manuals.
  const sent = {};
  if (calls.length) {
    const client = {search: (query) => {
      sent[sandbox.scope] = query.requests;
      return Promise.resolve({results: query.requests.map(() => ({hits: [], nbHits: 0}))});
    }};
    const search = calls[0].transformSearchClient(client).search;
    for (const scope of ['package', 'all']) {
      sandbox.scope = scope;
      vm.runInNewContext('searchScope = scope;', sandbox);
      search({requests: [{indexName: 'tikz', query: 'x'}]});
    }
  }
  // An unavailable CDN must not break navigation or the rest of the page.
  delete sandbox.window.docsearch;
  vm.runInNewContext('initDocSearch();', sandbox);
  cases.push({packageName, calls, sent});
}
process.stdout.write(JSON.stringify(cases));
'''
        result = subprocess.run(['node', '-e', script, str(ROOT / 'shared/pgfmanual.js')],
                                capture_output=True, text=True, check=True)
        for case in json.loads(result.stdout):
            package = case['packageName']
            if package == 'unknown':
                self.assertEqual(case['calls'], [])
                continue
            with self.subTest(package=package):
                self.assertEqual(len(case['calls']), 1)
                options = case['calls'][0]
                tag = 'tikz' if package == 'pgf' else package
                self.assertEqual([r['filters'] for r in case['sent']['package']], ['tags:' + tag])
                # all manuals: one request per manual, this page's manual first
                filters = [r['filters'] for r in case['sent']['all']]
                self.assertEqual(filters[0], 'tags:' + tag)
                self.assertEqual(len(filters), len(set(filters)))
                self.assertIn('tags:tikz', filters)
                self.assertIn('tags:pgfplots', filters)
                self.assertEqual((options['appId'], options['indexName'], options['container']),
                                 ('JS6V5VZSDB', 'tikz', '#search'))


if __name__ == '__main__':
    unittest.main()
