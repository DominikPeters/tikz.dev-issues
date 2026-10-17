"""Verify generated manual navigation, references, and illustration choices."""
import importlib.util
from contextlib import chdir
from pathlib import Path
import sys
import tempfile
import unittest

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shared'))
from check_manual_site import check_site

spec = importlib.util.spec_from_file_location('tikz_cd_site', ROOT / 'tikz-cd/postprocessing.py')
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)

HTML = r'''<!doctype html><html><head><title>Manual</title>
<link rel="stylesheet" href="style.css">
<script>// Lwarp MathJax emulation code</script>
<script id="MathJax-script" src="https://example.org/mathjax.js"></script>
</head><body><div class="pagegrid"><main class="bodycontainer"><section class="textbody">
<div data-nosnippet style="display:none">\(\newcommand{\custommacro}{x}\)</div>
<h4 id="autosec-1"><span class="sectionnumber">1 </span>First section</h4>
<a id="original-label"></a><p>See <a href="#original-label">this definition</a>.</p>
<div class="example"><div class="example-image"><p>
<a href="tikz-cd-doc-images/image-1.svg"><img src="tikz-cd-doc-images/image-1.svg" alt="diagram"></a>
</p></div><div class="example-code"><p>\begin{tikzcd}<br>A  B<br>\end{tikzcd}</p></div></div>
<h5 id="autosec-2"><span class="sectionnumber">1.1 </span>Another <em>&amp;</em> section</h5>
<table><tr><td>First column</td><td>Second column</td></tr></table>
</section></main></div></body></html>'''


class ManualSiteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        images = self.root / site.IMAGES
        images.mkdir()
        (images / 'image-1.svg').write_text('<svg width="60pt" height="30pt"/>')
        (images / 'image-1.png').write_bytes(b'png')
        for name in ['style.css', 'pgfmanual.js', 'lwarp-mathjax-emulation.js']:
            (self.root / name).write_text('fixture')
        for name in site.PAGES:
            result = site.finish_page(HTML, name, {'image-1': {'format': 'png'}}, self.root)
            (self.root / name).write_text(result)

    def test_site_preserves_anchors_and_uses_selected_images_with_dimensions(self):
        result = check_site(self.root)
        self.assertEqual(result, {'pages': 5, 'examples': 5, 'images': 5, 'entries': 0})
        soup = BeautifulSoup((self.root / 'getting-started.html').read_text(), 'html5lib')
        img = soup.img
        self.assertEqual(img['src'], 'tikz-cd-doc-images/image-1.png')
        self.assertEqual((img['width'], img['height']), ('80.000', '40.000'))
        self.assertEqual(img.parent['href'], img['src'])
        self.assertIsNotNone(soup.find(id='original-label'))
        self.assertIsNotNone(soup.find(id='autosec-1'))
        self.assertIsNotNone(soup.find(id='sec-1'))
        self.assertEqual(soup.select_one('.textbody .sectionnumber')['id'], 'sec-1')
        self.assertFalse(soup.select('#local-toc-container .sectionnumber'))
        self.assertIsNotNone(soup.select_one('#local-toc-container a[href="#sec-1"]'))
        self.assertIsNotNone(soup.select_one('#chapter-toc-container a[aria-current="page"]'))
        self.assertIsNotNone(soup.select_one('.example-code code'))
        self.assertEqual(len(soup.select('.clipboardButton')), 1)
        self.assertEqual(soup.select_one('.example-code .spaces').get_text(), '  ')
        self.assertNotIn('\u2007', soup.select_one('.example-code').get_text())
        self.assertIsNotNone(soup.select_one('.table-scroll[tabindex="0"] table'))
        self.assertEqual(soup.select_one('#autosec-2 .heading-title').get_text(),
                         'Another & section')

    def test_math_customizations_survive_externalizing_the_emulation_script(self):
        soup = BeautifulSoup((self.root / 'getting-started.html').read_text(), 'html5lib')
        self.assertIn(r'\custommacro', soup.select_one('[data-nosnippet]').get_text())
        self.assertEqual(len(soup.select('script[src^="lwarp-mathjax-emulation.js"]')), 1)
        self.assertIsNotNone(soup.find(id='MathJax-script'))

    def test_contributed_manuals_keep_their_own_images_navigation_and_metadata(self):
        for package in ['pgf-pie', 'tikz-feynman']:
            with self.subTest(package=package):
                spec = importlib.util.spec_from_file_location(
                    package.replace('-', '_'), ROOT / package / 'postprocessing.py')
                manual = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(manual)
                root = self.root / package
                root.mkdir()
                images = root / manual.IMAGES
                images.mkdir()
                for suffix in ['svg', 'png']:
                    (images / ('image-1.' + suffix)).write_bytes(
                        (self.root / site.IMAGES / ('image-1.' + suffix)).read_bytes())
                for asset in ['style.css', 'pgfmanual.js', 'lwarp-mathjax-emulation.js']:
                    (root / asset).write_text('fixture')
                for filename in manual.PAGES:
                    html = HTML.replace(site.IMAGES, manual.IMAGES)
                    (root / filename).write_text(manual.finish_page(
                        html, filename, {'image-1': {'format': 'png'}}, root))
                self.assertEqual(check_site(root)['pages'], len(manual.PAGES))
                soup = BeautifulSoup((root / 'index.html').read_text(), 'html5lib')
                self.assertEqual(soup.img['src'], manual.IMAGES + '/image-1.png')
                self.assertEqual(soup.select_one('header strong > a')['href'], '../')
                current = soup.select_one('header .pkg-menu a[aria-current="page"]')
                self.assertEqual(current['href'], './')
                self.assertIn('pkg-' + package, soup.html['class'])
                self.assertEqual(soup.select_one('link[rel="canonical"]')['href'],
                                 'https://tikz.dev/' + package + '/')
                self.assertIn(manual.MANUAL.title, soup.title.get_text())

    def test_validator_rejects_missing_asset(self):
        (self.root / site.IMAGES / 'image-1.png').unlink()
        with self.assertRaisesRegex(ValueError, 'missing file'):
            check_site(self.root)

    def test_validator_rejects_broken_anchors_and_duplicate_ids(self):
        path = self.root / 'index.html'
        original = path.read_text()
        for extra, expected in [('<a href="getting-started.html#missing">bad</a>', 'missing anchor'),
                                ('<span id="original-label"></span>', 'duplicate anchor')]:
            with self.subTest(expected=expected):
                path.write_text(original.replace('</body>', extra + '</body>'))
                with self.assertRaisesRegex(ValueError, expected):
                    check_site(self.root)

    def test_validator_checks_visible_reference_markers(self):
        path = self.root / 'index.html'
        original = path.read_text()
        path.write_text(original.replace('</body>', '<p>See ??</p></body>'))
        with self.assertRaisesRegex(ValueError, 'unresolved reference'):
            check_site(self.root)
        path.write_text(original.replace('</body>', '<code class="example-code">??</code></body>'))
        check_site(self.root)

    def test_validator_rejects_unexpanded_tex_even_in_external_links(self):
        path = self.root / 'index.html'
        original = path.read_text()
        path.write_text(original.replace('</body>',
            r'<a href="https://doi.org/\thefield{doi}">Journal</a></body>'))
        with self.assertRaisesRegex(ValueError, 'unexpanded TeX in URL'):
            check_site(self.root)

    def test_new_upstream_page_cannot_be_silently_omitted(self):
        (self.root / 'new-chapter.html').write_text(HTML)
        with chdir(self.root), self.assertRaisesRegex(ValueError, 'review the page map'):
            site.main()


if __name__ == '__main__':
    unittest.main()
