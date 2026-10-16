#!/usr/bin/env bash
# Build one manual into build/<package>/site (upstream must be fetched first).
#
#   scripts/fetch.sh pgf && scripts/build.sh pgf
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
pkg=${1:?usage: scripts/build.sh <package>}
docdir=$(sed -n 's/^docdir=//p' "$root/$pkg/upstream.lock")
out="$root/build/$pkg/site"

case $pkg in
  tcolorbox)
    # dedicated converter, reads the upstream checkout directly
    UPSTREAM="$root/.upstream/tcolorbox" "$root/tcolorbox/build.sh"
    site="$root/tcolorbox/build/site/tcolorbox"
    ;;
  *)
    # lwarp-based manuals: build in the prepared upstream tree
    python3 "$root/scripts/prepare.py" "$pkg"
    (cd "$root/build/$pkg/src/$docdir" && ./build.sh)
    site="$root/build/$pkg/src/$docdir/processed"
    ;;
esac

rm -rf "$out"
mkdir -p "$(dirname "$out")"
cp -R "$site" "$out"
echo "$pkg: site in ${out#$root/} ($(find "$out" -type f | wc -l | tr -d ' ') files)"
