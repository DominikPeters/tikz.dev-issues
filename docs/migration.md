# Migration from the fork repositories

Until 2026-10 the PGF/TikZ and PGFplots manuals were built in forks of their
upstream repositories,
[pgf-tikz-html-manual](https://github.com/DominikPeters/pgf-tikz-html-manual)
and [pgfplots-html-manual](https://github.com/DominikPeters/pgfplots-html-manual).
This repository replaces them. It started from the tikz.dev-issues repository,
so the issues are kept; it was renamed to tikz.dev (GitHub redirects the old
URLs), and the branch `monorepo`, where the switch was tested, became `master`.

The forks' own files (build scripts, styles, standalone images, banners) were
imported with their history into `pgf/` and `pgfplots/`; their edits to
upstream files became `patches/`. The prepared source trees were checked to be
identical to the forks at the pinned commits. Upstream history and the
Photoshop sources of the banners were not imported. The mapping from old to
new commit hashes was added in commit `ca2e143` as `migration/*-commit-map.txt`
and removed later.

## Still to do

* Switch from the test deployment under `tikz.dev/monorepo/`: delete the
  repository variable `DEPLOY_PREFIX`, build all manuals, and delete
  `monorepo/` on the server.
* Archive the two fork repositories, with a link to this one in their README.
* Point links on tikz.dev to the fork repositories (footer, README) here.
