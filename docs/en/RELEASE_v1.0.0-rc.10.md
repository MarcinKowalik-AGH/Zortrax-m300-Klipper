# M300 Classic RC10

Klipper automatically synchronizes the M300 Classic print-time counter with
MCU 1.0.5. When the printer is idle and a full pending minute has accumulated,
Klipper computes a new total and sends it to the MCU. The MCU checks the
on-board factory record and the write conditions, updates ID0 in its own
Flash and verifies it. Klipper reads the result back, reconciles its journal
and keeps the remaining seconds for the next transfer.

## Update an existing installation

With the printer Ready, finish the print and procedures and turn off both
heater targets. Run as the Klipper user:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

If MCU 1.0.5 is already installed, update the host only. For the paired MCU
application, use `MCU/M300_SD.zip` in the full RC10 package. RC10 accepts
and ignores the old `factory_counter_backup:` setting. It does not need a
Flash dump or a change to `printer.cfg`. Keep the original host print-time
state and synchronization journal during an update.

[First installation](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.10/docs/en/FIRST_INSTALL.md) · [Full update guide](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.10/docs/en/INSTALL.md) · [MCU and counter status](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.10/docs/en/MCU_FIRMWARE_1.0.5.md)

## Verify the counter

In Fluidd, run `ZORTRAX_HARDWARE_STATUS` for the sync and bank state and
`ZORTRAX_INFO REFRESH=0` for factory, pending local and combined print time.
After a successful transfer, `factory_counter_sync` reports `SYNCED`. Firmware
without the runtime counter commands can still accumulate new print time on
the host.

Software tests exercise synchronization and journal recovery. Automatic
ID0 writes and recovery after a power loss still require acceptance on the
physical M300 Classic. The beta.20 OLED pictures show their historical build.
[Acceptance register](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.10/docs/pl/ACCEPTANCE_REGISTER.md).
