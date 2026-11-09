# Zortrax M300 Classic — Klipper v1.0.0-beta.10

[Download v1.0.0-beta.10](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/v1.0.0-beta.10) ·
[First installation (EN)](docs/en/FIRST_INSTALL.md) ·
[Pierwsza instalacja (PL)](docs/pl/FIRST_INSTALL.md)

For a blank Raspberry Pi / Orange Pi, use the versioned beta bundle and its
first-install helper after KIAUH has prepared the services. The bundle contains
the complete pinned M300 host, precompiled MCU and precompiled Fluidd. The
normal updater below is for an already installed M300.

**R29 host stuck in Shutdown with `M300NativeMaintenance ... hotend`?**
[Startup repair without requiring Ready](docs/en/RELEASE_v1.0.0-beta.2.md#recover-an-installed-r29-host-that-is-stuck-in-shutdown).

**Beta.10 OEM-style icon cleanup (sound unchanged):** The complete three-tone
Klipper logo retains its lowercase wordmark and native 50×50 printer enclosure,
with a fixed two-pixel platform instead of the obsolete animated rectangle
under the bed. Home/Move Cartesian frames now use even 2px, full-bright
outlines comparable to the original recovered firmware icons. The MCU's
independent fallback renderer stays 50×50 and 15-level bright; the onboard
SPI pass-through now has an explicit 4bpp 7/11/15 regression check.
**Buzzer code, timings and controls are untouched.**
[Release notes](docs/en/RELEASE_v1.0.0-beta.10.md).

**Beta.9 independent X and Y homing, one OLED/Fluidd owner and full logo:**
`Home X` and `Home Y` now run through the same guarded procedures as Fluidd
macros `ZORTRAX_HOME_X` and `ZORTRAX_HOME_Y`. The OLED keeps the original
selected row rather than jumping to Back. Home Z accepts the separately
established X and Y references; safe 5 mm pre-XY clearance, 180 C Z preheat,
and contact checks are unchanged. The main Klipper icon contains the complete
V/nozzle graphic **and lowercase 'klipper' wordmark**, with three native
4bpp brightness shades matching the original OLED icon proportions.
[Beta.9 notes](docs/en/RELEASE_v1.0.0-beta.9.md).

**Beta.8 OLED logo and sound:** The main Klipper menu icon now displays
the official V/nozzle Klipper mark instead of a plain K. OLED navigation
uses 35 ms short beeps and a distinct 140 ms Back/Up confirmation, with a
dedicated beep timer independent of the slow RGB/status timer. Buzzer Disabled
immediately silences the output. The original project icon sprite is retained
as evidence, with its visible K replaced in the monochrome rendered frame.
[Source and update notes](docs/en/RELEASE_v1.0.0-beta.8.md).

**Beta.7 update repair:** The verified beta.4/beta.5 Orange Pi deployment
files were missing from five module-hash allowlists in the beta.6 host
installer. Existing official files triggered `Existing unknown M300 runtime
module` even though they came from published builds. Beta.7 adds precisely
those five SHA-256 digests, tests migration against immutable verified
beta.4/beta.5/beta.6 deployment manifests, and prints the unknown on-disk
SHA-256 when local edits remain. It retains the Ready/idle guard and
transactional backup. [Fix and update guide](docs/en/RELEASE_v1.0.0-beta.7.md).

**Beta.6 OLED menu changes:** Home X/Y/Z/XY/XYZ use one
order and vocabulary, the selected Cartesian arrows blink independently for
Home/Move, and Back returns to the parent menu's selected row. Removing
"(180C)" from Home Z does not change the 180 C contact-homing requirement.
The fragment seen at Print status is a frame of the original printing symbol,
not a percentage-progress gauge. Changes reach the Orange Pi deploy branch
only after the full build and validation succeeds.

Beta.5 restores the native colored mesh chart for saved M300 profiles and
groups the platform and print macros:
[changes and existing-printer update](docs/en/RELEASE_v1.0.0-beta.5.md).
The [beta.4 OLED ACK recovery](docs/en/RELEASE_v1.0.0-beta.4.md) remains included.

[Installation](docs/en/INSTALL.md) · [Features & acceptance](docs/en/FEATURES.md) · [Build](docs/en/BUILD.md) · [M07 leveling](docs/en/LEVELING.md) · [Procedure validation](docs/en/PRINT_CONTEXT.md)

Protected native pause/resume, rear-right park X300 Y305, long-pause bed hold,
M600 and shared Start/End: [workflow, parameters and audit (PL)](docs/pl/PRINT_CONTROL.md).

## Project overview — November 8, 2026

Klipper integration for the **original Zortrax M300 Classic** (STM32F103 MCU, Orange Pi host, original monochrome OLED and rotary encoder). The main Orange Pi build combines **MCU R14.18 with Host R16.12**.

R14.18 adds a [shared 21-code OEM error catalogue](docs/en/ERRORS.md) across
Klipper, Fluidd and OLED, plus autonomous MCU-local fault descriptions and
animations after shutdown. Native Klipper timing errors keep their own names.

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

**MCU R14.18 + host R16.12**, pinned Klipper
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
R14.16 aligns native host and offline MCU [hotend cooling](docs/en/COOLING.md):
50 C ON / 45 C OFF, based on measured temperature rather than heater target.
An ADC1-stale handoff can cool thermostatically only with fresh independent
ADC2 evidence; the shutdown and heater/motion locks remain latched.
R14.17 adds the shared [status LED policy](docs/en/SETTINGS_INFORMATION.md):
Ready green, heating red, pause purple and printing/active work white.
Errors repeat red → green → blue at five seconds per color. The MCU retains
that error indication after shutdown without UART traffic or user timers.
The timer motion core, guards and 50/45 C cooling behavior are retained.
Host menu revision `0.13.16.11-ACTIVITY-SYMBOLS` assigns these graphics to the
corresponding OLED screens and reported states. Brightness controls retain
16 segments in a shorter bar alongside the icon. See the
[rendered screen preview](docs/en/UI_SYMBOLS.md#host-oled-bindings--menu-revision-0131611).
Menu revision `0.13.16.12-PROCEDURE-RETURN` remembers the invoking OLED screen,
cursor and navigation history. Fluidd homing returns to native Klipper status
when that was the preceding screen, while manual navigation is respected.
Menu revision `0.13.16.13-BRIGHTNESS-MESH-BOUNDS` synchronizes the OLED/Fluidd
brightness preview and Save operation without expiring Back. Pad mesh preview
reports requested points against the configured XY travel and can suggest a
larger inset without changing motor limits. See [pad mesh geometry](docs/en/LEVELING.md#optional-klipper-pad-mesh).
Pad mesh revision `0.13.16.15-PAD-TRAVEL` fits unreachable corners inside
their own pad and the existing XY travel. Its macro respects configuration
and previews instead of restoring old 60 mm literals. X300/Y305 is exercised
in both geometry regression tests and the actual Klippy profile integration.
Pad mesh revision `0.13.16.16-PAD-TUNE` opens Fluidd Tune once probing starts,
shows progress and rejected-attempt diagnostics, and previews an accepted
native profile before compensation is activated. Saving is offered only for
the current accepted run. Current releases use a default 0.80 mm span limit.
Revision `0.13.16.17-PAD-PREPARE` makes the measurement a single command:
simultaneous native bed/nozzle heating, stable-temperature wait and required
native homing precede probing. Nozzle temperature uses 180 °C as a minimum
and retains a hotter working temperature. Tune shows each preparation phase.
Revision `0.13.16.18-PAD-OLED` opens the animated OLED five-pad page for
remote starts, retains it through internal homing and restores its invoking
screen after success. The multiline macro exposes all Fluidd parameter fields;
its name remains the ordinary quick button and Send submits field overrides.
G28, OEM leveling and pad mesh establish shared 5 mm Z clearance before XY.
Successful pad mesh restores the previous heater targets, including off;
failed runs turn both targets off.
Revision `0.13.16.19-PAD-ZERO-MARGIN` permits zero metal/travel margins and
preserves configured dimensions, including 60 mm outer pads. A home point
15 mm inside a 60 mm pad gives physical bounds −15..45 and a center at 15;
travel fitting can retain X0/Y0 while removing unreachable negative corners.
Revision `0.13.16.20-PAD-CONTACT-MAP` supports explicit rectangles for each
pad and a live top view in Tune, showing the fields, 25 planned/completed
points and the nozzle from existing Klipper motion reports. The measured
X0–43 / X260–300 and Y0–51 / Y260–305 ranges, with rear-right Y262, replace
the previous approximate square layout. See
[contact rectangles](docs/en/LEVELING.md#measured-contact-rectangles).

MCU R14.7 adds a local encoder-release stop for OLED platform movement and retains the factory serial and OEM print-time queries.
MCU R14.8 adds a Thumb-2 repeat fill for OLED RLE and a read-only cycle benchmark.
MCU R14.9 coalesces idle encoder diagnostics into the existing panel snapshots.
See [Settings and Information](docs/en/SETTINGS_INFORMATION.md).

[Install on Orange Pi](docs/en/INSTALL.md). The package includes the checked host,
MCU application and compiled Fluidd. The installer refuses unknown runtime
edits and preserves PID, E and deliberate geometry.

Canonical runtime: host/klippy/extras. Configuration: host/config. Installer
and self-contained tests: host/update_template. MCU: mcu/SOURCE_MCU. Current
reference documentation is under docs/en, with the first-install guide and
print-control audit also available in Polish under docs/pl. Immutable
multilingual firmware evidence remains audit data.
No private factory application dump or bootloader is distributed.

OLED frame transport, sleep/wake, local MCU cooling and bounded host startup
recovery retain their existing implementations. Physical contact repeatability,
filament lengths, hold response and loaded 300 mm/s timing remain printer tests.
