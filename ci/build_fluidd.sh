#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
upstream=b2edab5bc690f5265a5aa1e56ae3f67669053fd4

git clone --quiet --depth 1 --branch v1.37.7 https://github.com/fluidd-core/fluidd.git "$work/source"
cd "$work/source"
test "$(git rev-parse HEAD)" = "$upstream"
git apply --check "$root/frontend/fluidd/m300-leveling.patch"
git apply "$root/frontend/fluidd/m300-leveling.patch"
# Apply the narrow Tune correction after the original M300 integration.
git apply --check "$root/frontend/fluidd/m300-tune.patch"
git apply "$root/frontend/fluidd/m300-tune.patch"
cp "$root/frontend/fluidd/tune/"*.ts src/util/
# Preserve the verified beta.17 navigation and integer-pixel renderer unchanged.
cp "$root/frontend/fluidd/navigation/M300OledPreview.vue" src/components/widgets/thermals/
cp "$root/frontend/fluidd/navigation/"*.ts src/util/

pnpm install --frozen-lockfile --ignore-scripts
mkdir -p "$root/.ci/reports"
pnpm exec vitest run src/components/common/m300Leveling.spec.ts src/util/m300-homing.spec.ts src/util/m300-pad-mesh.spec.ts src/util/m300-pad-contact-map.spec.ts src/util/m300-feedback.spec.ts src/util/m300-macro-category.spec.ts src/util/m300-oled-preview.spec.ts src/util/m300-oled-navigation.spec.ts src/util/m300-oled-navigation-component.spec.ts src/util/m300-oled-paint.spec.ts src/util/m300-oled-pixels.spec.ts src/util/m300-tune-refresh.spec.ts src/util/m300-tune-view.spec.ts --reporter=default --reporter=json --outputFile="$root/.ci/reports/FLUIDD_UNIT_TESTS.json"
pnpm exec eslint --max-warnings 0 src/App.vue src/views/Tune.vue src/store/{mesh,macros}/getters.ts src/components/common/{ActionCommandPromptDialog.vue,M300LevelingDiagram.vue,m300Leveling.ts,m300Leveling.spec.ts,M300PadMeshObserver.vue} src/mixins/state.ts src/api/socketActions.ts src/util/m300-{homing,pad-mesh,pad-contact-map,feedback,macro-category}{,.spec}.ts src/components/widgets/thermals/M300OledPreview.vue src/util/m300-oled-preview{,.spec}.ts src/util/m300-oled-navigation{,.spec,-component.spec}.ts src/util/m300-oled-paint{,.spec}.ts src/util/m300-oled-pixels{,.spec}.ts src/util/m300-tune-{refresh,refresh.spec,view.spec}.ts src/components/widgets/toolhead/ToolheadControl{Bars,BarsAxis,Circle,Cross}.vue src/components/widgets/bedmesh/{BedMeshCard,M300PadMeshStatus,M300PadContactMap}.vue
pnpm run type-check
# Full application types were checked above. Compile this exact standalone
# production helper with explicit options for the actual browser raster test.
pnpm exec tsc --ignoreConfig --target ES2022 --module ES2022 --lib ES2022,DOM --skipLibCheck --outDir "$root/.ci/oled-browser" src/util/m300-oled-pixels.ts
python -m pip install --quiet playwright==1.57.0 Pillow==11.3.0
python -m playwright install --with-deps chromium firefox
python "$root/ci/check_oled_pixels.py" --module "$root/.ci/oled-browser" --output "$root/.ci/reports/OLED_PIXELS.json"
pnpm run build

cd "$work"
mv source/dist fluidd-m300
cp source/LICENSE "$root/frontend/fluidd/m300-leveling.patch" "$root/frontend/fluidd/m300-tune.patch" "$root/docs/en/FLUIDD_M300.md" .
cp -R "$root/frontend/fluidd/navigation" navigation-source
cp -R "$root/frontend/fluidd/tune" tune-source
mkdir -p "$root/dist/fluidd"
archive="$root/dist/fluidd/M300_FLUIDD_1_37_7_R16_12.zip"
rm -f -- "$archive"
zip -qr "$archive" fluidd-m300 LICENSE m300-leveling.patch m300-tune.patch FLUIDD_M300.md navigation-source tune-source
cd "$root/dist/fluidd"
sha256sum "$(basename -- "$archive")" > SHA256SUMS
sha256sum -c SHA256SUMS
