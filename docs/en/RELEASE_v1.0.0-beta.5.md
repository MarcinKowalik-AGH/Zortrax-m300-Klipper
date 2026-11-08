# v1.0.0-beta.5 — saved mesh chart and macro groups

For Zortrax M300 Classic; supersedes beta.4. Update the Orange Pi host/web
package. MCU R14.18, UART 750000, OLED SPI 4500000 and the beta.4 OLED ACK
recovery remain unchanged. No MCU reflash is required.

## Why the color chart was missing

Native Klipper represents an inactive mesh as `[[]]`. The previous frontend
treated that nonempty outer array as an active surface, which suppressed the
saved-profile preview. Earlier frontend fixtures used `[]` and missed the
actual native status shape.

Fluidd now recognizes only a rectangular numeric surface as active. After a
successful M300 pad measurement, and again after `SAVE_CONFIG` restarts
Klipper, Tune shows the saved `m300_pads` grid in the native colored 3D mesh
chart with minimum, maximum and range. A profile already present in the
configuration needs no new physical measurement. Failed or unfinished
measurements retain their existing guards against presenting stale results.

Viewing a saved profile does not enable Z compensation or move the printer.
Explicit profile loading and the established `START_PRINT` mesh policy remain
responsible for enabling compensation. The contact-area view remains below
the color chart when a surface is available.

## Platform macros and groups

| Macro | Purpose | Default group |
| --- | --- | --- |
| `ZORTRAX_HEAT_PLATFORM TEMP=60` | Start heating the bed now, with the shared procedure display; confirmation ends heating | ZORTRAX M300 |
| `ZORTRAX_FULL_PLATFORM_PREHEAT STATE=1` | Persistently enable an extra bed/nozzle stabilization period before printing; default extra duration 60 seconds | ZORTRAX M300 |
| `START_PRINT` / `END_PRINT` | Native print start/end workflow | Klipper |

`ZORTRAX_FULL_PLATFORM_PREHEAT` without a parameter opens its setting;
`STATE=0` disables it. It does not start heating immediately.

The grouping migration reads both raw configuration and accessed settings,
so newly added macros can be assigned even when absent from one snapshot.
The frontend also supplies defaults for these four macros when existing
preferences contain no valid category. That UI fallback preserves explicit
valid custom categories, visibility, aliases and colors.

## Update

With the printer Ready and idle, run on the Orange Pi:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Then reload Fluidd with **Ctrl+Shift+R** (macOS: **Cmd+Shift+R**) to load the
updated JavaScript and grouping preferences. Open Tune: an existing valid
`m300_pads` should show a colored surface, its name and numeric range. The
preview is labeled as not active until compensation is explicitly enabled.

## Validation

674 host tests include the macro discovery/grouping regression. Native
Klipper FILEOUTPUT exports an actual inactive `[[]]` status with a saved mesh
for frontend compatibility validation. Frontend regressions cover that shape
both before and after `SAVE_CONFIG`, genuine flat/active surfaces, stale and
failed results, and macro preferences. The native Fluidd WebGL chart is also
rendered locally using the user's saved 61 × 61 profile.

The complete repository checks, native Klipper scenarios, first-install
validation and production Fluidd build gate publication. These are software
checks; no heater, motor, probe or MCU firmware action was performed on the
physical printer for this update.
