# M300 RC7 print-time counter

RC7 records the model-printing phase of completed, cancelled and interrupted jobs. The standard M300 sequence excludes preheat, its purge lines, pauses and parking. During model printing, the clock suspends for blocking `M109`, `M190` and `TEMPERATURE_WAIT` after queued motion drains. With custom G-code, the first deposition command starts the clock, so a slicer-supplied prime line can start it early and a dwell inside the model phase counts. `Information` shows the factory serial and the combined time without counting synchronized minutes twice. `ZORTRAX_INFO` also reports the Klipper-only time and time awaiting synchronization. A power cut can lose the interval since the last durable Orange Pi checkpoint, scheduled every 15 seconds during a print.

The optional MCU 1.0.3 transfer writes full minutes to the factory ID0 record at startup, before the MCU accepts print configuration. Sub-minute time stays on the host. The existing factory total is the starting value. RC7 adds model-print time and does not accrue printer uptime. The host saves a serial-bound transaction before requesting a Flash write so a reconnect can confirm or retry it. The firmware alternates the OEM settings banks at `0x0803E800` and `0x0803F000`. It reads back the destination, verifies activation, and only then erases the previous bank. The new bank retains the previous ID0 as an earlier record and preserves the other effective factory settings. The factory serial and hardware record are in the separate page at `0x0803F800`.

## Update and enable

While the printer is idle and Ready, update the existing Orange Pi checkout:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Host accounting works with the existing MCU. For Flash synchronization, follow the board’s backup procedure and make two independent readouts from `0x08000000` through `0x0803FFFF`. Each raw file must contain 262144 bytes. Compare them with `cmp` and retain a copy and its SHA-256 off the printer. The host validates the backup’s size, vectors, factory serial and settings banks before permitting synchronization. [Original Flash backup procedure](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Boot-Loader/blob/156daf4d1d5f14d2f0e553a64b352397be397745/docs/en/v1.4/original-backup.md).

Install the MCU 1.0.3 application from `MCU/M300_SD.zip` using the [separate MCU instructions](MCU_FIRMWARE_1.0.3.md). Then add the backup path to the existing printer section on the Orange Pi:

```ini
[m300_mcu]
factory_counter_backup: /absolute/path/to/m300-full-flash.bin
```

Use `FIRMWARE_RESTART` while idle to synchronize accumulated time. `ZORTRAX_HARDWARE_STATUS` shows the state of the transfer. Keep the backup and the host’s runtime files together with the configuration. The beta.20 OLED illustrations remain historical references.

## Return to stock firmware

Before starting factory 1.3.1, use the matching RC7 host and MCU to finish any pending transfer. In `ZORTRAX_HARDWARE_STATUS` verify `factory_counter_banks: NORMALIZED` and `factory_counter_pending: false`. If a cut interrupts activation or erasure, the stock firmware can erase both banks when it sees two active headers or certain invalid headers. If RC7 cannot normalize the pair, verify and restore the saved NVM banks with the service procedure before booting the stock application. The application restore alone leaves the settings banks as they are. An MCU power-cut test and physical stock return remain pending.

[M300 Drive NVM audit](https://drive.google.com/file/d/171nuuE6n2x6FsBrVq8lLBb6I_-sS_4p8/view) · [Bootloader 1.4 stock restoration](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Boot-Loader/blob/156daf4d1d5f14d2f0e553a64b352397be397745/docs/en/v1.4/installation.md#restore-app-before-normal-use)
