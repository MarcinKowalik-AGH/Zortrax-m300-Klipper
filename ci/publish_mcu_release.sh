#!/usr/bin/env bash
# Publish exactly the firmware-only M300APP.M3B from a verified main build.
set -euo pipefail
version=$(jq -er '.mcu_release' PORT.json)
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
tag="mcu-v$version"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$SOURCE_RUN" =~ ^[0-9]+$ ]]
test "$(git rev-parse HEAD)" = "$SOURCE_SHA"

gh api "repos/$GITHUB_REPOSITORY/actions/runs/$SOURCE_RUN" > "$RUNNER_TEMP/m300-mcu-source.json"
jq -e --arg sha "$SOURCE_SHA" --arg repo "$GITHUB_REPOSITORY" '
  .head_sha == $sha and .head_branch == "main" and
  .head_repository.full_name == $repo and
  .path == ".github/workflows/build-m300.yml" and
  .status == "completed" and .conclusion == "success"
' "$RUNNER_TEMP/m300-mcu-source.json" >/dev/null

# A published firmware release is immutable. Never overwrite an existing tag.
if gh release view "$tag" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then
    echo "Firmware release $tag already exists; preserving its tag and assets."
    exit 0
fi

work=$(mktemp -d "$RUNNER_TEMP/m300-mcu-release.XXXXXX")
gh run download "$SOURCE_RUN" --repo "$GITHUB_REPOSITORY" \
    --name M300_ORANGE_PI --dir "$work/package"
(
    cd "$work/package"
    jq -e --arg sha "$SOURCE_SHA" --arg run "$SOURCE_RUN" --arg version "$version" '
      .github_commit == $sha and (.github_run_id | tostring) == $run and
      .mcu_release == $version and .model == "M300_CLASSIC" and
      .release_stage == "VERIFIED" and .flashed == false
    ' BUILD_PROVENANCE.json >/dev/null
    sha256sum -c --quiet SHA256SUMS
)
python3 ci/test_mcu_version.py \
    --dictionary "$work/package/MCU/klipper.dict" \
    --binary "$work/package/MCU/klipper.bin" \
    --m3b "$work/package/MCU/M300APP.M3B"
python3 - "$work/package/MCU/M300_SD.zip" "$work/package/MCU/M300APP.M3B" <<'PY'
import sys
from pathlib import Path
from zipfile import ZipFile
archive, firmware = map(Path, sys.argv[1:])
with ZipFile(archive) as z:
    assert z.namelist() == ['M300APP.M3B'], 'Firmware-only zip contains extra files'
    assert z.testzip() is None, 'Firmware-only ZIP CRC failure'
    assert z.read('M300APP.M3B') == firmware.read_bytes(), 'ZIP firmware differs from verified binary'
PY

cp "$work/package/MCU/M300_SD.zip" "$work/M300_MCU_v${version}_SD.zip"
cp "$work/package/MCU/BUILD_REPORT.json" "$work/MCU_BUILD_REPORT.json"
cp "$work/package/MCU/M3B_REPORT.json" "$work/MCU_M3B_REPORT.json"
cp "docs/en/MCU_FIRMWARE_${version}.md" "$work/MCU_FIRMWARE_${version}_EN.md"
cp "docs/pl/MCU_FIRMWARE_${version}.md" "$work/MCU_FIRMWARE_${version}_PL.md"
(
    cd "$work"
    sha256sum M300_MCU_v${version}_SD.zip MCU_BUILD_REPORT.json \
      MCU_M3B_REPORT.json MCU_FIRMWARE_${version}_EN.md \
      MCU_FIRMWARE_${version}_PL.md > SHA256SUMS-mcu-v${version}.txt
)
cp "docs/en/MCU_FIRMWARE_${version}.md" "$work/NOTES.md"
printf '\nSource commit: `%s`. [Verified build](https://github.com/%s/actions/runs/%s).\n' \
    "$SOURCE_SHA" "$GITHUB_REPOSITORY" "$SOURCE_RUN" >> "$work/NOTES.md"
gh release create "$tag" \
    "$work/M300_MCU_v${version}_SD.zip" \
    "$work/SHA256SUMS-mcu-v${version}.txt" \
    "$work/MCU_BUILD_REPORT.json" \
    "$work/MCU_M3B_REPORT.json" \
    "$work/MCU_FIRMWARE_${version}_EN.md" \
    "$work/MCU_FIRMWARE_${version}_PL.md" \
    --repo "$GITHUB_REPOSITORY" --target "$SOURCE_SHA" --prerelease \
    --title "Zortrax M300 Classic — MCU $version" \
    --notes-file "$work/NOTES.md"
