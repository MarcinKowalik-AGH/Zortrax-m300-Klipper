# Zortrax M300 Classic v1.0.0-beta.19 — OLED preview zoom ×1 ×2 ×3

Supersedes beta.18. The front-end OLED navigation protocol remains `NAV-PIPELINE-2` / `NAV-EVENT-1`, with the new visual control revision `OLED-ZOOM-1`.

## What changed

Three compact cyan-on-black, OLED-styled buttons **×1**, **×2**, **×3** now appear **to the right of the virtual 256×64 OLED** in the Fluidd Temperature card. The active value is highlighted, buttons are keyboard-accessible, and the choice is kept in this browser's local storage (a blocked/invalid preference safely falls back to ×1). The zoom controls stay visible while an enlarged image scrolls horizontally in a narrow window.

The choices target native OLED content sizes of **256×64, 512×128, 768×192 CSS pixels** at common DPR 1 and 2, plus a small dark guard. At fractional display DPR/browser page zoom, the canvas snaps to the nearest *whole* device-pixel block, so CSS size may differ slightly. All OLED source pixels remain equal square N×N device-pixel blocks; there is no fractional stretching or interpolation. OS magnifiers, pinch-compositor transforms and remote-screen scaling remain outside the browser's pixel-exact guarantee.

Changing ×1/×2/×3 **repaints the already decoded image**. It does **not** fetch or decode another PNG, send a printer command, interrupt fast navigation events, change animation timing or affect the physical OLED. Statuses, homing, four-line purge, PAUSE/CANCEL and the saved-mesh/Tune updates from beta.18 are preserved.

## Upgrade from beta.18

With the printer **idle and Ready**, on Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Then hard-refresh Fluidd with **Cmd+Shift+R**. The native MCU firmware and Moonraker setup do not change. No new bed probing or calibration is required. Do not force Git resets to bypass local modifications.

## Validation

The release requires a successful, matching full CI run with native Klippy/MCU/host regressions, Fluidd unit and component tests (button placement, preference persistence, rapid zoom changes and unchanged PNG decode count), strict ESLint and TypeScript, production Fluidd build, plus real Chromium/Firefox screenshots for pixel-exact zoom and unchanged legacy rendering. The resulting Orange Pi files are deployed only from a successful main-branch build, then published with SHA-256 checks.

These are software and browser checks, not a measured latency or physical printer test. Acceptance on the user's browser is: use ×1/×2/×3, verify the correct square-pixel sizes, and verify that rapid knob navigation and animations remain responsive.
