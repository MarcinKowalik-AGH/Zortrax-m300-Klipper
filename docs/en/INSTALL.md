# Install the R16.11 test release

[Procedure bindings](MAINTENANCE_MATERIAL.md) · [Validation and printer tests](PRINT_CONTEXT.md)

This host update is for M300 Classic with the native Klipper port and MCU R14.5.
It accepts recognized R15.3 through R16.10 baselines, including the browser
modules from the M300 TEST01 v0.13.2 R2 install archive. The installer checks
the existing module hashes before it writes anything.

## Stage and verify on Orange Pi

Clone the R16.11 branch into a separate directory on the Orange Pi. Run the
following from the Orange Pi shell.

```bash
git clone --branch r16.11 --single-branch https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper.git "$HOME/m300-r16.11-src" &&
cd "$HOME/m300-r16.11-src" &&
python3 ci/stage_host_update.py &&
cd .ci/host-update &&
python3 VERIFY.py &&
klipper_pid=$(systemctl show klipper.service -p MainPID --value) &&
[ "$klipper_pid" -gt 0 ] &&
IFS= read -r -d '' klipper_python < "/proc/$klipper_pid/cmdline" &&
"$klipper_python" -m unittest discover -s tests &&
python3 install.py \
  --root "$HOME/m300-test01-0.13.2/klipper" \
  --config "$HOME/printer_data/config/printer.cfg"
```

Expect package PASS, **322 tests OK** and PLAN_M300_R16_11. The plan is read
only. Inspect its file list before applying. Calibrated E, both saved PID
blocks, sensor includes, deliberate motion limits and usable geometry remain.
The HW05 factory profile still selects effective Z400 without rewriting the
factory record. Old saved language values remain readable; the UI uses English.

## Apply while the printer is idle

```bash
sudo systemctl stop klipper.service && {
  python3 install.py \
    --root "$HOME/m300-test01-0.13.2/klipper" \
    --config "$HOME/printer_data/config/printer.cfg" \
    --apply
  update_status=$?
  sudo systemctl start klipper.service && test "$update_status" -eq 0
}
```

Expect INSTALLED_M300_R16_11 and retain the exact RECEIPT.json path. Installation
does not run a motion/heating test. After Klipper reports Ready, update Fluidd:

```bash
python3 setup_fluidd.py
python3 setup_fluidd.py --apply
```

Refresh Fluidd. The procedure macros and the new Settings, Information and Help
macros belong to ZORTRAX M300. Test aliases are grouped under TEST M300. Existing unrelated groups,
visibility, colors and preferences are retained. The returned Fluidd backup
can be restored with `python3 setup_fluidd.py --rollback /EXACT/BACKUP.json --apply`.

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

Confirm Ready, the real HW05/Z400 identity, normal native control, host R16.11,
fan/maintenance/procedure revisions and an open PC7 contact with clearance.
Motion and calibration retain their R16.6 component revisions.
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

## Rollback and full artifact

Stop Klipper, run `python3 install.py --rollback /EXACT/PATH/RECEIPT.json`, then
start Klipper again. The receipt restores exact prior host/config bytes and
protects later edits. It does not change MCU firmware.

The full Actions artifact also contains a newly compiled matching R14.5
application, SHA256SUMS, BUILD_PROVENANCE.json, software reports and HOST_SOURCE.
HOST_SOURCE is a source snapshot, not a second installer. For installations
older than MCU R14.5, use the previously verified M300 SD/bootloader procedure
with MCU/M300APP.M3B or MCU/M300_R14_5_SD.zip while Klipper is stopped. The
application starts at 0x08008000; no bootloader or factory record is supplied.
