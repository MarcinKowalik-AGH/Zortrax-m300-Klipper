# Zortrax M300 Classic v1.0.0-beta.12 — first installation

This guide starts with a printer that already has the compatible M300 SD
bootloader, and a Raspberry Pi or Orange Pi without printer software.
It applies to the **original M300 Classic / STM32F103**, original contact
plate, hotend and 0.4 mm nozzle. It is not an M300 Plus, Dual or Inventure image.
The bootloader and factory application are not distributed in this release.

## What to install

| Component | Source |
|---|---|
| Linux | Board-specific Raspberry Pi OS Lite, or a supported Armbian/Debian/Ubuntu server image |
| Services, Python environment, nginx, Moonraker | One Klipper + Moonraker + Fluidd instance installed with KIAUH |
| Klipper actually used for M300 | The complete pinned and patched `KLIPPER_HOST` tree in this release |
| Printer MCU | Ready `MCU/M300APP.M3B`, R14.18, for the already installed SD bootloader |
| Fluidd actually used for M300 | Our precompiled Fluidd 1.37.7 extension in the same release |
| Machine configuration | First-install templates, with local paths/UART rendered by the installer |

KIAUH prepares the operating-system integration. Its temporary stock Klipper
and Fluidd are replaced by the matching M300 release. **Do not install the
latest upstream Klipper and copy a few extras over it.** The port is pinned to
Klipper `ee2c6fb6b00b2b5d097ef70d0868df7d74943b51` and includes core adaptations.
MCU and Fluidd need no compilation on the SBC. Klippy is Python; its small C
helper is compiled locally for the SBC's CPU, not copied from the x86 CI runner.

## 1. Install Linux and enable SSH/UART

For Raspberry Pi select the Lite Bookworm/Debian 12 image with Python 3.11;
for Orange Pi select a supported Debian 12 or Ubuntu 24.04 board image.
Use the image for the exact board model, enable SSH, configure the network and
create a normal user with sudo. Use that same user for KIAUH and this installer.
The first-install helper supports Python **3.10–3.12**; Debian 12 with Python
3.11 or Ubuntu 24.04 with Python 3.12 are suitable software baselines when
available for your board. CI exercises Python 3.12; a fresh OS installation on
each SBC is still a physical acceptance step. An image with Python 3.13 needs a
compatible 3.10–3.12 environment; do not force the helper past its version check.

| Host | UART setup |
|---|---|
| Raspberry Pi | `sudo raspi-config`: disable the serial login console and enable serial hardware, then reboot. Select a hardware UART exposed by that model; `/dev/serial0` is an alias, so inspect `readlink -f /dev/serial0`. Avoid assuming every Pi exposes the same PL011/mini-UART arrangement. |
| Orange Pi | Enable the UART overlay for the exact SoC/board image and reboot. The project's tested host uses `/dev/ttyS1`; that name and overlay are not universal. |

Connect the printer's documented 3.3 V UART: host TX to MCU RX, host RX to MCU
TX, and common GND. Use the pinout of the **specific board and existing
bootloader wiring**; do not infer a pin number from a different Pi. The M300
OLED connects to the printer MCU, not to the SBC's SPI header.
The compiled M300 MCU configuration uses USART1: PA9 is MCU TX and PA10 is
MCU RX. These are MCU signals, not verified physical DEBUG connector numbers.
Do not substitute the Inventure P4 pinout.

Start at **750000 baud**, matching the printer's bootloader UART setting.
That rate has the project's clean 400 mm/s XY dry-run evidence. The 1500000
baud test produced retransmissions and is not the release's recommended rate.
The installer does not change baud in the MCU or bootloader.

Check the selected UART, replacing `ttyS1` with your actual device:

```bash
ls -l /dev/ttyS1
sudo fuser -v /dev/ttyS1
systemctl is-active serial-getty@ttyS1.service
tr ' ' '\n' </proc/cmdline | grep '^console='
```

The UART must not be a Linux serial console or have another program using it.
If the user lacks device access, add it to the device's group (normally
`sudo usermod -aG dialout "$USER"`), then log out and back in.

## 2. Install the system services with KIAUH

```bash
sudo apt-get update
sudo apt-get install -y git curl unzip build-essential python3-dev libffi-dev
git clone https://github.com/dw-0/kiauh.git "$HOME/kiauh"
"$HOME/kiauh/kiauh.sh"
```

Select **Install → Klipper → one instance**, then **Moonraker**, then **Fluidd**.
Keep the standard single-instance paths: `~/klipper`, `~/klippy-env`,
`~/printer_data`, `klipper.service` and `moonraker.service`. Select **port 80**
for Fluidd, or record the different port you choose. Do not configure motors,
heaters or another printer in this temporary installation. An initial Klipper
configuration error before the M300 files are installed is expected.

## 3. Download the fixed beta package

The versioned ZIP is an ordinary public Release download; a GitHub login and
local MCU/Fluidd build tools are unnecessary.

```bash
mkdir -p "$HOME/m300-releases" &&
cd "$HOME/m300-releases" &&
curl -fLO https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/download/v1.0.0-beta.12/Zortrax_M300_Klipper_v1.0.0-beta.12.zip &&
curl -fLO https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/download/v1.0.0-beta.12/SHA256SUMS-v1.0.0-beta.12.txt &&
grep '  Zortrax_M300_Klipper_v1.0.0-beta.12.zip$' SHA256SUMS-v1.0.0-beta.12.txt | sha256sum -c - &&
unzip Zortrax_M300_Klipper_v1.0.0-beta.12.zip &&
cd Zortrax_M300_Klipper_v1.0.0-beta.12 &&
sha256sum -c --quiet SHA256SUMS
```

## 4. Flash the MCU application through the existing bootloader

Copy **`MCU/M300APP.M3B`** to the SD card root, using the existing bootloader's
documented card format/update entry. Stop the temporary Klipper service with
`sudo systemctl stop klipper`, insert the card and perform the bootloader's
application-update sequence. Retain 750000 baud on both ends. This is the
application at **0x08008000**, not a bootloader image or a whole-chip erase.
After a successful flash, remove the update card or remove the update file
before later boots. The old host updater never flashes the MCU automatically.

## 5. Install the matching M300 host/configuration/Fluidd

Restart the temporary host service if it was stopped for flashing:

```bash
sudo systemctl start klipper
python3 install-fresh.py --serial /dev/ttyS1 --baud 750000 --port 80
```

The command prints a read-only plan. For Raspberry Pi, substitute the UART
selected in step 1, for example `--serial /dev/serial0`. Review those paths,
then apply the same command with `--apply`:

```bash
python3 install-fresh.py --serial /dev/ttyS1 --baud 750000 --port 80 --apply
```

The helper verifies checksums, refuses an existing printer/M300 setup, installs
pinned Python requirements, builds the target CPU's C helper, backs up the
unused stock Klipper tree/configuration, installs the complete M300 host and
precompiled Fluidd, and restarts Klipper/Moonraker. It preserves Fluidd
`config.json` and saves the old web directory. Exact stock Klipper/Fluidd
updaters are removed; custom updater sources are refused for manual review.
UART overlays, Linux boot settings and MCU firmware are not changed.
No homing, movement or heating is requested by the installer.

If installation stops, keep the printed error and the directory
`~/m300-first-install-backup-<timestamp>`. A failure during the host/config/web
transaction restores the previous tree and configuration. `--apply` installs
files but does not claim a healthy MCU link; confirm Ready in the next step.

## 6. First power-on checks and calibration

Open `http://<host-IP>/` and fully reload Fluidd. First read, without movement:

```gcode
ZORTRAX_MCU_STATUS
ZORTRAX_OLED_STATUS
ZORTRAX_INFO REFRESH=0
PRINT_CONTROL_STATUS
QUERY_ENDSTOPS
QUERY_PROBE
M105
```

Expect Ready, matching 750000 baud, MCU `0.13.14.18-OEM-ERRORS-UART8`, print
controller `0.13.16.29-UNIFIED-NATIVE-START`, zero heater targets and sensible
ambient temperatures. Confirm the endstops/contact change when operated.
The [factory hardware/Z profile](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-beta.12/docs/en/HARDWARE_VARIANTS.md)
must match the printer. An erased/unknown factory record is an error, not a
reason to guess a Z scale.

The default profile provides X0..300, Y0..305, Z0..300 and park X300 Y305.
Verify physical clearance, actual travel, Z distance, nozzle diameter and
extrusion calibration on your printer before using that park or full travel.
PID values are starting references, not your machine's measured calibration.
Test homing under observation, run native PID tuning at the material's target
temperatures, then the OEM five-point mechanical leveling. Set and preview
the pad contact bounds before the separate 25-point `BED_MESH` compensation.
Contact rectangles differ between plates; the helper does not copy the
maintainer's measured rectangle dimensions to a new printer.

In OrcaSlicer use one shared start and one end:

```gcode
START_PRINT EXTRUDER_TEMP=[nozzle_temperature_initial_layer] BED_TEMP=[bed_temperature_initial_layer_single]
```

```gcode
END_PRINT
```

See the [workflow and pause/M600 parameters](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-beta.12/docs/pl/PRINT_CONTROL.md).

## Updates and acceptance scope

This beta is a fixed tag and fixed assets. `orange-pi` remains the moving
deployment channel for later project updates. To join that channel after the
first installation, clone its branch and use the normal updater with `--port 80`
(its historical default is 4080). Never use a generic upstream Klipper/Fluidd
update to replace this port. The operating system and Moonraker are separate
components; retain backups before changing them.

The package includes build provenance, source/licenses, compiled MCU/Fluidd,
700 host tests and FILEOUTPUT/first-install reports. Software validation is
not a physical test of every SBC, hardware revision, plate or Z-Suite export.
Known physical evidence includes the HW05 XY dry run at 750000 baud. Verify
printing, pause/resume/M600 and the link on the installed machine.

Upstream references: [KIAUH](https://dw-0.github.io/kiauh/setup/installation/),
[Raspberry Pi serial setup](https://www.raspberrypi.com/documentation/computers/configuration.html#configure-uarts),
[Armbian getting started](https://docs.armbian.com/User-Guide_Getting-Started/),
[Moonraker installation](https://moonraker.readthedocs.io/en/latest/installation/).
