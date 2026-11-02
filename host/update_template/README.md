# M300 host R16 — normal controls and separate TEST group

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
Unfinished OEM M03/M07/M08 procedures remain in TEST. The existing display
sleep, MCU cooling and lifecycle remain; an installed R14.5 MCU can remain.

Run python3 VERIFY.py, python3 -m unittest discover -s tests -v (157 tests),
and python3 install.py. Follow the installation instructions for --apply and
physical acceptance. CI tests software; it does not measure full-load 300 mm/s.

R16.3.1 also restores a connection after host/service reboot using one native
reset for a previous armed session or heartbeat fault. It never resumes old
heating/motion and does not automatically reset other fault codes.
See docs/en/CONNECTION.md for the printer acceptance steps.
