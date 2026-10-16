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
