# Install the R16.12 test release

[Procedure bindings](MAINTENANCE_MATERIAL.md) · [Validation and printer tests](PRINT_CONTEXT.md)

This host update is for M300 Classic with the native Klipper port and MCU R14.5–R14.7.
Factory serial and OEM print time require R14.6 or later.
OLED hold-to-move with local button release stop requires R14.7.
It accepts recognized R15.3 through R16.11 baselines, including the browser
modules from the M300 TEST01 v0.13.2 R2 install archive. The installer checks
the existing module hashes before it writes anything.

## Install directly from Git on Orange Pi

GitHub Actions builds and verifies the host, Fluidd and MCU. The same run
publishes a compact checkout with the ready-to-install files. Run this on the
Orange Pi as the Klipper user while the printer is idle:

```bash
m300_dir="$HOME/m300-orange-pi"
if [ -d "$m300_dir/.git" ]; then
  git -C "$m300_dir" pull --ff-only
else
  git clone --depth 1 --single-branch --no-tags --branch orange-pi \
    https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper.git "$m300_dir"
fi &&
python3 "$m300_dir/install-orange-pi.py"
```

The full build archive and test reports are also available in the successful
[GitHub Actions run](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/actions/workflows/build-m300.yml).

The installer checks the delivered file hashes, reads the active Klipper paths
from Moonraker, updates the host and macro groups, and deploys the compiled
Fluidd to the existing nginx web root on port 4080. It saves the old web files
and preserves config.json. A host already on the same R16.12 files skips its
restart. For a different nginx port, pass `--port`; for an atypical nginx
configuration, pass `--fluidd-root /absolute/path/to/current/fluidd`.

Expect `INSTALLED_M300_R16_12_FULL`, then reload Fluidd. Keep the host receipt
and the reported Fluidd backup path. The installer does not run printer
movement, heating or MCU flashing.

## Read-only checks and first tests

In the Fluidd console run:

```gcode
STATUS
ZORTRAX_HARDWARE_STATUS
ZORTRAX_MOTION_STATUS
ZORTRAX_CALIBRATION_STATUS
ZORTRAX_FILAMENT_STATUS
ZORTRAX_LINK_STATUS
ZORTRAX_UI_STATUS
ZORTRAX_FANS_STATUS
ZORTRAX_MAINTENANCE_STATUS
ZORTRAX_PROCEDURE_STATUS
ZORTRAX_SETTINGS_STATUS
ZORTRAX_INFO REFRESH=0
QUERY_PROBE
```

Confirm Ready, the real HW05/Z400 identity, normal native control, host R16.12,
fan/maintenance/procedure revisions and an open PC7 contact with clearance.
Motion reports the native rail speeds and a fault phase. Calibration still
reports its four independent movement speeds. The packaged
[M300 Fluidd build](FLUIDD_M300.md) renders the SVG in the same results dialog.
The link lifecycle revision remains 0.13.16.2-LIFECYCLE-RECONNECT; this is normal.
Targets are calibration/Heat 260°C, Load/Unload 240°C and ordinary Z home at
least 180°C. A hotter pre-existing target during ordinary homing is retained.

Follow the supervised sequence in [the validation report](PRINT_CONTEXT.md).

For a read-only SD import check on a printer with a qualified SD configuration,
run `ZORTRAX_SD_STATUS`, browse to a small G-code file under **Models**, and
open its preview. Check that the model becomes ready to start and cancel the
preview. Repeat with a larger file and check that the byte count reaches its
file size. The import finishes before the print can start.
The first procedure checks are Heat and bounded platform movement, then
Load/Unload, the interactive Fan test, ordinary Z reference and Autocalibration. Change requires an
already paused native print. Do not treat generic PROBE_ACCURACY as the OEM
wizard or a substitute for its owned measurement frame and release checks.

## Models from SD

Follow the [Models procedure](MODELS_SD.md) to enable the existing SD option
and test listing and import before starting a print. `ZORTRAX_MODELS_STATUS`
reports the current import and selection.

## Contextual print controls

Use [Print contexts](PRINT_CONTEXT.md) for the OLED 10-second holds,
Pause menu and Fluidd exact reprint. Re-run
`python3 setup_fluidd.py --apply` to group the ZORTRAX_REPRINT macro.

## Rollback and MCU

For a host rollback, stop Klipper, enter the included
`M300_HOST_R16_12_NORMAL_UI` directory, run
`python3 install.py --rollback /EXACT/PATH/RECEIPT.json`, then start Klipper.
The receipt restores exact prior host/config bytes and protects later edits.
For the frontend, restore the saved web directory to the reported
`fluidd_root` and reload nginx.

The included `MCU/M300APP.M3B` and `MCU/M300_R14_7_SD.zip` contain the
compiled M300 Classic application for the existing M300 SD/bootloader procedure.
The application starts at 0x08008000. Flashing is a separate operation.
BUILD_PROVENANCE.json identifies the tested source. The full Actions artifact
also contains the HOST_SOURCE snapshot.
