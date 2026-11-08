# Five-point M300 results in Fluidd

**ZORTRAX_LEVEL** is the single standard Autocalibration macro. It opens the
same review as the physical OLED. Stock Fluidd shows the five readings as
text. The M300 build renders those readings in the same prompt as a platform
diagram. Point 4 is rear left, 3 rear right, 2 center, 1 front left and 0
front right. Continue and Cancel remain normal Fluidd buttons and keep their
original shared procedure actions.

Printer information in the M300 build uses compact text rows for the model,
hardware version, serial number and printing time.

The OLED's native Klipper status keeps the original three upper rows. Its
bottom status strip uses a 5x7 font, with up to two 42-character lines for
the complete native message (for example, a Bed Mesh phase). This changes
only the existing bottom 16 pixels. Longer messages end with an ellipsis;
no scrolling timer, new display transport or encoder polling is added.

**Homing XY**, **Homing Z** and **Homing ALL** are available in OLED
Maintenance directly below Autocalibration, and as Fluidd macros
`ZORTRAX_HOME_XY`, `ZORTRAX_HOME_Z` and `ZORTRAX_HOME_ALL`. They call
`G28 X Y`, `G28 Z` and `G28` respectively. Z requires XY to be homed first.
On completion the OLED returns to its invoking screen, cursor and history;
external homing from native Klipper status returns to that status screen.
Fluidd's standard X, Y, XY,
Z and All home buttons show the matching busy state and phase text as a
tooltip, including starts from OLED and macros. Homing does not open a modal
dialog. OLED uses distinct four-frame XY, Z and ALL homing symbols, both
on the selected menu entry and during the matching native procedure.
Print start and Autocalibration keep their own procedure screens.
See [the symbol inventory and draft sheet](UI_SYMBOLS.md).

The dedicated OLED/LED brightness dialogs show the live physical encoder
preview from `m300_settings.brightness` using the normal status subscription.
Save stores the displayed preview; releasing the web slider saves as well.
Remote saves align the open OLED slider and keep Back usable. Stale dialogs
from navigation or restart are still rejected. No per-step console refresh
or additional MCU polling is needed.

## Native pad mesh in Tune

`BED_MESH` is the visible Klipper macro, including the matching OLED action.
The installer renames the previous `ZORTRAX_BED_MESH` macro and its Fluidd
preferences while preserving custom arguments, geometry and saved profiles.
The native `BED_MESH_CALIBRATE` entry still uses the same 25 contact positions.

After `SAVE_CONFIG` restarts Klipper, Tune previews the saved `m300_pads`
profile in the native colored 3D chart, with minimum, maximum and range in mm.
The native chart appears first once a mesh is available; the contact-area
drawing remains below it. During probing the contact-area drawing is first.
This preview does not load compensation or send a motion/heater command.
The native inactive-mesh placeholder `[[]]` is treated as empty, just like
`[]`. A valid saved profile therefore remains visible after calibration and
after `SAVE_CONFIG`, with its original colored native surface and range.
`BED_MESH_PROFILE LOAD=m300_pads` or the native profile's Load button enables
the saved compensation and displays the active native chart.

At that point the contact-area drawing can display corrections interpolated
from the saved native grid. These are explicitly labeled as saved mesh values;
they are not presented as original three-tap measurements, which are session
data. Failed or unfinished runs do not borrow an earlier profile's heights.

The `TEST M300` macro category is optional service diagnostics, not part of
printing or Bed Mesh. Status macros read diagnostics; XY test macros perform
deliberate test movements. Other diagnostic entries exercise OLED transport
or shared service procedures. They never run automatically and can be hidden
in Fluidd's macro settings without disabling ordinary printer functions.

## Platform heating macros

| Macro | Effect | Fluidd category |
| --- | --- | --- |
| `ZORTRAX_HEAT_PLATFORM TEMP=60` | Starts bed heating now, with shared OLED/Fluidd progress; confirm after heating to switch the bed heater off. | ZORTRAX M300 |
| `ZORTRAX_FULL_PLATFORM_PREHEAT STATE=ENABLED` | Saves a setting for print start; adds the configured stabilization interval after temperatures settle. The default extra interval is 60 seconds. It does not start heating by itself. | ZORTRAX M300 |
| `START_PRINT`, `END_PRINT` | Native print preparation and completion. | Klipper |

The grouping migration uses both raw configuration and accessed settings.
For an M300, the UI also supplies these defaults when a new macro has no
valid category in older preferences. Explicit valid custom categories,
visibility, aliases and colors are preserved by this UI fallback. Reload
Fluidd after installing its new build so an existing browser session reads
the updated preferences and code.

Revision `0.13.16.20-PAD-CONTACT-MAP` adds a top view above the native mesh
chart. It shows the five configured contact areas, all 25 planned points,
completed/current point colors and an animated live nozzle marker. Native
X0/Y0 is at the bottom left, with X increasing rightwards and Y upwards.
Measured fields can be rectangular and individually offset, including rear
right Y262 versus rear left Y260. Geometry is supplied by `m300_pad_mesh`
status; the UI does not substitute hardcoded pad coordinates.

Each contact area shows its completed native contact heights: four values
outside the corners and one at the interior sample. Heights are the native
median of three taps, in the unshifted homing frame, not interpolated values
or the five-point pad median. They appear as each location completes and
remain available after an aborted run. A changed preview does not reuse
old heights. Axis, head and height-label positions use the same display-only
Y inversion; no physical coordinate or move is changed.

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
No G-code or additional polling is sent to navigate. A new owned nonfatal
mesh error also opens this panel once, including after a browser reconnect.
Its shared error code, cause, remedy and acknowledgement appear in that one
panel, without an additional error dialog. Duplicate nonfatal error toasts
are hidden only when their exact cause is already owned by a valid shared
error view. Unrelated errors and native fatal/shutdown notices remain visible.

Revision `0.13.16.17-PAD-PREPARE` includes the preparation in that live run:
Tune shows simultaneous heating, native homing, temperature stabilization and
then the 25-point progress. Nozzle/bed targets are displayed. The nozzle uses
260 °C as the default mesh target and retains a hotter working temperature;
an explicit `HOTEND_TEMP` remains supported with a 180 °C floor. Ordinary
G28 keeps its independent 180 °C minimum. A previously off
bed defaults to 60 °C. `HOTEND_TEMP` and `BED_TEMP` are editable macro fields.
`PREVIEW=1` still never heats or homes. The panel displays both native actual
temperatures and the measurement targets for nozzle and bed, through the
existing subscription. No firmware flash is required.

Bed Mesh belongs to the Klipper OLED submenu and Fluidd macro group. The
`BED_MESH` macro forwards parameters to the native `BED_MESH_CALIBRATE`
adapter; it does not add an OEM Zortrax menu procedure. Flat-frame K/Z marks use the
same 50×50 geometry as the activity icons, without the former triangular roof.

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
