# Procedure error reporting audit — 2026-11-07

Scope: the current native M300 host, all supplied operator procedures/macros,
compatibility fault boundaries, and their existing MCU safety bindings. Source
baseline: `7844e5de5dec0f719131f911aa0f27e11dabe81f`. No physical printer was
operated during this audit. The software tests model faults and also execute
the pinned real Klippy in FILEOUTPUT; they are not hardware qualification.

## Contract

The procedure owns detection, cancellation, resource revocation and cleanup.
It reports an actual failure to `m300_error_codes.report`; `m300_errors` owns
identity, cause, history, Fluidd, OLED and metadata for the existing MCU error
ABI. Acknowledgement never resets a latch, arms hardware or resumes a job.
The console observer is a fallback for native commands, not the only path for
asynchronous failures. Input/preflight rejections do not create hardware faults.

The MCU independently owns its existing local guard, heater-off/shutdown,
offline cooling, local error screen and alarm. This host-only correction does
not change the MCU ABI, application release, firmware thresholds, step timers,
UART, fan hysteresis or motion speeds. MCU R14.18 remains compatible.

## Findings and corrections

1. Native Z had an initial PC7 release check but none between its two coarse
   probe passes. Add a check before each pass, with exactly one bounded extra
   Z retreat of at least 5 mm if the second pass starts closed. Keep the native
   no-movement guard. A permanent short or insufficient travel aborts before
   another approach. Do not move in the first pass's artificial force frame.
2. Both the shared observer and procedure presenter opened the same error.
   Deduplicate automatic presentation by error ID; preserve explicit refresh.
   Procedure shutdown invalidation cannot close an already displayed fatal
   notice without publishing a replacement.
3. Filament, job, fan-output, protective fan-test termination, thermal and
   compatibility maintenance paths lacked direct notification. Report at the
   actual fault boundary, before yielding cleanup or shutdown consequences.
4. Native print errors without console output were not necessarily visible.
   Observe `print_stats.note_error` while preserving its original callback.
   Add native PID-interruption and file-open/list messages to the conservative
   observer. Busy/invalid-parameter errors remain ordinary rejections.
5. A failed SD snapshot read could be relabelled as a model-format error by a
   parent importer. Retain the first typed diagnosis on the same exception;
   later native text cannot reclassify the identical owner-reported reason.
6. Generic shutdown consequences could replace an earlier unnumbered fatal
   cause. Keep that original cause; allow a more specific native/local cause
   to refine a generic one. Specific MCU faults retain their priority rules.
7. A generic nonfatal operational failure used a shutdown title. Present it
   as `Procedure failed`, with the actual reason and no fabricated OEM code.
8. Persistence and optional display failures could stay only in logs/status.
   Report failed settings/calibration writes, job-counter persistence, OLED
   transport timeouts and the first reported MCU OLED DMA fault.
9. A reporter exception could interrupt the very cleanup it describes.
   Make reporting best effort. Thermal/compatibility-maintenance shutdown is
   also requested if heater-off cleanup itself raises an exception.

## Procedure coverage

| Procedure / boundary | Detection and reporting | Safety / completion behavior |
|---|---|---|
| G28 X/Y, HOME_XY | Native homing exception → motion report; typed XY endstop faults use 034 | Existing native stopping, motor-off and failed-session state |
| G28 Z/ALL, HOME_Z/ALL | Native coarse pass checks, unchanged no-movement guard, five-reference faults → motion report; contact faults use 042 | Bounded initial clearance and one second-pass recovery; persistent short aborts; owned heat restored/off by outcome |
| OEM Platform leveling | Calibration `_fault` reports actual contact/calibration/thermal cause | No partial observation committed; existing cleanup and required shutdown retained |
| Native pad Bed Mesh | Measurement/preparation exceptions report before failure cleanup | Heaters off on failure; invalid coordinate frame revoked; result published only on success |
| Platform Up/Down and held-knob jog | Native maintenance `_fault` plus native release stop | Existing bounded travel, physical release/STOP and ownership revocation retained |
| Load / Unload / Change / Purge | Material `_fault` reports original failure before shutdown | Pending transport revoked, owned heat off, no automatic print resume |
| Manual hotend heating / cooldown | Native maintenance faults report directly; native thermal safety remains authoritative | Current heat ownership and cleanup retained |
| Native hotend/bed PID | Native errors via conservative console observer; thermal shutdown via original native reason | Native PID math/controller restoration and explicit SAVE_CONFIG retained |
| Commissioning thermal checks/PID compatibility | Actual `stop(fault=True)` reports; report failure cannot suppress shutdown | Both native heater targets/PWM cleared; cleanup exception still requests shutdown |
| Upper/lower fan test and Back/End | Output failures report before protective shutdown; protective/stale-status test termination reports a nonfatal failure | Leases released; current cooling floor wins over a cached OFF |
| Automatic hotend fan callback | Output exception uses the fan failure boundary | Existing 50°C ON / 45°C OFF policy and callback cadence retained |
| Native file print / pause / resume / cancel | Native print error callback reports even without console output; native shutdown observer retains root cause | Native print state and error G-code unchanged; reporting never resumes |
| Compatibility job / feeding lifecycle | Job `_fault` and accepted `file_error` report directly | Queues/context invalidated, heat off and existing shutdown policy retained |
| Local immutable model read / deferred close | Explicit file-read/close failure notification | Existing shutdown still requested; no automatic restart or replay |
| Physical SD / FAT / import / binary Z-code | Existing SD `_end(error)` and model-import reports, with typed nested-cause preservation | Checked immutable snapshots, cancellation generations and close ownership retained |
| Empty physical-SD Models browser | Explicit 101 report | Catalogue inspection and empty list do not operate hardware |
| NVM settings / calibration / job counters | Actual persistence failures report; invalid/stale requests remain preconditions | Transaction/identity checks retained; failed writes do not publish new values |
| Settings / brightness / light / buzzer / language / sorting / Help | Valid actions and input rejection remain ordinary UI/commands; actual storage failure goes through NVM | No new fault or MCU write merely from viewing a page |
| OLED transport / DMA / dim / sleep | Timeout, MCU DMA fault and optional display initialization failure report | Optional UI failure alone does not stop motion or heating; existing transport scheduling retained |
| TEST_ZORTRAX_XY and standard native calibration aliases | Native command errors / MCU shutdown observer | Existing native timing and motion guards retained; no new speed clamp |
| MCU ADC / platform input / heartbeat / communication / M112 | Existing local record plus native analyze_shutdown and metadata reconciliation | Local safety independent of host UI; fatal ACK cannot clear latch |

## Validation and limits

New regression tests reproduce the reported second-pass no-movement error
with the old behavior, then verify bounded release on Z400 and Z800. They also
cover a permanent short, late contact after a successful precheck, absent Z
travel, restart during query and unrelated owner events.

Procedure-boundary tests inject material, fan, thermal, native print, storage
and display failures; verify original causes, one notice, cleanup/shutdown,
and reporter failure isolation. Repository checks still require identical
OLED transport/scheduler methods after removing only the exact new reporting
statements. The full workflow rebuilds ARM and runs the existing guard,
cooling, timing, migration, menu and real Klippy FILEOUTPUT checks.

Startup configuration/schema/ABI errors can precede this service or a working
MCU connection. Native Klipper's configuration error remains authoritative in
that case; an unavailable MCU is not promised a new screen. Plain busy/input
rejections are intentionally not OEM hardware diagnoses. The project still
has no additional qualified jam/gear/cable-location sensors. Physical release,
measured temperatures and hardware acceptance remain to be tested on the
printer. Test counts and exact results are recorded in the Actions validation
artifact for the commit containing this audit.
