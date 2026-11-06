# Classic M300 error handling

Host error revision `0.13.16.22-OEM-ERRORS` pairs with MCU
`0.13.14.18-OEM-ERRORS-UART8`. This is the Classic M300 1.3.1 catalogue,
not the Plus, Dual or Inventure error numbering.

## Shared presentation

Klipper, Fluidd and the OLED use one 21-code catalogue. Each entry has an
English title, repair advice, compact OLED lines and a semantic icon. The
host uses the existing four-frame animations. Matching monochrome MCU
frames and text are generated from the same source catalogue and checked
in CI. The OLED font, navigation speed, X/Y STEP timer implementation,
UART baud, temperature thresholds and 50/45 C cooling policy are retained.

Use **Zortrax M300 → Information → Errors** on OLED or the equivalent
Fluidd information dialog. It includes the current error and the code
catalogue. Inspecting a catalogue entry does not raise a fault, change LEDs,
operate hardware or send an error to the MCU.
Back from a live catalogue entry restores the catalogue in Fluidd and OLED.

```gcode
ZORTRAX_ERROR_STATUS
ZORTRAX_ERROR_SHOW
ZORTRAX_ERROR_SHOW CODE=42
```

The last command displays help for OEM 042 only. These commands remain
available when Klipper is not Ready. `M300_ERRORS` reports the current
identity, original reason, source, a bounded 32-entry session history and
the cached MCU fault metadata. Explicit STATUS queries the MCU once; normal
status reads do not poll UART. MCU responses arrive asynchronously.

Nonfatal file/validation notices can be acknowledged using the button
carrying their exact identity, or `ZORTRAX_ERROR_ACK ID=<current-id>`.
An old acknowledgement cannot clear a newer error. Dismissing an OLED
notice returns to the preceding page; it does not acknowledge a fault or
resume printing. Acknowledgement never cancels an owner procedure, clears
an MCU latch, restarts Klipper, grants ARM or resumes a job. Error LEDs
retain priority until the notice is acknowledged or its owner is recovered.

## Runtime bindings and limits

| OEM code | Meaning | Evidence used by this port |
|---|---|---|
| 002 | SD card read error | Physical SD reader failure |
| 003 | Invalid model file | Header, records, CRC or supported-command validation |
| 004 | Print file read interrupted | SD timeout or native snapshot I/O failure |
| 010 | Extruder heating error | Native `verify_heater` heating failure |
| 011 | Hotend overtemperature | Explicit overtemperature or valid, non-rail hotend raw value above its limit |
| 012 | Bed overtemperature | Explicit overtemperature or valid, non-rail bed raw value below its limit |
| 013 | Unexpected hotend temperature drop | Explicit drop diagnosis; a generic native `verify_heater` message remains 010 |
| 014 | Bed thermistor error | Identified bed ADC range, rail or stale sample |
| 015 | Hotend thermistor connection error | Identified hotend ADC range, rail or stale sample |
| 030 | Small platform connector | Explicit small-connector diagnosis only |
| 031 | Large platform connector | Explicit large-connector diagnosis only |
| 032 | Main extruder cable | Explicit cable diagnosis only; no additional qualified cable sensor |
| 033 | Perforated plate contacts | Explicit plate-contact diagnosis; a general probing failure remains 042 |
| 034 | XY endstop error | Native XY homing failure |
| 035 | Extruder gear / ribbon inspection | Explicit confirmed report only; no automatic jam or gear feedback sensor |
| 040 | Firmware update needed | Required Z-code firmware triplet exceeds the audited profile |
| 041 | Calibration failed | Calibration rejection/attempt limits or unacceptable result |
| 042 | Pad probing failed | Actual PC7/contact/probe failure; missing homing/heating preconditions alone are not this error |
| 075 | Newer Z-Suite required | Explicit version diagnosis only; no guessed minimum version |
| 076 | Wrong printer model | Z-code model-family validation |
| 101 | No models on SD | Empty physical-SD browser result |

All 21 entries exist on the host and MCU. This does not create a detector
for hardware feedback that the printer has not supplied. In particular,
PE15 reports **Platform connector fault**, with advice to check both cables;
it does not choose 030 versus 031. An unidentified ADC fault stays
**Temperature sensor / ADC fault**, without asserting a particular sensor
or overheating. Both-stale ADC channels likewise remain unnumbered.
The native ADC accumulated range check identifies its channel but does not
infer overtemperature from an unreliable sample. Existing guard thresholds
and shutdown decisions are unchanged.

Native Klipper faults such as **Timer too close**, **Stepper timing error**,
**Emergency stop** and **Klipper connection lost** retain their actual names
and are not assigned invented OEM numbers. Original guard reasons 1–9/255
remain distinct from OEM codes. Full native reasons remain in the console
and `klippy.log`.
Identified native thermal failures retain priority over their homing or
calibration context when selecting the displayed code.

## MCU ownership after shutdown

The MCU records its first specific local cause before generic shutdown
handlers run. Healthy STEP generation and ADC samples do not format errors,
render graphics or send diagnostic packets. Error recording adds no timer
or periodic serial query. A nonfatal file notice cannot become the reason
for a later native timing shutdown.

After shutdown the existing local OLED owner renders the code, short cause,
repair advice and four-frame symbol using its 128-byte scanline buffer.
It runs from bounded task context, with interrupts available during SPI;
the shutdown path only records metadata and schedules the existing recovery.
Late host detail can refine a generic shutdown explanation with one small
metadata command. It cannot replace an already specific local diagnosis.
An MCU-native static reason ID is retained for diagnostics.

Only `m300_error_set code=... kind=... fatal=...` and `m300_error_query` are
added to the protocol. Both may run during shutdown and access metadata
only. Neither touches GPIO, actuator queues, cooling, heater gates or ARM.
Fatal records cannot be cleared through this interface, even after a native
`clear_shutdown`. An explicit full firmware restart is still required.
The local RGB alarm from R14.17 is retained.

## Update and validation

Update the `orange-pi` Git checkout using the normal installer and flash
the matching `MCU/M300_R14_18_SD.zip` application through the existing SD
bootloader procedure. Do not change the established UART baud for this update.
After startup, `ZORTRAX_ERROR_STATUS` should report revision
`0.13.16.22-OEM-ERRORS`, `mcu_abi: 1`, `catalogue_size: 21` and no active error.

CI checks catalogue/MCU text and bitmap equality, native board fault paths,
ADC rails versus overtemperature, missing-channel ambiguity, first-cause
retention, late metadata updates, local OLED redraw after shutdown, stale
acknowledgements, bounded history, no repeated UART writes, shared menu
navigation and all 21 read-only catalogue views. Real Klippy FILEOUTPUT
also checks the catalogue and a native M112 shutdown. These are software
and register-model checks, not physical fault-injection qualification.
