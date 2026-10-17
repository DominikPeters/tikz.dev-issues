# Automation and deployment

## Workflows

* `build.yml`: on a push, builds the manuals whose folders changed (all of
  them if `shared/`, `scripts/` or the build workflows changed) at their pinned
  upstream commit, and deploys them. Can also be run by hand for one or all
  manuals, with or without deployment.
* `upstream.yml`: every six hours, checks each manual's upstream repository for
  new commits touching the `watch` paths of its `upstream.lock`. For each such
  manual, `upstream-package.yml` builds the new commit, and
  * on success deploys it and records the commit in `upstream.lock` (a commit
    listing the upstream changes), closing any open failure issue;
  * on failure opens or updates the issue "[package] upstream build failing"
    and leaves the site as it is. That upstream commit is not tried again until
    upstream moves on or the build files here change (`scripts/build-key.sh`);
    running the workflow by hand with "retry" forces another attempt.

  wheelchart has no upstream repository and is updated by hand.

Builds run in the `texlive/texlive:latest` container; the tools are installed
in `build-package.yml`. Upstream archives and the illustration cache are kept
between runs with the Actions cache.

## Deployment

`scripts/deploy.sh <package>` uploads `build/<package>/site` by FTP over TLS
(lftp) to the manual's `sitepath`. Configuration, as repository variables:

* `FTP_HOST`, `FTP_USER`, and the secret `FTP_PASSWORD`
* `FTP_ROOT`: folder of the site relative to the FTP login (default: the login folder)
* `DEPLOY_PREFIX`: extra path for test deployments, e.g. `/monorepo`

Deployment never deletes files on the server. It uploads only files whose
contents changed since the last deploy, using a list of checksums
(`.deploy-manifest`) kept in each manual's folder on the server. A file
changed or deleted on the server by hand is restored only when it next changes,
or with `FULL_DEPLOY=1`, which uploads everything.
