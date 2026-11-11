# M300 Classic v1.0.0-beta.15 — PAUSE/CANCEL drain fix and four XY purge lines

Supersedes beta.14. Host print-control revision: `0.13.16.38-PRINT-DRAIN-XY-PURGE`.
No MCU, OLED, RLE, UART, SPI, motion limit, thermal guard or Fluidd frontend changes.

## PAUSE and CANCEL root cause

The previous `_drained()` called native `get_last_move_time()` on every 250 ms tick. In the pinned Klipper, that method primes an idle motion clock to estimated MCU time plus 250 ms. Repeated calls kept an empty queue permanently ahead of real time. PAUSE could remain in WAIT_PAUSE without parking; CANCEL could remain in WAIT_CANCEL with the native job still paused. START/END and individual park moves used the same helper.

The fix flushes only genuinely pending lookahead moves and otherwise observes `check_busy()` without re-priming the idle clock. A regression uses the exact four relevant ToolHead timing methods from the pinned Klipper, rather than the old passive test stub. It reproduces the previous failure before testing the corrected behavior.

Cancellation now closes the native file and clears the native pause after its worker has stopped, BEFORE waiting for physical motion to drain. Heater targets are turned off immediately. Safe parking remains conditional on known position, valid travel and clearance; a failed or impossible park does not keep the file paused. Cancellation does not resume the print.

PAUSE retains the configured M300 park X300 Y305, 5 mm separation subject to Z limits, hot-nozzle retraction, bed/motor retention, standby at 600 s and nozzle-off at 1800 s. RESUME still reheats saved targets and restores the saved native print state. No CR-10 S5 X509/Y515 coordinates are copied.

## Four start lines

The user's CR-10 S5 start pattern is now adapted to M300: two extruded Y lines, then two extruded X lines. Lane spacing is 0.5 mm; default height is 0.28 mm; a lifted transition separates the two axis pairs. Default PURGE length is 250 mm. The CR-10-style `PURGE=350` request is accepted but clipped to native travel minus a 5 mm far-edge margin. Filament is metered by actual segment length, with the original approximately 20 mm per 350 mm ratio.

The START_PRINT wrapper forwards PURGE and uses the nozzle/bed targets already set by the slicer when explicit temperatures are absent. Explicit EXTRUDER_TEMP/BED_TEMP override them. The current M300 homing and saved-mesh logic are retained; no CR-10-specific BLTouch or Z-tilt commands are introduced. Parser position modes, speed and flow overrides are restored even after a purge error.

## Upgrade

Use the usual verified `orange-pi` deployment only with the printer idle and Ready:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

The installer recognizes the beta.14 print module hash and migrates only the exact stock START_PRINT wrapper. Unknown local module edits still cause refusal; custom START_PRINT bodies are retained. No MCU flash is needed.

After installation, `PRINT_CONTROL_STATUS` must report revision `0.13.16.38-PRINT-DRAIN-XY-PURGE`. If the old job is stuck, do not update mid-print or try to resume it after restarting; safely abandon it and reach Ready first.

## Validation and limits

The host suite contains 721 tests, including 19 new timing, native endpoint, cancellation, four-line purge and migration regressions. The publishing pipeline also requires the existing repository, ARM, native Klippy FILEOUTPUT, frontend and package checksum validations. Local host tests passed before committing. Publication is gated on the matching successful CI run.

This is software validation with modeled MCU motion and temperatures, not a physical M300 test. First acceptance should check the four start lines, PAUSE park, RESUME return and CANCEL completion under supervision on a short test print. Existing thermal/homing safety rules remain active.
