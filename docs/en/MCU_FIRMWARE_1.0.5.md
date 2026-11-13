# M300 Classic MCU 1.0.5

[First installation](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.9/docs/en/FIRST_INSTALL.md) · [RC9 release notes](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.9/docs/en/RELEASE_v1.0.0-rc.9.md) · [Firmware SD ZIP and SHA-256 checksums](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.5)

## Install the SD application

Check `M300_MCU_v1.0.5_SD.zip` against the release checksum. Extract
`M300APP.M3B` to the root of the update card and use the SD application
update procedure of the bootloader already on your M300 Classic. The
application starts at `0x08008000`. Remove the update file before subsequent
boots. With Klipper Ready, confirm `mcu_release: 1.0.5` in
`ZORTRAX_MCU_STATUS`.

## Enable and inspect

In the existing `[m300_mcu]` section, set `factory_counter_backup:` to the
absolute path of the verified 256 KiB full Flash backup of this board. Klipper
checks the backup against the connected factory serial. Restart Klipper once
if you added or changed the setting. After that, Klipper synchronizes pending
whole minutes automatically when the printer is eligible.

The MCU reads the active factory ID0 record, checks its previous value,
writes the new value in the alternate settings bank and verifies it. The
board's factory serial and hardware revision occupy a separate Flash page.
The MCU requires idle motion, heaters off, current ADC data and a recent host
heartbeat. A stationary Z axis may remain energized. At a hotend temperature
of 50 °C or above, the MCU requires steady heatsink cooling. Klipper retains
time locally while the MCU defers the write.

Run `ZORTRAX_HARDWARE_STATUS` and inspect
`factory_counter_runtime_supported`, `factory_counter_sync`,
`factory_counter_banks` and `factory_counter_pending`. `SYNCED` reports a
verified result and `AWAITING_IDLE` indicates a deferred write.
`ZORTRAX_INFO REFRESH=0` shows factory, local and combined print time. If the
sync state is `RECOVERY_REQUIRED`, keep the Klipper journal for reconciliation.
After recovery, confirm `factory_counter_banks: NORMALIZED` and
`factory_counter_pending: false`.

The 1.0.5 build removes the development OLED RLE timing command. The counter
ABI and motion/thermal write guards retain their existing behavior. Simulated
Flash interruptions exercise bank recovery, and an on-board power-loss test
remains pending.
