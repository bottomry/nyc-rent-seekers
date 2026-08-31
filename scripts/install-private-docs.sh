#!/bin/sh
# Install the maintainer-only documentation overlay without tracking it here.
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
companion=${NRS_INTERNAL_REPO:-"$(dirname -- "$repo_root")/nyc-rent-seekers-internal"}
remote=${NRS_INTERNAL_REMOTE:-"https://github.com/bottomry/nyc-rent-seekers-internal.git"}

if [ ! -d "$companion/.git" ]; then
    git clone "$remote" "$companion"
else
    git -C "$companion" pull --ff-only
fi

for private_path in docs/adr docs/THREAT_MODEL.md docs/spec.md docs/PROGRESS.md; do
    if git -C "$repo_root" ls-files --error-unmatch "$private_path" >/dev/null 2>&1; then
        echo "refusing to replace tracked private path: $private_path" >&2
        exit 1
    fi
done

mkdir -p "$repo_root/docs"
rm -f "$repo_root/docs/adr" "$repo_root/docs/THREAT_MODEL.md" \
    "$repo_root/docs/spec.md" "$repo_root/docs/PROGRESS.md"

repo_parent=$(dirname -- "$repo_root")
companion_parent=$(dirname -- "$companion")
if [ "$companion_parent" = "$repo_parent" ]; then
    companion_link="../../$(basename -- "$companion")"
else
    companion_link=$companion
fi

ln -s "$companion_link/docs/adr" "$repo_root/docs/adr"
ln -s "$companion_link/docs/THREAT_MODEL.md" "$repo_root/docs/THREAT_MODEL.md"
ln -s "$companion_link/docs/spec.md" "$repo_root/docs/spec.md"
ln -s "$companion_link/docs/PROGRESS.md" "$repo_root/docs/PROGRESS.md"

echo "maintainer-private docs mounted from $companion"
