# M300 Classic 1.0.2 — park after bed calibration

21 November 2026. Host **1.0.2**, MCU **1.0.8**. Supersedes 1.0.1.

After successful Zortrax leveling and confirmation of its result, and after a
successful 25-point Klipper mesh, the head parks at the configured print-control
corner, normally **X300 Y305**. The native coordinate frame is restored first.
The procedure retains at least **Z5 mm** clearance, checks that PC7 is open and
waits for parking motion to finish. It preserves E and does not perform a new
home. Failed or cancelled measurements do not request this success park.

The host suite contains **995 tests**. Both calibration paths are exercised;
additional regressions cover clearance before XY, closed contact and an
out-of-range park. Software results do not constitute a new physical-printer
acceptance. The earlier full bed descent after Cancel remains available.

## Update

While idle and Ready with heater targets off, run in the existing orange-pi checkout:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

Read `ZORTRAX_INFO REFRESH=0` afterward: host 1.0.2, MCU 1.0.8.
An installed MCU 1.0.8 needs no reflash. The full archive retains `M300_SD.zip`
for printers requiring that MCU. Separate Fluidd repair remains
`python3 install-orange-pi.py --update-fluidd --port 4480`.

[Installation](INSTALL.md) · [Operator guide](USER_GUIDE.md).
The illustrated OLED catalogue retains its explicitly labeled beta.20 baseline.
