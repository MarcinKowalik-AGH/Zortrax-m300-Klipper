# M300 Classic RC29 — 240°C withdrawal during a paused material change

The OLED material-change action, Fluidd, `ZORTRAX_CHANGE` and `M600` share the same service. After parking, the nozzle reaches its 240°C withdrawal setpoint. With the default settings the extruder retracts 110 mm at 2 mm/s. The host waits for the last segment to finish before switching the heater to the loading temperature.

For a 210°C print the nozzle returns to 210°C to feed the new filament. An optional `TEMP` on `ZORTRAX_CHANGE` sets the loading temperature. Insert the new material and confirm on either panel. The extruder waits for the temperature and feeds 150 mm by default. Check the flow, confirm readiness and select Resume. For the first physical trial, inspect the tip of the removed filament and check that the replacement passes through the heatbreak.

## Orange Pi update

Finish the print. When Klipper is Ready and heater targets are zero, run the following commands in your existing `orange-pi` checkout:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

The change is a host update. MCU 1.0.8 supports this version. The separate firmware archive is `M300_SD.zip`. Fluidd uses port 4480. Its separate web installer accepts `--update-fluidd --port 4480`. The manual retains illustrations from beta.20.
