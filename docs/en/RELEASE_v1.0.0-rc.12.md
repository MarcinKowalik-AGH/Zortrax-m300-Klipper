# M300 Classic RC12

RC12 adds a recovery path for a recognized M300 Fluidd site whose
`index.html` and JavaScript entry point were emptied. The installer verifies
the manifest and matching startup assets, restores the static files from
the release and preserves `config.json`. Automatic print-time synchronization continues
with MCU 1.0.5. Klipper sends pending whole minutes when the printer is idle
and the MCU can safely update the factory ID0 record.

## Update Klipper

At Ready with printing and procedures finished and heater targets off,
run as the Klipper user:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

This is the host update. If MCU 1.0.5 is already installed, the host update
completes the upgrade. For a fresh MCU flash, the full release includes
`MCU/M300_SD.zip`. [First installation](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.12/docs/en/FIRST_INSTALL.md)

## If Fluidd is blank, recover it first

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --update-fluidd --port 4480 &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Open `http://<host-IP>:4480/` to check that Fluidd loads. In the console, run
`ZORTRAX_MCU_STATUS`, `ZORTRAX_HARDWARE_STATUS` and `ZORTRAX_INFO REFRESH=0`.
To verify persistence after a normal print, check for `SYNCED` and an increase
in the factory counter when idle. Read the value again after the next normal
power cycle. [Update and verification guide](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.12/docs/en/INSTALL.md)

## Verification scope

The software checks exercise the packaged installer's web repair and load the
recovered site in a real browser. The Flash write and interrupted-write recovery
are simulated. The read-back and persistence checks above still require the
physical printer. The OLED illustrations from beta.20 remain a historical
reference.
