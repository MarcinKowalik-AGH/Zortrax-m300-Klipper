"""Host-only Maintenance costs; simulated telemetry/output boundaries.

No printer, UART, physical RPM or Orange Pi timing is measured. Absolute
timings describe this executor only; deterministic lookup counts are portable.
"""
import argparse
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import sys
import time


def measure(callback, count=4000):
    for _ in range(100):callback()
    samples=[]
    enabled=gc.isenabled();gc.disable()
    try:
        for _ in range(count):
            start=time.perf_counter_ns();callback();samples.append(time.perf_counter_ns()-start)
    finally:
        if enabled:gc.enable()
    samples.sort()
    return dict(samples=count,p50_us=round(statistics.median(samples)/1000.,3),
                p95_us=round(samples[int(.95*(count-1))]/1000.,3))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--baseline',type=Path)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();package=args.package.resolve()
    sys.path[:0]=[str(package),str(package/'tests')]
    from test_native_maintenance_contract import FanHarness
    from payload.m300_maintenance_ui import fan_frame
    from payload.m300_leveling_oem import font
    import test_display
    h=FanHarness();h.board_reads=0;h.fans.get_status(h.now)
    reads=h.board_reads;assert reads==1
    h.board_reads=0;assert h.fans._tick(h.now)==h.reactor.NEVER;assert h.board_reads==0
    result=dict(status='PASS_HOST_MAINTENANCE_BENCHMARK',python=platform.python_version(),
        machine=platform.machine(),environment='Executor CPU; declared simulated boundaries',
        current_fan_status=measure(lambda:h.fans.get_status(h.now)),
        mcu_snapshots_per_status=reads,idle_timer_snapshots=0,physical_hardware=False,
        orange_pi_timing_measured=False,uart_timing_measured=False)
    if args.baseline:
        spec=importlib.util.spec_from_file_location('baseline_fans',args.baseline)
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        baseline=old.M300Fans.__new__(old.M300Fans);baseline.__dict__.update(h.fans.__dict__)
        h.board_reads=0;baseline.get_status(h.now)
        result['baseline_mcu_snapshots_per_status']=h.board_reads
        result['baseline_fan_status']=measure(lambda:baseline.get_status(h.now))
        result['baseline_source_sha256']=hashlib.sha256(args.baseline.read_bytes()).hexdigest()
    h.run('ZORTRAX_FAN_TEST_START')
    result['active_fan_status']=measure(lambda:h.fans.get_status(h.now))
    result['shared_procedure_view']=measure(lambda:h.p.view(h.now))
    font();fan_frame.cache_clear();cold=[]
    for upper in ('(Disabled)','(Enabled)'):
        for lower in ('(Disabled)','(Enabled)'):
            for selected in range(3):
                start=time.perf_counter_ns()
                wire=fan_frame(upper,lower,'',selected,test_display.renderer.Frame)
                cold.append(time.perf_counter_ns()-start);assert len(wire)==8192
    result['fan_menu_cold_frames']=dict(samples=len(cold),p50_us=round(statistics.median(cold)/1000.,3),
        p95_us=round(sorted(cold)[int(.95*(len(cold)-1))]/1000.,3))
    result['fan_menu_cached_frame']=measure(lambda:fan_frame('(Enabled)','(Disabled)','',1,test_display.renderer.Frame))
    result['frame_cache_max_entries']=fan_frame.cache_info().maxsize
    result['platform_tick_seconds']=.05
    result['platform_panel_freshness_seconds']=.75
    result['platform_stop_nominal_sample_seconds']=.001
    result['platform_stop_max_pulse_rate']=4000
    result['active_fan_watchdog_seconds']=.1
    result['native_thermostat_seconds']=1.
    result['notes']='No absolute timing threshold is used as a proxy for physical printer acceptance.'
    h.fans.end_oem()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
