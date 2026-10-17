#!/usr/bin/env bash
# Check out the upstream sources of a package into .upstream/<package>.
#
#   scripts/fetch.sh <package>           at the commit pinned in <package>/upstream.lock
#   scripts/fetch.sh <package> <ref>     at any commit, tag or branch (e.g. origin/master)
#
# The checkout is a blobless clone with full history, so git log / diff /
# bisect work while only the files of checked-out commits are downloaded.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
pkg=${1:?usage: scripts/fetch.sh <package> [ref]}
lock="$root/$pkg/upstream.lock"
if [[ $(sed -n 's/^source=//p' "$lock") == archives ]]; then
  exec python3 "$root/scripts/archive_upstream.py" "$pkg" "${2:-}"
fi
repo=$(sed -n 's/^repo=//p' "$lock")
commit=$(sed -n 's/^commit=//p' "$lock")
ref=${2:-$commit}
dir="$root/.upstream/$pkg"

if [[ ! -d $dir/.git ]]; then
  git clone --quiet --filter=blob:none --no-checkout "$repo" "$dir"
elif ! git -C "$dir" rev-parse --quiet --verify "$ref^{commit}" >/dev/null; then
  git -C "$dir" fetch --quiet origin
fi
git -C "$dir" -c advice.detachedHead=false checkout --quiet --detach "$ref"
echo "$pkg: $(git -C "$dir" log -1 --format='%h %cs %s')"
