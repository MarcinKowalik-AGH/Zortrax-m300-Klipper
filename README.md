# Zortrax M300 Classic — Klipper R16.7

[Installation](docs/en/INSTALL.md) · [Features & acceptance](docs/en/FEATURES.md) · [Build](docs/en/BUILD.md) · [M07 leveling](docs/en/LEVELING.md) · [Procedure validation](docs/en/VALIDATION_R16_7.md)

## Project overview — November 3, 2026

Klipper integration for the **original Zortrax M300 Classic** (STM32F103 MCU, Orange Pi host, original monochrome OLED and rotary encoder). Current test baseline: **MCU R14.5 + Host R16.7**. This is an active integration/test project, **not** a fully OEM-equivalent or physically certified release.

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

R16.7 adds the original interactive Maintenance fan test: saved requests,
independent upper/lower 0/150 toggles, original menu pixels and Back cleanup.
Heat and held/finite platform actions share their English state with Fluidd.
The existing R16.6 calibration, ordinary Z and material fixes are retained.

Fan status reads one MCU snapshot instead of six. Rendering is cached, idle
fan supervision does no periodic work, and native output/thermostat owners
remain unchanged outside the test. See the measured host-only evaluation.

The requested submenus use shared native owners and the same eleven Fluidd
macros. Original dialog text/font/sprites are retained. Native motion, PID,
sensors, calibrated E, factory Z selection and deliberate geometry remain
under their existing owners. The full legacy OEM print/Z-code engine remains
separately disabled.

Software evidence: **258 host tests**, **9 repository contracts**, **13 actual
Klippy FILEOUTPUT scenarios**, **122 original-renderer frames**, **20,002 turn
vectors**, and executable original material/wizard/Z-reference traces. These
are not physical printer acceptance. The photographs above remain historical
operator evidence and retain their original supplied order.

[Validation, confirmed differences and physical acceptance](docs/en/VALIDATION_R16_7.md)

## Test release

**MCU R14.5 + host R16.7**, pinned Klipper
`ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`, STM32F103 M300 Classic.

Download `m300-r14_5-host-r16_7-test-<commit>` from a successful GitHub Actions
run. It contains the verified `M300_HOST_R16_7_NORMAL_UI.zip`, build reports,
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
