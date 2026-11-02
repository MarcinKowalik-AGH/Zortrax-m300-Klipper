# Zortrax M300 Classic — Klipper R16.2

[Polski](README_PL.md) · [Installation](docs/en/INSTALL.md) · [Features & acceptance](docs/en/FEATURES.md) · [Build](docs/en/BUILD.md) · [Detailed project status (2 Nov 2026)](docs/en/STATUS_2026-11-02_OLED.md)

## Project overview — November 2, 2026

This project ports **Klipper to the original Zortrax M300 Classic**, using the STM32F103 controller, an Orange Pi host, the factory monochrome OLED and rotary encoder. The present integration baseline is **MCU R14.5 / Host R16.2**. It is a **functional integration / test release**, not a statement of full equivalence with the original firmware.

**Integrated and software-validated:** native Klipper temperature and fan control, PID and SAVE_CONFIG, Cartesian XYZ/extrusion, contact-homing adapter, OEM hardware-revision detection, OLED status and menu framework, firmware-side fault/heartbeat monitoring and local protective cooling, limited host startup reconnection, reversible host/config migration, and Fluidd organization. CI reports 131 host tests plus dedicated guard, cooling, hardware decoder and Klippy FILEOUTPUT scenarios.

**Still pending physical acceptance or completion:** latest 180°C contact-homing flow, high-speed 300 mm/s XY timing and stress tests, end-to-end OLED heater action / actual temperature display, complete M03/M07/M08 OEM workflows, binary Z-code and physical SD support, and comprehensive fault/recovery verification. The November 2 settings-screen photograph shows a live `M300NativeMotion.panel_update` exception, which **must be fixed**; settings-menu operation is not complete.

### On-device OLED gallery

**Picture 1 — Klipper status screen, Ready**

![Picture 1: Klipper status, Ready](docs/assets/oled/2026-11-02/picture%201.png)

**Picture 2 — Settings screen with visible panel_update error**

![Picture 2: Settings menu and integration exception](docs/assets/oled/2026-11-02/picture%202.png)

**Picture 3 — Heating menu, hotend selection**

![Picture 3: Heat hotend menu](docs/assets/oled/2026-11-02/picture%203.png)

**Picture 4 — Heating menu, bed selection**

![Picture 4: Heat bed menu](docs/assets/oled/2026-11-02/picture%204.png)

**Image publishing status:** The Markdown paths are prepared, but the four picture binaries must be committed at the paths above before GitHub can display them. An uncommitted image is **not** displayed as a photo. [See the annotated evidence and detailed implementation/acceptance matrix](docs/en/STATUS_2026-11-02_OLED.md).

---

## Release and build details

# Zortrax M300 Classic — Klipper R16.3

[Polski](README_PL.md) · [Install](docs/en/INSTALL.md) · [Features / acceptance](docs/en/FEATURES.md) · [Build](docs/en/BUILD.md)

Test iteration: **MCU R14.5 + host R16.3**, pinned Klipper
`ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`, STM32F103, Cartesian M300 Classic.

- Native Klipper heaters, fans, PID, SAVE_CONFIG, XYZ/E and print controls.
- Native G28/probe with M300 contact location, minimum 180C Z preheat and 5 mm clearance.
- Factory hardware revision selects Z400/Z800 once before configuration.
- STEP 2 us; XY profile 300 mm/s, native M220 and velocity/acceleration controls.
- Native first status screen; grouped Klipper / Zortrax M300 / Service / Tests menu.
- Existing OEM moon/dimming/wake, MCU local cooling and link recovery retained.
- Reversible host/config migration preserving PID and calibrated extrusion.

GitHub Actions performs a clean ARM build, 150 host tests, register-model checks
and 13 real Klippy FILEOUTPUT scenarios. Download
`m300-r14_5-host-r16_3-test-<commit>` under the successful run's Artifacts. It
contains compiled M3B/BIN/ELF/map/dictionary, the Orange Pi R16.3 installer,
Fluidd group setup, reports and checksums. An installed R14.5 MCU can remain.

Edit runtime sources in host/klippy/extras, configuration templates in host/config,
installer/tests in host/update_template, and MCU sources in mcu/SOURCE_MCU.
CI assembles packages from those canonical files and checksum-pinned upstream.
Documentation is separated in docs/en and docs/pl. No private factory dump or
bootloader is distributed.

The operator-confirmed features and new-iteration acceptance boundaries are
listed in FEATURES.md. New 180C/native homing and 300 mm/s full-load timing need
physical acceptance of this iteration. M03/M07/M08 procedures stay in TEST;
their complete workflows are not certified by a heater or XYZ test.

R16.3 adds one bounded native MCU reset on host-process startup for an old
armed session or heartbeat-loss latch only. Hardware faults/M112 remain
explicit recovery cases. See [Connection lifecycle](docs/en/CONNECTION.md).

R16.3 completes native M07 execution and the shared OLED/Fluidd flow; see [Leveling](docs/en/LEVELING.md).
