# Install the built artifact

[Polski](../pl/INSTALL.md)

The artifact is for **M300 Classic** and the already installed native R15.5
host. It is not an Inventure image. The host update leaves printer.cfg settings,
saved PID, extruder calibration and motion geometry in place.

## Orange Pi host

Extract the Actions artifact. Copy its M300_HOST_R15_6_OEM_SLEEP directory
from your Mac to the Orange Pi, then verify and inspect the plan:

~~~bash
scp -r "$HOME/Downloads/M300_HOST_R15_6_OEM_SLEEP" klipper@192.168.4.157:/home/klipper/
ssh klipper@192.168.4.157
cd ~/M300_HOST_R15_6_OEM_SLEEP
python3 VERIFY.py
python3 -m unittest discover -s tests -v
python3 install.py
~~~

Expected: 71 tests OK and a plan showing host_update R15.6.
If the known installed baseline does not match, retain REFUSED rather than
overwriting files manually. The installer discovers the Klipper/config paths
from Moonraker, with the established M300 paths as fallback.

Between printer operations:

~~~bash
sudo systemctl stop klipper.service
python3 install.py --apply
sudo systemctl start klipper.service
~~~

Keep the returned RECEIPT.json path. Apply requires the stopped service.
After Ready, inspect ZORTRAX_DISPLAY_STATUS, ZORTRAX_MENU_STATUS and
ZORTRAX_NATIVE_STATUS. The display revision is 0.2.0-M300-OEM-SLEEP and menu
revision is 0.13.15.6-M300-NATIVE-OEM-SLEEP. The unchanged OLED transport may
retain its earlier host_revision.

Check five-minute work dimming, idle moon/notice/off, wake without a hidden
selection and local waiting during a planned restart. Display settings are
in ~/printer_data/config/m300_display.cfg. Existing valid values are preserved.

Rollback with the exact receipt, while the service is stopped:

~~~bash
python3 install.py --rollback /EXACT/PATH/RECEIPT.json
~~~

Later edited files are protected from replacement. Restart the service afterward.

## MCU

An already working R14.4 MCU does not need re-flashing for this host update.
The newly built files are available for reproducible future deployments.

MCU/M300_R14_4_SD.zip contains M300APP.M3B. This is the **application** at
0x08008000 for the existing M300 bootloader. No bootloader is replaced.
The ELF/map/dictionary/build report belong to this exact build; do not mix
a dictionary or ELF from another commit. CI has not tested the image on a printer.

HOST_SOURCE is a complete reference snapshot. It is not a second automatic
installer and does not replace the calibration-preserving host update above.
