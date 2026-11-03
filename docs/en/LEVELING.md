# Autocalibration and Z reference — R16.7

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
9. Measure center point 2. Show the original five-deviation diagram with
   millimeter values using the selected Z400/Z800 scale.
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

Ordinary G28 Z retains the agreed **180°C minimum**. It uses the configured
center, native coarse contact, then five successive contact/release reference
updates following 0x0800ab90 / 0x0800ac10. The final reference comes from the
**fifth release edge**, not an average of five values. Status reports the
method and five observations. Final clearance is 5 mm from the newly established
reference, without accumulation on repeated homing.

The M07 wizard's initial center contact is a different source routine,
0x0801456c. Its Y/X/center path does not call the ordinary five-update helper.
The host retains native coarse endstop acquisition for this initial home.
Setting `[probe] samples: 5` is not a substitute for either sequence.

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
