# Optional host temperature

Fluidd gets one additional temperature series, **Host**, for the host CPU.
Other Linux thermal readings are available on demand over SSH, without adding
graph series. This feature is disabled by default.

## Existing installation

From the `orange-pi` checkout, download and copy the template if not yet installed:

```bash
cd "$HOME/m300-orange-pi" &&
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
cp -n FIRST_INSTALL/m300_host_temperature.cfg "$HOME/printer_data/config/"
```

This option does not require running `install-orange-pi.py`.
Fresh installations copy the template with its include commented out.
Enable it in `printer.cfg`, before `SAVE_CONFIG`:

```ini
[include m300_host_temperature.cfg]
```

Disable it by commenting out that line:

```ini
# [include m300_host_temperature.cfg]
```

After changing the include, run `FIRMWARE_RESTART` in Fluidd while the printer
is idle. The configuration defines a read-only temperature sensor.

## Other readings

Run over SSH:

```bash
python3 "$HOME/m300-orange-pi/read-host-temperatures.py"
```

Use `--json` for structured output. This only reads Linux system files; it works
with the include disabled and does not restart services or record history.

On the observed Orange Pi Zero 4 / A733, zones 0–4 are respectively
`cpub_thermal_zone`, `ddr_thermal_zone`, `npu_thermal_zone`, `cpul_thermal_zone`,
and `gpu_thermal_zone`. Only zone 0 is registered in Klipper as **Host**.
On other boards or after changes to thermal zone numbering, identify the CPU
zone with the command and adjust `sensor_path` before enabling the include.
The file must exist and be readable by the Klipper account.

This option does not enable the STM32 temperature sensor; support in the
custom M300 MCU firmware needs separate verification.
