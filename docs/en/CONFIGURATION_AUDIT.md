# Native configuration audit and cleanup — 2026-11-07

The supplied Orange Pi configuration snapshot was compared with source
`77546c99dbce7d922c3218cf12c36836911a7d97`, including native motion,
factory Z selection, OEM leveling, 25-point pad mesh, heater/fan ownership,
shared errors, material procedures and menu dependencies.

## Findings

| Finding | Resolution |
|---|---|
| Main file contains both heater conversion tables, including 205 bed table pairs | Move the complete original sections into `m300_temperature_sensors.cfg`; no pair is removed, rounded or interpolated anew |
| Empty `m300_pad_mesh` is declared a second time immediately before the configured section | Remove only the redundant empty declaration; preserve measured bounds and centers |
| Procedure options are mixed into main hardware declarations and macro files | Move the supported M300 service sections into `m300_services.cfg` |
| `klipper_calibration.cfg` is empty while PID aliases live in the thermal commissioning file | Consolidate existing PID aliases into the included calibration file; keep each body and parameter default |
| Comments still describe TEST01 diagnostics-only behavior, zero filament-temperature defaults and old watermark control | Replace recognizable stale generated comments; retain working PID in SAVE_CONFIG |
| An unqualified legacy M08 cycle and checked-file wrapper are retained although current printing uses native Virtual SD / Models | Retire only the recognized inactive cycle, its requirement/enabling hints and exact stock wrapper; preserve custom cycle macro references and qualified workflows |
| Default legacy jog/fan hints obscure native platform speed and thermostat ownership | Remove only unchanged redundant hints; custom values remain. Native platform speed, 50/45°C cooling and physical release stop are unchanged |
| Stock Fluidd web updater targets `fluidd-core/fluidd`, while the project installs its own verified extension | Retire that exact updater during opt-in cleanup; project Git installation remains the update path |
| Stock `fluidd-config` updater is present although the active include graph does not load `fluidd.cfg` | Retire it only when that file is unused; custom sources remain |
| A trusted-client CIDR is duplicated | Deduplicate the entry, preserving the same effective permissions and CORS |
| Extra `.cfg` snapshots and former profile directories are not loaded | Exclude them from the cleaned configuration package; they are not evidence of duplicate active macros |

The native resource audit (`m300_resources`), ADC owners, local cooling,
material facade and read-only Z-code diagnostics remain available. Empty
sections that actually instantiate a used service are not removed merely
because they contain no options.

## Values retained from the supplied snapshot

| Setting | Retained value |
|---|---|
| UART | 750000; native command restart |
| OLED | SPI 4500000, chunk interval 0.002 s, refresh interval 0.2 s |
| XY travel | X0..300, Y0..305 mm |
| Z travel | 0..315 mm |
| Native velocity / acceleration | 300 mm/s / 700 mm/s² |
| Native Z velocity / acceleration | 35 / 75 |
| X/Y homing / Z coarse homing | 50 / 15 mm/s |
| X/Y/E microsteps | 128 |
| Configured Z rotation distance / E rotation distance | 4 / 26.133 mm |
| Hotend PID | 15.152 / 0.472 / 121.598 |
| Bed PID | 61.966 / 1.410 / 680.852 |
| Contact margin | 0 |
| Center contact area | X130..180, Y130..180; center X155/Y155 |
| Front-left / front-right contact rectangles | (0,0)..(43,51) / (260,0)..(300,51) |
| Rear-left / rear-right contact rectangles | (0,260)..(43,305) / (260,262)..(300,305) |
| Native G28 contact XY | X150/Y158 |
| Pad-mesh preparation | Hotend minimum 180°C, bed 60°C, existing hotter-target policy |
| NVM file and identity | Exact existing values, including historical TEST01 names |

Historical `LAB` names on the active ADC sensor types are identifiers used by
the heaters. They are retained. The explicit OEM Z-scale hint is also retained:
the existing factory-profile audit selects the physical HW04/HW05 scale and
checks it against native step distance. Merely renaming an old path or replacing
this mechanism would not constitute safe configuration cleanup.

All 25 requested pad positions fit within the supplied XY travel and each
explicit contact rectangle. The original five OEM leveling positions also
remain inside those rectangles. No new physical probing was performed.

## Resulting layout

| File | Responsibility |
|---|---|
| `printer.cfg` | Hardware, limits, native heaters/fans/outputs, include links and SAVE_CONFIG |
| `m300_temperature_sensors.cfg` | Complete original ADC conversion tables |
| `m300_services.cfg` | Homing, leveling, mesh geometry, material, state, menu and diagnostic settings |
| `m300_fluidd.cfg` / `m300_operations.cfg` | Existing native/shared operator macros |
| `klipper_calibration.cfg` | One set of native PID aliases |
| `klipper_thermal.cfg` | Existing lifecycle and native thermal/status adapter |
| `m300_tests.cfg` | Explicit diagnostic/stress macros; never automatic |
| `m300_display.cfg` | Existing display sleep/brightness settings |
| `moonraker.conf` | Existing server/access settings and project-managed update sources |

For this snapshot, `printer.cfg` shrinks from 818 to 229 lines. The thermal
file has 421 lines and the procedure/settings file has 172 lines. This is
layout and unused-path cleanup, not a claimed speedup of the native ADC or
STEP code.

## Menu marks

Klipper and Zortrax use paired monochrome printer-frame marks with recognizable
K/Z glyphs, equal 50×50 geometry, four frames and the same 500 ms frame duration
as the activity catalog. Native PNG/GIF/SVG previews are in
`docs/assets/menu-symbols`. Runtime frames are loaded lazily through the
existing bounded 32-frame decoder cache. No new sender, polling timer, GPIO,
encoder sampling or MCU work loop is added.

## Validation and deployment

`install-orange-pi.py --organize-config` plans against the current files on the
Orange Pi; it does not blindly replace them with an older uploaded snapshot.
The installer remains idle-only, backs up originals, checks concurrent edits
and applies/rolls back atomically. Unknown duplicate nonempty sections and
unrecognized generated target files are refused before writing.

Tests verify effective hardware/settings equality, exact conversion blocks and
SAVE_CONFIG, custom macro preservation, include order, repeated-run identity,
custom updater preservation, real installer migration and exact rollback.
The full workflow also executes real pinned Klippy FILEOUTPUT on an organized
include tree and validates the native icon frames and animation exports.
The supplied snapshot is additionally validated locally using isolated state
and file-output paths. These are software checks, not physical hardware tests.
