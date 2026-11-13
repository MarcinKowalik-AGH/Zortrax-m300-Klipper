# Zortrax M300 Classic — Klipper 1.0.0-rc.8

**RC8:** Klipper automatically synchronizes accumulated model-print minutes with MCU 1.0.4 once the configured printer is idle and eligible to write. [Release notes](docs/en/RELEASE_v1.0.0-rc.8.md) · [RC6 menu animation](docs/en/RELEASE_v1.0.0-rc.6.md).


**MCU 1.0.4:** [lifetime counter storage, compatibility and qualification](docs/en/MCU_FIRMWARE_1.0.4.md). [Separate application ZIP](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.4).

**Eighth release candidate for the classic M300**, using its original controller,
OLED, encoder, temperature sensors and contact bed. This repository is not the
M300 Plus, M300 Dual or Inventure port. UI language: English. [Polski](README_PL.md).

[Download RC8](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/v1.0.0-rc.8) · [First installation](docs/en/FIRST_INSTALL.md) · [OLED / Fluidd controls](docs/en/RC1_UI.md) · [Illustrated manual](docs/pl/OLED_FUNCTIONS.md)

## Included

Native Klipper motion and print control; original temperature conversions;
contact Z homing and platform autocalibration; saved pad-mesh compensation;
material loading/unloading/change; protected cooling and OEM error reporting;
OLED menu with original artwork and unified shaded icons; low-latency Fluidd OLED
preview with integer square pixels and ×1/×2/×3 controls. Print START loads the
selected mesh after homing and primes with two Y and two X lines.

OLED, Fluidd macros and native commands share the same owners. All eight Settings
entries have direct macros, including OLED and LED brightness. Lab shortcuts
are removed from the normal UI; OEM fan service, PID and read-only diagnostics
remain. [Macro catalogue](docs/pl/MACRO_REFERENCE.md) · [Print control](docs/pl/PRINT_CONTROL.md).

**RC3 artwork retained:** one native shaded raster for 24 added icons across host, MCU and Fluidd. No blur, halo or threshold. Original OEM frames retain their original grayscale. [Artwork and verification](docs/en/RELEASE_v1.0.0-rc.3.md).

## Existing Orange Pi installation

Only while idle and Ready, not during a print or pause:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

The installer validates/persists the existing Fluidd endpoint, preserves operator
configuration, mesh, PID and qualified Z settings, and refuses unknown runtime
edits. Do not bypass checksums or force-reset local work. Refresh Fluidd after
installation. The host updater installs M300_HOST and M300_FLUIDD.zip. Install MCU 1.0.4 separately from SD to use automatic synchronization during normal operation. [MCU update and counter checks](docs/en/MCU_FIRMWARE_1.0.4.md).

## Qualification and limits

RC1 means release candidate, not universal hardware certification. The user's
first-print report confirms heating, homing and entry into printing, not a full
completed Benchy or every pause/resume scenario. [Acceptance register](docs/pl/ACCEPTANCE_REGISTER.md)
records observations separately from CI. The optional qualified Z profile
(-0.5 limit, M07 5/6.5/1, contact clearance 2 mm) is not silently applied to new
printers. No unverified Y315 cleaning zone or blind forced moves are included.

[Parameters and planner](docs/pl/PRINT_LIMITS_AND_PLANNER.md) · [Mesh and leveling](docs/pl/BED_MESH_AND_LEVELING.md) · [Installation and bounded CI retries](docs/pl/INSTALLATION_AND_CI.md) · [RC1 code review](docs/pl/CODE_REVIEW_RC1.md)

The full build verifies native Klippy/ARM, host regressions, actual browser pixel
and layout rendering, installer rollback and package checksums before publishing
orange-pi and versioned archives. Recognized transient infrastructure failures
have bounded retries; failed tests never become successful by being skipped.
Historical release notes, firmware evidence and 65 beta.20 illustrative screens
remain explicitly versioned, not relabeled as new hardware measurements.
