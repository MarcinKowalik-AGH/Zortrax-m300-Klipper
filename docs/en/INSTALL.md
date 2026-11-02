# Install MCU R14.5 and host R15.7

[Polski](../pl/INSTALL.md) · [Hardware variants](HARDWARE_VARIANTS.md)

For M300 Classic with the existing M300 bootloader and installed native
R15.5/R15.6 host. The factory Z feature requires **both** the R14.5 MCU application
and the R15.7 host. This is an application update, not a bootloader update.
The installer preserves printer.cfg Z numbers, saved PID, extruder calibration
and existing display settings. The effective Z scale is selected at startup.

## Prepare the host update

Download the artifact from the successful Actions run for the exact commit and
extract it. Copy its M300_HOST_R15_7_FACTORY_Z directory from the Mac:

~~~bash
scp -r "$HOME/Downloads/M300_HOST_R15_7_FACTORY_Z" klipper@192.168.4.157:/home/klipper/
ssh klipper@192.168.4.157
cd ~/M300_HOST_R15_7_FACTORY_Z
python3 VERIFY.py
python3 -m unittest discover -s tests -v
python3 install.py
~~~

Expected: 92 tests OK and an R15.7 plan reporting that factory Z requires MCU
R14.5. The installer discovers paths from Moonraker with the established M300
paths as fallback. Unknown modified runtime files are refused rather than
silently overwritten.

## Apply the matching pair

Between printer operations:

1. Run `sudo systemctl stop klipper.service`.
2. Install **MCU/M300APP.M3B** from this artifact through the already verified
   M300 bootloader/SD update procedure. MCU/M300_R14_5_SD.zip contains this
   application alone. Keep the factory Flash page and bootloader intact.
3. In the host update directory run `python3 install.py --apply`.
4. Run `sudo systemctl start klipper.service`.

Keep the returned RECEIPT.json. No service is started and no MCU is flashed by
the installer. The application base remains 0x08008000. The ELF/map/dictionary
and build report belong to this exact build; do not mix files from other commits.

## Verify the detected variant

In Fluidd run:

~~~gcode
STATUS
ZORTRAX_HARDWARE_STATUS
ZORTRAX_MCU_STATUS
ZORTRAX_MOTION_STATUS
~~~

Expected hardware state: FACTORY_PROFILE_APPLIED. For a retained HW05 record,
expect hardware_label=HW05, stock/effective Z=400 and effective rotation=8.
HW04 selects 800 and rotation=4. The configured rotation may differ because
factory selection does not rewrite the file. M07 must report/use the same scale.
OLED Information shows the hardware revision and effective Z scale. Physically
measure a short Z move from a properly homed, clear starting position before
using full travel. CI has not operated either physical printer.

A missing/corrupt ID3 or old MCU gives a descriptive startup error. An explicitly
configured/rebuilt machine can use `[m300_mcu] z_profile: config`; see Hardware
variants for its meaning. Do not use that mode to guess an unidentified screw.

R15.6 sleep/menu behaviour remains available: ZORTRAX_DISPLAY_STATUS,
ZORTRAX_MENU_STATUS and ZORTRAX_NATIVE_STATUS report their existing owners.
Display settings remain in ~/printer_data/config/m300_display.cfg.

## Rollback

Stop the service, run `python3 install.py --rollback /EXACT/PATH/RECEIPT.json`,
then start the service. Later edited files are protected. This restores host
files/configuration only; the MCU application is not changed by rollback.
HOST_SOURCE is the complete matching source snapshot, not another installer.
