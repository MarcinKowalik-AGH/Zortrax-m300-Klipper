<!-- Marcin Kowalik <mkowalik@agh.edu.pl> | RELEASE_v1.0.0-rc.33.md - Documents flow checks during pause cooling and after retraction. -->
# M300 Classic RC33 — Pause after a material change

After a material change, the measured and target nozzle temperatures must both reach the extrusion threshold. With a reading of 230°C and a target of 150°C, choose **Reheat to check flow** on the OLED or **Resume** in Fluidd. The print stays paused after reheating. Purge, check the visible flow and choose **Confirm material flow** or enter `FILAMENT_READY`. An accepted manual retraction clears the confirmation. After purging again, confirm the flow and explicitly choose **Resume**.

## Orange Pi update

Finish the print, turn off the heaters and wait for Ready. In the existing `orange-pi` checkout run:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

The installer updates the host. RC33 supports MCU 1.0.8. The separate MCU archive is `M300_SD.zip`. Fluidd runs on port 4480. Its optional installer accepts `--update-fluidd --port 4480`. The manual retains historical illustrations from beta.20.
