# M300 Classic RC28 — OLED bed mesh menu polling

The procedure panel reads the current mesh phase, point count, heater targets, error and profile name. Knob navigation and the procedure dialog use this compact status. The `ZORTRAX_PAD_MESH_STATUS` command and the Moonraker `m300_pad_mesh` object provide coordinates, contact regions, measurements and travel limits for diagnostics and the Fluidd map.

With the printer idle and Ready and heater targets off, run the host update from the existing `orange-pi` checkout:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py
```

This feature requires a host update. The MCU version is 1.0.8. The `M300_SD.zip` archive provides a separate firmware update. The host uses the existing Fluidd installation on port 4480. The separate web installer accepts `--update-fluidd --port 4480`. The manual retains illustrations from beta.20.

### Host measurements

Median times in µs on x86-64 with Python 3.13.5. The status benchmark sampled 4000 reads. Display timings cover 300 steps after 20 warm-up steps. Across all 320 steps on the bed mesh page the full diagnostic reads dropped from 960 to 0.

| Stage | RC27 | RC28 |
|---|---:|---:|
| Mesh panel read | 11.47 | 0.70 |
| Event to queued OLED frame | 161.32 | 91.35 |
| Same event to Fluidd PNG ready | 237.64 | 150.68 |

### Measuring the two displays

Open Klipper → Bed mesh on the OLED and open the Fluidd OLED preview. Film a mark on the knob, the OLED selection and the Fluidd selection in the same shot. Turn the knob one detent at a time, alternating directions 20 times without pressing it. Count the frames from each detent to the first visible selection change on each display. At 120 fps one frame represents about 8.3 ms. Compare the median and 95th percentile for each display under the same browser, network and menu conditions.

The host benchmark in `ci/benchmark_mesh_panel.py` replays encoder packets and times the outgoing OLED frame and Fluidd PNG. The camera measurement also includes hardware, transport and browser presentation.
