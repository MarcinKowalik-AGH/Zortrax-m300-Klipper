# M300 Classic RC11

RC11 makes the existing-installation updater update Klipper only by
default. The installed Fluidd files, user preferences and nginx
configuration are preserved. MCU 1.0.5 retains automatic synchronization
of the factory ID0 print-time counter introduced in RC10.

## Update the Klipper host

With the printer Ready, finish printing and other procedures and turn off
the heater targets. Run as the Klipper user:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

If MCU 1.0.5 is already installed, the host update completes the upgrade.
For a fresh flash, the full package includes `MCU/M300_SD.zip`.
[First installation](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.11/docs/en/FIRST_INSTALL.md) ·
[Full update guide](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.11/docs/en/INSTALL.md)

## Update or repair Fluidd when requested

```bash
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --update-fluidd --port 4480
```

This command uses the existing nginx site on 4480 and preserves
`config.json` and preferences. ZIP metadata changes no longer replace
matching usable website files. Newly installed static files receive
read permissions for nginx even with a restrictive installer umask.
When the local HTTP route can be verified, the installer tests the new
page and its JavaScript and restores the previous site if the test fails.

Open `http://<host-IP>:4480/` after the repair. HTTP 200 with no response
body indicates an empty page. Check the active site and its files with
the [Fluidd diagnosis and recovery guide](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.11/docs/en/INSTALL.md#diagnose-a-blank-or-unreachable-fluidd-page).
The beta.20 OLED illustrations document that historical build.
