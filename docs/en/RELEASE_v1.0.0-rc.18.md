# M300 Classic RC18

RC13–RC17 could replay a pending factory-counter transfer while identifying a board in shutdown. The MCU accepts reads in shutdown. The write command receives no response. RC18 reads the Z profile during identification and replays the transaction only after Klipper checks the guard, before it sends MCU configuration. Keep the existing counter journal. The host confirms the target and bank by reading the board.

## After a rolled-back installation

Save klippy.log and the output of `ZORTRAX_LINK_STATUS` and `ZORTRAX_MCU_STATUS` before resetting. If the previous host reports `RECOVERY_REQUIRED` and a missing `m300_factory_counter_result` before MCU identification completes, open the RC18 package directory on the Orange Pi and run:

```bash
python3 install-orange-pi.py --recover-counter-startup
```

The installer checks this specific state, starts the corrected host and requires Ready. For a hardware fault, inspect `previous_guard` in the `M300_HOST_START_GUARD` entry in klippy.log. See the [installation guide](INSTALL.md) for a normal update. Once Ready, run `ZORTRAX_HARDWARE_STATUS` and `ZORTRAX_INFO REFRESH=0`. Read the counter again after a normal power cycle to confirm persistence.

The MCU release is 1.0.5. The first-install package includes `MCU/M300_SD.zip`. Fluidd repair uses the separate option `--update-fluidd --port 4480`. OLED illustrations are from beta.20.
