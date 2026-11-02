# Current status — R16 test iteration

[Polski](../pl/STATUS.md) · [Feature status and acceptance](FEATURES.md)

MCU R14.5 + host R16.3, pinned Klipper ee2c6fb6b00b2b5d097ef70d0868df7d74943b51.
The operator reports native thermal/fan, XYZ/E, OLED and link work as confirmed.
R16 consolidates those paths under normal controls and keeps unfinished OEM
procedures separate. It replaces the older commissioning homing adapter with
native G28/probe plus the M300 contact location, 180C minimum and final 5 mm.
Repeated homing no longer adds clearance to a previous Z299 coordinate.

Normal motion has no 60-second declaration gate, Z30 envelope or per-G1
resource wrapper. Native Cartesian bounds, verify_heater, cold-extrusion
protection, MCU guard and independent cooling remain. The factory ID3
Z400/Z800 selection remains. PID and extruder calibration text are preserved.

OLED dim/off/wake and the original moon/Entering sleep mode remain unchanged.
Device idle_timeout remains the existing native setting. Screen sleep does
not imply restoration of heater targets or motor coordinates.

Software checks cover 131 host tests, 8 repository contracts, 6720 STEP cases,
52 cooling cases, 1792 factory-decoder cases, startup/timer checks and 13 real
Klippy FILEOUTPUT scenarios. Those include 180C XYZ/repeated Z homing, native
300 mm/s planning, M220=150%, ACCEL=3000 and Z299/Z300 boundaries.

Remaining acceptance: repeat the changed homing on the physical printer;
measure high-speed/full-load timing and sensor accuracy; validate complete
M03/M07/M08 procedures separately. A 2 us pulse setting or FILEOUTPUT PASS
is not a hardware measurement at 300 mm/s. Inventure remains a separate F207
project; its files/geometry are not installed here.

R16.3 adds [host-start connection recovery](CONNECTION.md), using one native
reset for an old session/heartbeat latch. Other fault codes require explicit
recovery. Tests exercise actual native restart/configuration helpers with
simulated guard replies. The service/Orange Pi reboot still needs acceptance
on the printer.

Operator report, 2026-11-02: HW05/Z400, dimming/moon, and reaching Z300 work.
A factory decode does not replace physical scale measurement; status still
explicitly reports physical_scale_measured=false.
