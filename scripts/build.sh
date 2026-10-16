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
    # compile with the package's own code from the same upstream commit, not
    # the release in TeX Live (or a local install), which may predate the docs
    tex="$root/build/$pkg/src/tex"
    (cd "$root/build/$pkg/src/$docdir" &&
      TEXINPUTS="$tex//:${TEXINPUTS:-}" LUAINPUTS="$tex//:${LUAINPUTS:-}" ./build.sh)
    # build.sh carries on after LaTeX errors; don't publish a half-built site
    for log in "$root/build/$pkg/src/$docdir"/*_html.log; do
      if grep -q "Fatal error occurred" "$log" || ! grep -q "^Output written on" "$log"; then
        grep -m1 -A3 "^! " "$log" || true
        echo "$pkg: LaTeX failed, see ${log#$root/}" >&2
        exit 1
      fi
    done
    site="$root/build/$pkg/src/$docdir/processed"
    ;;
esac

if [[ ! -f $site/index.html ]]; then
  echo "$pkg: no index.html in ${site#$root/}, not a complete site" >&2
  exit 1
fi
rm -rf "$out"
mkdir -p "$(dirname "$out")"
cp -R "$site" "$out"
echo "$pkg: site in ${out#$root/} ($(find "$out" -type f | wc -l | tr -d ' ') files)"
