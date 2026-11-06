# Five-point M300 results in Fluidd

**ZORTRAX_LEVEL** is the single standard Autocalibration macro. It opens the
same review as the physical OLED. Stock Fluidd shows the five readings as
text. The M300 build renders those readings in the same prompt as a platform
diagram. Point 4 is rear left, 3 rear right, 2 center, 1 front left and 0
front right. Continue and Cancel remain normal Fluidd buttons and keep their
original shared procedure actions.

Printer information in the M300 build uses compact text rows for the model,
hardware version, serial number and printing time.

**Homing XY**, **Homing Z** and **Homing ALL** are available in OLED
Maintenance directly below Autocalibration, and as Fluidd macros
`ZORTRAX_HOME_XY`, `ZORTRAX_HOME_Z` and `ZORTRAX_HOME_ALL`. They call
`G28 X Y`, `G28 Z` and `G28` respectively. Z requires XY to be homed first.
On completion the OLED returns to its invoking screen, cursor and history;
external homing from native Klipper status returns to that status screen.
Fluidd's standard X, Y, XY,
Z and All home buttons show the matching busy state and phase text as a
tooltip, including starts from OLED and macros. Homing does not open a modal
dialog. OLED keeps the original four-frame M300 hourglass.
Print start and Autocalibration keep their own procedure screens.
See [the symbol inventory and draft sheet](UI_SYMBOLS.md).

The dedicated OLED/LED brightness dialogs show the live physical encoder
preview from `m300_settings.brightness` using the normal status subscription.
Save stores the displayed preview; releasing the web slider saves as well.
Remote saves align the open OLED slider and keep Back usable. Stale dialogs
from navigation or restart are still rejected. No per-step console refresh
or additional MCU polling is needed.

## Native pad mesh in Tune

Revision `0.13.16.20-PAD-CONTACT-MAP` adds a top view above the native mesh
chart. It shows the five configured contact areas, all 25 planned points,
completed/current point colors and an animated live nozzle marker. Native
X0/Y0 is at the upper left, with X increasing rightwards and Y downwards.
Measured fields can be rectangular and individually offset, including rear
right Y262 versus rear left Y260. Geometry is supplied by `m300_pad_mesh`
status; the UI does not substitute hardcoded pad coordinates.

The map is available during an idle geometry preview as well as a live run.
It reads `motion_report.live_position` from the existing subscription and
shows the nozzle after XY homing. Stale/unhomed or non-finite positions are
hidden, and out-of-travel plans receive a warning. The graphic never sends
G-code or increases polling. Reduced-motion settings disable smooth marker
transitions and the current-point pulse.

The five new macro fields `FRONT_LEFT_BOUNDS`, `FRONT_RIGHT_BOUNDS`,
`CENTER_BOUNDS`, `REAR_LEFT_BOUNDS`, `REAR_RIGHT_BOUNDS` use
`X_MIN,Y_MIN,X_MAX,Y_MAX`. They directly define each pad's contact corners;
the separate configured interior sample is retained. See the exact
[measured rectangles and configuration](LEVELING.md#measured-contact-rectangles).

The M300 pad adapter reports the current probing run through the existing
Moonraker object subscription. A new live run opens **Tune** once, preserving
the printer query parameter. It does not reopen Tune after manual navigation,
on geometry-only previews, on preflight refusals or for an old completed run.
No G-code or additional polling is sent to navigate.

Revision `0.13.16.17-PAD-PREPARE` includes the preparation in that live run:
Tune shows simultaneous heating, native homing, temperature stabilization and
then the 25-point progress. Nozzle/bed targets are displayed. The nozzle uses
180 °C as a floor and retains a hotter working temperature; a previously off
bed defaults to 60 °C. `HOTEND_TEMP` and `BED_TEMP` are editable macro fields.
`PREVIEW=1` still never heats or homes. No firmware flash is required.

Revision `0.13.16.18-PAD-OLED` binds this same live run to the physical panel.
Fluidd quick-button, parameter-form and console starts all open the Bed mesh
OLED page, with its four-frame 500 ms five-pad animation and phase/point text.
Internal homing keeps the parent measurement view. Successful completion restores
the prior OLED screen/cursor/history, manual navigation is respected, and failure
stays visible until Back. These updates never open a Fluidd prompt over Tune.

The macro name is a quick button with no parameters. The expanded form's
**Send** submits its filled values. To match the console example, fill widths
50/50 mm, `EDGE_MARGIN=16` and `BED_TEMP=60`; empty fields use the printer's
configuration/current geometry (margin 5 mm by default). References now occupy
separate Jinja lines, allowing stock Fluidd to discover all editable fields.
Both `EDGE_MARGIN=0` and `TRAVEL_MARGIN=0` are preserved by Send and supported
by pad revision `0.13.16.19-PAD-ZERO-MARGIN`. The first controls inset from
physical metal; the second controls inset from native travel limits. Correct
the pad centers for the real home-to-metal offset before measuring; see
[home inside metal](LEVELING.md#measured-contact-rectangles).

Tune shows progress through 25 positions, five pad medians/spreads and the
measured range versus its configured limit. A failed attempt retains its
diagnostics and error, without a Save button or a newly generated map. On
success, an inactive native profile can be previewed in the chart with an
explicit interpolated-grid label. This read-only preview never sends
`BED_MESH_PROFILE LOAD` and never replaces an active native mesh. The current
accepted run offers **Save configuration** while idle; it sends the normal
`SAVE_CONFIG`, which restarts Klipper. Geometry and physical probing limits
remain unchanged. See [pad mesh](LEVELING.md#optional-klipper-pad-mesh).

## Build

The patch applies to [Fluidd v1.37.7](https://github.com/fluidd-core/fluidd/tree/b2edab5bc690f5265a5aa1e56ae3f67669053fd4).
From the M300 repository on a workstation with Node 24, pnpm, standard
shell utilities, Git and zip:

```bash
bash ci/build_fluidd.sh
```

The build verifies the exact upstream commit, applies the published patch,
tests the SVG, fallback, home-button status and pad-mesh navigation/results,
runs type checks and produces
`dist/fluidd/M300_FLUIDD_1_37_7_R16_12.zip` with `SHA256SUMS`.
Corresponding source is the pinned Fluidd commit plus
[`m300-leveling.patch`](../../frontend/fluidd/m300-leveling.patch)
under the Fluidd GPL-3.0 license. The patch and license are included in the ZIP.

## Install the web files

The standard `orange-pi` installer installs this compiled Fluidd together
with the host update and preserves the existing `config.json`. Pull
`orange-pi` and run `install-orange-pi.py` as described in [Install](INSTALL.md).
The steps below are for a custom web-root deployment only.

1. On the Orange Pi, identify the actual web root of your existing Fluidd
   server block (for nginx, inspect `sudo nginx -T` and the matching
   `listen` and `root` directives). Keep the current root as a rollback copy.
2. Extract the ZIP beside the existing site. Set the same server block's
   `root` to the absolute path of the extracted `fluidd-m300` directory.
   If you customized `config.json`, copy it from the old site into the new
   web root. Keep the existing Moonraker routes and printer address.
3. Check `sudo nginx -t`, reload nginx and open the same Fluidd URL. If
   Fluidd is installed as a PWA, reload the site after its update. Roll back
   by restoring the original root path and reloading nginx.

The diagram is limited to complete M300 leveling results. Incomplete reports
use the text rendering. The site neither interprets HTML from G-code nor
makes extra requests to the printer.
