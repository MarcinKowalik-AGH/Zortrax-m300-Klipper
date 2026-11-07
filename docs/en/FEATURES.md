# R16.9 features and acceptance boundaries

[Installation](INSTALL.md) · [Validation](VALIDATION_R16_9.md)

Current host print workflow: [Start/End, protected pause, M600 and compatibility audit](../pl/PRINT_CONTROL.md).
This extends the earlier acceptance inventory below; hardware acceptance remains separate.

| Function | Owner / presentation | Evidence / boundary |
|---|---|---|
| Native XYZE, heaters, fans, PID, SAVE_CONFIG | Existing Klipper objects and Klipper menu | Native bindings, preserved calibration and FILEOUTPUT planning |
| Factory Z400/Z800 | Existing hardware identity reader before native configuration | Factory decoder and both synthetic hardware profiles; physical scale measurement remains separate |
| Autocalibration | Native M07; OLED and ZORTRAX_LEVEL | Original wizard ordering/math, bounded PC7 acquisition, explicit operator decisions |
| Ordinary Z homing | Native G28 adapter and five successive release references | 180°C minimum; actual HomingMove in modeled tests; physical acceptance pending |
| Heat the extruder | Native maintenance owner and ZORTRAX_HEAT | OEM 260/258 readiness and confirmation-to-off flow |
| Manual platform movement | Same native maintenance owner | OLED hold/release/freshness; finite Fluidd distance; genuine homed Z required |
| Interactive upper/lower fan test | Shared native fan session and four macros | Original 0/150 duty, entry/Back flow and 12 complete cold-menu frames; upper thermostat and MCU cooling have priority |
| Load / Unload | Native filament owner and matching macros | 240/238, confirmation-before-transport, nominal 130/110 mm, native calibrated E |
| Change during pause | Real native pause/file owner | 110 mm out / 150 mm in, one insertion confirmation, preserved pause and explicit Resume |
| English interface | Shared presenter and NVM-facing language policy | Old saved PL/FR/DE/ES choices cannot alter runtime text; release documents are English only |
| Original dialogs / sprites | Recovered text, 13-pixel font and existing sprite decoder | 110 original dialog frames plus 12 English fan-menu frames retained as evidence |
| Sleep mode / OLED transport | Existing frame/ACK and dim/off/wake controllers | Saved Enabled/Disabled choice uses the configured timing |
| Settings and Information | Shared OLED and Fluidd menu | Persistent choices, actual available printer data and GitHub Help |
| MCU supervision / offline cooling | Unchanged R14.5 code | Existing register-model and cooling tests |
| Host startup recovery | Existing bounded lifecycle policy | One permitted recovery attempt; no automatic old motion/heater resume |
| Models from physical SD | Read-only MCU SPI1, FAT16/FAT32, native Klippy worker | Text G-code and validated M300 1.3.1 Z-code subset |
| Legacy OEM job engine | Separate M02 workflow | Diagnostic configuration |

The first display remains the native Klipper status screen. The main groups
are Klipper, Zortrax M300 and Service / Tests. The Zortrax menu groups
Models, Maintenance, Material, Settings and Information in that order.
OLED menu lists use the same original font as Settings. The cursor points
left on Back, and Back in the main menu returns to the Klipper status screen.
Change is available from paused Print status. Fluidd
keeps Klipper / ZORTRAX M300 / TEST M300 categories and unrelated user settings.

Existing 2 µs STEP, native XY profile, Z limits, E rotation distance, PID,
sensor includes, acceleration and corner choices are preserved by the upgrade.
A known temporary commissioning Z30 envelope is migrated by the established
installer rule; other deliberate geometry, including Z315, is preserved.
No additional general G1 velocity cap is introduced. FILEOUTPUT planning at
300 mm/s and M220 150% does not measure physical F103 scheduling at that speed.

299 host tests and 16 actual Klippy FILEOUTPUT scenarios support software
integration. Electrical inputs and movement are modeled in the full procedure
tests. Follow [the supervised acceptance sequence](VALIDATION_R16_9.md) for
new contact homing, screw instructions, manual holds and material transport.
