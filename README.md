# Zortrax M300 Classic — Klipper R16.2

[Polski](README_PL.md) · [Install](docs/en/INSTALL.md) · [Features / acceptance](docs/en/FEATURES.md) · [Build](docs/en/BUILD.md)

Test iteration: **MCU R14.5 + host R16.2**, pinned Klipper
`ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`, STM32F103, Cartesian M300 Classic.

- Native Klipper heaters, fans, PID, SAVE_CONFIG, XYZ/E and print controls.
- Native G28/probe with M300 contact location, minimum 180C Z preheat and 5 mm clearance.
- Factory hardware revision selects Z400/Z800 once before configuration.
- STEP 2 us; XY profile 300 mm/s, native M220 and velocity/acceleration controls.
- Native first status screen; grouped Klipper / Zortrax M300 / Service / Tests menu.
- Existing OEM moon/dimming/wake, MCU local cooling and link recovery retained.
- Reversible host/config migration preserving PID and calibrated extrusion.

GitHub Actions performs a clean ARM build, 131 host tests, register-model checks
and 13 real Klippy FILEOUTPUT scenarios. Download
`m300-r14_5-host-r16_2-test-<commit>` under the successful run's Artifacts. It
contains compiled M3B/BIN/ELF/map/dictionary, the Orange Pi R16.2 installer,
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

R16.2 adds one bounded native MCU reset on host-process startup for an old
armed session or heartbeat-loss latch only. Hardware faults/M112 remain
explicit recovery cases. See [Connection lifecycle](docs/en/CONNECTION.md).
