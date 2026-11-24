# Update an existing M300 Classic installation

For a new host, use the [first-install guide](FIRST_INSTALL.md) and the
[fixed v1.0.3 ZIP](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/v1.0.3).
For a blank Fluidd page, [recover Fluidd before the host update](#recover-fluidd-then-update-klipper).
[Polski](../pl/INSTALL.md).

If a previous update rolled back with a missing counter reply, see [RC18 startup recovery](RELEASE_v1.0.0-rc.18.md).

## 1. Update Klipper

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
(cd "$m300_dir" && sha256sum -c --quiet SHA256SUMS) &&
python3 "$m300_dir/install-orange-pi.py"
```

To update from the fixed release instead, extract the complete verified ZIP
and run `python3 install-orange-pi.py` in its root. Check the ZIP and package
SHA-256 sums using [the download steps](FIRST_INSTALL.md#3-download-the-fixed-release-package).
The standard command installs the Klipper host update. It preserves the UART
configuration, saved PID, mesh, machine settings, Fluidd website and
preferences, and nginx configuration.

Look for `INSTALLED_M300_HOST` and `host_update`. Keep the `host_receipt`
path when present. If the updated host fails to start or reach Ready, the
updater uses the receipt to restore its prior files. If installation is
refused, review the reported file or state before retrying.

For optional configuration cleanup, add `--organize-config` to the same
command. It separates M300 procedures, temperature tables and saved PID
aliases, and removes recognized unused stock web update entries. Review the
changes in the [configuration audit](CONFIGURATION_AUDIT.md). The
machine-specific `--qualified-first-print-z` option requires confirmed
mechanical clearance and is unnecessary for routine updates.

## Update after a Git corrupt loose object error

Leave the damaged checkout in place. With the printer idle, clone the published deployment branch into a new directory on the Orange Pi. The installer uses the existing printer configuration.

```bash
m300_src=$(mktemp -d "$HOME/m300-orange-pi.XXXXXX") &&
git clone --depth 1 --single-branch --no-tags --branch orange-pi \
  https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper.git "$m300_src" &&
(cd "$m300_src" && sha256sum -c --quiet SHA256SUMS) &&
python3 "$m300_src/install-orange-pi.py"
```

Keep the new path for subsequent updates. Use the versioned full ZIP to install exactly 1.0.3. After a separate Fluidd repair check `fluidd_http_verified` and open the menu on port 4480.

## 2. Check the MCU version

If the printer already runs MCU 1.0.8, skip the SD update. Otherwise, to use
the paired MCU version, take `MCU/M300APP.M3B` from the full release or
extract it from `MCU/M300_SD.zip` or the separate
[MCU SD ZIP](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.8).
Use the SD application update procedure of the bootloader already installed
on your M300. [MCU 1.0.8 instructions](MCU_FIRMWARE_1.0.8.md).

With MCU 1.0.8, synchronization runs automatically with the current
configuration. Klipper accepts and ignores the old `factory_counter_backup:`
setting. You can remove that entry after updating the host. Keep the existing
Klipper print-time files, including the synchronization journal. If the MCU
firmware lacks the runtime counter commands, Klipper continues counting new
print time locally.

## 3. Verify the installation

In the existing Fluidd console at `http://<host-IP>:4480/`, run these
read-only checks:

```gcode
STATUS
ZORTRAX_MCU_STATUS
ZORTRAX_HARDWARE_STATUS
ZORTRAX_LINK_STATUS
ZORTRAX_INFO REFRESH=0
QUERY_PROBE
```

Confirm Ready, matching host and MCU UART rates, and MCU `1.0.8` if you
flashed it. Verify the [factory hardware revision and Z scale](HARDWARE_VARIANTS.md)
for your board, for example HW04/Z800 or HW05/Z400. With the nozzle clear of
the contact plate, the probe should report open. Use the
[counter status checks](MCU_FIRMWARE_1.0.8.md#read-the-counter) to verify
automatic synchronization.

To verify the counter on a physical printer, record the factory minutes in
`ZORTRAX_HARDWARE_STATUS` before a normal print with at least one minute of model-print time.
After the printer becomes idle and eligible to write, check for `factory_counter_sync: SYNCED`,
`factory_counter_banks: NORMALIZED`, `factory_counter_pending: false` and
an increase in `factory_print_minutes`. Check that value again after the
next normal power cycle. The release tests simulate the Flash write and
recovery.

Before probing, use `BED_MESH PREVIEW=1` to check the configured pad layout.
See the [contact geometry](LEVELING.md#measured-contact-rectangles) and
[print validation steps](PRINT_CONTEXT.md). [Models from SD](MODELS_SD.md) ·
[OLED and Fluidd controls](RC1_UI.md) · [Illustrated OLED manual](../pl/OLED_FUNCTIONS.md)

## Recover Fluidd, then update Klipper

For an existing checkout in `~/m300-orange-pi` and a machine that is idle
and Ready, run over SSH as the Klipper user:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --update-fluidd --port 4480 &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

The Fluidd step repairs the static site on 4480 and preserves `config.json`.
The Klipper step installs the host update. Open `http://<host-IP>:4480/`
and run the checks above.

## Update or repair Fluidd

Use this command when you explicitly want to update the website or repair a
recognized M300 Fluidd deployment. It uses the existing nginx site on 4480
and can run when Klipper or Moonraker is unavailable.

```bash
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --update-fluidd --port 4480
```

For an extracted release ZIP, run the same command with
`python3 install-orange-pi.py` from its root. For a custom nginx layout,
`--fluidd-root /absolute/path/to/fluidd` can point to the verified existing
web directory. The update preserves the nginx configuration, `config.json`
and Fluidd preferences. The `INSTALLED_M300_FLUIDD` receipt with
`fluidd_http_verified: true` confirms that nginx served the expected HTML
and startup JavaScript and CSS over HTTP. The installer checks the selected
site's listen address, including a LAN-only bind. Keep the `fluidd_root`
and `fluidd_backup` paths. A `null` backup means the existing site passed
verification with identical files. A `FLUIDD_HTTP_UNVERIFIED` error exits
with failure. If a swap took place, the installer exchanges the directories
back. Check nginx and the HTTP requests described below.
[Port detection and CI retries](../pl/INSTALLATION_AND_CI.md).

## Diagnose a blank or unreachable Fluidd page

Run these checks over SSH on the host:

```bash
base=http://127.0.0.1:4480
curl --noproxy '*' --silent --show-error --max-time 5 --output /dev/null \
  --write-out 'Fluidd: HTTP %{http_code}, %{size_download} bytes\n' "$base/"
curl --noproxy '*' --silent --show-error --max-time 5 --output /dev/null \
  --write-out 'Moonraker via nginx: HTTP %{http_code}\n' "$base/server/info"
```

- **HTTP 200 with 0 bytes for Fluidd** means the HTML response is empty.
  Find the active 4480 site with `sudo nginx -T` and check its `index.html`.
  For a recognized M300 deployment, run the explicit Fluidd repair above.
- **HTTP 403 or 404 for Fluidd** calls for checking the 4480 site root,
  the file's existence and whether the nginx worker can read it.
- **HTTP 000 or a connection error** calls for checking nginx with
  `sudo nginx -t`, `systemctl is-active nginx` and `sudo ss -ltnp`.
  If the site binds to a specific LAN address, use it instead of
  `127.0.0.1` in the checks.
- **Fluidd HTML works but Moonraker returns 502** calls for checking
  `systemctl is-active moonraker` and the site's Moonraker proxy.
- **Fluidd HTML arrives but the browser is blank** calls for checking the
  main `assets/index-*.js` request in the browser's Network panel.
  It should return a nonempty JavaScript file. Test the URL in a private
  browser window.

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
the edit and review the reported file before retrying.

## Restore the previous Fluidd website

Copy the **absolute `fluidd_backup` path** from this site's installation
receipt. A `null` value means that update created no backup. Replace the
example path with the one from the receipt.

```bash
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480 --restore-fluidd '/path/from/receipt/.m300-fluidd.ABC123.previous'
```

The installer checks the live site directory and its sibling backup,
restores the static files, and preserves the current `config.json`.
It exchanges the directories atomically. After `RESTORED_M300_FLUIDD`,
check `fluidd_http_verified: true` and open the Fluidd menu on port 4480.
The selected backup remains available. Repeating the command with the same
backup verifies the restored version.
