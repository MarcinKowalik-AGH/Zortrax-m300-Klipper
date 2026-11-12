#!/usr/bin/env bash
# Publish only an immutable, successful main-branch build; never rebuild assets.
set -euo pipefail
tag=$(jq -er .distribution_version PORT.json)
[[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+-(beta|rc)\.[0-9]+$ ]]
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$SOURCE_RUN" =~ ^[0-9]+$ ]]
test "$(git rev-parse HEAD)" = "$SOURCE_SHA"

# Later development commits keep an existing release immutable. A new version in
# PORT.json is required for a new release; existing assets are never replaced.
if gh release view "$tag" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then
    echo "Release $tag is already published; leaving its tag and assets unchanged."
    exit 0
fi
gh api "repos/$GITHUB_REPOSITORY/actions/runs/$SOURCE_RUN" > "$RUNNER_TEMP/m300-source-run.json"
jq -e --arg sha "$SOURCE_SHA" --arg repo "$GITHUB_REPOSITORY" '
  .head_sha == $sha and .head_branch == "main" and .head_repository.full_name == $repo and
  .path == ".github/workflows/build-m300.yml" and
  .status == "completed" and .conclusion == "success"
' "$RUNNER_TEMP/m300-source-run.json" >/dev/null

existing=$(gh api "repos/$GITHUB_REPOSITORY/git/matching-refs/tags/$tag" \
    --jq ".[] | select(.ref == \"refs/tags/$tag\") | .object.sha")
if [[ -n "$existing" && "$existing" != "$SOURCE_SHA" ]]; then
    echo 'Refusing to move an existing release tag.' >&2
    exit 1
fi
name="Zortrax_M300_Klipper_$tag"
work=$(mktemp -d "$RUNNER_TEMP/m300-release.XXXXXX")
gh run download "$SOURCE_RUN" --repo "$GITHUB_REPOSITORY" \
    --name M300_ORANGE_PI --dir "$work/$name"
(
    cd "$work/$name"
    jq -e --arg sha "$SOURCE_SHA" --arg run "$SOURCE_RUN" --arg tag "$tag" '
      .github_commit == $sha and (.github_run_id | tostring) == $run and
      .distribution_version == $tag and .model == "M300_CLASSIC" and .release_stage == "VERIFIED"
    ' BUILD_PROVENANCE.json >/dev/null
    sha256sum -c --quiet SHA256SUMS
    test -f install-fresh.py
    test -f KLIPPER_HOST/klippy/klippy.py
    test -f MCU/M300APP.M3B
    test -f FIRST_INSTALL_PL.md
)
cp "$work/$name/FIRST_INSTALL_EN.md" "$work/"
cp "$work/$name/FIRST_INSTALL_PL.md" "$work/"
(
    cd "$work"
    zip -q -r "$name.zip" "$name"
    sha256sum "$name.zip" FIRST_INSTALL_EN.md FIRST_INSTALL_PL.md > "SHA256SUMS-$tag.txt"
)
notes="$work/notes.md"
cp "docs/en/RELEASE_$tag.md" "$notes"
printf '\nSource commit: `%s`. [Successful build and deployment](https://github.com/%s/actions/runs/%s).\n' \
    "$SOURCE_SHA" "$GITHUB_REPOSITORY" "$SOURCE_RUN" >> "$notes"
gh release create "$tag" "$work/$name.zip" "$work/SHA256SUMS-$tag.txt" \
    "$work/FIRST_INSTALL_EN.md" "$work/FIRST_INSTALL_PL.md" \
    --repo "$GITHUB_REPOSITORY" --target "$SOURCE_SHA" --prerelease \
    --title "Zortrax M300 Classic — $tag" --notes-file "$notes"

previous=$(jq -r '.supersedes_version // empty' PORT.json)
if [[ -n "$previous" ]]; then
    [[ "$previous" =~ ^v[0-9]+\.[0-9]+\.[0-9]+-(beta|rc)\.[0-9]+$ ]]
    gh release view "$previous" --repo "$GITHUB_REPOSITORY" --json body --jq .body > "$work/previous-notes.md"
    {
        printf '> Superseded by [%s](https://github.com/%s/releases/tag/%s).\n' "$tag" "$GITHUB_REPOSITORY" "$tag"
        printf '> See the newer release for corrections and update instructions.\n\n'
        cat "$work/previous-notes.md"
    } > "$work/superseded.md"
    gh release edit "$previous" --repo "$GITHUB_REPOSITORY" --notes-file "$work/superseded.md"
fi
