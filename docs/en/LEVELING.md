# M07 leveling — R16.3 printer acceptance

[Installation](INSTALL.md) · [Polski](../pl/LEVELING.md)

R16.3 integrates the recovered M300 five-point/three-screw algorithm with R16
native motion and one OLED/Fluidd procedure view. The existing R14.5 MCU stays
compatible. Software tests exercise modeled boundaries, not a physical printer.

`PROBE_ACCURACY` is a separate Klipper command; it does not start M07 or its
screens. With position_min=0 and probe.z_offset=0 it can reach the zero endpoint
just before contact is sampled. A subsequent probe can then report contact
already active. The zero-margin model reproduces this case; that does not
by itself qualify the physical contact or wiring.

R16.2 also skipped native-mode M07 timers and the shared presenter, and its
calibration authority depended on the legacy M02 qualification flag. R16.3
uses an independent M07 profile while leaving M02/M03/M08 qualification separate.

Start from **Service / Tests → TEST: platform calibration**, the Fluidd
**TEST M300 → TEST_M300_LEVEL** macro, or:

```gcode
ZORTRAX_PROCEDURE_START OP=LEVEL TEMP=180
```

The common sequence is preparation → explicit confirmation → 180°C heating →
XYZ homing → corner measurements 0,1,4,3 → rear/front screw instructions and
confirmations with repeated measurement → center measurement → review →
separate save confirmation. Three samples per point use a 0.05 mm spread
threshold. The recovered coefficient, quarter-turn rounding and Z400/Z800
arithmetic are unchanged. The center remains an operator review result.

Console and Fluidd starts automatically open the current procedure on OLED.
Both surfaces use the same phase/token. The OEM atlas supplies preparation,
heating, probing, screw-specific adjustment, result and cancellation icons.
Old or duplicate confirmations cannot advance another phase.

The test profile is safe_z=5, probe_search_margin=1, approach_distance=6,
release_distance=1 and 180°C. After its own successful G28, M07 translates its
known measurement frame by 1 mm, allowing bounded native PC7 probing down to
1 mm below the contact reference. Measurements are translated back. Global
position_min=0, Z315, XY limits, PID and extrusion calibration are preserved.
Foreign movement is blocked only during the session; native owners and the
ordinary frame return after completion or idle cancellation. An interrupted
move faults and requires fresh homing after restart, with no partial save.

Saving records a complete observation/confirmation ledger in host NVM. It does
not alter probe.z_offset, PID or extrusion calibration, or create bed_mesh.
If contact remains active after an earlier probe and Z is still homed, retract
the bed by 2 mm positive Z and check QUERY_PROBE before starting. Active contact
is rejected without movement; do not extend the search after a missing-contact
fault without diagnosing its cause.

Physical acceptance must confirm synchronized screens, 180°C, homing, contact
locations and repeatability, correct screw/direction instructions, explicit
confirmation waits, remeasurement, review/save, restored frame, cancellation
and the following first layer.
