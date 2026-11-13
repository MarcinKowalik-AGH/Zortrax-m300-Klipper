# Update an existing M300 Classic installation

For a new host, use the [first-install guide](FIRST_INSTALL.md) and the
[fixed v1.0.0-rc.9 ZIP](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/v1.0.0-rc.9).
This guide applies to a running M300 port. [Polski](../pl/INSTALL.md)

## 1. Update Klipper and Fluidd

Wait for Klipper to be Ready, with no active or paused print, movement, or
procedure. Turn both heater targets off. Run as the account that runs Klipper
and make sure Moonraker can report printer state on `127.0.0.1:7125`.

The `orange-pi` branch carries the latest verified deployment. If you already
cloned that branch into `~/m300-orange-pi`, the following updates it. If the
directory does not exist, the commands clone it first.

```bash
m300_dir="$HOME/m300-orange-pi"
if [ -d "$m300_dir/.git" ]; then
  git -C "$m300_dir" pull --ff-only
else
  git clone --depth 1 --single-branch --no-tags --branch orange-pi \
    https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper.git "$m300_dir"
fi &&
python3 "$m300_dir/install-orange-pi.py" --port 4480
```

To update from the fixed release instead, extract the complete verified ZIP
and run `python3 install-orange-pi.py --port 4480` in its root. Check the ZIP and package
SHA-256 sums using [the download steps](FIRST_INSTALL.md#3-download-the-fixed-release-package).
Use this updater for M300 Klipper and Fluidd.

The installer checks the package hashes and the installed host baseline before
applying changes. It preserves the configured UART, saved PID, mesh and
machine settings. The command selects the existing Fluidd endpoint on port
4480 and saves it beside `printer.cfg`. The endpoint must already be served
by nginx. If detection is refused, check the running configuration with
`sudo nginx -T`. For a custom nginx layout, also pass
`--fluidd-root /absolute/path/to/fluidd`.
[Port detection and CI retries](../pl/INSTALLATION_AND_CI.md).

Look for `INSTALLED_M300_HOST` and check the reported `host_update`,
`fluidd_port` and `fluidd_root`. Keep the `host_receipt` and `fluidd_backup`
paths when present. If a newly updated host fails to start or reach Ready, the
updater uses the host receipt to restore the prior files. If installation is
refused, keep the error and review the reported file or state before retrying.

For optional configuration cleanup, add `--organize-config` to the same
command. It separates M300 procedures, temperature tables and saved PID
aliases, and removes recognized unused stock web update entries. Review the
changes in the [configuration audit](CONFIGURATION_AUDIT.md). The
machine-specific `--qualified-first-print-z` option requires confirmed
mechanical clearance and is unnecessary for routine updates.

## 2. Update the MCU from SD

The host updater leaves the MCU application untouched. To pair RC9 with
MCU 1.0.5, take `MCU/M300APP.M3B` from the full release, or extract it from
`MCU/M300_SD.zip` or the separate [MCU SD ZIP](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.5).
Use your existing M300 bootloader's SD application update procedure.
Earlier supported MCU firmware can still be used for local print-time
accounting. [MCU installation and counter synchronization](MCU_FIRMWARE_1.0.5.md).

## 3. Verify the installation

Open `http://<host-IP>:4480/` and reload Fluidd without the browser cache.
In the console, run these read-only checks:

```gcode
STATUS
ZORTRAX_MCU_STATUS
ZORTRAX_HARDWARE_STATUS
ZORTRAX_LINK_STATUS
ZORTRAX_INFO REFRESH=0
QUERY_PROBE
```

Confirm Ready, matching host and MCU UART rates, and MCU `1.0.5` if you
flashed it. Verify the [factory hardware revision and Z scale](HARDWARE_VARIANTS.md)
for your board, for example HW04/Z800 or HW05/Z400. With the nozzle clear of
the contact plate, the probe should report open. If you enabled counter
synchronization, use the [counter status checks](MCU_FIRMWARE_1.0.5.md#enable-and-inspect).

Before probing, use `BED_MESH PREVIEW=1` to check the configured pad layout.
See the [contact geometry](LEVELING.md#measured-contact-rectangles) and
[print validation steps](PRINT_CONTEXT.md). [Models from SD](MODELS_SD.md) ·
[OLED and Fluidd controls](RC1_UI.md) · [Illustrated OLED manual](../pl/OLED_FUNCTIONS.md)

## Restore a prior host update

To restore the host manually while the printer is idle, take `root` and
`config` from the saved JSON receipt and use its exact path. From the update
package, substitute all three paths before running:

```bash
if cd "$HOME/m300-orange-pi/M300_HOST" &&
  sudo systemctl stop klipper.service
then
  python3 install.py --root "/actual/klipper/root" \
    --config "/actual/printer.cfg" --rollback "/actual/RECEIPT.json"
  sudo systemctl start klipper.service
fi
```

For an extracted ZIP, use its `M300_HOST` directory instead. Confirm the
rollback reports `ROLLED_BACK_M300_HOST`. If it restored `moonraker.conf`, run
`sudo systemctl restart moonraker.service`. If it refused a later edit, preserve
the edit and review the reported file before retrying. For a separate Fluidd
rollback, use the reported `fluidd_backup`
and `fluidd_root` paths. Move the current web directory aside, restore the
saved directory to `fluidd_root`, then run `sudo systemctl reload nginx`.
