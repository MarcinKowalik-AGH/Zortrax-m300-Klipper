# M300 Classic beta.18 — consistent Tune entry and mesh layout

Supersedes beta.17. Tune frontend revision: `TUNE-VIEW-2`.

## Corrected behavior

The Tune page now always places the native colored bed-mesh card first and the M300 contact-area drawing below it. The previous `meshChartFirst` condition swapped their positions whenever no active or accepted preview matrix existed, including before a measurement and during preparation. The cards no longer exchange places when a procedure changes state.

Entering Tune through the sidebar requests one read-only snapshot of `bed_mesh` and `m300_pad_mesh`. Finishing native M300 homing requests another snapshot, so the All path does not depend on first running BED_MESH. A small Refresh view button performs the same read-only operation. Normal subscriptions remain authoritative; this is not a new polling loop. Requests are bounded and coalesced. Late replies from a previous view/connection are ignored, and an object changed by a newer subscription is not overwritten by a stale query.

**All remains axis homing (`G28`). It does not measure the bed or activate compensation.** `BED_MESH` / Calibrate remains the explicit measurement action. Merely opening Tune does not move axes, heat the printer, start a calibration or issue BED_MESH_PROFILE LOAD.

A valid saved `m300_pads` profile can be shown while inactive. Its status remains explicitly marked not active. If there is no valid active or previewable profile, the heatmap card gives an explicit empty-data message instead of suggesting that a fabricated flat surface is measured. The contact drawing still shows configured pads and planned points. The live nozzle marker becomes available after XY homing. No measured heights are invented.

## Preserved functionality

No runtime host, MCU, calibration, printer configuration or print-control source changes. PAUSE/CANCEL, the four purge lines and START mesh behavior remain unchanged. All beta.17 OLED navigation, animations, integer square pixels and UART/SPI/RLE/ACK transport remain unchanged. Standard Klipper/Fluidd status timing is unchanged.

## Validation

The full build includes the existing host/native Klippy/ARM tests and all previous frontend tests. Added tests cover idle/probing/complete/failed card order, manual entry, saved inactive profiles, empty data, contact geometry before All, the real All button sending only G28, a refresh after native homing, automatic routing from BED_MESH, ordinary non-M300 behavior, bounded read requests and stale-response races. The compiled helper is also exercised locally without a printer. Browser OLED pixel-raster checks remain enabled.

These are software tests, not a physical M300 test. CI writes `REPORTS/FLUIDD_UNIT_TESTS.json`; publication requires a successful full build and orange-pi deployment.

## Update

With the printer idle and Ready:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Hard-refresh Fluidd with Cmd+Shift+R. No MCU flash is required. Open Tune before running BED_MESH: the heatmap card stays above the contact drawing. If a profile was not persisted with SAVE_CONFIG before a Klipper restart, All cannot recreate its measurements; use the explicit calibration procedure to create new data.

The Tune root reports `data-m300-tune-revision="TUNE-VIEW-2"`. The OLED frontend/API remain `NAV-PIPELINE-2` / `NAV-EVENT-1`.
