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
#
# Files are only added or updated, never deleted, so files the build does not
# produce (.htaccess, favicons, the other manuals' folders) are safe.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
: "${FTP_HOST:?}" "${FTP_USER:?}" "${FTP_PASSWORD:?}"
export LFTP_PASSWORD=$FTP_PASSWORD
settings="set ftp:ssl-force true; set ftp:ssl-protect-data true; set net:max-retries 3; set net:timeout 60"

if [[ ${1:-} == --list ]]; then
  lftp --env-password -u "$FTP_USER" -e "$settings; pwd; cls -1F; bye" "$FTP_HOST"
  exit
fi

pkg=${1:?usage: scripts/deploy.sh <package> | --list}
sitepath=$(sed -n 's/^sitepath=//p' "$root/$pkg/upstream.lock")
dest="${FTP_ROOT:-.}${DEPLOY_PREFIX:-}$sitepath"
lftp --env-password -u "$FTP_USER" -e "$settings; pwd; cls -1F; mkdir -pf $dest; \
  mirror --reverse --no-perms --parallel=8 --verbose=1 $root/build/$pkg/site/ $dest; bye" "$FTP_HOST"
echo "$pkg: deployed to $FTP_HOST:$dest"
