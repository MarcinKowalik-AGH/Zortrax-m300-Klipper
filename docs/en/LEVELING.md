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
   empty motion queue. Establish 5 mm Z clearance before heating or XY motion,
   then require an open PC7 contact.
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

Native G28, OEM Autocalibration and pad mesh share an initial Z-only clearance
check before heating or XY motion, including when PC7 is already open after
an interrupted probe. With unknown Z, the platform retreats by at least 5 mm
at the configured lift speed using a temporary native coordinate frame;
Klipper clears that temporary homing state before proceeding. A valid Z
reference already at 5 mm clearance needs no additional retreat. Logical Z
travel limits are unchanged; insufficient room aborts before XY. This does
not establish an absolute Z reference: genuine native contact homing does.
An open PC7 reading is required after the move and rechecked before XY and
the Z seek. Persistent or renewed contact stops the session with `NO_RELEASE`.
An unchanged position can reuse the verified clearance during nested homing
instead of adding another 5 mm. Restart or disabling the Z motor invalidates
that evidence; disabling Z also clears its homing reference.

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

The operator corrected all five contact squares to **50 × 50 mm**, with
configured travel **X0–300 / Y0–305**. The earlier 60 mm corner-pad assumption
is superseded. The five configured centers remain independently adjustable;
changing a pad's width never moves its center. Defaults retain X30/290,
Y30/290 and center X160/Y160 from the earlier layout. Those centers must
match the physical metal: pad width and axis limits alone do not locate them.
The randomized OEM Autocalibration offset is not used here.

Each pad contributes its center and four corners inset 5 mm from the metal
edge. `FIT_TRAVEL=1` (the default) clips only unreachable corners to the
reachable part of that same square, with a 1 mm margin inside configured
axis limits. It preserves all five centers and all 25 distinct points.
For the stated centers and X300/Y305 limits, the prepared plan is:

| Pad | Center X, Y (mm) | Corner X coordinates (mm) | Corner Y coordinates (mm) |
| --- | --- | --- | --- |
| Front right | 290, 30 | 270, 299 | 10, 50 |
| Front left | 30, 30 | 10, 50 | 10, 50 |
| Center | 160, 160 | 140, 180 | 140, 180 |
| Rear right | 290, 290 | 270, 299 | 270, 304 |
| Rear left | 30, 290 | 10, 50 | 270, 304 |

Add these sections to the existing printer configuration when ready to test
the probe. Do not duplicate an existing section. Before moving, run
`ZORTRAX_BED_MESH PREVIEW=1` to prepare and review all 25 positions and confirm that each one
lies on conductive metal with nozzle clearance. The configuration is opt-in;
it does not increase the configured axis travel limits. A center outside
the reachable region, a collapsed contact rectangle or invalid pad topology
is rejected before movement. `FIT_TRAVEL=0` requests the exact nominal
corners and rejects any of them outside the configured travel.

On an older installed host without travel fitting, this explicit command
provides the conservative plan confirmed by the operator:

~~~gcode
ZORTRAX_BED_MESH CORNER_PAD_WIDTH=50 CENTER_PAD_WIDTH=50 EDGE_MARGIN=16 PREVIEW=1
~~~

It gives X21–299 / Y21–299 and samples only 18 × 18 mm around each pad
center. On the old host, pass the same three geometry parameters when
measuring; its macro otherwise restores stale defaults. The updated macro
forwards only parameters actually supplied, so it respects configured values
and the most recent preview instead of overwriting them with 60 mm literals.

`PREVIEW=1` and `ZORTRAX_PAD_MESH_STATUS` report configured travel, effective
bounds, all actual points and `adjusted_points` with requested/actual corner
coordinates. No homing, heating or movement occurs in a preview. Review it
again after changing a center, size or axis limit. Limits confirm reachability;
the operator must still confirm conductive metal at every position.

~~~ini
[bed_mesh]
mesh_min: 10, 10
mesh_max: 299, 304
probe_count: 3, 3
mesh_pps: 0, 0

[m300_pad_mesh]
corner_pad_width: 50.0
center_pad_width: 50.0
edge_margin: 5.0
fit_travel: True
travel_margin: 1.0
hotend_temperature: 180.0
bed_temperature: 60.0
heat_timeout: 1800.0
~~~

The `ZORTRAX_BED_MESH` macro appears in the Fluidd **ZORTRAX M300** group.
The M300 Fluidd build opens **Tune** once an actual measurement passes preflight
and starts preparation, including starts from the console. It preserves the selected
printer connection. A geometry-only preview or preflight refusal does not change
the page, and later manual navigation is respected. Tune shows heating/homing phases and point progress,
the five pad summaries and the result of the current attempt.
The physical OLED automatically opens its Bed mesh page for the same run,
shows preparation/probing progress with the four-frame five-pad animation,
and returns to the invoking screen after success. An internal G28 cannot
replace that parent view. Back leaves the screen while measurement continues;
manual navigation is respected. A rejected measurement stays visible for review.
Its parameter fields allow individual corrections without editing Python:

| Parameter | Default | Meaning |
| --- | --- | --- |
| `FRONT_RIGHT_X`, `FRONT_RIGHT_Y` | 290, 30 | Front-right pad center |
| `FRONT_LEFT_X`, `FRONT_LEFT_Y` | 30, 30 | Front-left pad center |
| `CENTER_X`, `CENTER_Y` | 160, 160 | Center pad center |
| `REAR_RIGHT_X`, `REAR_RIGHT_Y` | 290, 290 | Rear-right pad center |
| `REAR_LEFT_X`, `REAR_LEFT_Y` | 30, 290 | Rear-left pad center |
| `CORNER_PAD_WIDTH` | 50 | Width of each corner square, mm |
| `CENTER_PAD_WIDTH` | 50 | Width of the center square, mm |
| `EDGE_MARGIN` | 5 | Distance inward from every physical metal edge, mm; 0 is allowed |
| `PROFILE` | `m300_pads` | Native profile name |
| `PREVIEW` | 0 | Set to 1 to show geometry without homing, heating or moving |
| `FIT_TRAVEL` | 1 | Clip corners to the reachable part of their own pad |
| `TRAVEL_MARGIN` | 1 | Margin inside XY travel when fitting, 0–5 mm; 0 retains native X0/Y0 |
| `HOTEND_TEMP` | Minimum 180 | Minimum nozzle target; a hotter working temperature is retained |
| `BED_TEMP` | Active bed target, otherwise 60 | Bed temperature for the measurement, °C |

Clicking the **macro name** in Fluidd sends `ZORTRAX_BED_MESH` without arguments.
It uses `[m300_pad_mesh]` and current command/preview geometry. To reproduce an
explicit console command, expand the arrow, fill the fields and press **Send**.
For the conservative operator plan set `CORNER_PAD_WIDTH=50`,
`CENTER_PAD_WIDTH=50`, `EDGE_MARGIN=16` and `BED_TEMP=60`. Empty fields inherit
configuration; they do not mean zero. The default margin is 5 mm, so an empty
quick button can use a different 25-point plan from that explicit 16 mm command.
The updated macro places parameter references on separate Jinja lines so stock
Fluidd exposes every field, then emits exactly one native calibration command.

For example, preview a 1 mm front-left X correction and a different center:

~~~gcode
ZORTRAX_BED_MESH PREVIEW=1 FRONT_LEFT_X=31 CENTER_X=159.5 CENTER_Y=160
~~~

Run the same macro with the same corrections and `PREVIEW=0` to measure.
The macro and direct native command use the same geometry. To retain a
correction across restart, set its lowercase name in `[m300_pad_mesh]` (for
example `front_left_x: 31`). Omitted macro fields no longer override these
settings. Unsaved command overrides last until restart. The installer preserves
all explicit pad dimensions and centers and updates the recognized old
forwarding macro without replacing a configured 60/50 mm layout with 50/50.
The saved native mesh profile retains the resulting surface.

### Measured contact rectangles

Native X0/Y0 is a nozzle position after homing, not the physical edge of the
plate. Initial estimates based on 60 mm squares and 15 mm offsets have been
superseded by the operator's measured reachable contact bounds:

| Pad | Contact X range, mm | Contact Y range, mm | Configured interior sample X/Y |
| --- | --- | --- | --- |
| Home-side / front left | 0..43 | 0..51 | 15, 15 |
| Front right | 260..300 | 0..51 | 285, 15 |
| Middle | 125..175 | 125..175 | 150, 150 |
| Rear right | 260..300 | 262..305 | 285, 290 |
| Rear left | 0..43 | 260..305 | 15, 290 |

The middle rectangle follows the previously specified 50 mm middle pad
centered at X150/Y150. All five fields and interior samples remain editable.
Different X/Y lengths and the 2 mm difference between the two rear fields
are represented directly; no shared square width is inferred.

Revision `0.13.16.20-PAD-CONTACT-MAP` adds one optional bound tuple per pad,
ordered **X_MIN,Y_MIN,X_MAX,Y_MAX**. Add these options to the existing
`[m300_pad_mesh]` section:

~~~ini
front_left_bounds: 0, 0, 43, 51
front_right_bounds: 260, 0, 300, 51
center_bounds: 125, 125, 175, 175
rear_left_bounds: 0, 260, 43, 305
rear_right_bounds: 260, 262, 300, 305
edge_margin: 0
fit_travel: True
travel_margin: 0
~~~

Each explicit tuple defines the four requested contact corners. It overrides
that pad's legacy square width and `EDGE_MARGIN`, without moving the configured
interior sample (`FRONT_LEFT_X/Y`, etc.). The interior sample must be strictly
inside the rectangle. To inset one edge by 2 mm, edit that bound directly;
for example, change front-left X_MAX from 43 to 41 while retaining X_MIN=0.
No second automatic metal inset is added. Native XY limits and optional
`TRAVEL_MARGIN` fitting still apply.

Macro fields use the same names in uppercase. For example:

~~~gcode
ZORTRAX_BED_MESH FRONT_LEFT_BOUNDS=0,0,43,51 FRONT_RIGHT_BOUNDS=260,0,300,51 CENTER_BOUNDS=125,125,175,175 REAR_LEFT_BOUNDS=0,260,43,305 REAR_RIGHT_BOUNDS=260,262,300,305 EDGE_MARGIN=0 TRAVEL_MARGIN=0 PREVIEW=1
~~~

`PREVIEW=1` updates the 25-point plan and Tune's top view without heating,
homing or moving. Review all positions before measuring. Explicit bounds
are optional; `FRONT_LEFT_BOUNDS=AUTO` returns that pad to its configured
square width/inset in the current session. Remove its config option or use
`front_left_bounds: AUTO` to keep that choice across restart. The installer
preserves custom bounds and migrates the preceding standard forwarding macro
to expose the five new fields, including zero coordinates and comma-separated
values. Quoted macro values may contain spaces after commas.

The top view draws the configured contact fields, completed/current probe
points and the live XY nozzle location from the existing Moonraker status
subscription. X increases rightwards and Y downwards. Unhomed or unavailable
XY positions are hidden; the queued movement endpoint is not used as a live
position. The view sends no movement commands or additional MCU polling.
The geometric interior sample of a pad remains separate from the native
homing contact location (normally X150/Y158), which defines the mesh Z datum.

On this configuration `BED_MESH_CALIBRATE` uses the five pad centers and
four corners of each configured contact area. Arbitrary regular-grid, adaptive
and manual probing options are rejected by the pad adapter. It uses three native contacts per
position (at least 75 contacts), their median and a bounded Z search. The
native repeat tolerance is 0.05 mm at each position. The Z coordinate
frame is restored after the measurement. A failed search invalidates the
Z reference and the previous saved mesh remains available.

For the first supervised test, clean the nozzle and pads and confirm that the
pads represent the printing surface. One macro now prepares the full native
measurement. It validates geometry, native heater limits, ownership and fresh
MCU status before changing outputs; clears an active compensation mesh while
retaining its saved profile; establishes the shared 5 mm Z clearance before
XY; starts both native heaters together; waits for stable temperatures; and
performs missing native homing before probing. A persistent closed PC7 or
insufficient logical Z travel aborts before a horizontal move.

The nozzle setting is a **minimum**, normally 180 °C. An active 240 °C target
is retained. An already-hot idle nozzle is held at its current temperature,
including after G28 restores its former zero target. A nozzle significantly
hotter than a lower target is held rather than cooled to 180 °C; ordinary PID
overshoot within 3 °C retains its working target. The configured native homing
minimum also applies. The existing bed target is retained unless `BED_TEMP`
overrides it; an off bed uses `bed_temperature` (60 °C by default).

Use the same temperatures for later comparisons. For example, the operator's
conservative 25-point plan with a 60 °C bed:

~~~gcode
ZORTRAX_BED_MESH CORNER_PAD_WIDTH=50 CENTER_PAD_WIDTH=50 EDGE_MARGIN=16 BED_TEMP=60
~~~

To repeat an earlier measurement made with a 185 °C nozzle, add
`HOTEND_TEMP=185`. This remains a minimum and does not cool a hotter nozzle.
The native XYZ path is used when multiple axis references are missing; a
missing XY or Z reference alone uses its corresponding native homing path.
If heating changes the bed or nozzle temperature significantly, Z is renewed
after stabilization even if it was previously homed. A closed PC7 before an
XY-only home selects the native XYZ release path. Failure to establish XYZ
prevents any pad probing. Native contact stopping, release checks, five
precision Z references and physical motion limits remain in effect.

Preparation requires both readings within 3 °C of their unchanged targets for
three seconds, with a bounded `heat_timeout` (default 1800 seconds). A target
change, lost authority, timeout, disconnect or shutdown aborts preparation;
failed runs turn both heater targets off. Successful completion restores the
targets present before the run, as ordinary G28 does: a procedure that starts
with both targets off turns them off again automatically. A prior printing
setpoint is restored, and an explicit heater-off request is not overwritten.
Native automatic hotend cooling continues to follow measured temperature
(50 °C on, 45 °C off). Read the result after the measurement:

~~~gcode
ZORTRAX_PAD_MESH_STATUS
~~~

The current default travel fitting supports the confirmed X300/Y305 limits.
On success, Tune previews the newly stored native profile without activating
compensation. The chart is explicitly labeled as an interpolated preview from
25 contact positions; the ordinary active chart takes precedence after loading
a profile. Before a print, load the
result with `BED_MESH_PROFILE LOAD=m300_pads`; the measurement intentionally
leaves compensation inactive. The **Save configuration** button is available
only for a successfully generated profile from the current attempt while idle.
`SAVE_CONFIG` stores that profile and restarts Klipper, so a temporary
Shutdown/Disconnect at that point is the expected restart.

The status command reports all 25 heights, each pad's median and its spread.
All 25 heights contribute to the compensation. A difference over 0.50 mm
between any two positions rejects the mesh by default. A sloped 60 mm pad can
have a real spread above 0.05 mm, so pad spread is reported separately from
repeatability. An optional `max_pad_spread` can impose an additional limit.
An excessive span produces a detailed error with the measured span and the
configured limit. Tune retains the rejected attempt's pad diagnostics, without
offering a new profile or Save button. The previous accepted profile is left
unchanged. `SAVE_CONFIG` after a failed measurement does not make it valid or
create the rejected profile. Run OEM `ZORTRAX_LEVEL` to adjust the screws,
then repeat the mesh at the same stabilized temperatures. A span rejection
alone does not establish whether the remaining difference is tilt or curvature.
The reported 75-contact case is covered by regression data: median heights span
0.8025 mm against the 0.5000 mm limit, although the largest three-repeat spread
at one location is only 0.0175 mm. These are different checks; the limit is not
automatically increased to accept the measurement.

The interpolation joins the 25 measured positions into 36 triangles with
continuous piecewise-linear heights. This preserves a plane, uses each
measurement and avoids polynomial overshoot. The surface is resampled to a
61 × 61 native Klipper grid, normalized to zero at the
native homing XY position (normally X150, Y158). Correcting a pad's geometric
center does not change that Z datum. Native Bed Mesh handles profile storage, visualization and
motion compensation. The regular-grid conversion approximates triangle
edges; the 3,721 grid values are interpolated, not additional measurements.
Curvature in the unmeasured gaps between the five squares remains unknown.
The current default example covers X10–299 / Y10–304. If individual
pad corrections make the outside edges uneven, the mesh rectangle is reduced
to stay inside both pads along each side.
Outside that rectangle Klipper clamps the correction to the mesh edge.

Existing `pad_width` configurations retain their common width, 1 mm default
inset and legacy OEM centers when the direct native command is used. For the
measured layout, remove `pad_width`, use the explicit widths and 5 mm inset
shown above, and measure a fresh profile. The macro preserves these configured
values and accepts explicit individual overrides.

A successful run leaves a profile in the current session. Use `SAVE_CONFIG`
to keep it across restarts. After homing in the print-start sequence, use
`BED_MESH_PROFILE LOAD=m300_pads` to activate the profile. Use
`BED_MESH_CLEAR` before OEM Autocalibration and after completing the print.
Measure again after moving the leveling screws or changing the build surface.
