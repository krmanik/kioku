#!/bin/bash
# Fetch add-ons from GitHub (no AnkiWeb load) into <addons dir>/<id>.
#   fetch_github.sh <github-ids.txt> <addons dir>
# github-ids.txt comes from names.py. Existing folders are skipped; 4 at a time.
set -uo pipefail
if [ "$1" = --one ]; then
  d=$2/$3 repo=$4
  [ -d "$d" ] && exit 0
  mkdir -p "$d"
  if curl -sfL --max-time 120 --max-filesize 209715200 "https://codeload.github.com/$repo/tar.gz/HEAD" |
    tar -xzf - -C "$d" --strip-components 1 2>/dev/null && [ -n "$(ls -A "$d")" ]; then
    echo "ok $3"
  else
    rm -rf "$d"
    echo "fail $3 $repo"
  fi
  exit 0
fi
xargs -P4 -n2 "$0" --one "$2" < "$1"
