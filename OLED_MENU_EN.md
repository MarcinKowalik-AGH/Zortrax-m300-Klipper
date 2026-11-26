# OLED menu audit — R16.18

The R16.18 functional audit is included in release **1.0.4 / R16.19**.
[Installation](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/d1616a9e7007b44dda2a737cc0297b7f66a77b63/docs/en/INSTALL.md) · [Hardware acceptance](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/d1616a9e7007b44dda2a737cc0297b7f66a77b63/docs/pl/ACCEPTANCE_REGISTER.md) · [Complete view and command inventory](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/d1616a9e7007b44dda2a737cc0297b7f66a77b63/docs/reports/OLED_MENU_AUDIT.json)

Scope: **M300 Classic, MCU 1.0.9, host R16.18**. Software checks cover production
menu branches, actual Klippy command registration, shared procedure owners,
confirmations and return navigation. They did not operate physical hardware.
Not every procedure has a completed hardware acceptance test; the linked ledger
retains confirmed results, reported failures and pending tests separately.

## Corrections

- The user reported leaving **Fan test after toggling a fan with the OLED knob**.
  The general status shortcut could end an active test, and an old procedure's
  late completion could take its view. An active fan test now retains presentation
  ownership and ignores unrelated status requests. Both mechanisms were checked
  in software; the specific caller on the printer still needs diagnostics.
  A long press follows the current **Back** action and restores the invoking row.
- **Current procedure / M300_PROCEDURE** now reopens the OLED view as well as the
  Fluidd view. It opens the existing session without restarting an operation.
- **Back** from a homing fault restores its invoking screen. It does not clear
  FAULT, acknowledge an MCU safety latch or continue motion.
- The PID menu uses the same `PID_HOTEND`, `PID_BED` and `PID_SAVE` macros as Fluidd.

## Bindings

Navigation and read-only rows do not need separate G-code macros. Confirmation
buttons carry the current owner's view token. The JSON inventory contains every
inspected row and checks referenced commands against the actual Klippy registry.
The Klippy process inspected **44 views, 582 rows and 26 registered commands**.
Separate host tests cover active phases, acknowledgements and return paths.

| Function | Shared entry / owner |
|---|---|
| OEM Autocalibration | `M300_LEVEL` → `m300_calibration` |
| Home X / Y / Z / XY / XYZ in both menus | `M300_HOME_X/Y/Z/XY/ALL` → native homing |
| OEM Heat extruder / platform | `M300_HEAT`, `M300_HEAT_PLATFORM` → `m300_maintenance` |
| Platform up / down | Physical hold → maintenance; Fluidd uses `M300_PLATFORM_UP/DOWN` |
| Fan test | `M300_FAN_TEST_START`, `M300_FAN_UPPER/LOWER`, `M300_FAN_TEST_END` |
| Current procedure | `M300_PROCEDURE` → current owner and phase |
| Load / Unload / paused Change | `M300_LOAD/UNLOAD/CHANGE` → filament and print owners |
| Manual heater targets / off | `SET_HEATER_TEMPERATURE`, `TURN_OFF_HEATERS` |
| Optional pad mesh | `BED_MESH` → `m300_pad_mesh`; separate from OEM Autocalibration |
| Move axes | Native `SAVE_GCODE_STATE`, `G91`, `G1`, restore parser state without moving |
| Part-fan speed | Native `M106`; upper automatic cooling remains owned by its thermostat |
| PID | `PID_HOTEND TARGET=200`, `PID_BED TARGET=60`, `PID_SAVE` |
| Models | Browser → models → native virtual SD; checked file identity and configured SD policy |
| Print / Pause / Resume / Stop / Reprint | Native print owners and `PAUSE`, `RESUME`, `CANCEL_PRINT`, `M300_REPRINT` |
| All ten Settings entries | `m300_settings` / `m300_nvm`; existing `M300_*` settings macros |
| Information / Help / Errors / Diagnostics | Existing read-only owners; 21-code catalogue, retained alarm cause |

## OEM comparison and limits

Host tests compare the retained OEM instruction-model results in
`firmware131_procedures.json`, `firmware131_maintenance.json` and
`firmware131_settings.json`. Their source application SHA-256 is
`11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75`.
Those traces explicitly model operator, heater and mechanical boundaries.
This audit does not claim a fresh physical OEM execution.

The historical atlas lists 66 OEM structures: 58 adapted, three not reproduced
(the separate hot-head warning and generic Yes/No structures), and five unused
entries/spacers. Port confirmations have session identities. Historical beta.20
illustrations are not the current menu specification; Service / Tests is retired.

Physical fan rotation has no verified tachometer feedback. Z accuracy, thermal
performance, filament transport, first layer and long printing need hardware
acceptance. Successful software tests do not qualify those physical functions.

## Install

With an existing printer idle and Ready:

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Use the host updater: `--update-fluidd` alone does not install OLED Python changes.
MCU 1.0.9 remains sufficient. Existing PID, mesh, qualified Z and optional thermal
includes are preserved. New users follow [the complete installation](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/d1616a9e7007b44dda2a737cc0297b7f66a77b63/docs/en/FIRST_INSTALL.md);
the `orange-pi` branch contains built files and checksums.
