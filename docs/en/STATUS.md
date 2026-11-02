# Current status and evidence boundary

[Polski](../pl/STATUS.md)

This source snapshot carries MCU R14.5 and host R15.7. It preserves the existing
native Klipper owners and the R15.5 split-homing contract. R15.6 corrects the
menu regression, M11 action registration, startup contrast and OEM sleep notice.
R15.7 reads factory ID3 and selects Z=400/800 at startup. Configuration files
are preserved; the effective Z scale can change to match the factory revision.
See [Hardware variants](HARDWARE_VARIANTS.md). No new speed or thermal limits are installed.

The ordinary status screen, transport, renderer and encoder remain the existing
implementations. The original moon is a 50×50 one-frame resource, descriptor
0x0801D908 from stock M300 1.3.1. The exact English text is Entering sleep mode,
at 0x080266F0. Entry routine 0x08015FC8 references that text and the moon, then
waits 10,000 firmware ticks before the physical sleep routine. The display
adaptation uses an explicit ten-second acknowledged notice. It does not copy
the original wake-up bed target of 70°C or other actuator side effects.

The public checks cover 92 host tests, 8 repository contracts, 6,720 STEP cases,
52 autonomous-cooling cases, protected pin rejections, guard snapshots, startup
epochs, periodic timer deadlines and native heater verification. Real Klippy
FILEOUTPUT checks nine scenarios using the fresh dictionary. Results are
software evidence, not physical UART, electrical timing or thermal measurements.

Offline cooling stays in the MCU: hotend approximately 50°C on / 45°C off,
part fan off, invalid/critical state emergency cooling. The live host heater_fan
policy remains positive heater target OR temperature above its threshold.

Still open in this historical motion branch:

- The R15.5 test example uses Z rotation_distance=8 and temporary Zmax=30.
  Factory selection now resolves the OEM variant; physical distance and
  full travel still need measurement.
- Its staged Z speed/acceleration and clearance qualification remain.
- It contains 220°C homing rather than the later requested 180°C.
- Absolute hotend sensor calibration and simultaneous full-load timing
  require physical measurements.
- Historical LAB M03/M07/M08 audits do not qualify every workflow in the
  current native branch.
- Inventure is a separate F207/CoreXY project; binaries are not interchangeable.

tests/fixtures/printer_r15_5_test.cfg is solely a synthetic CI input. It is not
installed or shipped as a replacement printer.cfg. The current user's values
are preserved by the host update.
