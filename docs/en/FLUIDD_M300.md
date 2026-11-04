# Five-point M300 results in Fluidd

**ZORTRAX_LEVEL** is the single standard Autocalibration macro. It opens the
same review as the physical OLED. Stock Fluidd shows the five readings as
text. The M300 build renders those readings in the same prompt as a platform
diagram. Point 4 is rear left, 3 rear right, 2 center, 1 front left and 0
front right. Continue and Cancel remain normal Fluidd buttons and keep their
original shared procedure actions.

Printer information in the M300 build uses compact text rows for the model,
hardware version, serial number and printing time.

**Homing XY** and **Homing ALL** are available in the OLED Zortrax menu and
as Fluidd macros `ZORTRAX_HOME_XY` and `ZORTRAX_HOME_ALL`. They call
`G28 X Y` and `G28` respectively. Fluidd's standard XY and All controls
also show the shared phase when the printer is idle. The M300 Fluidd build
animates an hourglass while the OLED uses the original four-frame sprite.
Print start and Autocalibration keep their own procedure screens.

## Build

The patch applies to [Fluidd v1.37.7](https://github.com/fluidd-core/fluidd/tree/b2edab5bc690f5265a5aa1e56ae3f67669053fd4).
From the M300 repository on a workstation with Node 24, pnpm, standard
shell utilities, Git and zip:

```bash
bash ci/build_fluidd.sh
```

The build verifies the exact upstream commit, applies the published patch,
tests the SVG and fallback, runs type checks and produces
`dist/fluidd/M300_FLUIDD_1_37_7_R16_12.zip` with `SHA256SUMS`.
Corresponding source is the pinned Fluidd commit plus
[`m300-leveling.patch`](../../frontend/fluidd/m300-leveling.patch)
under the Fluidd GPL-3.0 license. The patch and license are included in the ZIP.

## Install the web files

This step is separate from the R16.12 host installer. It changes only the
static Fluidd site. Use the built ZIP or the matching GitHub Actions artifact.

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
