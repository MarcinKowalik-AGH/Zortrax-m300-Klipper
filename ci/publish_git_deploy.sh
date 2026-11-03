#!/usr/bin/env bash
# Publish the ready-to-install tree without bringing source history or docs to Orange Pi.
set -euo pipefail

release=$(realpath -- "$1")
commit=$(git rev-parse HEAD)
work=$(mktemp -d)
checkout="$work/checkout"
trap 'git worktree remove --force "$checkout" 2>/dev/null || :; rm -rf -- "$work"' EXIT
branch=orange-pi

python3 ci/package_git_deploy.py --release "$release" --output "$work/bundle" --commit "$commit"

if git ls-remote --exit-code origin "refs/heads/$branch" >/dev/null; then
    git fetch --depth=1 --no-tags origin "refs/heads/$branch"
    git worktree add --detach "$checkout" FETCH_HEAD
    git -C "$checkout" rm -rq -- .
else
    status=$?
    if [ "$status" -ne 2 ]; then
        exit "$status"
    fi
    git worktree add --detach --no-checkout "$checkout" "$commit"
    git -C "$checkout" switch --orphan "$branch"
fi

cp -a -- "$work/bundle/." "$checkout/"
git -C "$checkout" add --all
if git -C "$checkout" diff --cached --quiet; then
    exit 0
fi
git -C "$checkout" -c user.name=github-actions -c user.email=41898282+github-actions[bot]@users.noreply.github.com \
    commit -m "Deploy M300 Orange Pi build $commit"
git -C "$checkout" push origin "HEAD:refs/heads/$branch"
