# tikz.dev

Sources of [tikz.dev](https://tikz.dev), HTML versions of the manuals of
PGF/TikZ and related packages:

| Manual | On tikz.dev | Upstream |
|---|---|---|
| PGF/TikZ | [tikz.dev](https://tikz.dev/) | [pgf-tikz/pgf](https://github.com/pgf-tikz/pgf) |
| PGFplots | [/pgfplots/](https://tikz.dev/pgfplots/) | [pgf-tikz/pgfplots](https://github.com/pgf-tikz/pgfplots) |
| tcolorbox | [/tcolorbox/](https://tikz.dev/tcolorbox/) | [T-F-S/tcolorbox](https://github.com/T-F-S/tcolorbox) |
| tikz-cd | [/tikz-cd/](https://tikz.dev/tikz-cd/) | [astoff/tikz-cd](https://github.com/astoff/tikz-cd) |
| pgf-pie | [/pgf-pie/](https://tikz.dev/pgf-pie/) | [pgf-tikz/pgf-pie](https://github.com/pgf-tikz/pgf-pie) |
| TikZ-Feynman | [/tikz-feynman/](https://tikz.dev/tikz-feynman/) | [JP-Ellis/tikz-feynman](https://github.com/JP-Ellis/tikz-feynman) |
| wheelchart | [/wheelchart/](https://tikz.dev/wheelchart/) | [CTAN](https://ctan.org/pkg/wheelchart) |
| pgfgantt | [/pgfgantt/](https://tikz.dev/pgfgantt/) | [skafdasschaf/latex-pgfgantt](https://github.com/skafdasschaf/latex-pgfgantt) |
| tkz-euclide | [/tkz-euclide/](https://tikz.dev/tkz-euclide/) | [CTAN](https://ctan.org/pkg/tkz-euclide) |
| chemfig | [/chemfig/](https://tikz.dev/chemfig/) | [CTAN](https://ctan.org/pkg/chemfig) |

Feedback, suggestions and bug reports are welcome as
[issues](https://github.com/DominikPeters/tikz.dev/issues).

## How it works

The package sources are not stored here. Each manual pins an upstream commit
in `<package>/upstream.lock`, and is built from that commit plus the edits in
its folder (patches, HTML adaptations, postprocessing). Most manuals are
converted with [lwarp](https://ctan.org/pkg/lwarp); tcolorbox, tkz-euclide and
chemfig are converted by a Python converter. All manuals share one stylesheet, one script and one header.

GitHub Actions builds and deploys a manual whenever its folder changes, and
checks every six hours for new upstream commits to its documentation. A new
commit that builds is published and recorded in the lock file; one that fails
opens an issue and leaves the site unchanged.

## Building a manual locally

```bash
scripts/fetch.sh pgf      # upstream checkout at the pinned commit
scripts/build.sh pgf      # result in build/pgf/site
scripts/serve.py          # http://127.0.0.1:8765/, with every manual built so far
```

This needs a recent TeX Live with LuaLaTeX and lwarp, Python 3 and the image
tools listed in [.github/workflows/build-package.yml](.github/workflows/build-package.yml).
The full PGF manual takes a while; the smaller manuals build in minutes.

## Repository layout

```
<package>/     one folder per manual: upstream.lock, patches/, build.sh,
               postprocessing.py, HTML adaptations; README.md with notes
shared/        style.css, pgfmanual.js, the header menu and the build tools
               shared by all manuals (image conversion, caches, checks)
scripts/       fetch.sh, prepare.py, build.sh, serve.py, deploy.sh; tests/ for
               the build tools (python3 -m unittest discover -s scripts/tests)
docs/          how the build works in detail
```

More detail:

* [docs/building.md](docs/building.md): building, patches, the shared frontend
* [docs/caching.md](docs/caching.md): drawing reuse, image conversion and formats
* [docs/converters.md](docs/converters.md): manuals converted without lwarp (tcolorbox, tkz-euclide, chemfig)
* [docs/automation.md](docs/automation.md): GitHub Actions, upstream updates, deployment
* [docs/migration.md](docs/migration.md): moving from the old fork repositories

## License

The tikz.dev tooling (scripts, workflows, `shared/`, build and postprocessing
scripts, the tcolorbox converter) is under the [MIT license](LICENSE). The
manuals belong to their authors and keep their licenses, which also apply to
the patches and adaptations derived from them and to the generated pages.
[REUSE.toml](REUSE.toml) lists which files fall under which license.
