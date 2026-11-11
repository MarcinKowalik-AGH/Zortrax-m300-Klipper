# M300 Classic beta.22 — sharp host-rendered menu icons

Supersedes beta.21. Default live-menu style: **SHARP-HOST-1**.
This is a reversible Orange Pi presentation update, not an MCU firmware change.

All 24 activity symbols / 96 frames display exactly the original binary
pre-toning artwork. All 37 OEM groups / 61 frames display at 0/15 using the
threshold 8. Source firmware assets and their hashes are preserved byte-for-byte.
A bounded 64-frame cache stores only the derived visual representation. Original
source-mode APIs remain available for the firmware-fidelity tests and handbook.
Functional Home/Move axis dimming and the three-tone Klipper logo stay unchanged.
No text, navigation cadence, transport, frontend, mesh or printer procedure changes.

## Install (Fluidd port 4480)

With the printer idle and Ready, as the Klipper user on Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Hard-refresh Fluidd. `ZORTRAX_UI_STATUS` reports `icon_style: SHARP-HOST-1`.
Do not manually overwrite packaged JSON files: that invalidates integrity checks.
The updater recognizes only the exact previous module hashes and rejects unknown
local edits. No reset or repeated probing is needed.

**No MCU flash is necessary.** Normal host-rendered menus on the physical OLED
and Fluidd use the sharp frames. Autonomous waiting/fault screens on MCU R14.19
retain beta.21 tones; this release does not pretend to update those screens.

For an A/B comparison, set `sharp_icons: False` in the existing `[m300_menu_ui]`
section and restart Klipper while idle. True (the default) restores sharp output.
Do not create a duplicate section or issue RESTART during a print.

The matching full CI must validate all 157 frames, exact old activity pixels,
canonical OEM evidence, lossless transport, real host-renderer integration,
previous-install compatibility, 741 host regressions, native Klippy, ARM, Fluidd
and package checksums before publication. These are software tests, not physical
OLED visual acceptance. Binary diagonal contours may look more stepped; view at
native scale. The 65-screen beta.20 handbook remains a versioned reference.
