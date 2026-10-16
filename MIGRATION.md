# Migration from the fork repositories

Until 2026-10 the manuals were built in forks of the upstream repositories:
[pgf-tikz-html-manual](https://github.com/DominikPeters/pgf-tikz-html-manual)
(fork of pgf-tikz/pgf) and
[pgfplots-html-manual](https://github.com/DominikPeters/pgfplots-html-manual)
(fork of pgf-tikz/pgfplots). This repository replaces them; it started from
the tikz.dev-issues repository so that the issues are kept.

## What was done

1. History: each fork was filtered with `git filter-repo`, keeping only
   paths that never existed upstream (the HTML build scripts, styles,
   standalone images, banners, ...), moved from `doc/generic/pgf/` to `pgf/`
   and from `doc/latex/pgfplots/` to `pgfplots/`, and merged here.
   Not kept: upstream commits and merges, commits that only edited upstream
   files (their result lives on in `patches/`), and
   `pgf/banners/photoshop-sources/` (49 MB). Old to new commit hashes:
   `migration/*-commit-map.txt`. Repository size: 5.7 MB (pgf fork: 1.2 GB).
2. Edits to upstream files became `scripts/prepare.py --refresh-patches` output
   (pgf: 62 patches + `preprocess.py` for the 119 section page names;
   pgfplots: 59 patches). Verified: the prepared trees at the pinned commits
   are identical to the forks (pgf: 1697 files, pgfplots: 2335) apart from
   the shared assets below.
3. `style.css`, `pgfmanual.js`, `lwarp-mathjax-emulation.js`: merged into
   `shared/` (pgf's versions plus `.pkg-pgfplots` / `.pkg-tcolorbox` rules).
   Verified by comparing the computed style of every element of every page of
   the last local builds (pgf: build42, pgfplots: pgfplots-build7), old vs new,
   at 1200px and 500px width. Only intended difference: pgfplots images get
   `height: auto` (no more stretched images on narrow screens).
4. tcolorbox: the prototype converter from T-F-S/tcolorbox (branch
   html-manual, never committed there) was added as `tcolorbox/`.

## Not yet done

* Rename this repository DominikPeters/tikz.dev-issues to DominikPeters/tikz.dev
  (GitHub redirects the old URLs) and merge the branch `monorepo` into `main`.
* Test deploys go to `tikz.dev/monorepo/` (repository variable
  `DEPLOY_PREFIX=/monorepo`, and the `monorepo` branch in `build.yml`). For the
  switch: delete `DEPLOY_PREFIX`, remove `monorepo` from `build.yml`.
* Run `build.yml` by hand once per package and compare the result with the
  live site before letting it deploy (`deploy: false` input).
* The lwarp builds (`pgf/build.sh`, `pgfplots/build.sh`) have only run on the
  author's machine so far; the CI container may need extra fonts or tools.
* Archive the two fork repositories, with a link to this one in their README.
* `tikz.dev` links to the fork repositories (footer, README) should point here.
