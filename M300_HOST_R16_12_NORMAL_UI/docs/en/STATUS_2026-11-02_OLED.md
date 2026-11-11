# Zortrax M300 Classic — Project Status and OLED Demonstration (2026-11-02)

## OLED photographs — on-device evidence

**Picture 1 — Klipper status screen (Ready)**

![Picture 1 — Ready status screen](../assets/oled/2026-11-02/picture%201.png)

**Picture 2 — Settings screen and panel_update exception**

![Picture 2 — Settings and panel_update exception](../assets/oled/2026-11-02/picture%202.png)

**Picture 3 — Heating menu, hotend selected**

![Picture 3 — Heat hotend](../assets/oled/2026-11-02/picture%203.png)

**Picture 4 — Heating menu, bed selected**

![Picture 4 — Heat bed](../assets/oled/2026-11-02/picture%204.png)

**Release under review:** MCU R14.5 / Host R16.3  
**Hardware:** original Zortrax M300 Classic, STM32F103-based MCU, Orange Pi host and original monochrome OLED/rotary control.  
**Status:** functional integration with a number of operator-observed features; not yet a fully certified OEM-equivalent implementation.

## Physical OLED evidence — November 2, 2026

The four original photographs below are displayed in the exact order supplied by the machine operator (not timestamp order):

1. **Ready / live status:** Klipper-style first screen showing approximately 126 °C hotend temperature, 26 °C bed temperature, feed rate 100%, 0% progress, elapsed time 00:00, and the `Ready` state. The visible temperatures are instantaneous readings, not heater setpoints.
2. **Settings / diagnostics:** encoder-operated menu with `Settings`, `Information`, and an on-screen Python exception: `'M300NativeMotion' object has [no] attribute 'panel_update'` (word wrapping on the photograph). This is evidence of an unresolved menu integration bug, **not** a completed settings workflow.
3. **Heating menu — hotend highlighted:** `Hotend TEMP: ---`, `Bed TEMP: ---`, `Heat hotend`, `Heat bed`, `Turn off heaters`; an hourglass graphic on the right.
4. **Heating menu — bed highlighted:** the same temperature and heater commands with the alternative hourglass image/selection shown.

These photographs independently confirm working OLED rendering, the first status page, menu navigation and display of heater commands. **They do not prove that selecting those commands heats the hardware, that displayed dashes correctly represent sensor readings, or that all OEM icon states and menu procedures are finished.** The exception visible in photograph 2 is a tracked regression to resolve.

### Original photograph filenames and repository assets

| Order | New filename | Supplied photograph |
|---|---|---|
| 1 | `picture 1.png` | `Zrzut ekranu 2026-11-2 o 20.13.04.png` — Ready/status |
| 2 | `picture 2.png` | `Zrzut ekranu 2026-11-2 o 20.12.50.png` — Settings/error |
| 3 | `picture 3.png` | `Zrzut ekranu 2026-11-2 o 20.12.31.png` — Heat hotend |
| 4 | `picture 4.png` | `Zrzut ekranu 2026-11-2 o 20.12.16.png` — Heat bed |

## Completed or integrated in the current codebase

- **Target platform and build:** STM32F103 / M300 Classic MCU target, pinned upstream Klipper, maintained host extras and Orange Pi integration, clean CI build and reproducible release artifacts.
- **Native Klipper architecture:** native thermal/PID, bed and hotend controls, fan configuration, SAVE_CONFIG, Cartesian XYZE control, G28/probe adapter, print/pause/resume functionality as documented in current configuration.
- **OLED transport and basic UI:** native Klipper status page, rotary input and grouped menu infrastructure; existing display dim/off/wake and host-link waiting/recovery paths retained. Today's photographs substantiate first-page drawing and two menu states, but also reveal a missing `panel_update` method.
- **MCU safety supervision:** local thermostat-based hotend cooling when the host link is absent, protective cooling for invalid/critical conditions, heartbeat and fault guard, without relying solely on the host process.
- **Host startup reconnection (introduced in R16.2, retained in R16.3):** a bounded single native reset attempt for a previous armed session / lost heartbeat under documented conditions; hardware faults and M112 require explicit recovery. The software logic is tested; fresh physical restart/reboot acceptance is still required.
- **R16.3 M07 procedure integration:** five-point contact measurements, three-screw instructions, synchronized OLED/Fluidd confirmations, and a host NVM observation ledger are implemented in software; physical machine acceptance remains pending. See [M07 leveling](LEVELING.md).
- **Hardware revision / Z:** factory Z400/Z800 identification before native configuration, preserving the scale through native motion and the OEM levelling adapter.
- **Configuration management:** reversible migration that preserves prior PID, extrusion calibration and deliberate geometry, with settings and Fluidd macro-category setup.
- **Software verification:** as reported by the R16.3 README, 150 host tests, 8 repository contracts, 6720 STEP guard cases, 52 cooling cases, 1792 factory decoder cases, startup/timer checks and 13 actual pinned Klippy FILEOUTPUT scenarios. These counts are **software coverage, not physical printer acceptance**.

## Implemented but not yet fully physically accepted

- **Z contact homing:** native G28/probe adapter with an intended minimum 180 °C hotend preheat, M300 contact point and final 5 mm clearance. Check repeat homing and no accumulating Z offset on the printer.
- **Motion envelope / performance:** configured 2 µs step pulses, XY profile up to 300 mm/s, Z up to 25 mm/s and native M220/velocity/acceleration controls. Native FILEOUTPUT tests include M220 150%, but this does not prove F103 scheduling or reliable physical motion at the highest rates.
- **Host restart workflow:** confirm on an idle machine that a Klipper service restart and separate Orange Pi reboot recover without manual FIRMWARE_RESTART, do not resume heaters or motion, and require re-homing.
- **Heating control through OLED:** menu entries render, but end-to-end knob-to-Klipper-to-heater execution must be tested separately; the menu currently displays `---` for both temperature fields.
- **OLED menu consistency:** correct the missing `M300NativeMotion.panel_update` interface and test settings, selection, information, back navigation and redraw through the full menu lifecycle.

## Not closed / not to be advertised as complete

- Full factory-equivalent M03/M08 procedures and physical acceptance of the R16.3 M07 leveling wizard, including all its state transitions and safety cases.
- OEM binary Z-code execution and physical SD workflows, including all preview, validation and error cases.
- End-to-end verified OEM menu, original graphics and every status/icon/buzzer/LED combination.
- Full machine-level print acceptance, extreme speed/acceleration stress testing, all heater/fan failure cases and all interruption/recovery scenarios.
- Certification of all original firmware behaviour or a production-ready release.

## Recommended next acceptance sequence

1. Fix and regression-test `M300NativeMotion.panel_update`; preserve the screenshot as a reproducible issue.
2. Bind actual current temperatures / targets in the heating submenu and test selection, feedback, back navigation, and safety interlocks on the real machine.
3. Verify host restart and Orange Pi reboot recovery; ensure heaters stay off, fault handling stays local and homing is invalidated.
4. Physically validate native homing with the 180 °C minimum and repeat-contact 5 mm clearance.
5. Execute progressive XY 200 / 250 / 300 mm/s tests with realistic load and inspect skipped steps, timing, MCU logs and faults.
6. Physically accept R16.3 M07 and continue M03/M08, SD and Z-code as separate tracked workflows.

### Related documentation

- [Main README](../../README.md)
- [Features and acceptance](FEATURES.md)
- [Connection lifecycle](CONNECTION.md)
- [M07 leveling](LEVELING.md)

**Evidence standard:** photographed = visible on the machine; integrated = present in the code/configuration; software-tested = covered by automated tests; physically accepted = explicitly run and observed on hardware. These must remain separate claims.
