# R16 normal operations and acceptance

[Polski](../pl/FEATURES.md)

R16 consolidates the operator-confirmed native thermal/fan, XYZ, extruder,
OLED and host-link work. Earlier R15.7 sources still contained a 30 mm Z
commissioning envelope, 220C contact homing and a 60-second clearance gate.
R16 removes those normal-operation restrictions through an explicit, reversible
configuration migration. Earlier software PASS reports did not establish
physical high-speed performance.

| Function | Normal owner / presentation | Evidence |
|---|---|---|
| Heater regulation, PID, SAVE_CONFIG | Native Klipper; Klipper group | Operator reports + native bindings, PID preservation tests |
| Hotend/part fans | heater_fan / fan, Fluidd widgets and Klipper menu | Operator reports + native bindings |
| Offline/fault cooling | R14.5 MCU: local hotend thermostat, part fan off; invalid/critical state protective cooling | Existing 52 C cases and operator reports; no MCU policy change |
| RGB and buzzer | Existing OEM indicator observer and native output_pin | Operator reports; existing ownership retained |
| Display dim/off/wake | Existing display controller and OEM moon notice | Existing host regressions; no machine motion on screen wake |
| Disconnect/restart/waiting OLED | Existing MCU lease and host lifecycle | Startup/guard tests and operator reports |
| XYZ and calibrated E | Native Cartesian planner; Klipper controls | Operator reports; extrusion calibration is preserved |
| Homing | Native G28/probe; M300 contact location, minimum 180C and final 5 mm clearance | New unit and real Klippy FILEOUTPUT tests; repeat physical acceptance of this adapter |
| Factory Z400/Z800 | Read retained ID3 before configuration; shared native/M07 scale | 1792 C cases and synthetic HW04/HW05 real Klippy tests |
| OEM M03/M07/M08 procedures | Service / Tests and TEST M300 | Retained for continued process validation; not promoted by XYZ/thermal confirmation |

## Menu and Fluidd groups

The first OLED screen stays the native Klipper status screen. Click opens
Klipper / Zortrax M300 / Service / Tests. Back remains first; the existing
bounded scrolling and knob direction are retained, with no fixed title/version
rows consuming the menu area.

Klipper contains homing, movement, temperatures, native fan controls, PID and
print status/pause/resume. Zortrax M300 contains OEM settings and information.
Service / Tests contains diagnostics and unfinished OEM procedures, including
material, calibration and checked OEM print/SD views. A successful temperature
or manual extrusion check does not qualify every state of those workflows.

After installing and restarting the host, run setup_fluidd.py --apply. It
updates the categories Klipper, ZORTRAX M300 and TEST M300 through Moonraker,
keeps unrelated settings and macro visibility, and makes a rollback backup.
The browser may need a refresh. Macro comments alone do not create categories.

## Motion and timing

The shared installer/CI migration sets STEP to **0.000002 seconds (2 us)** on
XYZ/E, raises the native XY profile to at least 300 mm/s, Z to 25 mm/s and
Z acceleration to 50 mm/s². Existing XY acceleration, corner settings, calibrated
E rotation_distance, PID, sensor definitions and saved calibration text are
preserved. Only the recognized temporary Zmax=30 becomes usable Zmax=300;
other deliberate geometry is kept. No M220=150% rejection or extra G1 limiter
is installed. Native SET_VELOCITY_LIMIT remains available.

The official Zortrax Marlin M300_v5 configuration at commit
12b32a9a2eb69c070f69a6cb4dfbd1a3fa74da22 declares XY=300, Z=25 mm/s,
maximum accelerations 3000/3000/50/4000 and default print/travel acceleration
700 mm/s². Its mechanical Z maximum is 312 mm; this port uses the 300 mm usable
height when replacing the temporary 30 mm envelope, not that larger travel.
Reference: https://github.com/Zortrax3D/MarlinConfigurationsZortraxM200/blob/12b32a9a2eb69c070f69a6cb4dfbd1a3fa74da22/config/examples/Zortrax/M300_v5/Configuration.h

At 640 XY steps/mm, 300 mm/s requires 192000 STEP pulses/s on one axis;
a 300 mm/s diagonal needs roughly 271529 pulses/s combined. A 2 us pulse
setting is not a measurement of total MCU scheduling capacity. FILEOUTPUT
checks the real native planner at 300, M220=150 and ACCEL=3000, including heater,
fan and OLED commands; it does not execute those events on the F103.

## Printer acceptance of the new iteration

1. Verify STATUS, ZORTRAX_HARDWARE_STATUS and ZORTRAX_MOTION_STATUS. Check the
   detected factory variant, mode native and homing target 180C.
2. Check XY home without heating, then Z home and full XYZ. Repeat Z home:
   final clearance must remain 5 mm relative to freshly established contact,
   with no accumulated retreat or request for Z304.
3. Use Fluidd native heaters/fans, confirm RGB and local cooling/link recovery
   against the already tested behaviour. Retain native verify_heater and MCU
   fault protection.
4. With the head/bed physically clear and XY homed, TEST_M300_XY SPEED=200,
   then SPEED=250 and SPEED=300. The test moves XY only; it does not heat,
   home, move Z/E or change velocity/acceleration settings. Inspect motion,
   lost steps and timing under real load before accepting 300 mm/s.
5. Check screen dimming, moon/off, wake and category navigation. Keep M03/M07/M08
   acceptance in the TEST group while refining their procedures.

The release contains 131 host tests, 8 repository contracts, 6720 STEP guard
cases, 52 cooling cases, 1792 factory-decoder cases, startup/timer checks and
13 actual Klippy FILEOUTPUT scenarios. CI never flashes or operates a printer.
