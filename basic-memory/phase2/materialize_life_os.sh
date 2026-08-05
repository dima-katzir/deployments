#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 REPOSITORY COMMIT DESTINATION" >&2
  exit 2
fi

repository="$1"
commit="$2"
destination="$3"

git -C "$repository" cat-file -e "${commit}^{commit}"

if [[ -e "$destination" ]]; then
  echo "destination already exists: $destination" >&2
  exit 1
fi

mkdir -p "$destination"
git -C "$repository" archive "$commit" current | tar -x -C "$destination"

count="$(find "$destination/current" -maxdepth 1 -type f -name '*.md' | wc -l)"
if [[ "$count" -ne 10 ]]; then
  echo "expected 10 canonical markdown files, found $count" >&2
  exit 1
fi

find "$destination/current" -maxdepth 1 -type f -name '*.md' -print0 \
  | sort -z \
  | xargs -0 sha256sum
