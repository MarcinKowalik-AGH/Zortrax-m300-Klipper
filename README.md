# Zortrax M300 Classic — Klipper R16.3.1

[Polski](README_PL.md) · [Installation](docs/en/INSTALL.md) · [Features & acceptance](docs/en/FEATURES.md) · [Build](docs/en/BUILD.md) · [M07 leveling](docs/en/LEVELING.md) · [Detailed project status (2 Nov 2026)](docs/en/STATUS_2026-11-02_OLED.md)

## Project overview — November 2, 2026

Klipper integration for the **original Zortrax M300 Classic** (STM32F103 MCU, Orange Pi host, original monochrome OLED and rotary encoder). Current test baseline: **MCU R14.5 + Host R16.3.1**. This is an active integration/test project, **not** a fully OEM-equivalent or physically certified release.

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

**Integrated in software:** native Klipper hotend/bed control, PID/SAVE_CONFIG, fan handling, Cartesian XYZE and G28/contact-homing adapter; Z400/Z800 hardware identification; factory OLED status and encoder-based menu; host-link and local MCU protection, including autonomous hotend cooling; reversible configuration migration and Fluidd menus. **R16.3.1 integrates the five-point/three-screw M07 leveling workflow** with shared OLED/Fluidd presentation and host NVM recording, but it still requires physical acceptance.

**Verified on the printer by the photographs:** actual OLED status rendering, navigation to settings/heating menus, and display of heater commands. The second photograph also records an **unresolved `M300NativeMotion.panel_update` exception**. Visible menu text alone does not prove successful heater actuation or correct temperature binding.

**Automated validation:** the R16.3.1 release documentation reports **157 host tests**, plus MCU/register, safety-guard, cooling, decoder and **13 real Klippy FILEOUTPUT** scenarios. These are software/CI checks, not performance measurements on the physical STM32.

**Open acceptance items:** the 180°C Z-contact-homing sequence and repeat clearance, 300 mm/s loaded motion and 2 µs step scheduling, service restart/Orange Pi reboot recovery, the OLED settings exception and heater menu end-to-end behaviour, physical M07 wizard acceptance, M03/M08, OEM Z-code and SD handling, and the complete OEM menu/indicator and fault matrix.

[Full evidence, feature boundaries and test plan](docs/en/STATUS_2026-11-02_OLED.md) · [M07 acceptance procedure](docs/en/LEVELING.md)

---

## Release and build details

Test iteration: **MCU R14.5 + host R16.3.1**, pinned Klipper
`ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`, STM32F103, Cartesian M300 Classic.

- Native Klipper heaters, fans, PID, SAVE_CONFIG, XYZ/E and print controls.
- Native G28/probe with M300 contact location, minimum 180C Z preheat and 5 mm clearance.
- Factory hardware revision selects Z400/Z800 once before configuration.
- STEP 2 us; XY profile 300 mm/s, native M220 and velocity/acceleration controls.
- Native first status screen; grouped Klipper / Zortrax M300 / Service / Tests menu.
- Existing OEM moon/dimming/wake, MCU local cooling and link recovery retained.
- Reversible host/config migration preserving PID and calibrated extrusion.

GitHub Actions performs a clean ARM build, 157 host tests, register-model checks
and 13 real Klippy FILEOUTPUT scenarios. Download
`m300-r14_5-host-r16_3_1-test-<commit>` under the successful run's Artifacts. It
contains compiled M3B/BIN/ELF/map/dictionary, the Orange Pi R16.3.1 installer,
Fluidd group setup, reports and checksums. An installed R14.5 MCU can remain.

Edit runtime sources in host/klippy/extras, configuration templates in host/config,
installer/tests in host/update_template, and MCU sources in mcu/SOURCE_MCU.
CI assembles packages from those canonical files and checksum-pinned upstream.
Documentation is separated in docs/en and docs/pl. No private factory dump or
bootloader is distributed.

The operator-confirmed features and new-iteration acceptance boundaries are
listed in FEATURES.md. New 180C/native homing and 300 mm/s full-load timing need
physical acceptance of this iteration. M07 is integrated as a TEST procedure with a shared OLED/Fluidd presenter; physical machine acceptance is pending. M03/M08 and full OEM print/SD workflows are not certified.

R16.2 introduced one bounded native MCU reset (retained in R16.3.1) on host-process startup for an old
armed session or heartbeat-loss latch only. Hardware faults/M112 remain
explicit recovery cases. See [Connection lifecycle](docs/en/CONNECTION.md).

R16.3.1 completes native M07 execution and the shared OLED/Fluidd flow; see [Leveling](docs/en/LEVELING.md).

R16.3.1 corrects test macro names to `TEST_ZORTRAX_LEVEL`, `TEST_ZORTRAX_STATUS` and `TEST_ZORTRAX_XY`. Native G-code lexer tests cover button dispatch; installation migrates existing names and Fluidd preferences. The M07 executor and MCU remain unchanged.
