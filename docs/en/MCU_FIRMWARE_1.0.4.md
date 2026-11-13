# M300 Classic MCU 1.0.4

[Installation](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.8/docs/en/FIRST_INSTALL.md) · [RC8 notes](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.8/docs/en/RELEASE_v1.0.0-rc.8.md) · [MCU release and SD ZIP](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.4)

MCU 1.0.4 exposes factory counter operations during normal configured idle operation. `m300_factory_counter_query_runtime` returns the serial, active bank and ID0 value. `m300_factory_counter_commit_runtime` checks the previous value, updates ID0 in the alternate bank and verifies the change. The host calls these operations automatically after enabling synchronization. The factory serial and hardware revision remain on a separate Flash page.

## Enable and inspect

In the existing `[m300_mcu]` section, set `factory_counter_backup:` to the absolute path of the verified 256 KiB full Flash backup of this board. Klipper checks the backup against the connected factory serial. The MCU requires idle motion, heaters off, fresh ADC data and a recent host heartbeat. A stationary Z axis can remain energized. At a hotend temperature of 50 °C or more, the MCU requires steady heatsink cooling. Klipper retains unsynchronized time while the MCU defers the operation.

In `ZORTRAX_HARDWARE_STATUS`, `factory_counter_runtime_supported` confirms that the connected MCU exposes the runtime commands. `factory_counter_sync` reports `SYNCED` after verification or `AWAITING_IDLE` when the write is deferred. `ZORTRAX_INFO REFRESH=0` shows the live aggregate. If the synchronization status is `RECOVERY_REQUIRED`, keep the saved Klipper journal so the interrupted transaction can be reconciled. After an interrupted write, check `factory_counter_banks: NORMALIZED` and `factory_counter_pending: false` before starting the factory application. Ordinary stock launch via the existing bootloader was already confirmed by the operator. The RC8 Flash write and power-cut path still needs physical validation.

## SD application package

The firmware-only ZIP contains `M300APP.M3B`. Verify the release checksum and install it using the application-update procedure of the existing M300 SD bootloader. The application starts at `0x08008000`. After installation, confirm `1.0.4` in `ZORTRAX_MCU_STATUS`.

The Classic MCU build reserves a 68 KiB application linker region for the runtime counter code. This region fits in the existing bootloader application slot below `0x0803A000`. The linker uses the existing 20 KiB SRAM budget.
