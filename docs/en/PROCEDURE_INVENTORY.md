# Klipper, OLED and Fluidd procedure inventory

This inventory covers the native M300 Classic profile. The OLED selects
actions, Klippy owns the running procedure, and Fluidd sends commands to the
same owner. The R14.5 MCU owns the physical I/O, input capture, local fault
response and protective cooling. Legacy M02 print and M08 cycle paths are
separate diagnostic code.

## Entry points and ownership

| Operator path | Shared implementation | State and finish condition |
|---|---|---|
| Klipper → Heat hotend / Heat bed | Choose a preset within the configured heater limits, then send native M104 or M140. Fluidd uses the native heater controls. | The preset only selects a target. Heating begins when the operator invokes the heat action. TURN_OFF_HEATERS uses the same Klipper heaters. |
| Klipper → Home Y / X / XY / Z / XYZ | Native G28 through the M300 motion adapter. | XY can home independently. Z uses the configured center and at least 180°C, coarse contact and five successive contact/release updates. The fifth release is the reference. A 5 mm final clearance uses that reference, so it does not accumulate. |
| Klipper → Move axes | Relative XYZ jogs of 0.1, 1 or 10 mm through native G1. | Preserve parser state with SAVE/RESTORE_GCODE_STATE. Native homing and kinematic limits govern the move. |
| Klipper → Fans / PID calibration | Native M106 and the existing automatic cooling policy. Native PID_CALIBRATE and SAVE_CONFIG. | Tune while idle. SAVE_CONFIG persists accepted native calibration values. |
| Klipper → Print status | Native print statistics, virtual SD and pause/resume. | Reflects the same job as Fluidd and exposes the applicable contextual actions. |
| Zortrax M300 → Models | Read-only MCU SPI1 reader for FAT16/FAT32, or Klipper's host file directory. Browser generation and file identity bind the selection. | Choose a file, import and check it locally, then explicitly start. Back cancels import or releases the preview. A confirmed copy runs via native virtual SD. |
| Maintenance → Autocalibration / ZORTRAX_LEVEL | Native contact acquisition and M07 five-point wizard. | Heat to 260°C with 258°C readiness. Confirm hot-head warning, home Y then X and acquire center contact, confirm screw preparation, measure and adjust. Confirm the five-point result with heating off to save the observation. |
| Maintenance → Homing XY / Homing Z / Homing ALL | ZORTRAX_HOME_XY, ZORTRAX_HOME_Z and ZORTRAX_HOME_ALL call native G28 X Y, G28 Z and G28. | Directly below Autocalibration. Z requires homed XY. OLED and Fluidd share phase text and an animated hourglass; completion returns to Maintenance. |
| Maintenance → Heat the extruder / ZORTRAX_HEAT | Exclusive maintenance service over the native extruder heater. | 260°C with 258°C readiness. Operator confirmation turns heating off and returns to Maintenance. |
| Maintenance → Move the platform up/down | Native Z with an acknowledged held row on OLED, or ZORTRAX_PLATFORM_UP/DOWN for a finite command. | Up is negative Z toward the nozzle. Down is positive Z. Release, row change or stale input stops new quanta. Fluidd commands specify a finite distance and speed. |
| Maintenance → Fan test | ZORTRAX_FAN_TEST_START, ZORTRAX_FAN_UPPER, ZORTRAX_FAN_LOWER and ZORTRAX_FAN_TEST_END use the same fan-test session. | Each toggle requests 0 or 150/255. The automatic upper fan requirement overrides the requested off state. Back restores the lower request and recomputes the current upper thermostat requirement. |
| Material → Load / Unload | ZORTRAX_LOAD and ZORTRAX_UNLOAD share native E-only transport. | Default 240°C, 238°C readiness, operator confirmation before transport. Load defaults to 130 mm and Unload to 110 mm. Both turn heating off at completion. |
| Paused print → Change the material | ZORTRAX_CHANGE or M600 verifies native pause ownership, saved PAUSE_STATE and file position. | Retract 110 mm, wait for insertion confirmation, load 150 mm and restore the pause state and previous target. The parent remains paused until an explicit Resume. |
| Settings | Shared host NVM for light, buzzer, display sleep and model sorting. English is the only operator language. | Choice changes take effect on both surfaces. Sorting changes expire the browser generation. Re-selecting an active value avoids an NVM write. |
| Information / Help | Existing MCU identity, build/config metadata and optional Moonraker history refresh. | History is asynchronous and reports cache or error status. Printer serial is unavailable without actual serial data. Help links to the project repository. |
| Service / Tests | Separate diagnostic status, material/calibration aliases and deliberate XY motion checks. | Use motion and heating tests while idle. Test results describe the tested setup and do not grant automatic hardware qualification. |

[Maintenance and Material](MAINTENANCE_MATERIAL.md) ·
[Settings and Information](SETTINGS_INFORMATION.md) ·
[Models from SD](MODELS_SD.md)

## Print state and contextual screens

| Observed state | OLED context | Fluidd or Klippy equivalent |
|---|---|---|
| Importing or preview ready | Model file import or confirmation. | ZORTRAX_BROWSER_LIST, ZORTRAX_BROWSER_PREVIEW, ZORTRAX_MODELS_STATUS and token-bound start/cancel commands. The print worker has no file until start. |
| Native printing | PRINTING. A continuous ten-second knob hold requests Pause for that job. | The main Pause control invokes PAUSE. Native virtual SD stops scheduling additional file lines and PauseResume captures PAUSE_STATE. |
| Native paused with a valid pause owner | PAUSE MENU with Resume the print, Change the material and Stop the print. | RESUME restores PAUSE_STATE and continues the same file. ZORTRAX_CHANGE opens the shared material procedure. CANCEL_PRINT stops the print. |
| Material change in progress | Material procedure takes the active modal slot. | Existing procedure controls and token/phase checks. Resume is withheld by the service until its cleanup and pause restoration finish. |
| Native completion | PRINTING DONE and Remove the model. Show the replay action only when a verified previous job is eligible. | Reprint is a new native print of the eligible completed file. An operator initiates it after removing the model. |
| Cancel, fault or disconnect | End or error state for that context. | Native job and MCU owners handle cancellation, fault or shutdown. These states do not qualify a completed copy for replay. |

The UI must keep the native print state and the actual file session together.
A queued click or hold rechecks both under the G-code mutex. A filename alone
cannot distinguish a delayed action on one run from the next run of the same
file. A native SD pause can also be reported without a usable PAUSE_STATE
after a low-level M25, so Change and Resume require a restorable pause. At
EOF, accepted motion may still be in Klipper's queue. The completion path
waits for the queue before prompting for removal and starting a new job.

Knob holds for print contexts differ from the short firmware long-press event
used by ordinary menu navigation. They require fresh continuous input on
the current displayed job. Release, a changed job or view, an unacknowledged
or hidden display, and lifecycle loss revoke the hold. A hold belongs to one
action. A paused or completed screen requires its own new gesture.

Fluidd's dashboard controls and M300 macro group are separate interfaces.
The macro setup helper groups available G-code macros. In the inspected
Fluidd source, Reprint sends the filename from the current status or the
chosen history entry. Moonraker forwards it through SDCARD_PRINT_FILE. The
MCU SD snapshot needs an exact replay identity at that boundary. A reused
filename alone cannot prove which snapshot the operator selected.

[Fluidd print status source](https://github.com/fluidd-core/fluidd/blob/develop/src/components/widgets/status/PrinterStatusCard.vue) ·
[Moonraker print start source](https://github.com/Arksine/moonraker/blob/master/moonraker/components/klippy_apis.py#L127-L152)

## Algorithms and interlocks

| Layer | Rule |
|---|---|
| Reader and file identity | Read the card without writing it. Use card and file identity plus a bounded local copy. A directory change or sort change expires the old selection. Source validation precedes worker start. |
| Text G-code | Check size, UTF-8 and line framing. Copy commands as supplied and add a missing final line feed for the native worker. The slicer profile and configured macros supply the print sequence. |
| Classic M300 Z-code | Check M300 family/header, every record and CRC, heater and axis limits. Decode with the source's X/Y/E scales of 640/640/960 and its Z scale of 400 or 800. Native scale still determines actual movement. Conversion adds native heat, XYZ home and heater/fan shutdown. The Inventure fixture has a different family, scale and opcode. |
| Factory Z scale | Read factory record ID3 during identification. Revisions below 5 select 800 steps/mm, revisions 5 and later select 400. Invalid evidence blocks automatic profile selection. Explicit config mode uses configured values. The choice feeds native motion and calibration math. |
| Ordinary Z versus M07 | Ordinary G28 uses five successive release references after coarse contact. M07's first center contact is its own coarse home. It uses a common session XY offset in the range ±3 mm and nominal points 0, 1, 2, 3 and 4. |
| M07 correction | Measure 0 → 1 → 4 → 3 and fix the maximum initial corner raw count as the reference. Compare rear left then rear right and remeasure the pair. Use the signed truncating mean of points 0 and 1 for the front screw. Rear limits are inclusive from −0.20 to +0.10 mm. Front limits are strict. Round required turns upward to quarters with the original binary32 coefficient. Measure point 2 for review. The saved observation does not apply a live mesh. |
| Native services | Gate exclusive procedures on actual job ownership, MCU freshness, position when required, and native heater/fan limits. Contact search and release have finite endpoints and deadlines. Standalone material transport can run without XY/Z home. Material and platform movement use bounded segments or quanta and stop issuing work on cancellation. |
| Normal pause and stop | PAUSE saves parser and position state and stops the worker at its native boundary. It is distinct from emergency shutdown. The installed CANCEL_PRINT wrapper turns heaters off and delegates to native cancellation. M112 remains the immediate native emergency path. |
| Display and panel | Acknowledge frame transfers. Bind actions to view/session/phase, expire queued clicks on context changes, and keep a visible progress screen dim while busy after inactivity. Idle shows the moon notice and then turns off. An invisible wake gesture is consumed before accepting actions on the visible screen. |
| Cooling and faults | Local MCU protective cooling and guard remain independent of the OLED. A fan-test session can request a duty, but automatic upper cooling keeps priority. A fault or lifecycle change revokes service and gesture authority. |
| Host reconnect | After identification, permit one native restart attempt for a recognized previous-session heartbeat loss or a still-armed prior host session. Fresh native configuration and guard evidence are required. Restart clears old operation authority. |

[Leveling and Z reference](LEVELING.md) ·
[Factory profiles](HARDWARE_VARIANTS.md) ·
[Connection recovery](CONNECTION.md)

## Consistency and acceptance

- Operator surfaces should show a shared procedure state, even when their
  presentation differs. They should send one command to the same owner
  instead of reimplementing motion, temperature, pause or replay logic.
- A visible OLED selection is a permission to request an action, not a
  machine-state proof. The actual owner rechecks the motion bounds, native
  pause identity, source snapshot, or service phase as appropriate.
- A completed replay candidate is limited to an identity the running host
  can prove. It requires a new explicit operator confirmation and a ready,
  idle printer. Test print completion, normal stop, errors, restart,
  source replacement and another job starting before confirmation.
- The R16.9 baseline has 299 host tests, 16 native Klippy FILEOUTPUT cases
  and 28 modeled MCU SD scenario groups. Those cover both file types through
  native EOF, plus modeled FAT16/FAT32 and OLED import. The earlier suites
  cover original UI frames, homing and screw math, material transport,
  fan policy, sleep, startup, installer and rollback.
- Physical acceptance still covers SD/UART throughput, representative
  M300 Z-Suite exports, native stop/heater behavior, the long knob holds,
  removal/replay on the printer and integration with the installed Fluidd
  build. The software run cannot establish these properties on hardware.

[Baseline validation](VALIDATION_R16_9.md)
