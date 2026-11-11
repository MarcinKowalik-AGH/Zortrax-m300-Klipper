OLED ACK-loss correction for **Zortrax M300 Classic**. Supersedes beta.3.
MCU R14.18, UART 750000 and OLED SPI 4500000 remain supported unchanged.
Install this host update on the Orange Pi; no MCU reflash is required.

## Why the panel stopped

In the supplied 21:34 log, `bytes_invalid` increases from 0 to 10 in the same
second that OLED acknowledgements stop advancing. Host token 7904 is pending;
two later ACKs have been ignored. The MCU subsequently reports that its DMA
queue is empty with no display fault, while the host remains permanently
stopped. The log does not identify the electrical or driver cause of those
invalid incoming bytes.

The old host required every individual ACK in strict sequence. Losing an
earlier return packet made it discard later valid completion notifications.
The beta.3 queue re-claim correction addressed a separate bug; it did not
handle this loss of return packets during normal operation.

## Changes

* For the existing four-slot MCU DMA FIFO, an ACK for a token currently in
  the host window confirms that token and its earlier outstanding operations.
  The MCU emits it only after completing SPI transfers in FIFO order. This
  recovers missing earlier notifications without repeating display writes.
  Unknown, stale and already-retired tokens remain ignored. Reset and delay
  barriers remain intact, including unsigned token wrap.
* Losing the final ACK has no later token to prove completion. With fresh,
  healthy MCU display status and a healthy lease, the host can re-claim and
  fully initialize **only the OLED** once per 30 seconds. Another timeout
  during that initialization stops recovery rather than creating a reset
  loop. Real MCU display faults, stale status and printer shutdown prevent
  automatic recovery.
* `ZORTRAX_OLED_REINIT` can recover a host ACK timeout while MCU status is
  healthy. Actual MCU display faults still require explicit firmware restart.
  Host ACK-loss messages now request display resynchronization rather than
  claiming that an MCU reset is always necessary.
* Status exposes `recovered_acks`, `ack_recoveries` and
  `ack_recovery_active`, retaining the timeout snapshot for diagnosis. `acked`
  counts confirmed operations, including those proven by a later FIFO ACK.

There is no automatic restart of Klipper or the MCU, no heater/motor action,
and no replay of encoder events or menu confirmations during OLED recovery.
Persistent transmission corruption still requires diagnosis; it is not
declared fixed by this host-side recovery change.

## Update

With Klipper Ready and idle, run on the Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Then, in Fluidd:

```gcode
ZORTRAX_OLED_STATUS
```

Expect `host_revision: 0.13.16.32-OLED-ACK-RECOVERY`. The lease module remains
`0.13.16.31-OLED-QUEUE-SYNC`. Test one `G28`, navigate with the knob, then
leave the panel idle for 5–6 minutes and wake it. If a panel ACK timeout still
persists, retain OLED/LINK/DISPLAY status and the log before any restart. On
this version, a healthy MCU also permits `ZORTRAX_OLED_REINIT`.

## Validation

673 host tests include a reproduction of the old missing-ACK deadlock,
recovery on later FIFO tokens, wrap/duplicate/unknown-token cases, exact SPI
write equality under heavy ACK loss, missing final ACK, bounded OLED-only
recovery, rate limiting and hardware/shutdown refusal. The actual MCU C
overlay is also exercised with four DMA slots across token wrap to verify
FIFO completion order and that IRQ alone does not acknowledge a transfer.

The complete public native Klipper, installer, thermal, timing, STM32 and
Fluidd checks gate publication. These are software and register-model tests,
not a claim of physical acceptance on the printer.
