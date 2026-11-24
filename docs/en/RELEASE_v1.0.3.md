# M300 Classic 1.0.3 — mesh cancellation and planned restart

24 November 2026. Host **1.0.3**, MCU **1.0.8**. Supersedes 1.0.2.

A planned restart keeps the healthy MCU heartbeat running while native Klipper
finishes its queued motion. New motion/heating requests are refused during
this drain. Supervision ends on disconnect or shutdown; a 120-second deadline
bounds a stalled restart. Missing/stale state or an MCU fault is never cleared.
`SAVE_CONFIG` and `RESTART` request a firmware restart as well, so a new host
must establish a new MCU ARM session rather than inherit an armed old session.

Fluidd Cancel reaches an active 25-point mesh even while its G-code command
holds the mutex. It invalidates the measurement and switches heater targets off.
The existing cancellation worker waits for the command to unwind and the native
motion queue to drain before parking. The next file remains blocked until this
handoff completes. Interrupted contact/homing motions retain their safety stops.

The regression suite includes 999 host tests, including real-parser restart,
mesh cancel followed by replacement-file preparation, heater ownership release,
and upgrade/rollback of the previous published parser. These are software
checks; no physical printer was operated for this change.

## Thermal fault remains a separate hardware acceptance item

The supplied log also records `Heater extruder not heating at expected rate`:
a 230 C demand with reported PWM 100% and a falling reading around 218–215 C.
The log alone does not identify whether the cause is physical heating/cooling
or another runtime condition. This release does not claim to resolve that fault
and does not relax `verify_heater`, MCU watchdogs, ADC or thermal limits.

## Update

Wait for idle Ready and heater targets off. In the existing deployment checkout:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Confirm `ZORTRAX_INFO REFRESH=0`: host 1.0.3, MCU 1.0.8. No MCU reflash
is required when 1.0.8 is already installed. After cooling and checking the
heater assembly, validate mesh → SAVE_CONFIG → Ready and Cancel → complete
park → new file on the physical machine. Retain the resulting log.

Separate Fluidd repair: `python3 install-orange-pi.py --update-fluidd --port 4480`.

The full package retains `M300_SD.zip` with MCU 1.0.8 for printers requiring a firmware update. The illustrated OLED manual retains its explicitly labeled historical beta.20 baseline.
