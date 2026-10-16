#!/usr/bin/env bash
# Upload build/<package>/site to the web server, into <sitepath> (upstream.lock).
#
# DEPLOY_TARGET   rsync destination of the site root, e.g. user@host:/www/tikz.dev
# DEPLOY_SSH_KEY  private key (optional if ssh is already set up)
#
# Files are only added or updated, never deleted, so files the build does not
# produce (.htaccess, favicons, the other manuals' folders) are safe.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
pkg=${1:?usage: scripts/deploy.sh <package>}
target=${DEPLOY_TARGET:?set DEPLOY_TARGET}
sitepath=$(sed -n 's/^sitepath=//p' "$root/$pkg/upstream.lock")
ssh_cmd="ssh -o StrictHostKeyChecking=accept-new"
if [[ -n ${DEPLOY_SSH_KEY:-} ]]; then
  keyfile=$(mktemp)
  trap 'rm -f "$keyfile"' EXIT
  printf '%s\n' "$DEPLOY_SSH_KEY" > "$keyfile"
  chmod 600 "$keyfile"
  ssh_cmd="$ssh_cmd -i $keyfile"
fi
rsync -rlz --checksum -e "$ssh_cmd" "$root/build/$pkg/site/" "${target%/}$sitepath"
echo "$pkg: deployed to ${target%/}$sitepath"
