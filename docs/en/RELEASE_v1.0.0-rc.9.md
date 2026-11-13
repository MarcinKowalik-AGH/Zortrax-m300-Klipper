# M300 Classic RC9

RC9 hardens the Orange Pi installer and automatic print-time synchronization.
Klipper checks that the pending transaction is durable before retrying a Flash
write. After the MCU verifies the commit, Klipper reads ID0 back and reconciles
the local journal. A brief failure to sync the journal directory during
reconciliation no longer hides the lifetime total. Pending sub-minute time
stays on the host until enough accumulates to write a full minute.

MCU 1.0.5 reduces work when checking a repeat transaction. It still checks both
bank transitions and the committed value. The development-only OLED RLE timing
command is removed from host and MCU; normal OLED transfer uses the same RLE
implementation. [MCU 1.0.5 details](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.9/docs/en/MCU_FIRMWARE_1.0.5.md).

## Installation and update

Use the [first-install guide](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.9/docs/en/FIRST_INSTALL.md)
on a fresh host. For an existing checkout, wait for Ready with no print,
movement or procedure in progress and both heater targets off:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

The updater validates the existing Fluidd endpoint on 4480. If the updated host
fails to start or reach Ready, it restores the prior host files. See the
[update guide](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.9/docs/en/INSTALL.md)
for cloning the deployment branch and checking the installation.

Install the MCU 1.0.5 application separately from `MCU/M300_SD.zip` using the
existing SD bootloader. An existing `factory_counter_backup:` setting remains
in effect. For first-time activation, see the MCU instructions above.
Use `ZORTRAX_HARDWARE_STATUS` to check synchronization and
`ZORTRAX_INFO REFRESH=0` to read print time.

## Verification

The software checks cover existing-host updates, first-install rollback,
counter reconciliation, and simulated interruption during MCU writes.
Automatic ID0 synchronization and interrupted Flash writes still require an
acceptance test on the actual board. The beta.20 OLED images document that
historical build. [Acceptance register](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.9/docs/pl/ACCEPTANCE_REGISTER.md).
