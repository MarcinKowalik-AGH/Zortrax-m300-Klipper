# Zortrax M300 Classic — Klipper R16.8

[Installation](docs/en/INSTALL.md) · [Features & acceptance](docs/en/FEATURES.md) · [Build](docs/en/BUILD.md) · [M07 leveling](docs/en/LEVELING.md) · [Procedure validation](docs/en/VALIDATION_R16_8.md)

## Project overview — November 3, 2026

Klipper integration for the **original Zortrax M300 Classic** (STM32F103 MCU, Orange Pi host, original monochrome OLED and rotary encoder). Current test baseline: **MCU R14.5 + Host R16.8**. This is an active integration/test project, **not** a fully OEM-equivalent or physically certified release.

### Actual printer photographs — OLED / Klipper

**Picture 1 — Native Klipper status screen (Ready)**

![Picture 1: Klipper Ready status](docs/assets/oled/2026-11-02/picture%201.png)

**Picture 2 — Settings menu and observed `panel_update` exception**

![Picture 2: Settings menu / panel_update error](docs/assets/oled/2026-11-02/picture%202.png)

**Picture 3 — Heating menu, hotend selected**

![Picture 3: Heat hotend selection](docs/assets/oled/2026-11-02/picture%203.png)

**Picture 4 — Heating menu, bed selected**

![Picture 4: Heat bed selection](docs/assets/oled/2026-11-02/picture%204.png)

### Current implementation status

R16.8 adds English Settings and Information to the OLED and Fluidd. It saves
Light, Buzzer, Sleep mode and Models sorting choices, reads available printer
data and directs Help to this repository. Sleep mode uses the existing OLED
sleep sequence. The menu audit fixes Models listing and preview, preserves
mandatory procedure instructions and removes large calibration data copies
from ownership checks.

Software evidence includes **289 host tests**, **9 repository contracts**,
**14 actual Klippy FILEOUTPUT cases**, **174 original-renderer frames** and
**20,002 turn vectors**. Physical validation is pending. The photographs above
show the historical printer setup.

[Settings and Information](docs/en/SETTINGS_INFORMATION.md) · [Validation and performance](docs/en/VALIDATION_R16_8.md)

## Test release

**MCU R14.5 + host R16.8**, pinned Klipper
`ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`, STM32F103 M300 Classic.

Download `m300-r14_5-host-r16_8-test-<commit>` from a successful GitHub Actions
run. It contains the verified `M300_HOST_R16_8_NORMAL_UI.zip`, build reports,
provenance/checksums and a freshly compiled R14.5 application for older setups.
An already installed R14.5 MCU can remain.

[Install on Orange Pi](docs/en/INSTALL.md). After Ready run
`python3 setup_fluidd.py --apply` and refresh Fluidd. No procedure runs during
installation. The installer lists changes, refuses unknown runtime edits and
provides exact rollback while preserving PID, E and deliberate geometry.

Canonical runtime: host/klippy/extras. Configuration: host/config. Installer
and self-contained tests: host/update_template. MCU: mcu/SOURCE_MCU. Current
documentation is English under docs/en. Legacy localized URLs redirect to
English; immutable multilingual firmware evidence remains audit data.
No private factory application dump or bootloader is distributed.

OLED frame transport, sleep/wake, local MCU cooling and bounded host startup
recovery retain their existing implementations. Physical contact repeatability,
filament lengths, hold response and loaded 300 mm/s timing remain printer tests.
