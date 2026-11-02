# R16.6 — firmware 1.3.1 procedure audit and test progress

Date: 2026-11-02. Model: M300 Classic. Stage: software validated, supervised
printer acceptance pending. This is a new revision after R16.5.

## What the audit found and changed

| Requirement | Finding and R16.6 result |
|---|---|
| Maintenance and Material menus | Exact requested submenu items, English labels, seven shared procedure macros; Change appears in paused native Print status |
| Autocalibration heat | 260°C target, ready from 258°C; ordinary G28 Z retains its separate 180°C minimum |
| Autocalibration home | Explicit Y, then X, then the session's shifted center contact; distinct from the ordinary five-update Z helper |
| Five nominal points | 0=(269,44), 1=(35,44), 2=(150,158), 3=(269,275), 4=(35,275); one shared OEM-style integer XY offset in [-3,3] |
| Initial/rear/front/center order | 0,1,4,3; fixed maximum corner reference; rear-left then rear-right instructions from one pair; rear remeasure 3,4 with recovered alternating cursor; front remeasure 1,0; center 2 |
| Screw mathematics | Binary32 coefficient 0.5099999904632568, upward quarter-turn rounding, inclusive rear [-0.20,+0.10] and strict front (-0.20,+0.10); front signed average truncates toward zero |
| Failure policy | 40 instruction limit; #041 calibration / #042 pad failure; no-contact/release failure never publishes a height or overwrites the prior valid result |
| Ordinary Z | Genuine native coarse home followed by five contact/release updates; reference from the fifth release, not the mean; explicit finite endpoints and deadlines |
| Load | 240/238°C, insert confirmation before loading, nominal 130 mm; finish without an extra purge confirmation |
| Unload | R16.5 was wrong: confirmation belongs before retraction. Removed WAIT_REMOVE; nominal 110 mm after the original removal prompt |
| Change | Actual native paused print, retract 110 mm, insert confirmation, load 150 mm; preserve PAUSE_STATE and logical E; no automatic Resume |
| Native print ownership | Calibration now explicitly rejects native printing/paused state before heating or motion; Change verifies its real paused file identity |
| English everywhere | Shared OLED/Fluidd presenter, menu labels, effective NVM language, macro defaults, release package and current documentation are English |

The menu/macro mapping and operating controls are in
[Maintenance and Material](MAINTENANCE_MATERIAL.md). Full M07 details are in
[Autocalibration and Z reference](LEVELING.md).

## Independent original-firmware evidence

Source application SHA-256:
`11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75`.
27,982 recovered instruction comments were checked against those application
bytes. The recovered register-C model was freshly compiled and executed on
the host. This is instruction-semantics reproduction, not physical MCU
execution or ARM binary emulation. UI acknowledgements, electrical inputs,
heating and motor peripheral boundaries are explicitly modeled.

| Evidence | Result |
|---|---|
| Original material flow | Five runs: Load/Unload accepted and cancelled, plus paused Change |
| Independent material loop literals | 124800 Load and 105600 Unload requests checked at their binary addresses; Change's 144000 loading requests reproduced |
| Original Z helper | All five contact/release bodies executed for HW04 and HW05; result equals fifth release and differs from the sample mean |
| Original M07 wizard | Converging sequence, 40-instruction failure and initial pad failure reproduced |
| Original XY generator | Six seed cases compared to the host's recovered LCG |
| Original screw arithmetic | 20,002 raw-delta vectors across factory 400/800 scales reproduced |
| Original display renderer | 110 complete 8192-byte frames match, including the five-language evidence archive; runtime uses the English subset |

Material busy loops are accelerated at the motor boundary. Request counts
are source program values, not physical pulse measurements. Nominal lengths
130/110/150 mm use the OEM 960-unit/mm scale; the port keeps calibrated E.
The private source application is not distributed. Reproduction scripts,
hashed reference data and host comparison tests are included in the source.

The OLED uses the recovered font, compressed graphics, wording and layout.
Fluidd receives the same English semantic text, point/screw, direction, turn
count and current action identity from the shared presenter. A Fluidd prompt
does not reproduce a pixel-addressed physical OLED layout. Developer IDs are
kept in machine status rather than inserted into the OEM dialog wording.

## Port safeguards and intentional differences

Successful original Unload leaves its hotend target enabled. R16.6 turns it
off explicitly. This is intentional, not a claim of literal OEM parity.
Successful native Change restores the previous paused-print target; a cold
paused target uses 240°C during service unless TEMP is provided.

Native planners, heater/extrusion checks, MCU endstop stopping, hardware fault
supervision and factory scale selection remain the owners. The port adds
finite search/release distances, deadlines, stable-opening checks, session
revocation and native queue drainage. Ordinary Z retains physical clearance
above the fifth release rather than blindly returning into the electrical
edge. M07 repeated samples/median and bounded spread retries are additional
port policies. No unbounded GPIO/TIM probing loop is copied.

Legacy unfinished M02/Z-code printing remains disabled. Change does not
enable that engine. English compatibility reads do not reset unrelated NVM,
PID, calibrated E, sensor includes or deliberate printer geometry.

## Code cleanup and optimization

A single bounded native probe capability now serves M07 and ordinary Z
refinement. Shared temperature-readiness logic handles the OEM lower threshold
and normal overshoot while retaining native heater bounds. The obsolete
post-Unload prompt/state was removed. Material status polling requests a
compact snapshot rather than copying the full segmented transport plan on
every OLED/Moonraker poll; a regression test prevents that copy from returning.
Original reproduction tools rebuild their harness from the verified source.

## Validation performed

The full public check suite passes: **233 host tests**, **9 repository
contracts**, MCU/register/cooling/startup checks, recognized-baseline install
migration and exact rollback, reconnect policy, and **13 actual Klippy
FILEOUTPUT cases**. Native procedure tests exercise the pinned HomingMove,
GCodeMove and PauseResume implementations with declared simulated boundaries.
They cover stale confirmations, changed/cancelled paused files, no automatic
Resume, no trigger, missing release, reclosed contact after retreat, deadline,
restart/shutdown and both Z scales.

FILEOUTPUT uses no UART and no physical endstop signal. Some range/planning
cases declare synthetic coordinates; factory decode cases declare synthetic
records. Upstream FILEOUTPUT disables its physical cold-extrusion check.
The reports identify those limitations; they do not qualify printer motion,
heater performance, actual feed length or physical release repeatability.

The Actions release contains the newly compiled R14.5 application, matching
R16.6 host, exact source/commit provenance, package hashes and CI reports. The
distributed host ZIP must be taken from that verified build. [Install and
rollback instructions](INSTALL.md) include the known Orange Pi paths.

## Supervised printer acceptance still required

1. Install while idle and retain the receipt. Read status to verify Ready,
   actual HW05/Z400, native mode, R16.6 revisions and open PC7 with clearance.
2. Check both exact OLED submenu lists. Run Heat from the OLED, then Fluidd:
   260°C, ready at or above 258°C, same warning/completion text, confirmation
   turns heating off and returns to Maintenance. Exercise cancellation.
3. With a genuinely homed, clear Z axis, check bounded platform directions,
   button release and hold timeout. The macro route is a finite distance;
   the panel route must stop accepting quanta on release or lost visibility.
4. Run Load and Unload from each surface at 240°C. Confirm that no E move
   occurs before the relevant prompt. Observe 130/110 mm nominal transport,
   logical E restoration, completion destination and heater-off behavior.
5. Supervise ordinary G28 Z: coarse acquisition, five stable contact/release
   updates and final 5 mm clearance. Inspect its reported five observations;
   repeat to check that clearance does not accumulate.
6. Run Autocalibration with clean nozzle/contact pads and prepared screw
   access. Observe 260/258°C, original warning, Y/X/center, tighten-three
   confirmation, 0/1/4/3 sequence, correct rear-left/right/front instructions
   and turn counts, remeasurement, center and five-value review. Compare
   OLED text and graphics with Fluidd semantic instructions at every phase.
7. From a paused native test print, run Change: 110 mm retract, insert prompt,
   150 mm load, intact paused state, no automatic Resume. Resume separately.

Use M112 for unexpected physical motion. A failed acquisition must not be
repeated by forcing a position or extending search limits. Capture the
actual shutdown reason from klippy.log plus ZORTRAX_* status before restarting.
The previously supplied console excerpt ends at Shutdown and does not contain
that reason; this audit cannot establish the cause of that physical failure.
