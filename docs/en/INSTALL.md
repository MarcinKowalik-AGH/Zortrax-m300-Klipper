# Install the R16 test iteration

[Polski](../pl/INSTALL.md) · [Features and acceptance](FEATURES.md)

For M300 Classic with the installed native R15.3/R15.5/R15.6/R15.7 host and the M300
bootloader. R16 needs MCU R14.5 for factory Z detection; an already installed
R14.5 does not need re-flashing. The complete Actions artifact also contains
a fresh compiled R14.5 application for older installations.

Extract the artifact and copy its host directory from the Mac:

~~~bash
scp -r "$HOME/Downloads/M300_HOST_R16_5_NORMAL_UI" klipper@192.168.4.157:/home/klipper/
ssh klipper@192.168.4.157
cd ~/M300_HOST_R16_5_NORMAL_UI
python3 VERIFY.py
python3 -m unittest discover -s tests -v
python3 install.py
~~~

Expected: 203 tests OK and an R16 plan. Inspect the listed files: this update
migrates the commissioning motion section to native mode, sets 180C Z homing,
2 us STEP and the 300 mm/s XY profile, and adds three macro includes. Saved PID,
calibrated E and deliberate geometry outside the old Z30 envelope are retained.
Unknown locally edited runtime modules are refused; no configuration is written
by the plan. Valid existing display settings remain.

Between printer operations:

~~~bash
sudo systemctl stop klipper.service
python3 install.py --apply
sudo systemctl start klipper.service
~~~

Keep the printed RECEIPT.json path. If the installed MCU is older than R14.5,
install MCU/M300APP.M3B through the already verified M300 bootloader/SD procedure
while Klipper is stopped, before starting this host. The application is based
at 0x08008000; factory records and the bootloader are not replaced. The matching
SD application archive is MCU/M300_R14_5_SD.zip.

After Klipper is Ready, set the Fluidd categories:

~~~bash
python3 setup_fluidd.py
python3 setup_fluidd.py --apply
~~~

Refresh the browser. Categories are Klipper, ZORTRAX M300 and TEST M300. The
script only uses Moonraker's Fluidd database API and preserves unrelated UI
settings; its returned backup can be restored with
`python3 setup_fluidd.py --rollback /EXACT/BACKUP.json --apply`.

In the console inspect STATUS, ZORTRAX_HARDWARE_STATUS, ZORTRAX_MOTION_STATUS,
ZORTRAX_DISPLAY_STATUS and ZORTRAX_NATIVE_STATUS. Check native mode, the actual
factory Z scale, target 180C and 2 us config values. Use the physical acceptance
sequence in FEATURES.md. High-speed/full-load timing remains a printer test.
No test macro runs automatically during installation.

Host/config rollback: stop Klipper, run
`python3 install.py --rollback /EXACT/PATH/RECEIPT.json`, then start it again.
The receipt restores exact prior files and protects subsequent edits. It does
not change the MCU. HOST_SOURCE is a matching source snapshot, not another
installer. SHA256SUMS and BUILD_PROVENANCE.json identify the exact Actions build.

R16.5 adds direct migration from the known native R15.3 host, including
installations without the display extension. The real API check and hash-based
upgrade are exercised using archived R15.3 modules. Runtime/MCU behaviour is
unchanged from R16. Expected installer result: INSTALLED_M300_R16_5.

If the previous installer printed `REFUSED: R15.5 motion and M11 presentation support required`,
R16 was not installed. A successful setup_fluidd.py only changes macro groups.
R16.5 removes that migration obstacle for the recognized R15.3 baseline. Before motion,
confirm `INSTALLED_M300_R16_5` and `ZORTRAX_MOTION_STATUS` reporting
`normal_control=true` and `z_home_hotend_target_c=180`. `G28 X Y` does not heat;
`G28 Z` waits for the native heater check before moving to contact.

R16.5 also updates m300_lifecycle.py. After installation, ZORTRAX_LINK_STATUS
should report 0.13.16.2-LIFECYCLE-RECONNECT. Host/service reboot gains one recovery
attempt for an old session or heartbeat latch. Acceptance and explicit-recovery
cases are described in [Connection lifecycle](CONNECTION.md).

[M07 leveling in R16.5 — start and acceptance](LEVELING.md)

R16.5 restores stock procedure targets: calibration/leveling 260°C and Load/Unload 240°C. Migration updates existing R16.3/R16.4 sections and macro defaults. Ordinary G28 Z retains its separate 180°C setting. Manual heating, PID and M600 paused-print target selection retain their existing behavior. Both calibration and filament status expose procedure_temperature.

R16.5 implements the OEM Maintenance and Material menus and their six Fluidd
macros. See [controls, source evidence and acceptance](MAINTENANCE_MATERIAL.md).
