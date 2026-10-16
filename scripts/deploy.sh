#!/usr/bin/env bash
# Upload build/<package>/site to the web server by FTP (with TLS), into
# $FTP_ROOT$DEPLOY_PREFIX<sitepath> (sitepath from upstream.lock).
#
#   scripts/deploy.sh <package>
#   scripts/deploy.sh --list        show the folders on the server
#
# FTP_HOST, FTP_USER, FTP_PASSWORD   server and login
# FTP_ROOT       folder of tikz.dev on the server, relative to the FTP login
#                folder (default: the login folder itself)
# DEPLOY_PREFIX  extra path below the site root, e.g. /monorepo for testing
# FULL_DEPLOY=1  upload everything, not only the files that changed
#
# Files are only added or updated, never deleted, so files the build does not
# produce (.htaccess, favicons, the other manuals' folders) are safe.
#
# Only files whose contents changed since the last deploy are uploaded: the
# server keeps a list of checksums of the deployed files (.deploy-manifest in
# the destination folder), which is replaced after each successful upload.
# A file changed or deleted on the server by hand is therefore only restored
# by the next deploy that changes it, or by FULL_DEPLOY=1.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
: "${FTP_HOST:?}" "${FTP_USER:?}" "${FTP_PASSWORD:?}"
export LFTP_PASSWORD=$FTP_PASSWORD
settings="set cmd:fail-exit true; set ftp:ssl-force true; set ftp:ssl-protect-data true; set net:max-retries 3; set net:timeout 60"

if [[ ${1:-} == --list ]]; then
  lftp --env-password -u "$FTP_USER" -e "$settings; pwd; cls -1F; bye" "$FTP_HOST"
  exit
fi

pkg=${1:?usage: scripts/deploy.sh <package> | --list}
sitepath=$(sed -n 's/^sitepath=//p' "$root/$pkg/upstream.lock")
dest="${FTP_ROOT:-.}${DEPLOY_PREFIX:-}$sitepath"
site="$root/build/$pkg/site"
manifest=.deploy-manifest
ftp() { lftp --env-password -u "$FTP_USER" -e "$settings; $1; bye" "$FTP_HOST"; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
(cd "$site" && find . -type f ! -name "$manifest" -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) > "$tmp/new"
if [[ -z ${FULL_DEPLOY:-} ]]; then
  ftp "get $dest/$manifest -o $tmp/old" 2>/dev/null || true
fi
if [[ ! -s $tmp/old ]]; then
  echo "$pkg: no manifest from the server, uploading everything"
  : > "$tmp/old"
fi

# files that are new or whose checksum changed ("<sha256>  ./path")
LC_ALL=C comm -23 <(LC_ALL=C sort "$tmp/new") <(LC_ALL=C sort "$tmp/old") | cut -c67- > "$tmp/changed"
total=$(wc -l < "$tmp/new" | tr -d ' ')
count=$(wc -l < "$tmp/changed" | tr -d ' ')
echo "$pkg: $count of $total files changed"
mkdir "$tmp/stage"
if [[ $count -gt 0 ]]; then
  tar -C "$site" -cf - -T "$tmp/changed" | tar -C "$tmp/stage" -xf -
  find "$tmp/stage" -type f -exec touch {} +   # newer than anything on the server
fi
cp "$tmp/new" "$tmp/stage/$manifest"   # uploaded last, after the files it lists
ftp "mkdir -pf $dest; mirror --reverse --no-perms --parallel=8 --verbose=1 --exclude-glob $manifest $tmp/stage/ $dest; \
  put $tmp/stage/$manifest -o $dest/$manifest"
echo "$pkg: deployed to $FTP_HOST:$dest"
