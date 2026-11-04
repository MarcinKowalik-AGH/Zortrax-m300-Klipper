# Zortrax M300 Classic — Klipper R16.12

[Installation](docs/en/INSTALL.md) · [Features & acceptance](docs/en/FEATURES.md) · [Build](docs/en/BUILD.md) · [M07 leveling](docs/en/LEVELING.md) · [Procedure validation](docs/en/PRINT_CONTEXT.md)

## Project overview — November 3, 2026

Klipper integration for the **original Zortrax M300 Classic** (STM32F103 MCU, Orange Pi host, original monochrome OLED and rotary encoder). The current test baseline is **MCU R14.8 + Host R16.12**. This is an active integration and test project.

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

R16.12 presents the five-point Autocalibration result graphically in the
optional [M300 Fluidd build](docs/en/FLUIDD_M300.md). It retires the stock test
duplicate, restores the OEM Y-before-X order, checks PC7 before the Z seek
and retains an already-held Z on normal idle.
[Homing comparison and validation](docs/en/LEVELING.md).

R16.10 adds contextual OLED PRINTING, PAUSE MENU and PRINTING DONE screens.
R16.11 batches local SD imports and transfers only the used bytes of the final
file sector from the MCU to the host.
A 10-second hold pauses the native print or reprints the verified completed
copy after the model has been removed. OLED and Fluidd share the native print
state, including the existing material change procedure. The R16.9 card reader
and Models menu support G-code and the audited Classic M300 Z-code subset.

[Print contexts](docs/en/PRINT_CONTEXT.md) · [Procedure inventory](docs/en/PROCEDURE_INVENTORY.md) · [Models from SD](docs/en/MODELS_SD.md)

## Test release

**MCU R14.8 + host R16.12**, pinned Klipper
`ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`, STM32F103 M300 Classic.

GitHub Actions publishes the tested build for direct Git deployment on Orange Pi.
MCU R14.7 adds a local encoder-release stop for OLED platform movement and retains the factory serial and OEM print-time queries.
MCU R14.8 adds a Thumb-2 repeat fill for OLED RLE and a read-only cycle benchmark.
See [Settings and Information](docs/en/SETTINGS_INFORMATION.md).

[Install on Orange Pi](docs/en/INSTALL.md). The package includes the checked host,
MCU application and compiled Fluidd. The installer refuses unknown runtime
edits and preserves PID, E and deliberate geometry.

Canonical runtime: host/klippy/extras. Configuration: host/config. Installer
and self-contained tests: host/update_template. MCU: mcu/SOURCE_MCU. Current
documentation is English under docs/en. Legacy localized URLs redirect to
English; immutable multilingual firmware evidence remains audit data.
No private factory application dump or bootloader is distributed.

OLED frame transport, sleep/wake, local MCU cooling and bounded host startup
recovery retain their existing implementations. Physical contact repeatability,
filament lengths, hold response and loaded 300 mm/s timing remain printer tests.
