Host corrections for **Zortrax M300 Classic**. Supersedes v1.0.0-beta.2.
The MCU stays at R14.18 and UART at 750000. No MCU reflash is needed.

## Precision Z contact/release

The supplied MCU trace shows PC7 opening during release arming, before the
first Z step. The previous code treated this like a premature approach
contact and shut down the printer. The new code discards that entire
contact/release pair, retreats the bed by 1 mm, waits and verifies opening,
then retries the current sample at most twice. Retries share the original
45-second sample deadline and all existing native motion, temperature and
session guards. Five valid contact/release references are still required;
the fifth valid release defines Z. A zero-step release never defines Z.

Premature approach contacts, a contact remaining closed after retreat,
exhausted retries and native limits still fail the procedure. The error
notice now retains the original precision-reference failure reason.

## OLED transaction boundary

Re-claiming the OLED cancels the MCU display FIFO. The host previously kept
waiting for those cancelled ACKs, guaranteeing a timeout when re-claiming
with outstanding work. The old adapter reproduces that failure in a new
regression test. The corrected adapter discards only the old display window
and serializes the claim on the same native command queue as old writes and
the new initialization. Late ACKs cannot advance the new transaction or
replay menu actions. Printing, heaters and motor state are not resumed or
reset by display recovery.

The supplied 20:44 timeout has no accompanying UART retransmissions, invalid
bytes or MCU shutdown. The old log does not contain the display queue/lease
snapshot needed to prove which event initiated that particular timeout.
This release fixes the independently reproduced re-claim bug and adds a
bounded `M300_OLED_TIMEOUT` log snapshot before missing-token evidence is
cleared. It does not label the hardware symptom resolved without a printer
test. Genuine MCU display faults still require an explicit firmware restart.

## Update an installed printer

With Klipper Ready and idle, run on the Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

The existing updater backs up and installs the host package and restarts its
service. Do not reinstall the MCU firmware for these host changes. Verify
`ZORTRAX_OLED_STATUS` reports `0.13.16.31-OLED-QUEUE-SYNC`. Then test one ordinary
`G28`. If the OLED timeout recurs, capture the following before restarting:

```gcode
ZORTRAX_OLED_STATUS
ZORTRAX_LINK_STATUS
ZORTRAX_DISPLAY_STATUS
```

For the earlier R29 startup `AttributeError`, the narrowly guarded
[`--repair-startup` procedure](RELEASE_v1.0.0-beta.2.md#recover-an-installed-r29-host-that-is-stuck-in-shutdown)
remains available. It does not authorize recovery from a probe safety fault.

## Validation

655 host tests include native pinned `HomingMove` scenarios for Z400/Z800,
bounded retry exhaustion, cancellation, shared deadline, unchanged approach
guards, and display re-claim with cancelled/late ACKs and pending contrast.
Publication also requires the full native FILEOUTPUT, installer, STM32,
timing, thermal and Fluidd checks. Software validation does not substitute
for physical probing or OLED acceptance on the printer.
