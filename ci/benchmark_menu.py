"""Measure repeated host menu rendering and observation-free ownership reads."""
import argparse
import json
from pathlib import Path
import platform
import sys

from benchmark_maintenance import measure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    sys.path[:0] = [str(package), str(package / 'tests')]
    from test_settings_information import session
    from test_print_context import printing, pause
    from payload.m300_print_ui import frame_for
    from payload.m300_settings_ui import menu_frame

    with session() as printer:
        menu, oled, now = printer.menu, printer.oled, printer.now
        # Model a populated leveling observation. The former ownership path
        # copied this data on every read, even when checking only busy/state.
        printer.nvm.store._published['calibration'] = dict(
            events=[dict(point=i % 5, samples=[1., 2., 3., 4., 5.]) for i in range(120)])
        result = dict(
            status='PASS_M300_HOST_MENU_BENCHMARK', python=platform.python_version(),
            machine=platform.machine(), modeled_observation_entries=120,
            full_nvm_status=measure(lambda: printer.nvm.get_status(now)),
            ownership_summary=measure(lambda: printer.nvm.get_ownership_status(now)),
            physical_hardware=False, orange_pi_timing_measured=False,
            frame_cache_capacity=menu_frame.cache_info().maxsize)
        pages = ('zortrax', 'models', 'maintenance', 'material', 'settings',
                 'setting_sort_mode', 'information', 'info_firmware', 'help')
        result['pages'] = {}
        allocations = tuple(printer.allocations)
        for page in pages:
            menu.page = page
            oled.selection = 1
            def render():
                oled._render(now)
                assert len(oled._render_wire) == 8192
            result['pages'][page] = dict(rows=measure(lambda: menu.rows(now), 1000),
                                         cached_oled=measure(render, 1000))
        menu.page = 'setting_sort_mode'
        def cold():
            menu_frame.cache_clear()
            render()
        result['sort_menu_cold_oled'] = measure(cold, 150)
        assert allocations == tuple(printer.allocations)
        result['history_executors_allocated_during_render'] = 0
    with printing() as printer:
        def render_context():
            printer.oled._render(printer.now)
            assert len(printer.oled._render_wire) == 8192

        result['print_context'] = {'printing': measure(render_context, 1000)}
        pause(printer)
        result['print_context']['pause_menu'] = measure(render_context, 1000)
        printer.sd.print_stats.state = 'complete'
        printer.sd.current_file = None
        result['print_context']['printing_done'] = measure(render_context, 1000)
        result['print_context']['cache_capacity'] = frame_for.cache_info().maxsize
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
