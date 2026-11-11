# R16.7 — Maintenance correctness, code quality and performance

Date: 2026-11-03 (Europe/Warsaw). Model: M300 Classic.
Stage: software validated; supervised physical acceptance pending.

## Delivered behavior

Maintenance contains Back, Autocalibration, Heat the extruder, Move the
platform up, Move the platform down, and Fan test. The Fan test submenu is
Back, Toggle upper fan, Toggle lower fan. Existing Material and M07 procedures
remain on the R16.6 implementation and are regression-tested together.

| OLED item | Fluidd / Klipper macro | Behavior |
|---|---|---|
| Heat the extruder | ZORTRAX_HEAT | Target 260°C; ready from 258°C; original completion dialog; confirm to turn off and return |
| Move the platform up | ZORTRAX_PLATFORM_UP | Panel hold moves negative native Z; release stops issuing quanta; macro uses a finite distance |
| Move the platform down | ZORTRAX_PLATFORM_DOWN | Panel hold moves positive native Z; same limits/ownership and finite macro route |
| Fan test | ZORTRAX_FAN_TEST_START | Save current requests and open the original interactive submenu |
| Toggle upper fan | ZORTRAX_FAN_UPPER | Channel 1 / PE14; toggle 0 / 150⁄255 request, with native automatic cooling as a floor |
| Toggle lower fan | ZORTRAX_FAN_LOWER | Channel 0 / PE13; toggle 0 / 150⁄255 request |
| Back from Fan test | ZORTRAX_FAN_TEST_END | End session; restore saved lower request and CURRENT upper native thermostat policy |

The four new macros join the existing seven procedure macros in Fluidd's
ZORTRAX M300 group. The obsolete five-second commissioning fan test remains
separate and closed in native mode. The new OEM test is interactive until
Back or the existing bounded service deadline.

## Original firmware evidence

The supplied firmware 1.3.1 application has SHA-256
`11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75`.
27,982 recovered instruction comments were checked against these application
bytes. The recovered register-C was freshly compiled and executed on the host;
this is instruction-semantics reproduction with declared peripheral/UI models,
not ARM binary emulation or physical MCU execution.

| Recovered routines | Independent reproduction |
|---|---|
| Fan entry 0x08014940, toggles 0x080157f0 / 0x080157c8, event 0x08014980 | Three sessions with different saved requests; entry off, independent 0/150 toggles and saved-request restoration |
| Fan setters 0x0800c0ac / 0x0800c0c4 | Actual request bytes and inverted TIM1 CCR3/CCR4 writes checked, including 255 minus request |
| Fan-menu renderer 0x08018c4c / 0x0801846c | Twelve complete 8192-byte English frames: all 4 enable states × 3 selected rows, byte-for-byte equal |
| Heat helper 0x08015ed0 | Ready and interrupted branches: 260/258, original completion descriptor when ready, target off and Maintenance return |
| Platform hold dispatcher 0x08015d1c | Fifteen cases: only the two platform rows, while pressed in Maintenance, call the up/down motor boundary |

The fan renderer uses the recovered 13-pixel font, label coordinates,
Enabled/Disabled wording and selection marker. This path has a menu and state
fields; no separate fan-test animation or picture was found. The existing
110 original dialog frames and 20,002 screw-turn vectors remain regression
references for M07/material services. Private firmware images are not shipped.

## OLED and Fluidd consistency

One service owner and one English presentation model supply both interfaces.
Fan buttons carry the same labels and Enabled/Disabled state as OLED rows.
They share a token/phase-derived view identity. Stale or duplicated buttons
cannot toggle a newer phase. The physical display preserves the selected fan
row after a toggle and only acts on an acknowledged current frame.

Heat uses the same original text/font/sprite descriptor and confirmation on
both routes. Platform hold stays on its acknowledged Maintenance row; Fluidd
names that exact selected action. A finite platform macro selects the matching
OLED row. The firmware has no separate platform-progress illustration in this
path, so none is presented as OEM. Live transport and local MCU fault-display
behavior remain under their existing owners.

A warm, targeted or invalidly measured upper heater cannot be cooled less by
the test. The display says (Cooling) and Automatic upper-fan cooling; Fluidd
uses those same words. These are explicit port status additions. Requested
duty is not RPM or measured airflow; no tachometer result is manufactured.

## Correctness and code-quality evaluation

| Area | Evaluation / correction |
|---|---|
| Ownership | Existing native fan queues, heater_fan thermostat, motion/heater objects and MCU cooling remain owners; no raw GPIO/PWM owner introduced |
| Scope of interception | Temporary fan/motion/heater command wrappers exist only during the test and restore exact native handlers afterward |
| Entry | Reject active/paused native prints, other services, queued movement, pending native fan requests, protective/stale MCU status and FILEOUTPUT before actuation |
| Exit | Back, leaving the page, timeout and lifecycle revoke the session; fault/stale status cannot replay old duty |
| Upper restoration | Recompute current thermostat policy rather than restoring an old OFF or old PWM; native automatic callback cannot lower an enabled cold test |
| Error evidence | Fixed loss of fan and Maintenance fault reasons at shutdown; same reason remains visible in the shared view and Fluidd prompt with no available action |
| Navigation | Fixed generic cursor reset to Back after a fan toggle; retain the source's in-place selection |
| Shared data | One coherent cached MCU snapshot per fan-status poll; no repeated decoding of the same telemetry |
| Rendering | Pure, bounded cached rendering; all cold fan-menu states have independent original pixels as references |
| Existing work | M07, ordinary Z, material transport/Change, PID/E, sensor includes, hardware scale and deliberate geometry retain existing regression coverage |

The existing NativeServiceLease is reused for exclusive manual ownership.
The native fan adapter and pure presentation module are separate from legacy
commissioning logic. No per-step hook, additional global velocity cap or new
MCU interrupt work was added. Current runtime/release documentation is English.
The generic renderer, OLED SPI/UART transport, MCU timers and sleep policy
retain their existing implementations.

Intentional OEM differences remain explicit: the upper thermostat/MCU cooling
has priority; upper restoration follows CURRENT native policy; the host adds
service deadlines, finite native Z quanta, real homing requirements, request
queue checks and stale-view protection. The source's raw continuous motor loop
and unconditional upper-OFF entry request are adapted to those native owners.

## Performance measurements

The following local microbenchmark uses Python 3.12.14 on x86_64, with
simulated telemetry/output boundaries, 100 warmups and 4,000 samples per hot
path (12 unique cold frames). GC is disabled only during sampling. Baseline
is the actual R16.6 fan-status implementation; no new service is run on hardware.

| Path | Median, µs | 95th percentile, µs |
|---|---:|---:|
| R16.6 fan status | 3.856 | 4.286 |
| R16.7 idle fan status | 3.014 | 3.215 |
| R16.7 active fan status | 3.586 | 3.925 |
| Shared active procedure view | 27.581 | 58.787 |
| Cold fan-menu composition | 404.865 | 454.934 |
| Cached fan-menu bytes | 0.150 | 0.170 |

Fan-status reads changed deterministically from **6 to 1 cached MCU snapshots
per poll** (83.3% fewer). These are host object reads, not six UART transactions.
The exact absolute timings depend on this executor and are not Orange Pi
measurements. Both versions receive the same simulated telemetry. The new
status also reports the native upper cooling floor.

Unchanged fan-menu frames reuse cached bytes; the frame cache holds at most
24 entries (192 KiB of framebuffer payload plus Python overhead). The idle
fan test schedules no periodic work. During an active test its guard checks
cached MCU status every 0.1 s. Native heater_fan keeps its own 1 s thermostat
callback. Existing platform tick/freshness are 0.05/0.75 s and the maximum
already queued quantum is 0.1 mm. Receipt of release issues no new quantum;
a queued one drains. Lost-input detection depends on the cooperative reactor
and does not prove a hard real-time physical stop latency.

No Orange Pi CPU load, UART/DMA throughput, physical RPM, actual duty waveform,
MCU interrupt latency or printer travel time was measured. Those require a
supervised device test. The benchmark script is included and CI records its
own current-build measurements without imposing a machine-dependent timing
threshold.

## Validation and test release

All 258 host tests, 9 repository contracts and 17 full check groups pass.
The latter include cooling/guards/startup/register checks, real migration and
exact rollback, reconnect policy, benchmark checks and 13 actual Klippy
FILEOUTPUT cases. Native fan tests use the pinned heater_fan callback; common
procedure tests retain the pinned dispatcher, motion, homing and pause code
with explicitly modeled physical boundaries.

The release is host R16.7 with MCU R14.5. An installed R14.5 does not need
flashing. The installer preserves PID, calibrated E, sensors and deliberate
geometry. The distributed package is taken from the successful Actions build
and verified against its provenance, hashes and canonical source.

[Installation and rollback](INSTALL.md) · [Complete menu bindings](MAINTENANCE_MATERIAL.md)

## Physical acceptance still pending

1. Verify Ready and the expected factory Z scale, then check all Maintenance
   and Fan test labels on OLED. Update Fluidd groups and compare its controls.
2. Check Heat at 260/258°C, confirm-to-off and cancel. Compare its OLED/Fluidd
   dialog text and check that it returns to Maintenance.
3. With genuine homed Z and clearance, test up/down holds, release, leaving
   the row and lost-panel input. Check finite Fluidd moves separately.
4. On a cold, idle machine enter Fan test, toggle upper and lower separately,
   verify their actual physical correspondence and observe the 150/255 request.
   Verify the same states and selected row on OLED and Fluidd.
5. Check upper cooling priority while still warm after Heat, then Back and
   page-exit cleanup. The upper fan must follow native cooling; the lower
   request must return to its saved value. Do not treat absence of a tachometer
   as proof that either fan is spinning.
6. Capture ZORTRAX_FANS_STATUS, ZORTRAX_MAINTENANCE_STATUS,
   ZORTRAX_PROCEDURE_STATUS, ZORTRAX_OLED_STATUS and klippy.log for any discrepancy.
   Unexpected physical motion calls for the existing M112 shutdown.
