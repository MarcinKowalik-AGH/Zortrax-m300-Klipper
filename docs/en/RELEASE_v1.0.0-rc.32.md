<!-- Marcin Kowalik <mkowalik@agh.edu.pl> | RELEASE_v1.0.0-rc.32.md - Documents manual extrusion in a paused print and the host update. -->
# M300 Classic RC32 — manual extrusion and retraction during a pause

In Fluidd or OrcaSlicer’s Device tab, wait until the pause movement or automatic filament transport finishes. On a colour change, you can purge as soon as the flow confirmation appears. Set the filament length and speed under **Tool** and click **Extrude** or **Retract** as often as needed. For example, 30 mm at 4 mm/s produces a relative E-only move of +30 or −30 mm at F240. Confirm the flow when satisfied. Resume is a separate action.

The buttons move the filament while preserving XYZ, the native pause snapshot and the file position. They require a hot nozzle. If pause cooling has lowered the target, set the material working temperature and wait for the nozzle to heat. After successful standalone Load or Unload, the nozzle stays at the selected target until manual switch-off or normal idle cooling. The four automatic material settings still default to 240°C and 2 mm/s in each direction.

## Orange Pi update

Finish the print, turn off the heaters and wait for Ready. In the existing `orange-pi` checkout run:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

The installer updates the host. RC32 supports MCU 1.0.8. The separate MCU archive is `M300_SD.zip`. Fluidd runs on port 4480. Its optional installer accepts `--update-fluidd --port 4480`. The manual retains historical illustrations from beta.20.
