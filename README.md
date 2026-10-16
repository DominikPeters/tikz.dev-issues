# tikz.dev

Sources of [tikz.dev](https://tikz.dev), the HTML versions of the manuals of
[PGF/TikZ](https://github.com/pgf-tikz/pgf) (`tikz.dev/`),
[pgfplots](https://github.com/pgf-tikz/pgfplots) (`tikz.dev/pgfplots/`) and
[tcolorbox](https://github.com/T-F-S/tcolorbox) (`tikz.dev/tcolorbox/`).

Feedback, suggestions and bug reports: please open an
[issue](https://github.com/DominikPeters/tikz.dev/issues).

## Layout

```
shared/        style.css, pgfmanual.js, lwarp-mathjax-emulation.js for all manuals
scripts/       fetch.sh, prepare.py, build.sh, deploy.sh
pgf/           pgf manual: lwarp build scripts, postprocessing, standalone images, ...
  upstream.lock    upstream repository and the commit the site is built from
  preprocess.py    mechanical edits to the upstream sources (section page names)
  patches/         remaining edits to upstream files, one patch per file
pgfplots/      pgfplots manual (same structure, no preprocess.py)
tcolorbox/     tcolorbox manual: dedicated converter instead of lwarp
migration/     commit maps from the old fork repositories
.upstream/     (not committed) upstream checkouts made by fetch.sh
build/         (not committed) build trees and generated sites
```

The upstream package sources are not part of this repository. Each package
pins an upstream commit in `<package>/upstream.lock`; the manual is built from
that commit plus the package's preprocessing and patches.

## Building

```bash
scripts/fetch.sh pgf          # upstream checkout at the pinned commit
scripts/build.sh pgf          # -> build/pgf/site
```

`scripts/fetch.sh pgf origin/master` (or any commit) tries another upstream
version without changing the pin. `scripts/prepare.py pgf` only assembles the
source tree (`build/pgf/src`) without running LaTeX.

Package-specific CSS and JavaScript go into the shared files, selected by the
class on `<html>` that each build sets: `.pkg-pgf`, `.pkg-pgfplots`,
`.pkg-tcolorbox`.

### LaTeX formatting

Both lwarp manuals load `shared/tikz-dev-fast-lwarp.sty`. It reuses parsed
argument handlers for spans and filename sanitization, instead of rebuilding
those handlers for every colored word and link. Internal links whose destination
is already a plain filename also bypass font-command cleanup. Formatted names
and custom filename prefixes retain the original cleanup. LaTeX still reruns
until actual references stabilize. An image-page scratch counter is omitted
from include checkpoints to avoid an otherwise redundant pass; illustration
execution is unchanged. If lwarp changes the relevant
implementation, that optimization falls back to the original handler and logs
a warning. Integration tests compare extracted HTML, references and image
manifests against stock lwarp.

### Drawing reuse between LaTeX passes

PGFplots also reuses selected, reviewed illustrations within one build. The
first pass draws them normally; subsequent passes reuse their original PDF
pages. Setup code, code outside pictures, pre/post hooks, listings and lwarp's
HTML/reference bookkeeping still execute. PNG/SVG conversion reads the saved
original pages directly, avoiding rounding changes from PDF imports.

The package `illustration-audit.json` files record unsafe examples and a limited
opt-in set. Labels, remembered nodes, random state, global declarations, file
writes and uncertain dependencies are reasons to keep drawings live. Unreviewed
examples always execute. Eligibility requires the reviewed upstream commit,
whole chapter hash and exact example hash; changed sources run uncached until
reviewed again. The PGF review is retained, but its drawing cache is disabled:
the simple tutorial sample did not show a consistent benefit.

The initial review explicitly classifies 391 of 4,145 inventoried codeexamples;
3,754 remain unclassified and uncached. Drawing reuse is enabled for 118 reviewed
PGFplots examples. Completing the classification and measuring a full manual
build with drawing reuse remain follow-up work.

This cache lives in the prepared source tree and is cleared at the start of
each build. It accelerates repeated LaTeX passes even on a fresh GitHub runner.
Set `TIKZ_RENDER_CACHE=0` to disable it for comparison. Keep the original-page
cache and its generated map together when rerunning illustration conversion.

To generate an untagged inventory for a new review:

```bash
python3 scripts/prepare.py pgfplots --no-illustration-cache --dest build/pgfplots/review
python3 scripts/illustration_audit.py pgfplots build/pgfplots/review/doc/latex/pgfplots \
  --output build/pgfplots/illustration-inventory.json
```

Automatic hazard tags are review prompts, not a proof of safety. Update the
review manifest only after checking dependencies and comparing cached and
uncached HTML, auxiliary files and rendered illustrations.

### Illustration conversion

PGF and PGFplots extract and crop illustrations in batches, then render them
with a bounded worker pool. PGFplots also generates the ImageMagick PNGs used
for shader fallbacks. SVG/PNG output formats, 300 dpi and one-point crop margins
are preserved. Bounding boxes are measured in separate Ghostscript processes
to preserve the original crop edges. Tcolorbox already uses a separate batch
converter.

Rendered results are cached in `build/image-cache`, outside the disposable
prepared sources. GitHub Actions restores this cache between builds. Cache
keys include the individual PDF page and its resource objects (fonts, embedded
images, etc.), converter code, settings and tool versions. File names, page
numbers and document timestamps do not determine reuse. Every required output
must exist and match its recorded checksum; incomplete or damaged entries are
rebuilt. A conversion failure stops the build before publishing new images.

Set `TIKZ_IMAGE_JOBS` to change the default of four workers, or
`TIKZ_IMAGE_CACHE` to choose a different cache directory. Removing
`build/image-cache` forces conversion on the next build. The cache stores
unoptimized SVGs so postprocessing and SVGO can be changed independently.

To rerun just illustration conversion from an existing prepared tree, without
repeating LaTeX:

```bash
cd build/pgf/src/doc/generic/pgf
python3 convert_illustrations.py pgfmanual_html.pdf pgfmanual-images.txt pgfmanual-images \
  --cache ../../../../../image-cache
```

The Python dependencies include `pypdf`. Cache invalidation and failure tests
run with `python3 -m unittest discover -s tests` from the repository root.

## Automation (GitHub Actions)

* `build.yml`: on every push to `main`, the manuals whose folders changed (all
  of them if `shared/` or `scripts/` changed) are built at their pinned upstream
  commit and deployed.
* `upstream.yml`: every six hours, checks whether the upstream repositories have
  new commits touching the documentation (`watch` in `upstream.lock`). If so,
  the manual is built at the new commit and
  * on success deployed, and the new commit is recorded in `upstream.lock` by
    a commit to `main` listing the upstream changes;
  * on failure an issue "[package] upstream build failing" is opened (or
    updated); the site stays as it is. The issue is closed automatically after
    the next successful build. A failed upstream commit is not built again
    until upstream has a newer relevant commit or the files here that the
    build uses change (`scripts/build-key.sh`); running the workflow by hand
    with "retry" forces another attempt.

Deployment uses `scripts/deploy.sh` (FTP with TLS, via lftp) with the
repository variables `FTP_HOST`, `FTP_USER`, `FTP_ROOT` (folder of the site,
relative to the FTP login), optionally `DEPLOY_PREFIX` (e.g. `/monorepo` for
testing), and the secret `FTP_PASSWORD`. It never deletes files on the server,
and uploads only the files whose contents changed since the last deploy (it
keeps a list of checksums, `.deploy-manifest`, in each manual's folder on the
server; `FULL_DEPLOY=1` uploads everything).

## Fixing a patch

When upstream changes a place one of the patches touches, the build stops
with "patch X does not apply". To fix it:

```bash
scripts/fetch.sh pgf <new-commit>
scripts/prepare.py pgf --reject      # applies what it can, leaves *.rej files
# edit the files named by the .rej files in build/pgf/src by hand, then
scripts/prepare.py pgf --refresh-patches build/pgf/src
```

`--refresh-patches` rewrites `pgf/patches/` from the edited tree; commit the
result together with the new commit in `pgf/upstream.lock`.

## License

The tikz.dev tooling (scripts, workflows, `shared/`, the build and
postprocessing scripts, the tcolorbox converter) is under the MIT license
(`LICENSE`). The manuals belong to their authors and keep their licenses, which
also apply to the patches and other material derived from them here, and to
the generated pages:

* pgf: documentation GNU FDL 1.2 or LPPL 1.3c (code GPL 2 or LPPL 1.3c)
* pgfplots: GPL 3 or later
* tcolorbox: LPPL 1.3c or later

`REUSE.toml` lists which files fall under which license; the texts are in
`LICENSES/`.
