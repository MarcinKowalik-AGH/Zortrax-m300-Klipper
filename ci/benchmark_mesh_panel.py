#!/usr/bin/env python3
# Marcin Kowalik <mkowalik@agh.edu.pl>
# benchmark_mesh_panel.py - Mierzy odczyt stanu i przygotowanie obu obrazów po zdarzeniu enkodera na hoście.
"""Replay alternating single detents on the bed mesh page using a staged host."""
import argparse
import json
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter_ns

from benchmark_maintenance import measure


def distribution(samples):
    ordered = sorted(samples)
    return dict(p50_us=round(median(ordered) / 1000, 2),
                p95_us=round(ordered[int(.95 * (len(ordered) - 1))] / 1000, 2))


def benchmark(package):
    sys.path[:0] = [str(package), str(package / 'tests')]
    from payload.m300_oled_preview import M300OLEDPreview
    from test_pad_mesh import PadMeshTests
    from test_settings_information import session
    from test_temperature_editor import event

    with session() as h:
        mesh, _ = PadMeshTests().preflight_case('xyz')
        mesh.busy, mesh.phase, mesh.state = True, 'PROBING', 'PROBING'
        mesh.run_id, mesh.points_measured = 'mesh-benchmark', 12
        mesh.measurements = [(x, y, 0.) for x, y in mesh.points[:12]]
        h.objects['m300_pad_mesh'] = mesh
        h.menu.page, h.oled.selection = 'bed_mesh', 0
        h.oled.menu_reverse = False
        mirror = h.oled._oled_preview = M300OLEDPreview()
        h.oled._render(h.now)
        h.panel_display.pump()
        event(h, 1)
        reads = 0
        full_status = mesh.get_status

        def count_status(now):
            nonlocal reads
            reads += 1
            return full_status(now)

        mesh.get_status = count_status
        assert h.p.view(h.now)['owner'] == 'm300_pad_mesh'
        per_poll = reads
        poll = measure(lambda: h.p.view(h.now))
        status = measure(lambda: h.p._read('m300_pad_mesh', h.now))
        reads = 0
        oled_samples, preview_samples = [], []
        for i in range(320):
            selection = (i + 1) % 2
            previous = mirror._navigation
            start = perf_counter_ns()
            event(h, i + 2, nav=selection)
            h.oled._render(h.now)
            queued = perf_counter_ns()
            preview = mirror._snapshot()
            encoded = perf_counter_ns()
            assert h.oled.selection == selection and mirror._navigation == previous + 1
            assert preview['online'] and mirror._wire == h.panel_display.base.latest
            if i >= 20:
                oled_samples.append(queued - start)
                preview_samples.append(encoded - start)
            h.panel_display.pump()  # Model ACKs outside the host timing window.
        return dict(machine=platform.machine(), python=platform.python_version(),
                    samples=len(oled_samples), mesh_panel_read=status, procedure_view=poll,
                    full_mesh_reads_per_view=per_poll, full_mesh_reads_in_320_detents=reads,
                    event_to_oled_frame_queued=distribution(oled_samples),
                    event_to_fluidd_png_ready=distribution(preview_samples),
                    physical_hardware=False, browser_paint_measured=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.package.resolve()), indent=2))
