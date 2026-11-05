# Maintenance and Material — R16.7

Native Z homing allows up to 600 seconds for nozzle preheat by default.
Each precision contact and release cycle has a 45-second deadline.
Maintenance platform movement defaults to 10 mm/s, subject to native
Z limits. The OLED hold keeps the MCU's local button-release stop.
The XY diagnostic defaults to 50 mm/s and accepts up to 60 mm/s.
These values apply to the diagnostic, independent of the print speed override.

[Installation](INSTALL.md) · [M07 leveling](LEVELING.md) · [Validation](VALIDATION_R16_7.md)

All current printer UI, Fluidd prompts, macros and release documentation use
English. The retained multilingual firmware tables and reference frames are
audit evidence, not runtime language choices. Existing NVM settings remain
readable; an old language selection cannot change the English interface.

## Menu and macro bindings

Open Zortrax M300 on the OLED. Its catalog order is Models, Maintenance,
Material, Settings, Information. Back follows the menu history.

| Menu | Item | Macro | Behavior |
|---|---|---|---|
| Maintenance | Back | Navigation | Return to parent |
| Maintenance | Autocalibration | `ZORTRAX_LEVEL` | 260°C, five points and three manual screws |
| Maintenance | Homing XY | `ZORTRAX_HOME_XY` | Native `G28 X Y`, OLED hourglass and Fluidd home-button status |
| Maintenance | Homing Z | `ZORTRAX_HOME_Z` | Native `G28 Z`; XY must already be homed |
| Maintenance | Homing ALL | `ZORTRAX_HOME_ALL` | Native `G28`, OLED hourglass and Fluidd home-button status |
| Maintenance | Heat the extruder | `ZORTRAX_HEAT` | 260°C, ready from 258°C, confirm to turn off |
| Maintenance | Move the platform up | `ZORTRAX_PLATFORM_UP` | Negative native Z, toward the nozzle |
| Maintenance | Move the platform down | `ZORTRAX_PLATFORM_DOWN` | Positive native Z, away from the nozzle |
| Maintenance | Fan test | `ZORTRAX_FAN_TEST_START` | Open the original interactive submenu |
| Fan test | Back | `ZORTRAX_FAN_TEST_END` | Restore lower request and current upper thermostat policy |
| Fan test | Toggle upper fan | `ZORTRAX_FAN_UPPER` | Toggle 0 / 150⁄255 request; automatic cooling has priority |
| Fan test | Toggle lower fan | `ZORTRAX_FAN_LOWER` | Toggle 0 / 150⁄255 request |
| Material | Back | Navigation | Return to parent |
| Material | Unload the material | `ZORTRAX_UNLOAD` | 240°C → confirm removal → retract 110 mm → heater off |
| Material | Load the material | `ZORTRAX_LOAD` | 240°C → insert and confirm → feed 130 mm → heater off |
| Klipper / Print status, while paused | Change the material | `ZORTRAX_CHANGE`, `M600` | Retract 110 mm → insert and confirm → feed 150 mm; remain paused |

Maintenance includes the requested Fan test submenu. Change belongs to
the paused-print context, not the idle Material submenu. Homing XY, Homing Z
and Homing ALL are directly below Autocalibration in Maintenance. They return
to Maintenance on completion. OLED retains its original animated hourglass;
Fluidd shows status on the corresponding home button without a homing dialog,
including starts from macros and OLED. The phase text is shared. The procedure
macros are assigned to Fluidd's ZORTRAX M300 group by `setup_fluidd.py --apply`.
Existing macro visibility, colors and unrelated Fluidd preferences are preserved.

## Operation

A short press confirms the currently acknowledged dialog. A long press
cancels it. Fluidd buttons carry that same phase identity. A stale or repeated
confirmation cannot advance a new phase. Starting Heat/Load/Unload/Change from
a macro or console opens the same OLED dialog as starting from the menu.
Completion closes the Fluidd prompt and returns to Maintenance, Material or
the paused native Print status, as appropriate.

On the OLED, select a platform direction and hold the button. MCU R14.7
detects the raw encoder button's rising edge and samples the button every
millisecond as a fallback. On release it triggers
Klipper's native same-MCU stop to discard queued Z pulses, before debounce
and before any UART notification. At the allowed maximum of 4,000 step
pulses/s, a nominal 1 ms sample interval represents four step pulses.
The host reconciles Z from the halted step count. The stop latency is
modeled in software and has yet to be measured on hardware.

A fresh press on an acknowledged row and homed Z are required. A stale
press counter cannot arm motion. Leaving the row or losing panel snapshots
for 0.75 seconds requests a stop from the host. The move ends at the native Z
limit if reached first. Earlier MCU versions refuse this panel hold.

Fluidd platform macros execute a finite distance. The default is 1 mm.
Supply any positive distance whose endpoint fits the homed Z travel:

```gcode
ZORTRAX_PLATFORM_UP DISTANCE=1 SPEED=1
ZORTRAX_PLATFORM_DOWN DISTANCE=20 SPEED=1
```

The full requested endpoint must fit the actual homed Z range. The service
queues one segment of up to 1 mm at a time, so Cancel lets the current
segment finish and stops the remaining distance. The maintenance timeout
bounds waiting for progress during the finite move.

Load and Unload move E only; XYZ need not be homed. Native extrusion and
heater checks remain active. Configured lengths, speeds and E calibration
are preserved; defaults are 130/110 mm at 2 mm/s in up to 5 mm acknowledged
segments. Cancel cuts heat and drains the already accepted segment. M112
retains immediate native shutdown behavior.

For native Change, first pause the print. The service verifies the real
pause owner, PAUSE_STATE and file position. It preserves the pause snapshot,
XYZ and logical E; Resume is blocked while transport owns the printer.
Change uses the paused print's positive target, or 240°C if that target is
cold, unless TEMP is explicitly supplied. Successful completion restores the
previous paused target and leaves the print paused. The operator separately
chooses Resume. Cancel leaves the print paused with heating off. Cancellation
or replacement of the paused parent revokes the material service.

## Interactive Fan test

The original menu is Maintenance → Fan test → Back / Toggle upper fan /
Toggle lower fan. Entering saves the two OEM requests and starts the test
with both requests off. Each toggle requests 0 or 150/255 (about 58.8%), not
100%. It stays on the selected row. Back ends the session.

The upper fan is channel 1 / PE14, the native hotend fan. The lower fan is
channel 0 / PE13, native print cooling. R16.7 uses those existing fan queues,
not new pins or PWM owners. The cold submenu reproduces all twelve original
selection/state combinations byte for byte, including the font, Enabled /
Disabled fields and left selection marker. No separate OEM fan-test picture
was found in this path; the source draws a menu and two text fields.

Fluidd shows the same three action labels and state text. Console macros
use the same session, and direct upper/lower macros open it first if needed.
Back, leaving the page, host restart, a fault or the existing 300-second
service deadline revokes the session. A stale button cannot toggle a new phase.
Pending native fan requests must drain before entry. Printing, pause, another
service, queued movement and FILEOUTPUT cannot start a physical fan test.

Upper automatic cooling is a floor: with a heater target, temperature above
the native threshold, or invalid temperature evidence, the test cannot switch
it off. The screen then says (Cooling) and Automatic upper-fan cooling; Fluidd
uses those same words. Back restores the saved lower request and recomputes
CURRENT upper thermostat policy instead of replaying an old OFF. Faults or
stale MCU status never replay saved duty. Protective MCU cooling remains local.
The configured native thermostat remains unchanged.

## Source evidence and corrections

The supplied M300 Classic 1.3.1 application has SHA-256
`11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75`.
The original control-flow model was checked against 27,982 instruction
comments and executed with declared hardware/UI boundaries.

| Routine | Source address | Verified result |
|---|---|---|
| Load | `0x08014f24` | Heat 240/238, text 20 confirmation, text 22 feed, 124800 requests |
| Unload callback / helper | `0x08015004` / `0x08019680` | Heat 240/238, text 21 confirmation **before** text 19 retraction, 105600 requests |
| Change during pause | `0x08015384` | Text 19 retract, text 20 insertion confirmation, text 22 load; 105600/144000 requests; return to pause menu |
| Heat the extruder | `0x08015ed0` | 260/258, text 16 completion, heater off and Maintenance return |
| Hold platform controls | `0x08015d1c` | Button hold chooses the up/down motor routines |
| Interactive fan test | `0x08014940`, `0x080157f0`, `0x080157c8`, `0x08014980` | Save, requests off, independent 0/150 toggles, saved-request restoration |
| Fan state fields | `0x0801846c` | Original Enabled/Disabled text at x190, y12/y24 |

The table records the recovered source layout. Host menu revision 0.13.16.11
retains the three fan actions and moves each Enabled/Disabled/Cooling state
below its label, reserving the right side for the corresponding upper/lower
fan icon. Rotation requires an enabled selected fan and live/fresh status;
it reports the commanded state, not measured RPM. Original reference frames
remain in the software tests. See [activity bindings](UI_SYMBOLS.md).

With the nominal OEM E scale of 960 units/mm, the transport counters give
130, 110 and 150 mm. These are nominal program values, not independent
physical length measurements. The port retains the printer's calibrated E.

R16.5's post-retraction Unload confirmation was incorrect. R16.6 removes that
extra WAIT_REMOVE state and restores the original confirmation-before-retract
order. Native Change now uses the actual paused Klipper print rather than
requiring the disabled legacy M02 print engine.

## Deliberate port differences

Successful original Unload returns to Material without clearing its hotend
target. The port explicitly turns heating off. Material timeouts, stable
readiness, bounded segments, token revocation and restoring parser/idle state
are port protections. They are not presented as literal firmware behavior.

No raw TIM/GPIO motor loop is copied. Native planners, heater limits, sensors,
MCU fault supervision and factory Z400/Z800 selection remain authoritative.
Physical feed length, hold response and full procedure acceptance still need
a supervised printer test. See [validation and acceptance](VALIDATION_R16_7.md).

The OLED stays on the selected Maintenance row during a physical hold. The
hold is visible in the shared procedure status without opening a Fluidd
dialog. Finite Fluidd macros open their own motion prompt and select the
corresponding OLED row. At either Z limit the hold stops at the last whole
step within native travel. The host preserves the existing logical X, Y and
extruder coordinates when reconciling the halted Z step count.
