# M300 Classic v1.0.0-beta.18 — consistent Tune entry and homing

Supersedes beta.17. Tune frontend revision: `TUNE-PREPARE-1`.
The OLED frontend remains `NAV-PIPELINE-2` and its host API `NAV-EVENT-1`.

## Corrections

- Opening Tune from the sidebar now displays the preparation panel for the real initial `IDLE` state (`run_id=null`). It does not fabricate a measurement, send G-code, heat, home, load a profile or enable mesh compensation.
- The contact-area plan stays above the colored mesh chart before, during and after measurement and after reloading a saved profile. There is only one contact-map component; availability of a mesh no longer swaps the cards.
- All in Tune explicitly calls the shared `ZORTRAX_HOME_ALL` on M300 and shows standalone homing progress and actual/target temperatures. All is homing only, not a new mesh measurement.
- Calibrate on M300 calls the shared `BED_MESH`. The backend already owns its guarded heating and homing preparation, so a separate All click is not required. Ordinary non-M300 printers retain `G28`, `BED_MESH_CALIBRATE` and the prior-homing prerequisite.
- Ready/busy/printing/paused and concurrent-procedure checks prevent competing commands. No backend safeguard has been removed.

This is a Fluidd correction only. Runtime host and MCU sources, physical OLED,
fast OLED navigation, square pixels, animation/status cadence, thermal and motion
settings, saved mesh profiles and START/PAUSE/RESUME/CANCEL remain unchanged.
The older documentation screenshot with the heatmap first is historical; beta.18
uses the fixed contact-plan-first order.

## Update from a standard beta.17 installation

With the printer **idle and Ready**, run on the Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Hard-refresh Fluidd with **Cmd+Shift+R**. No MCU flashing, configuration reset,
new mesh measurement or Moonraker configuration change is required. Do not install
the earlier source-only ZIP on the printer. Do not force past unknown local edits.

The deployment's `BUILD_PROVENANCE.json` must report `v1.0.0-beta.18`.
`ZORTRAX_OLED_STATUS` still reports `NAV-EVENT-1`; that is intentional.

## Validation and acceptance

Publication requires the full matching GitHub Actions run: host regressions,
native Klippy FILEOUTPUT, ARM build, existing frontend/OLED regressions, new Vue
component tests, ESLint, full TypeScript checking, actual Chromium/Firefox OLED
pixel comparisons, production Fluidd build and package checksums.

The new component tests exercise initial Tune entry without commands, malformed
IDLE rejection, explicit All/Calibrate actions, standalone homing, busy/paused/
printing/not-ready guards, ordinary-printer fallback and stable card order.
They simulate printer data; no test sends motion or heating commands to hardware.

After updating, first open Tune without starting a procedure: the contact plan
must be above the heatmap and the preparation panel visible. Under normal physical
supervision, All should display homing progress without creating a new mesh.
A real printer acceptance test is separate from the automated software checks.
