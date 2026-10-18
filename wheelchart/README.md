# wheelchart manual

The lwarp build of [wheelchart](https://ctan.org/pkg/wheelchart) for
`tikz.dev/wheelchart/`, using the shared PGF documentation helpers and the
same navigation, styling and DocSearch frontend as the other manuals.

```bash
scripts/fetch.sh wheelchart
scripts/build.sh wheelchart
scripts/serve.py          # http://127.0.0.1:8765/wheelchart/
```

Wheelchart is distributed through CTAN without an upstream Git repository.
`upstream.json` pins immutable Debian TeX Live distribution archives containing
the original wheelchart 6.0 package and documentation. Their SHA-256 hashes
are checked before extracting the three named source files. Downloads are
cached in `.upstream/archive-cache` and restored by CI. The lock's `commit`
field is the SHA-256 of the source manifest. Package sources remain outside
this repository, as they do for Git-based manuals.

To update the release, select matching package/documentation archives, update
their checksums and paths in `upstream.json`, then update the manifest hash in
`upstream.lock`. `fetch.sh` replaces the previous snapshot after validating the
new archives. Git upstream-watch intentionally skips this release pin; updates
are reviewed explicitly. The normal build and deployment workflows include it.

The contents wheel at the start of the manual is drawn from the sections and
page numbers of the PDF manual (read from the bookmarks of `wheelchart.pdf`,
pinned with the sources by `preprocess.py`), as the HTML build's own page
numbers have nothing to do with the PDF's; it stays on the start page above
the contents.

The adapter preserves all 93 `codeexample` blocks. Complete example output is
rendered as an image, including legends outside `tikzpicture`. The real `etoc`
package is retained for examples using its table-of-contents data. TikZlings'
preamble fading declaration remains a PDF resource instead of being captured
as a document illustration. Print headers and footers are removed, while the
source appendix becomes copyable HTML code.

Illustrations use the shared cached conversion and SVG/PNG selection after
SVGO. All example code executes in its original order, retaining shared data
definitions. Requires the usual TeX Live lwarp tools plus `dpkg-deb` when
fetching the pinned distribution archives (provided by Ubuntu/Debian and CI).
