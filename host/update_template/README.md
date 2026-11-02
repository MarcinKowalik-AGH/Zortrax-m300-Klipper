# M300 host R16.5 — OEM Maintenance and Material

[Polski](README_PL.md) · [Install](docs/en/INSTALL.md) · [Features](docs/en/FEATURES.md)

Upgrade for installed native M300 R15.3/R15.5/R15.6/R15.7, requiring MCU R14.5 for
factory Z selection. The complete Actions artifact includes the MCU application.
This host ZIP contains no bootloader or firmware to flash.

The installer updates the normal menu/G28 adapter and migrates the installed
configuration to 180C Z homing, STEP 2 us, XY 300 mm/s and native limits.
PID, calibrated E, display settings and saved calibration are preserved;
all changes are listed in the plan and backed up for exact rollback.

OLED and Fluidd groups: Klipper, Zortrax M300, Service / Tests (TEST M300 in
Fluidd). Run setup_fluidd.py --apply after Ready, then refresh the browser.
The Maintenance and Material submenus use shared native procedure owners.
Their six macros are grouped in ZORTRAX M300; unfinished OEM print remains in TEST. The existing display
sleep, MCU cooling and lifecycle remain; an installed R14.5 MCU can remain.

Run python3 VERIFY.py, python3 -m unittest discover -s tests -v (203 tests),
and python3 install.py. Follow the installation instructions for --apply and
physical acceptance. CI tests software; it does not measure full-load 300 mm/s.

R16.5 also restores a connection after host/service reboot using one native
reset for a previous armed session or heartbeat fault. It never resumes old
heating/motion and does not automatically reset other fault codes.
See docs/en/CONNECTION.md for the printer acceptance steps.

R16.5 restores stock procedure targets: calibration/leveling 260°C and Load/Unload 240°C. Migration updates existing R16.3/R16.4 sections and macro defaults. Ordinary G28 Z retains its separate 180°C setting. Manual heating, PID and M600 paused-print target selection retain their existing behavior. Both calibration and filament status expose procedure_temperature.

R16.5 adds the original ordered Maintenance/Material submenus, native Heat
(260°C), hold-to-move platform controls, and native Load/Unload (240°C). The
six macros are in ZORTRAX M300. Their literal OEM dialogs are shared by OLED
and Fluidd; 110 reference frames match the recovered original renderer.
[Menu controls and acceptance](docs/en/MAINTENANCE_MATERIAL.md).
