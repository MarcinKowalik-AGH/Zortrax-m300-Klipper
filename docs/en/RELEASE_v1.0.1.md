# M300 Classic 1.0.1 — lower the bed after Cancel

21 November 2026. **Host 1.0.1 + MCU 1.0.8**, project Fluidd on **4480**.
This correction supersedes 1.0.0.

Normal **Cancel** now uses the same bed-descent distance as `END_PRINT`:
up to **300 mm from the current position**, bounded by the configured Z maximum.
After the descent drains, the head parks at the configured corner, normally
X300 Y305, when the available clearance permits XY travel.

Heating is turned off and the native file and pause are closed before waiting
for the queued motion and subsequent bed descent. A slow Z axis receives the
actual planned travel time in its deadline, so a valid 300-second descent does
not fail the ordinary 120-second move timeout. Invalid homing or MCU guards
still prevent parking. Cancel with no active print does not move the printer.

The host suite contains **992 tests**, including cancellation from printing
and pause, Z-limit/clearance cases, a slow full descent and native Fluidd
endpoints. The real Klippy FILEOUTPUT cancellation scenario also verifies the
final bed height. The installer recognizes the exact 1.0.0 modules being replaced.

## Update

While idle and Ready with both heater targets off, run in your existing
`orange-pi` checkout:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Verify `ZORTRAX_INFO REFRESH=0`: host **1.0.1**, MCU **1.0.8**. The change
requires a host update; an installed MCU 1.0.8 does not need reflashing.
The full package still includes `M300_SD.zip` for printers needing that MCU.
For a separate Fluidd repair use
`python3 install-orange-pi.py --update-fluidd --port 4480`.

[Installation and rollback](INSTALL.md) · [First installation](FIRST_INSTALL.md) ·
[Print controls](PRINT_CONTEXT.md). The illustrated OLED catalogue retains
its explicitly labeled beta.20 baseline. Software tests do not record a new
physical-printer acceptance result for this change.
