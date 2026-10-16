#!/usr/bin/env bash
# Print a short hash of everything in this repository that a build of
# <package> depends on (its folder, shared/, scripts/, the build workflow).
# Together with the upstream commit it identifies a build: upstream.yml does
# not retry an upstream commit that failed with the same key.
#
#   scripts/build-key.sh <package>
set -euo pipefail
cd "$(dirname "$0")/.."
pkg=${1:?usage: scripts/build-key.sh <package>}
git rev-parse "HEAD:$pkg" HEAD:shared HEAD:scripts HEAD:.github/workflows/build-package.yml \
  | sha1sum | cut -c1-12
