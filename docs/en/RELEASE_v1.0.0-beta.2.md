Startup regression fix for **Zortrax M300 Classic**. Supersedes v1.0.0-beta.1.
The MCU remains R14.18; this correction does not require reflashing it.

## Cause and fix

Moonraker can subscribe to printer objects while MCU identification yields,
before `klippy:connect` has assigned the maintenance heater references. The
platform-heating status added in R29 accessed an absent `hotend` field, raising
`AttributeError` and shutting down Klipper on repeated restarts.

Initialize both heater references before connection. New regressions query
the status before connect, between connect/Ready and after an early shutdown.
The actual pinned Klippy test also queries all available printer objects
through its native webhooks query helper before connect and again after Ready.
There is no new MCU reset policy, heater/motion path or UART change.

## Recover an installed R29 host that is stuck in Shutdown

On the Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --repair-startup
```

Then issue **`FIRMWARE_RESTART` once from Fluidd**. The recovery mode verifies
the exact buggy runtime hash and traceback in the current Klippy session.
It applies the normal backed-up host migration while the service is stopped,
then starts the service. It performs no MCU reset, flashing, movement or
heating. Other shutdowns, unknown/custom runtimes, printing and paused prints
remain refused. This special recovery does not require Ready or an nginx update.

For a healthy existing M300, use the ordinary updater. For a blank host, use
the attached [English](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-beta.2/docs/en/FIRST_INSTALL.md)
or [Polish](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-beta.2/docs/pl/FIRST_INSTALL.md)
first-install guide and the complete beta.2 ZIP. Existing beta.1 assets/tags
are retained unchanged, with a superseded notice in their release description.

## Validation

641 host regressions, first-install and recovery installer tests, the existing
native workflows, the new actual early-webhooks status scenario and the
actual first-install FILEOUTPUT configuration. All normal public software,
STM32 ARM and Fluidd checks gate publication of the assets. These software
checks do not claim a physical UART recovery on the user's printer.
