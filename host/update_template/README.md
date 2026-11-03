# M300 host R16.7 — validated OEM procedures, English only

[Install](docs/en/INSTALL.md) · [Validation](docs/en/VALIDATION_R16_7.md) ·
[Maintenance / Material](docs/en/MAINTENANCE_MATERIAL.md) · [M07 / Z](docs/en/LEVELING.md)

Test update for an installed native M300 Classic host. MCU R14.5 can remain.
This host ZIP contains no firmware or bootloader to flash.

R16.7 retains the R16.6 corrections: Unload confirmation before retraction, Y-before-X M07
homing, OEM session offsets and five successive ordinary Z references; supports
Change on the real paused native print, with explicit Resume. It enforces an
English runtime and shares OEM dialogs between OLED and Fluidd.

Load/Unload: 240°C, ready at 238°C. Autocalibration and Heat: 260°C, ready at
258°C. Ordinary G28 Z retains its separate 180°C minimum. Native heater limits,
PID, calibrated E, sensor includes and deliberate geometry are preserved.
Source parity and deliberate safety differences are documented separately.

Run VERIFY.py, the 258 self-contained tests, and install.py to inspect the plan.
Stop Klipper before install.py --apply, then start it again. After Ready run
setup_fluidd.py --apply and refresh Fluidd. Preserve the exact rollback receipt.
The eleven procedure macros are in ZORTRAX M300; unfinished OEM print stays
separate. Installation starts no heater or movement.

CI validates software and FILEOUTPUT planning, not physical printer acceptance.

Maintenance now includes the OEM Fan test submenu and four matching Fluidd
macros. Upper automatic cooling remains authoritative. See
[validation and performance](docs/en/VALIDATION_R16_7.md).
