# Menu 2. Maintenance and 3. Material — host R16.5

[Polski](../pl/MAINTENANCE_MATERIAL.md) · [Install](INSTALL.md) · [Autocalibration](LEVELING.md)

Open **Zortrax M300** on the OLED. Its catalog order is Models, Maintenance,
Material, Settings, Information. Maintenance has exactly Back, Autocalibration,
Heat the extruder, Move the platform up, Move the platform down. Material has
Back, Unload the material, Load the material. Back follows the menu history;
the other native controls remain under Klipper.

| OLED item | Fluidd ZORTRAX M300 macro | Execution |
|---|---|---|
| Autocalibration | `ZORTRAX_LEVEL` | M07 at 260°C with shared confirmations and three-screw instructions |
| Heat the extruder | `ZORTRAX_HEAT` | 260°C, ready at 258°C; confirm to switch heater off |
| Move the platform up | `ZORTRAX_PLATFORM_UP DISTANCE=1 SPEED=1` | Native negative Z, platform toward nozzle |
| Move the platform down | `ZORTRAX_PLATFORM_DOWN DISTANCE=1 SPEED=1` | Native positive Z, platform away from nozzle |
| Unload the material | `ZORTRAX_UNLOAD` | 240°C → retract → confirm removal → heater off |
| Load the material | `ZORTRAX_LOAD` | 240°C → confirm insertion → feed → heater off |

After installation and Ready run `python3 setup_fluidd.py --apply` and refresh
Fluidd. Existing macros are reassigned while their visibility, colors and other
user preferences are preserved. `TEST_ZORTRAX_LEVEL` remains a test alias.

## Controls

Follow the [M07 audit](LEVELING.md) for Autocalibration. Heat/Load/Unload open
the same modal OLED dialog when started by a macro or console. A short press
confirms the visible phase; a long press cancels. Fluidd acts on that same
phase. Expired or duplicate confirmations are rejected. Completion returns
Heat to Maintenance and material operations to Material. Load adds no purge
confirmation after its fixed feed.

Select Move the platform up/down and **hold the button**. Releasing stops
issuing further moves. The gesture uses the button, not encoder rotation;
its long event is consumed as part of the hold. A genuinely homed Z is
required; no automatic or fabricated home is added. The OLED requires an
acknowledged selected row and a fresh press after release. Leaving the view
or losing fresh panel input for 0.75 s ends the hold. At most one native
quantum of 0.1 mm can remain queued. Fluidd macros execute a finite DISTANCE,
default 1 mm, at SPEED in mm/s. Both paths use the same native Z owner and
existing axis bounds and `max_jog_distance`/`jog_speed` configuration.

Load/Unload move E only and do not require XYZ homing. Existing configured
lengths and speeds are retained: defaults Load 130 mm, Unload 110 mm, 2 mm/s,
up to 5 mm per acknowledged segment. Cancel cuts heating and drains the
already accepted segment. M112 retains native behavior. Services require an
idle native print; they do not implement material change in a paused native
print. The legacy M600/M02 path is outside this change. PID, calibrated E,
sensors, axis geometry and MCU control retain their existing owners.

During a procedure external movement, coordinate changes and positive heater
targets are rejected. Heater-off cancels the service. Completion restores
the original native command functions, material parser state and idle timeout.
Restart never replays interrupted motion. Enabling the software profile is
separate from measuring hardware: `hardware_qualified=false` remains accurate.

## Original evidence and parity boundaries

Source: supplied M300 Classic 1.3.1 application, SHA-256
`11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75`.
RAM nodes: Maintenance `0x20000680`, Material `0x200007b0`, Heat `0x200006c0`,
Up `0x20000700`, Down `0x20000720`, Unload `0x200007d0`, Load `0x200007f0`.
Hold dispatcher `0x08015d1c`, directions `0x08015354`/`0x08015324`, heating
`0x08015ed0`, Load `0x08014f24`, Unload `0x08015004`.

| Phase | OEM text ID | Dialog descriptor | Sprite descriptor |
|---|---:|---|---|
| Heating | 123 | Direct table call `0x0801b96c` | `0x0801c2b8` |
| Heating done | 16 | `0x08021d38` | `0x0801c024` |
| Retracting | 19 | `0x08021eac` | `0x0801cfb0` |
| Insert and press button | 20 | `0x08021eb8` | `0x0801d0b8` |
| Removal confirmation | 21 | `0x08021ec4` | `0x0801cfb0` |
| Feeding | 22 | `0x08021ea0` | `0x0801d0b8` |

Literal text, line breaks, 13-pixel glyphs and sprites come from the binary.
Fluidd uses the same description as the OLED renderer without state/session
metadata in OEM dialog text. Port cancellation and fault messages are additions.

The port uses native motion and thermal control rather than copying the old
TIM/GPIO motor loops. Physical feed length and hold speed require printer
acceptance; a timer-call count alone is not a physical calibration.

Software validation: 203 host tests, 9 repository contracts, 13 actual Klippy
FILEOUTPUT processes, 110 complete frames in five languages matching the
recovered original renderer byte for byte. Added tests execute the pinned
G-code dispatcher and GCodeMove, full material sessions and actual OLED dispatch,
ownership, cancellation and restoration. Heater, clock and physical move
boundaries are modeled. Orange Pi/printer acceptance remains outstanding.
