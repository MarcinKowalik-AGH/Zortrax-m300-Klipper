# M300 Classic RC15

Dynamic Light uses the current SD file's completed `START_PRINT` to
stay white through printing, including changes in heater targets after a
raft. It works independently of print-time accounting. Preheat, operator
pause, fault indication, light preference and brightness retain their roles.

RC14 and RC15 run the same four purge passes at one commanded height,
normally Z0.28, with mesh compensation. A visible Z correction at the Y→X
corner can result from the active mesh. The older `0.13.16.38-PRINT-DRAIN-XY-PURGE`
commanded an intermediate lift to Z5.

## Update Klipper

When the printer is Ready, with printing and procedures finished and the
heater targets off, run as the Klipper user:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

A printer already running MCU 1.0.5 takes the host update only. The full
package includes `MCU/M300_SD.zip` for first installation. Use the existing
Fluidd site on port 4480. The separate `--update-fluidd --port 4480` command
is for an explicit website repair.
[First installation](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.15/docs/en/FIRST_INSTALL.md) ·
[Update guide](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.15/docs/en/INSTALL.md)

## Verify

```gcode
PRINT_CONTROL_STATUS
ZORTRAX_MAINTENANCE_STATUS
ZORTRAX_ERROR_STATUS
```

`PRINT_CONTROL_STATUS` reports `0.13.16.40-PRINT-LIGHT` and
`model_print_ready: true` once purge has drained for the active file.
Check `status_led.state` if the light is red. `HEATING` indicates heating.
`ERROR` indicates a fault signal, with details in `ZORTRAX_ERROR_STATUS`.

Software checks cover print readiness and the commanded purge height.
Verification on the physical printer is pending. The beta.20 OLED images
remain a historical reference.
