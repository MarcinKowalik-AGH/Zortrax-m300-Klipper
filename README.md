# Zortrax M300 Classic — Klipper R16.12

[Installation](docs/en/INSTALL.md) · [Features & acceptance](docs/en/FEATURES.md) · [Build](docs/en/BUILD.md) · [M07 leveling](docs/en/LEVELING.md) · [Procedure validation](docs/en/PRINT_CONTEXT.md)

## Project overview — November 3, 2026

Klipper integration for the **original Zortrax M300 Classic** (STM32F103 MCU, Orange Pi host, original monochrome OLED and rotary encoder). The main Orange Pi build combines **MCU R14.15 with Host R16.12**.

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

## Main release

**MCU R14.15 + host R16.12**, pinned Klipper
`ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`, STM32F103 M300 Classic.

GitHub Actions publishes the verified package to the
[`orange-pi` deployment branch](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/tree/orange-pi).
R14.14 enables gated hardware STEP timers for eligible X/Y blocks. On an HW05
printer at 750,000 baud, the dry run completed 6,054 moves, including four
segmented diagonals commanded at 400 mm/s. The 201.6-second link sample
recorded zero retransmitted and zero rejected bytes. Loaded printing remains
a separate validation step. Fluidd procedure prompts reserve brightness bars
for the dedicated brightness pages.

R14.15 retains that motion core and adds local MCU waiting/disconnection
animations without UART frame traffic. The [24 activity symbols](docs/en/UI_SYMBOLS.md)
include GIF previews, individual frames and native OLED data. Thermal limits
and fault detection are unchanged.
Host menu revision `0.13.16.11-ACTIVITY-SYMBOLS` assigns these graphics to the
corresponding OLED screens and reported states. Brightness controls retain
16 segments in a shorter bar alongside the icon. See the
[rendered screen preview](docs/en/UI_SYMBOLS.md#host-oled-bindings--menu-revision-0131611).
Menu revision `0.13.16.12-PROCEDURE-RETURN` remembers the invoking OLED screen,
cursor and navigation history. Fluidd homing returns to native Klipper status
when that was the preceding screen, while manual navigation is respected.

MCU R14.7 adds a local encoder-release stop for OLED platform movement and retains the factory serial and OEM print-time queries.
MCU R14.8 adds a Thumb-2 repeat fill for OLED RLE and a read-only cycle benchmark.
MCU R14.9 coalesces idle encoder diagnostics into the existing panel snapshots.
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
