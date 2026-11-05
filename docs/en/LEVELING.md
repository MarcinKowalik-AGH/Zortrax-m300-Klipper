# Autocalibration and Z reference — R16.12

[Maintenance / Material](MAINTENANCE_MATERIAL.md) · [Validation](VALIDATION_R16_7.md)

Autocalibration is a five-point contact procedure with manual adjustment of
three screws. It does not invoke BED_MESH_CALIBRATE or install a height mesh.
The OEM application and its recovered instruction model are the source of
the ordering, tolerances, coefficient, wording and original graphics.

## Five points

| Point | X, mm | Y, mm |
|---:|---:|---:|
| 0 | 269 | 44 |
| 1 | 35 | 44 |
| 2 | 150 | 158 |
| 3 | 269 | 275 |
| 4 | 35 | 275 |

Firmware functions 0x08008174 / 0x080159a0 generate one pair of integer XY
offsets in [-3, 3] for a calibration session. R16.6 uses that recovered LCG
and applies a common offset to the five nominal points and initial center.
The host seeds a session from its monotonic clock rather than copying MCU
SysTick state. Status and committed geometry expose the actual offset.
Every resulting point is checked against native bounds before actuation.

The OEM point routine (0x0800DD28 in firmware 1.3.1) sets F6000 for the
horizontal move, equivalent to 100 mm/s. The native M07 default requests
100 mm/s between points, subject to the Klipper planner limits. The host
installer migrates the previous 10 mm/s setting and preserves other explicit
XY settings. Z lift, contact approach and release use their separate speeds.
`ZORTRAX_CALIBRATION_STATUS` reports all four requested speeds in mm/s.

## Wizard

1. Start Maintenance → Autocalibration or `ZORTRAX_LEVEL`. Require an idle
   native print, healthy connector/MCU and fresh native temperature status,
   empty motion queue and an initially open PC7 contact.
2. Heat the nozzle to 260°C. Readiness is a lower threshold of 258°C, with the
   configured stable-readiness interval. Show the original hot-head warning.
3. After its confirmation, home **Y, then X**, move to the session center
   and establish genuine contact Z through native endstop homing.
4. Show the original instruction to tighten all three knobs. Wait for an
   explicit button/Fluidd confirmation before point measurements.
5. Measure 0 → 1 → 4 → 3 and establish the fixed reference from those corners.
6. Assess rear left (point 4), then rear right (point 3). If both need changes,
   issue both instructions from the same pair of measurements.
7. After confirmation, measure the rear pair, starting 3 → 4 after the first
   pair of instructions. Subsequent pair order follows the recovered cursor.
8. Compute front correction from the signed, truncating average of deviations
   at 0 and 1. Confirm the instruction and remeasure the front pair.
9. Measure center point 2. Show the five-deviation diagram with millimeter
   values using the selected Z400/Z800 scale. The
   [M300 Fluidd build](FLUIDD_M300.md) draws those same values in the same
   orientation inside the result prompt.
10. Heating is off in result review. Confirm the complete result to commit the
    observation ledger, close the dialog and return to Maintenance. A failed,
    cancelled or incomplete measurement cannot publish a new height/result.

The observation is a host NVM record, not a live coordinate/mesh correction.
The pure measurement ledger and all operator confirmations are replayed before
accepting the stored result. The previously valid record survives failures.

| Element | Accepted deviation |
|---|---|
| Rear left and rear right | -0.20 ≤ delta ≤ +0.10 mm |
| Front, signed average | -0.20 < delta < +0.10 mm |
| Center | Report only by default; an explicit optional port limit is identified separately |

The reference is the maximum initial corner raw value and remains fixed for
the session. Negative odd front sums truncate toward zero. Turn count is
`ceil((abs(delta_mm) / coefficient) * 4) / 4`, where coefficient is the actual
binary32 OEM literal 0.5099999904632568, not an ideal decimal replacement.
Directions, paired instructions and quarter-turn boundaries are reproduced
for both 400 and 800 counts/mm. The shared limit is 40 adjustment instructions.
Error #041 represents calibration failure; #042 represents pad probing failure.

## Ordinary Z homing is a separate routine

Ordinary G28 Z waits for a valid reading of **at least 180°C** by default and
preserves a higher active nozzle setpoint. A nozzle already at or above the
homing minimum can proceed while heating or cooling. It uses the configured
center, native coarse contact, then five successive contact/release reference
updates following 0x0800ab90 / 0x0800ac10. The final reference comes from the
**fifth release edge**, not an average of five values. Status reports the
method and five observations. Final clearance is 5 mm from the newly established
reference, without accumulation on repeated homing.

At the contact stage, the nozzle may read up to 5°C below the homing minimum
(175°C with the default minimum), including with a higher active setpoint. An
absent temperature reading or a changed setpoint aborts the reference.
`z_home_temperature_tolerance` in `[m300_motion]` accepts 0.5–5°C.

The M07 wizard's initial center contact is a different source routine,
0x0801456c. Its Y/X/center path does not call the ordinary five-update helper.
The host retains native coarse endstop acquisition for this initial home.
Setting `[probe] samples: 5` is not a substitute for either sequence.

## Homing speed comparison with 1.3.1

The verified 1.3.1 application homes Y before X in both its normal dispatcher
(0x0800B4CC) and M07. The R16.12 host now uses that order whenever both are
selected. The normal contact-position traverse uses the configured
`home_travel_speed`. Its default is 50 mm/s and is independent of the
100 mm/s M07 point-to-point travel.

| Phase | Firmware 1.3.1 binary | Klipper values in the supplied printer log |
|---|---|---|
| X and Y limit seek | 265 busy-loop counts per timer start (0x0800B504 / 0x0800B588). One limit seek per axis. | 30 mm/s seek, 10 mm/s retract, 15 mm/s second seek |
| Ordinary coarse Z contact | 1555 scaled busy-loop counts (0x0800B608) | 5 mm/s seek, 5 mm/s retract, 2.5 mm/s second seek |
| M07 coarse center contact | 1600 scaled busy-loop counts (0x0801456C) | Same native Z rail speeds |
| Ordinary precise Z | 21550 scaled counts for approach, 11550 for release (0x0800AC10) | 0.5 mm/s for both |
| Ordinary final Z clearance | 2555 scaled counts for the 5 mm segments (0x0800B608) | 5 mm/s default |
| M07 horizontal motion between measurement points | F6000 (0x0800DD28) | 100 mm/s default |

The Z helper at 0x0801820C scales loop counts by 800 divided by the active
Z scale. The XY and Z helpers start the step timer and then spin in
0x080192A2. The counts are CPU iterations. Actual pulse spacing also depends
on timer behavior, branch/flash timing and interrupt service. The audit does
not establish equal physical speeds in the homing rows. Use step pulse
timing or measured travel on a stock board before changing those setpoints.
`ZORTRAX_MOTION_STATUS` reports the installed rail speeds, Z cap and contact
traverse, refinement and clearance speeds.

Z homing reads PC7 before preheat, before XY motion and at the Z seek. A
closed contact allows one positive-Z retreat per homing session, capped at
1 mm and 1 mm/s and limited by the native Z travel range. When Z is unhomed,
Klipper clears the temporary frame used to queue this move before checking
PC7 again. Native homing continues after an open reading and establishes
the Z reference through the normal contact sequence. A contact that stays
closed or closes again after the retreat stops the session with `NO_RELEASE`.

The default idle script shuts down heaters, releases X/Y/E and keeps an
already energized Z motor. It clears the X/Y references. The installer
preserves custom idle scripts. Explicit M84/M18, restart, emergency or MCU
shutdown and power loss can still release the platform. In the supplied
`Timer too close` trace, the first Z movement coincided with late step
scheduling and increased UART retransmissions. The physical cause still
needs a repeat run with a fresh Klippy log.

## Bounded native acquisition

All PC7 movement uses the existing MCU endstop and native HomingMove. A shared
private capability permits only its expected target/speed and reconciles the
real stepper position. It cannot reset unrelated XYZ/E or grant arbitrary
movement. The probe must own exactly the one native Z stepper.

The M07 session translates the freshly homed measurement frame by the existing
1 mm search margin, without changing global limits. Search and release have
finite endpoints and deadlines. Each sample detects release, completes the
full configured retreat and verifies stable opening. A no-contact, no-release,
no-motion, timeout, stale token or shutdown cannot become a valid observation.

Ordinary five-update homing uses a 5 mm maximum approach, 1 mm release search,
30-second per-cycle deadline and full stable retreat after each opening.
The source's extra 100-count retreat is covered; the port does not copy its
unbounded release loop or blind final return into the electrical edge. It
keeps clearance above the fifth release reference before the final 5 mm lift.
An error requests shutdown and does not assign a successful new reference.

M07's configured repeated samples/median and limited spread retries are
additional port policies. Native coarse homing and metric speeds are also
adaptations; no claim of original GPIO timing or physical repeatability is
made. FILEOUTPUT records zero physical refinement contacts explicitly.

## Software evidence

The reproduction script executes the original wizard for convergence,
non-convergence and initial pad failure; it also executes all five original Z
contact/release bodies for both hardware scales. Separate native tests use
the pinned HomingMove with modeled electrical/stepper boundaries. The original
renderer matches 110 full reference frames; runtime uses the English subset.
20,002 original quarter-turn vectors remain covered. Physical acceptance
remains open; follow [the test sequence](VALIDATION_R16_7.md).

## Optional Klipper pad mesh

Use OEM Autocalibration for the three screws. The optional M300 pad mesh
measures residual height differences for native Klipper Z compensation.
It uses the existing PC7 nozzle contact and Klipper's ProbePointsHelper.
The operator can use this option without replacing the MCU firmware.

The measured corner squares are 60 × 60 mm and the center square is 50 × 50 mm.
The default inset is 5 mm from each edge. This puts the rearmost samples at
Y300 instead of Y304 with a 1 mm inset. The procedure uses the fixed nominal
OEM points as pad centers; verify this alignment on the actual platform.
The randomized offset used for OEM Autocalibration is not used for the mesh.
Each pad contributes its center and four inset corners:

| Pad | Center X, Y (mm) | Corner X coordinates (mm) | Corner Y coordinates (mm) |
| --- | --- | --- | --- |
| Front right | 269, 44 | 244, 294 | 19, 69 |
| Front left | 35, 44 | 10, 60 | 19, 69 |
| Center | 150, 158 | 130, 170 | 138, 178 |
| Rear right | 269, 275 | 244, 294 | 250, 300 |
| Rear left | 35, 275 | 10, 60 | 250, 300 |

Add these sections to the existing printer configuration when ready to test
the probe. Do not duplicate an existing section. Before moving, run
`ZORTRAX_PAD_MESH_STATUS` to review all 25 positions and confirm that each one
lies on conductive metal with nozzle clearance. The configuration is opt-in;
it does not increase the configured axis travel limits.

~~~ini
[bed_mesh]
mesh_min: 10, 19
mesh_max: 294, 300
probe_count: 3, 3
mesh_pps: 0, 0

[m300_pad_mesh]
corner_pad_width: 60.0
center_pad_width: 50.0
edge_margin: 5.0
~~~

On this configuration `BED_MESH_CALIBRATE` uses the five pad centers and
four inset corners of each pad. Rectangular, adaptive and manual probing
options are rejected by the pad adapter. It uses three native contacts per
position (at least 75 contacts), their median and a bounded Z search. The
native repeat tolerance is 0.05 mm at each position. The Z coordinate
frame is restored after the measurement. A failed search invalidates the
Z reference and the previous saved mesh remains available.

For the first supervised test, clean the nozzle and pads and confirm that the
pads represent the printing surface. Heat the bed to the first-layer
temperature and stabilize the clean nozzle at 180 °C or above. Use the same
temperatures for later comparisons. Run the commands individually and turn
off the heaters if calibration fails. Example for a 60 °C bed:

~~~gcode
BED_MESH_CLEAR
M190 S60
M109 S185
G28
BED_MESH_CALIBRATE PROFILE=m300_pads
ZORTRAX_PAD_MESH_STATUS
TURN_OFF_HEATERS
~~~

The status command reports all 25 heights, each pad's median and its spread.
All 25 heights contribute to the compensation. A difference over 0.50 mm
between any two positions rejects the mesh by default. A sloped 60 mm pad can
have a real spread above 0.05 mm, so pad spread is reported separately from
repeatability. An optional `max_pad_spread` can impose an additional limit.

The interpolation joins the 25 measured positions into 36 triangles with
continuous piecewise-linear heights. This preserves a plane, uses each
measurement and avoids polynomial overshoot. The surface is resampled to a
61 × 61 native Klipper grid (about 4.7 mm spacing), normalized to zero at the
center contact. Native Bed Mesh handles profile storage, visualization and
motion compensation. The regular-grid conversion approximates triangle
edges; the 3,721 grid values are interpolated, not additional measurements.
Curvature in the unmeasured gaps between the five squares remains unknown.
Keep the first print inside the measured rectangle X10–294, Y19–300.
Outside that rectangle Klipper clamps the correction to the mesh edge.

Existing `pad_width` configurations retain their common width and 1 mm default
inset. For the measured 60/50 mm geometry, replace that legacy option with the
two explicit widths and 5 mm inset shown above, then measure a fresh profile.

A successful run leaves a profile in the current session. Use `SAVE_CONFIG`
to keep it across restarts. After homing in the print-start sequence, use
`BED_MESH_PROFILE LOAD=m300_pads` to activate the profile. Use
`BED_MESH_CLEAR` before OEM Autocalibration and after completing the print.
Measure again after moving the leveling screws or changing the build surface.
