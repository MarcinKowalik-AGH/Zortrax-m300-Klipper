# M300 Classic MCU 1.0.3

[Installation](FIRST_INSTALL.md) · [RC7 notes](RELEASE_v1.0.0-rc.7.md) · [MCU release and SD ZIP](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.3)

MCU 1.0.3 adds a versioned command for the lifetime print counter on the
original M300 Classic STM32F103 board. The existing factory serial and
hardware revision remain readable. RC7 host accounting works with earlier
compatible MCU applications and retains pending time locally.

## Qualify the counter before enabling writes

Keep a full 256 KiB flash backup of this particular board and verify that it
opens and has the expected serial number. The RC7 host requires the full
image at the absolute path given by `factory_counter_backup:` in
`[m300_mcu]` before requesting an MCU write. This enables the feature for
that printer. `ZORTRAX_HARDWARE_STATUS` reports the state of the counter
transfer. Keep the backup for recovery.

The write is eligible during MCU preconfiguration. Pending counter time is
offered after the MCU starts unconfigured, including after
`FIRMWARE_RESTART` when the machine is idle. The procedure stages and verifies
the alternate block before activation. Software fault-injection and native
ARM validation exercise the transaction. Physical readback and controlled
power-loss qualification belong to the first hardware test on this release.

## SD application package

The firmware-only ZIP contains `M300APP.M3B`. Verify the release checksum and
use the application update procedure of the installed compatible M300 SD
bootloader. The application starts at `0x08008000`. When updating a working
Klipper host, perform the SD procedure while the printer is idle and cooled.
After the update, check `ZORTRAX_MCU_STATUS` for MCU version `1.0.3` and
`ZORTRAX_INFO REFRESH=0` for the factory serial and reported counter.
