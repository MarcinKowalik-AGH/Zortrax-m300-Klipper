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

The M300 pad adapter reports the current probing run through the existing
Moonraker object subscription. A new live run opens **Tune** once, preserving
the printer query parameter. It does not reopen Tune after manual navigation,
on geometry-only previews, on preflight refusals or for an old completed run.
No G-code or additional polling is sent to navigate.

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
