# Zortrax M300 Classic v1.0.0-rc.9 — first installation

If Klipper for M300 is already running on this host, follow the [update guide](INSTALL.md).

This guide starts with a printer that already has the compatible M300 SD
bootloader, and a Raspberry Pi or Orange Pi without printer software.
It applies to the **original M300 Classic / STM32F103**, original contact
plate, hotend and 0.4 mm nozzle. It is not an M300 Plus, Dual or Inventure image.

## What to install

| Component | Source |
|---|---|
| Linux | Board-specific Raspberry Pi OS Lite, or a supported Armbian/Debian/Ubuntu server image |
| Services, Python environment, nginx, Moonraker | One Klipper + Moonraker + Fluidd instance installed with KIAUH |
| Klipper actually used for M300 | The complete pinned and patched `KLIPPER_HOST` tree in this release |
| Printer MCU | Ready `MCU/M300APP.M3B`, 1.0.5, for the already installed SD bootloader |
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
Run the first-install helper with Python **3.10–3.12**; Debian 12 with Python
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
Keep the single-instance paths `~/klipper`, `~/klippy-env`, `~/printer_data`
and the services `klipper.service` and `moonraker.service`. At
**Configure Fluidd for port**, enter **4480**. Answer **No** if KIAUH offers
the optional `Fluidd-Config`; the M300 package supplies its own macros.
Leave KIAUH's temporary `printer.cfg` as generated, including the serial
placeholder. Klipper can report a configuration error until the M300 files
are installed.

If KIAUH already set Fluidd to 80 on this new host, inspect the active
configuration with `sudo nginx -T`. The standard KIAUH Fluidd file is
`/etc/nginx/sites-available/fluidd`. Use `sudoedit` on the actual Fluidd site
file and change only its active `listen 80;` to `listen 4480;` and, if
enabled, `listen [::]:80;` to `listen [::]:4480;`. Leave other sites alone.
Validate the configuration before reloading it:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Verify the Fluidd page on port 4480 before continuing:

```bash
curl --fail --silent --show-error http://127.0.0.1:4480/ | grep -io '<title>fluidd</title>'
```

## 3. Download the fixed release package

The versioned ZIP is an ordinary public Release download; a GitHub login and
local MCU/Fluidd build tools are unnecessary.

```bash
mkdir -p "$HOME/m300-releases" &&
cd "$HOME/m300-releases" &&
curl -fLO https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/download/v1.0.0-rc.9/Zortrax_M300_Klipper_v1.0.0-rc.9.zip &&
curl -fLO https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/download/v1.0.0-rc.9/SHA256SUMS-v1.0.0-rc.9.txt &&
grep '  Zortrax_M300_Klipper_v1.0.0-rc.9.zip$' SHA256SUMS-v1.0.0-rc.9.txt | sha256sum -c - &&
unzip Zortrax_M300_Klipper_v1.0.0-rc.9.zip &&
cd Zortrax_M300_Klipper_v1.0.0-rc.9 &&
sha256sum -c --quiet SHA256SUMS
```

## 4. Flash the MCU application through the existing bootloader

Copy **`MCU/M300APP.M3B`** to the SD card root, using the existing bootloader's
documented card format/update entry. Stop the temporary Klipper service with
`sudo systemctl stop klipper`, insert the card and perform the bootloader's
application-update sequence. Retain 750000 baud on both ends. This is the
application at **0x08008000**, not a bootloader image or a whole-chip erase.
After a successful flash, remove the update card or remove the update file
before later boots. Keep the temporary Klipper service stopped until the
installer starts the M300 service in step 5.

## 5. Install the matching M300 host/configuration/Fluidd

From the extracted release directory, run the installer as the KIAUH user:

```bash
python3 install-fresh.py --serial /dev/ttyS1 --baud 750000 --port 4480
```

The command prints a read-only plan. For Raspberry Pi, substitute the UART
selected in step 1, for example `--serial /dev/serial0`. Verify the UART, baud,
Klipper path, Fluidd port 4480 and the expected web root in the plan. Then
run the same command with `--apply`:

```bash
python3 install-fresh.py --serial /dev/ttyS1 --baud 750000 --port 4480 --apply
```

The helper verifies checksums, refuses an existing printer/M300 setup, installs
pinned Python requirements, builds the target CPU's C helper, backs up the
unused stock Klipper tree/configuration, installs the complete M300 host and
precompiled Fluidd, and restarts Klipper/Moonraker. It preserves Fluidd
`config.json` and saves the old web directory. Exact stock Klipper/Fluidd
updaters are removed; custom updater sources are refused for manual review.
UART overlays, Linux boot settings and MCU firmware are not changed.
No homing, movement or heating is requested by the installer.

On success, keep the `backup` path reported with
`INSTALLED_FIRST_M300_CHECK_READY`. If the transaction fails, keep the error
and the directory `~/m300-first-install-backup-<timestamp>` if it was created.
The installer restores the previous files and services on a transaction
failure. Confirm the MCU link and Ready in the next step.

## 6. First power-on checks and calibration

Open `http://<host-IP>:4480/`. Fully reload Fluidd and run these read-only
commands:

```gcode
ZORTRAX_MCU_STATUS
ZORTRAX_OLED_STATUS
ZORTRAX_INFO REFRESH=0
PRINT_CONTROL_STATUS
QUERY_ENDSTOPS
QUERY_PROBE
M105
```

Expect Ready, the UART baud rate selected in step 5, MCU `1.0.5`, zero heater
targets and temperatures consistent with the room. Confirm that endstop and
probe states change when operated.
The [factory hardware/Z profile](HARDWARE_VARIANTS.md)
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

See the [workflow and pause/M600 parameters](../pl/PRINT_CONTROL.md).

## Optional MCU print-time synchronization

Klipper starts with local print-time accounting. After confirming Ready, edit
the existing `[m300_mcu]` section in `~/printer_data/config/printer.cfg` and
set `factory_counter_backup:` to the absolute path of the verified full Flash
backup for this board. Save and restart Klipper once to load the setting.
The next pending whole minute synchronizes automatically when the printer
becomes eligible to write. [MCU setup and status checks](MCU_FIRMWARE_1.0.5.md).

## Updates and acceptance scope

The fixed `v1.0.0-rc.9` package installs this candidate. The `orange-pi` branch
serves later project updates. See the [update guide](INSTALL.md) to clone that
branch and deploy to the existing Fluidd endpoint on 4480. Use the M300
installer for Klipper and Fluidd. Back up the Moonraker and operating-system
configuration before
updating those components separately.

The package includes build provenance, source/licenses, compiled MCU/Fluidd,
reports from the host regression, FILEOUTPUT and first-install checks.
Physical evidence includes the HW05 XY dry run at 750000 baud. Verify
printing, pause/resume/M600 and the link on the installed machine.

System setup references

[KIAUH](https://dw-0.github.io/kiauh/setup/installation/),
[Raspberry Pi serial setup](https://www.raspberrypi.com/documentation/computers/configuration.html#configure-uarts),
[Armbian getting started](https://docs.armbian.com/getting-started/),
[Moonraker installation](https://moonraker.readthedocs.io/en/latest/installation/).

## After setup

[OLED and Fluidd controls](RC1_UI.md) · [Illustrated OLED reference](../pl/OLED_FUNCTIONS.md) · [Print workflow](PRINT_CONTEXT.md)
