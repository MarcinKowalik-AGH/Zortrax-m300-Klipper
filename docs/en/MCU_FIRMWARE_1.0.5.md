# M300 Classic MCU 1.0.5

[First installation](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.18/docs/en/FIRST_INSTALL.md) · [RC18 release notes](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.18/docs/en/RELEASE_v1.0.0-rc.18.md) · [Firmware SD ZIP and SHA-256 checksums](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/releases/tag/mcu-v1.0.5)

## Install the SD application

Check `M300_MCU_v1.0.5_SD.zip` against the release checksum. Extract
`M300APP.M3B` to the root of the update card and use the SD application
update procedure of the bootloader already on your M300 Classic. The
application starts at `0x08008000`. Remove the update file before subsequent
boots. With Klipper Ready, confirm `mcu_release: 1.0.5` in
`ZORTRAX_MCU_STATUS`.

## Read the counter

From Klipper RC10 onward, synchronization starts automatically with the existing
configuration. RC9 used `factory_counter_backup:` to authorize writes. RC10
accepts the old entry and synchronizes without reading a Flash dump.
Keep the existing print-time state and journal. With the default
`[m300_nvm]` path, the journal is
`~/printer_data/config/m300_settings.json.runtime-sync`.

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
verified write, `CURRENT` indicates there is no whole minute to transfer
and `AWAITING_IDLE` indicates a deferred write.
`ZORTRAX_INFO REFRESH=0` shows factory, local and combined print time. If the
sync state is `RECOVERY_REQUIRED`, keep the Klipper journal for reconciliation.
After recovery, confirm `factory_counter_banks: NORMALIZED` and
`factory_counter_pending: false`.

The 1.0.5 build removes the development OLED RLE timing command. The counter
ABI and motion/thermal write guards retain their existing behavior. Simulated
Flash interruptions exercise bank recovery, and an on-board power-loss test
remains pending.

### When the host cannot reconcile previous transfers

`RECONCILIATION_REQUIRED` suspends automatic counter writes. Printing remains available. RC17 keeps a second receipt alongside `.runtime-sync`. Preserve both with the printer settings. The synchronizer checks receipts before writing when one copy is missing or older.

Read `ZORTRAX_HARDWARE_STATUS`. If reconciliation remains necessary, use the command below only with an independently established accounting baseline. Supply the current serial, `factory_counter_observed_minutes`, and the whole minutes of this host's history already credited to ID0. Zero is appropriate only when the retained history has never been credited. An earlier `DISABLED` status does not establish what happened afterwards. Leave an uncertain baseline unresolved.

```text
ZORTRAX_COUNTER_RECONCILE SERIAL=<serial> MCU_MINUTES=<observed_ID0> COMMITTED_MINUTES=<previously_credited_host_minutes>
```

The command records the accounting baseline. The MCU writes any outstanding minutes during an eligible idle period. Verify the ID0 increase, normalized banks, cleared pending status and retention after a normal cold restart.
