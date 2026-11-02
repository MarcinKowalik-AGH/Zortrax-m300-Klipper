# Host restart and MCU connection — R16.2

[Installation](INSTALL.md)

Restarting the Klipper service or Orange Pi ends the host process, while the
printer MCU remains powered. The local guard shuts down its previous armed
session when the one-second heartbeat deadline expires. Native Klipper refuses
to configure an already shutdown MCU. This is why a subsequent explicit
FIRMWARE_RESTART could restore the connection. Setting `restart_method: command`
selects how to reset this UART MCU; it does not, by itself, add this recovery.

The existing port mapped an ordinary RESTART from Ready to FIRMWARE_RESTART.
That mapping did not cover a new OS process. R16.2 adds one read of the guard
after native identification and before native configuration. In native mode,
on `start_reason=startup` only, it requests Klipper's existing MCU restart when:

- a configured prior session has guard fault 1 (lost host heartbeat); or
- a rapid service restart finds the configured prior session still armed,
  with fault 0, before that heartbeat deadline has expired.

An active platform-connector fault blocks the attempt. Other guard faults,
including ADC faults, explicit DISARM, native shutdown/M112, and unknown codes,
remain explicit operator recovery cases. Invalid/missing responses never
trigger a blind reset. An unknown shutdown reported only by the native layer
is not reclassified as a communication failure.

The attempt uses the native `MCURestartHelper._check_restart` and requires
`[mcu] restart_method: command`. The installer selects that native reset method
for the M300 direct UART, preserving the serial path and baud rate. There is at most one automatic attempt per
host process, recorded in Klippy's internal restart arguments and the log.
A failed reset stops through native configuration checks. No retry daemon,
service restart loop, extra runtime polling, UART-rate change, or MCU change
is introduced. MCU R14.5 remains compatible. The lifecycle module issues no
heater, fan, movement, position-restore or ARM command. Existing native board
initialization runs after a fresh reset and checks fresh ADC/guard status;
old heater targets and homing state are not restored.

`ZORTRAX_LINK_STATUS` reports revision `0.13.16.2-LIFECYCLE-RECONNECT` and a
`startup_reconnect` record. `RECOVERED` means a fresh Ready followed the
automatic reset; the previous guard code is retained. `NO_OLD_ACTIVE_SESSION`
is normal for a cold MCU boot. `automatic_fault_clear_codes` lists only code 1,
`automatic_hardware_fault_clear=false`, and `automatic_action_resume=false`.
Logs retain `M300_HOST_START_RECONNECT` and `M300_HOST_START_RECONNECTED`.

The policy defaults on only for a native board. To explicitly disable it:

```ini
[m300_lifecycle]
reconnect_on_host_start: False
```

Acceptance on the printer, with heating and motion idle:

1. Confirm Ready, zero heater targets, and `ZORTRAX_LINK_STATUS` showing R16.2.
2. Run `sudo systemctl restart klipper.service`. It should return to Ready
   without a separate FIRMWARE_RESTART. Read the startup-reconnect decision.
3. Reboot only the Orange Pi, leaving the printer powered. Confirm the local
   Waiting screen while disconnected and automatic return to Ready afterwards.
4. Verify both heater targets remain zero and XYZ need homing again. Confirm
   native G28, 180C Z preheat, display and cooling still behave as before.

Software validation covers 17 lifecycle regressions and actual pinned native
restart/configuration helpers with simulated guard replies, plus the existing
real Klippy FILEOUTPUT suite. CI does not execute a physical UART reset or
Orange Pi reboot. Those remain the acceptance steps above.
