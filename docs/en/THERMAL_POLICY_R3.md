# M300 host R3 — target-temperature policy

The host-only R3 work remains in this repository. OrcaSlicer profiles and slicing tests have moved to [Zortrax-m300-Orca-Slicer](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Orca-Slicer). Importing a slicer profile does not install or update this host.

The `m300_temperature_policy` module is loaded by `m300_mcu`. It checks native heater `set_temp` and `alter_target`, and the M300 operation entry points use the same target limits. A bed target above **105 C** is rejected. The existing sensor shutdown ceiling **120 C** is separate and is not raised or disguised. A stricter configured heater ceiling is respected. The existing hotend ceiling **270 C**, sensor conversions, PWM, MCU guards, PID values and motion settings are unchanged by this policy. OLED includes 105 C and excludes higher bed targets; a generic Fluidd component may still display the sensor ceiling, but the host refuses excessive requests.

After a reviewed, idle-printer host installation, use `ZORTRAX_TEMPERATURE_LIMITS` to inspect requested versus sensor shutdown limits without heating. Expected defaults are target limits extruder 270 / bed 105, sensor ceilings extruder 270 / bed 120. Zero-temperature/off commands remain available.

Micro Swiss M2580-04 preparation does not establish that a retrofit is installed or calibrated and does not justify a higher temperature ceiling or a universal temperature offset. Hotend replacement requires supervised mechanical, sensor, cooling, PID and extrusion checks. No physical qualification was performed by this repository split.

`START_PRINT`, `END_PRINT`, parser save/restore, thermal-policy implementation and 756 host regression tests remain here. The slicer independently emits M83 and per-filament PA; its delivered PA=0 is neutral pending measurement. Host tests do not require the Orca profile repository or an Orca binary.

The old combined generator has been removed after its edits were committed. Maintain the actual host sources directly; do not regenerate slicer assets in this repository. Historical source and test evidence remain reachable through the pre-split commits and PR #14.
