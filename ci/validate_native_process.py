#!/usr/bin/env python3
"""Actual pinned Klippy processes, FILEOUTPUT only: no printer UART or MCU execution."""
import argparse
import base64
import configparser
import glob
import io
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
import native_config

ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
    'toolhead.move': 'toolhead.ToolHead.move',
    'toolhead.drip_move': 'toolhead.ToolHead.drip_move',
    'toolhead.set_position': 'toolhead.ToolHead.set_position',
    'extruder.set_temp': 'extras.heaters.Heater.set_temp',
    'extruder.alter_target': 'extras.heaters.Heater.alter_target',
    'extruder.set_pwm': 'extras.heaters.Heater.set_pwm',
    'heater_bed.set_temp': 'extras.heaters.Heater.set_temp',
    'heater_bed.alter_target': 'extras.heaters.Heater.alter_target',
    'heater_bed.set_pwm': 'extras.heaters.Heater.set_pwm',
    'extruder.pwm': 'mcu.MCU_pwm',
    'extruder.check_move': 'kinematics.extruder.PrinterExtruder.check_move',
    'heater_bed.pwm': 'mcu.MCU_pwm',
    'fan.set_speed': 'extras.fan.Fan.set_speed',
    'G0': 'extras.gcode_move.GCodeMove.cmd_G1',
    'G1': 'extras.gcode_move.GCodeMove.cmd_G1',
    'G28': 'extras.m300_native_motion.M300NativeMotion.cmd_G28',
    'G28:native_backend': 'extras.homing.PrinterHoming.cmd_G28',
    'M220': 'extras.gcode_move.GCodeMove.cmd_M220',
    'SET_VELOCITY_LIMIT': 'toolhead.ToolHeadCommandHelper.cmd_SET_VELOCITY_LIMIT',
    'M104': 'kinematics.extruder.PrinterExtruder.cmd_M104',
    'M140': 'extras.heater_bed.PrinterHeaterBed.cmd_M140',
    'M106': 'extras.fan.PrinterFan.cmd_M106',
    'M107': 'extras.fan.PrinterFan.cmd_M107',
    'PID_CALIBRATE': 'gcode.GCodeDispatch.register_mux_command.<locals>.<lambda>',
    'PID_CALIBRATE:extruder': 'extras.pid_calibrate.PIDCalibrate.cmd_PID_CALIBRATE',
    'PID_CALIBRATE:heater_bed': 'extras.pid_calibrate.PIDCalibrate.cmd_PID_CALIBRATE',
    'SAVE_CONFIG': 'configfile.ConfigAutoSave.cmd_SAVE_CONFIG',
    'PAUSE': 'extras.pause_resume.PauseResume.cmd_PAUSE',
    'RESUME': 'extras.pause_resume.PauseResume.cmd_RESUME',
}

def flat_config(path):
    path = Path(path).resolve()
    files = native_config.read_tree(path)

    def expand(current, ancestors=()):
        if current in ancestors:
            raise ValueError('Recursive configuration include: ' + str(current))
        for name, block in native_config.blocks(files[current])[1]:
            if name.lower().startswith('include '):
                pattern = Path(name[8:].strip()).expanduser()
                if not pattern.is_absolute():
                    pattern = current.parent / pattern
                for match in sorted(glob.glob(str(pattern))):
                    yield from expand(Path(match).resolve(), ancestors + (current,))
            else:
                yield block

    # Match Klipper's in-place include expansion. Grouping whole files would
    # incorrectly load heaters before conversion tables included above them.
    saved = native_config.split_saved(files[path])[1]
    return '\n'.join(expand(path)) + saved

def binary_print_fixture():
    record = json.loads((ROOT / 'host/update_template/tests/reference/models_zcode.json').read_text())
    return base64.b64decode(record['m300_stock_subset_synthetic']['base64'], validate=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--dictionary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case',help='Run one named FILEOUTPUT scenario for regression diagnosis')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    base=native_config.convert_text(flat_config(args.config))
    existing = {name.lower() for name, _ in native_config.blocks(base)[1]}
    for filename in ('klipper_calibration.cfg', 'm300_operations.cfg', 'm300_tests.cfg'):
        path = Path(__file__).resolve().parents[1] / 'host/config' / filename
        extra = native_config.module.missing_macros(path.read_text(), existing)
        base += '\n' + native_config.convert_text(extra)
        existing.update(name.lower() for name, _ in native_config.blocks(extra)[1])
    settings_script = (
        'ZORTRAX_NATIVE_STATUS\nZORTRAX_SETTINGS\n'
        'ZORTRAX_LIGHT MODE=WHITE\nZORTRAX_BUZZER STATE=DISABLED\n'
        'ZORTRAX_SLEEP_MODE STATE=DISABLED\nZORTRAX_MODELS_SORT MODE=NAME_CASE\n'
        'ZORTRAX_UI_SETTING NAME=oled_brightness VALUE=8\n'
        'ZORTRAX_UI_SETTING NAME=led_brightness VALUE=5\n'
        'ZORTRAX_FULL_PLATFORM_PREHEAT STATE=ENABLED\n'
        'ZORTRAX_FULL_PLATFORM_PREHEAT STATE=DISABLED\n'
        'ZORTRAX_CONFIG_STATUS\n'
        'ZORTRAX_LANGUAGE\nZORTRAX_SETTINGS_STATUS\nZORTRAX_DISPLAY_STATUS\n'
        'ZORTRAX_INFORMATION REFRESH=0\nZORTRAX_INFO REFRESH=0\nZORTRAX_HELP\n'
        'ZORTRAX_SLEEP_MODE STATE=ENABLED\nZORTRAX_DISPLAY_STATUS\n'
        'ZORTRAX_LIGHT\nZORTRAX_BUZZER\nZORTRAX_SLEEP_MODE\nZORTRAX_MODELS_SORT\n'
        'ZORTRAX_SETTINGS_STATUS\n')
    model_fixtures = {
        'native_models_gcode': ('Model text.gcode',
            b'G90\nG28\nG1 X155 Y158 Z5 F600\nM400\nTURN_OFF_HEATERS', 'G-code'),
        'native_models_reprint': ('Repeat.gcode', b'M105\nZORTRAX_CI_REPLAY_MARK VALUE=ORIGINAL\n', 'G-code'),
        'native_models_zcode': ('Model binary.zcode', binary_print_fixture(), 'Z-code'),
        'native_models_zcode_mesh': ('Model binary.zcode', binary_print_fixture(), 'Z-code'),
        'native_models_zcode_soak': ('Model binary.zcode', binary_print_fixture(), 'Z-code'),
    }
    shutil.copy2(Path(__file__).with_name('m300_ci_models_fixture.py'),
                 args.root / 'klippy/extras/m300_ci_models_fixture.py')
    model_script = 'ZORTRAX_NATIVE_STATUS\nZORTRAX_BROWSER_LIST SOURCE=HOST\nZORTRAX_CI_RUN_MODEL\n'
    shutil.copy2(Path(__file__).with_name('m300_ci_pad_mesh_fixture.py'),
                 args.root / 'klippy/extras/m300_ci_pad_mesh_fixture.py')
    shutil.copy2(Path(__file__).with_name('m300_ci_print_fixture.py'),
                 args.root / 'klippy/extras/m300_ci_print_fixture.py')
    pad_mesh_script = (
        'ZORTRAX_CI_PAD_MESH CHECK=8\n'
        'BED_MESH PREVIEW=1\n'
        'ZORTRAX_NATIVE_STATUS\nZORTRAX_PAD_MESH_STATUS\nZORTRAX_CI_PAD_MESH\n'
        'ZORTRAX_CI_PAD_MESH CHECK=9\n'
        'BED_MESH_PROFILE LOAD=m300_pads\nZORTRAX_CI_PAD_MESH CHECK=1\n'
        'BED_MESH PREVIEW=1 FRONT_LEFT_X=31\nZORTRAX_CI_PAD_MESH CHECK=2\nBED_MESH_CLEAR\n'
        'BED_MESH_CALIBRATE\n')
    cases=[
        ('native_early_moonraker_status','ZORTRAX_NATIVE_STATUS\nZORTRAX_MAINTENANCE_STATUS\n',False,None),
        ('native_oem_error_catalog',
         'ZORTRAX_NATIVE_STATUS\nZORTRAX_UI_SHOW PAGE=errors\n'
         'ZORTRAX_UI_SHOW PAGE=error_catalog\n' + ''.join(
             'ZORTRAX_ERROR_SHOW CODE=%d\n' % code for code in
             (2,3,4,10,11,12,13,14,15,30,31,32,33,34,35,40,41,42,75,76,101))
         + 'ZORTRAX_ERROR_STATUS\n', False, None),
        ('native_oem_error_shutdown',
         'ZORTRAX_NATIVE_STATUS\nM112\nZORTRAX_ERROR_STATUS\nZORTRAX_ERROR_SHOW\n',
         False, 'Shutdown due to M112 command'),
        ('native_settings_information',settings_script,False,None),
        ('native_pad_mesh', pad_mesh_script, False, 'requires an idle native M300 with a physical MCU'),
        ('native_pad_mesh_zero_margin',
         'ZORTRAX_NATIVE_STATUS\nBED_MESH PREVIEW=1\nZORTRAX_PAD_MESH_STATUS\n'
         'ZORTRAX_CI_PAD_MESH CHECK=3\nBED_MESH_PROFILE LOAD=m300_zero_pads\n'
         'ZORTRAX_CI_PAD_MESH CHECK=4\nBED_MESH_CLEAR\nBED_MESH_CALIBRATE\n',
         False, 'requires an idle native M300 with a physical MCU'),
        ('native_pad_mesh_bounds',
         'ZORTRAX_NATIVE_STATUS\nBED_MESH PREVIEW=1\n'
         'ZORTRAX_CI_PAD_MESH CHECK=5\nBED_MESH_PROFILE LOAD=m300_contact_pads\n'
         'ZORTRAX_CI_PAD_MESH CHECK=6\n'
         'BED_MESH REAR_RIGHT_BOUNDS=260,263,300,305 PREVIEW=1\n'
         'ZORTRAX_CI_PAD_MESH CHECK=7\nBED_MESH_CLEAR\nBED_MESH_CALIBRATE\n',
         False,'requires an idle native M300 with a physical MCU'),
        ('native_controls','ZORTRAX_NATIVE_STATUS\nZORTRAX_CALIBRATION_STATUS\nZORTRAX_FILAMENT_STATUS\nM104 S40\nM140 S40\nM106 S128\nM107\nTURN_OFF_HEATERS\nPID_SAVE\n',False,None),
        ('native_bed_heat_guard','ZORTRAX_NATIVE_STATUS\nZORTRAX_CI_PRINT_PREPARE\nZORTRAX_HEAT_PLATFORM TEMP=60\n',False,
         'FILEOUTPUT cannot actuate a physical maintenance service'),
        ('native_unhomed_xyz','ZORTRAX_NATIVE_STATUS\nG1 X1 F60\n',False,'Must home axis first'),
        ('native_e_planning_FILEOUTPUT','ZORTRAX_NATIVE_STATUS\nG1 E1 F60\n',False,None),
        # Coordinates below are deliberately synthetic FILEOUTPUT fixture data.
        # They are never installed and do not prove physical homing or motion.
        ('native_xyz_planning','ZORTRAX_NATIVE_STATUS\nSET_KINEMATIC_POSITION X=150 Y=150 Z=5\nG90\nG1 X50 F12000\nG1 X250 F12000\nG1 Y50 F12000\nG1 Y250 F12000\nG1 Z10 F300\nG1 Z5 F300\nM400\nSET_VELOCITY_LIMIT\n',True,None),
        ('native_axis_bounds','ZORTRAX_NATIVE_STATUS\nSET_KINEMATIC_POSITION X=150 Y=150 Z=5\nG1 X301 F12000\n',True,'Move out of range'),
        ('normal_homing_xyz_FILEOUTPUT','ZORTRAX_NATIVE_STATUS\nG28 X0 Y0\nG28 Z\nZORTRAX_MOTION_STATUS\nG28\nZORTRAX_MOTION_STATUS\n',False,None),
        ('native_300_M220_150','ZORTRAX_NATIVE_STATUS\nSET_KINEMATIC_POSITION X=150 Y=150 Z=5\nM220 S150\nG90\nG1 X250 F12000\nTEST_ZORTRAX_XY SPEED=50\nM220 S100\nSET_VELOCITY_LIMIT ACCEL=3000\nG1 X250 F18000\nTEST_ZORTRAX_XY SPEED=60\nSET_VELOCITY_LIMIT\nZORTRAX_MOTION_STATUS\n',True,None),
        ('native_z_usable_range','ZORTRAX_NATIVE_STATUS\nSET_KINEMATIC_POSITION X=150 Y=150 Z=5\nG1 Z299 F1500\nG1 Z300\nM400\n',True,None),
        ('native_300_thermal_display_planning','ZORTRAX_NATIVE_STATUS\nSET_KINEMATIC_POSITION X=150 Y=150 Z=5\nM104 S180\nM140 S60\nM106 S128\nG90\nG1 X250 F18000\nTEST_ZORTRAX_XY SPEED=60\nZORTRAX_DISPLAY_STATUS\nTURN_OFF_HEATERS\nM107\nZORTRAX_MOTION_STATUS\n',True,None),
    ]
    cases.extend((name, model_script, False, None) for name in model_fixtures)
    cases.extend((name,'ZORTRAX_NATIVE_STATUS\nZORTRAX_CI_PRINT_RUN\n',False,None)
                 for name in ('native_print_lifecycle','native_print_cancel','native_print_cancel_soak'))
    # These identities are synthetic, never read from or sent to a printer.
    factory_cases = {
        'factory_hw04_800': (0xe4, 0xaabb0103, 'factory', 800),
        'factory_hw05_400': (0xe5, 0xaabb0103, 'factory', 400),
        'factory_config_override': (0xe4, 0xaabb0103, 'config', 400),
        'factory_erased_refused': (0xff, 0xffffffff, 'factory', 0),
    }
    shutil.copy2(Path(__file__).with_name('m300_ci_factory_fixture.py'),
                 args.root / 'klippy/extras/m300_ci_factory_fixture.py')
    for name, (_, _, _, scale) in factory_cases.items():
        script = ('ZORTRAX_NATIVE_STATUS\nSET_KINEMATIC_POSITION X=150 Y=150 Z=5\n'
                  'ZORTRAX_CI_SCALE_CHECK MODE=START\nG90\nG1 Z6 F60\nM400\n'
                  'ZORTRAX_CI_SCALE_CHECK MODE=END\nZORTRAX_HARDWARE_STATUS\n')
        cases.append((name, script, True, 'missing/corrupt factory ID3' if not scale else None))
    results=[]
    if args.case:
        cases=[case for case in cases if case[0]==args.case]
        if not cases:raise ValueError('Unknown FILEOUTPUT case: '+args.case)
    shutil.copy2(Path(__file__).with_name('m300_ci_early_status.py'),
                 args.root/'klippy/extras/m300_ci_early_status.py')
    shutil.copy2(Path(__file__).with_name('m300_ci_thermal_bindings.py'),
                 args.root/'klippy/extras/m300_ci_thermal_bindings.py')
    shutil.copy2(Path(__file__).with_name('m300_ci_runtime_bindings.py'),
                 args.root/'klippy/extras/m300_ci_runtime_bindings.py')
    for name,script,synthetic,error in cases:
        dest=args.output/name
        dest.mkdir(exist_ok=True)
        (dest/'gcodes').mkdir(exist_ok=True)
        cp=configparser.RawConfigParser()
        cp.read_string(base)
        if 'TEST_ZORTRAX_XY' in script:
            cp.read(Path(__file__).resolve().parents[1]/'host/update_template/legacy/m300_tests.cfg')
        cp.add_section('m300_ci_thermal_bindings')
        cp.add_section('m300_ci_runtime_bindings')
        if name == 'native_early_moonraker_status':
            cp.add_section('m300_ci_early_status')
            if not cp.has_section('gcode_arcs'):
                cp.add_section('gcode_arcs')
        for section in ('stepper_x', 'stepper_y', 'stepper_z', 'extruder'):
            assert cp.getfloat(section, 'step_pulse_duration') == .000002
        assert cp.getfloat('m300_motion', 'z_home_hotend_target') == 180
        assert cp.getfloat('m300_calibration', 'procedure_temperature') == 260
        assert cp.getfloat('m300_filament', 'procedure_temperature') == 240
        assert cp.getfloat('printer', 'max_velocity') >= 300
        for color in 'rgb':
            led = 'output_pin m300_led_' + color
            assert cp.getboolean(led, 'pwm') and cp.getfloat(led, 'cycle_time') == .010
        assert not cp.getboolean('output_pin m300_buzzer', 'pwm', fallback=False)
        cp.set('virtual_sdcard','path',str(dest/'gcodes'))
        # Repeated FILEOUTPUT runs must not inherit previously saved settings
        # or late writes from an earlier process using the same output root.
        state_dir=Path(tempfile.mkdtemp(prefix='nvm-',dir=dest))
        cp.set('m300_nvm','path',str(state_dir/'settings.json'))
        if name in ('native_pad_mesh','native_pad_mesh_zero_margin','native_pad_mesh_bounds'):
            cp.set('stepper_x', 'position_max', '300')
            cp.set('stepper_y', 'position_max', '305')
            cp.read_dict({'bed_mesh': {'mesh_min': '10, 10', 'mesh_max': '299, 304',
                                       'probe_count': '3, 3', 'mesh_pps': '0, 0'},
                          'm300_pad_mesh': {}, 'm300_ci_pad_mesh_fixture': {}})
            if name in ('native_pad_mesh_zero_margin','native_pad_mesh_bounds'):
                cp.read_dict({'m300_pad_mesh': {'corner_pad_width':'60','center_pad_width':'50',
                    'edge_margin':'0','travel_margin':'0','front_left_x':'15','front_left_y':'15',
                    'front_right_x':'285','front_right_y':'15','center_x':'150','center_y':'150',
                    'rear_left_x':'15','rear_left_y':'290','rear_right_x':'285','rear_right_y':'290'}})
            if name == 'native_pad_mesh_bounds':
                cp.read_dict({'m300_pad_mesh': {'front_left_bounds':'0,0,43,51',
                    'front_right_bounds':'260,0,300,51','center_bounds':'125,125,175,175',
                    'rear_left_bounds':'0,260,43,305','rear_right_bounds':'260,262,300,305'}})
        if name in model_fixtures:
            filename, data, _ = model_fixtures[name]
            (dest / 'gcodes' / filename).write_bytes(data)
            cp.add_section('m300_ci_models_fixture')
            if name == 'native_models_reprint':
                cp.set('m300_ci_models_fixture', 'replay', 'True')
            if model_fixtures[name][2]=='Z-code':
                cp.set('stepper_y','position_max','305')
            if name=='native_models_zcode_mesh':
                cp.set('m300_ci_models_fixture','mesh','True')
                cp.read_dict({'bed_mesh':{'mesh_min':'0,0','mesh_max':'300,305',
                                        'probe_count':'3,3','algorithm':'lagrange'}})
            if name=='native_models_zcode_soak':
                cp.set('m300_ci_models_fixture','soak','True')
                cp.set('m300_print_control','platform_soak_seconds','2')
            assert not cp.getboolean('m300_job', 'workflow_qualified')
        if name in ('native_print_lifecycle','native_print_cancel','native_print_cancel_soak'):
            cp.add_section('m300_ci_print_fixture')
            cp.set('m300_ci_print_fixture','mode',
                   'cancel_soak' if name.endswith('cancel_soak') else 'cancel' if name.endswith('cancel') else 'lifecycle')
            if name.endswith('cancel_soak'):cp.set('m300_print_control','platform_soak_seconds','2')
            cp.set('stepper_y','position_max','305')
            if not cp.has_section('bed_mesh'):
                cp.read_dict({'bed_mesh':{'mesh_min':'0,0','mesh_max':'300,305',
                              'probe_count':'3,3','algorithm':'lagrange'}})
        if name=='native_bed_heat_guard':cp.add_section('m300_ci_print_fixture')
        if synthetic:
            if not cp.has_section('force_move'):cp.add_section('force_move')
            cp.set('force_move','enable_force_move','True')
        if name in factory_cases:
            raw, header, profile, scale = factory_cases[name]
            cp.set('m300_mcu', 'z_profile', profile)
            cp.add_section('m300_ci_factory_fixture')
            for key, value in {'raw': raw, 'header': header, 'expected_steps': scale}.items():
                cp.set('m300_ci_factory_fixture', key, str(value))
        config=io.StringIO();cp.write(config)
        (dest/'printer.cfg').write_text(config.getvalue())
        (dest/'input.gcode').write_text('ZORTRAX_DISPLAY_STATUS\n' + script)
        # Klippy opens its log in append mode. Discard a prior validation
        # run's output so repeated checks report only this startup's handlers.
        log = dest / 'klippy.log'
        log.unlink(missing_ok=True)
        command=[sys.executable,str(args.root/'klippy/klippy.py'),str(dest/'printer.cfg'),
                 '-i',str(dest/'input.gcode'),'-o',str(dest/'protocol.bin'),'-d',str(args.dictionary)]
        command+=['-l',str(log)]
        process=subprocess.run(command,capture_output=True,text=True,timeout=45)
        text=process.stdout+process.stderr+log.read_text()
        log.write_text(text)
        if name == 'factory_erased_refused':
            assert error in text, (name, text[-3000:])
            assert "Configured MCU 'mcu'" not in text
            results.append({'case': name, 'PASS': True, 'startup_refused': True,
                            'synthetic_factory_record': True, 'physical_hardware': False})
            continue
        assert 'M300_DISPLAY ' in text, (name, process.returncode, text[-4000:])
        if name=='native_early_moonraker_status':
            snapshots=[json.loads(line.split('M300_CI_EARLY_STATUS ',1)[1])
                       for line in text.splitlines() if 'M300_CI_EARLY_STATUS ' in line]
            assert [s['phase'] for s in snapshots]==['before_connect','ready'],text[-4000:]
            assert all(s['objects']>=40 for s in snapshots)
        display_line=next(line.split('M300_DISPLAY ',1)[1] for line in text.splitlines() if 'M300_DISPLAY ' in line)
        # M112 deliberately revokes the host display lease; the MCU local
        # screen owns the panel after shutdown. Other cases remain connected.
        assert json.loads(display_line)['connected'] is (name != 'native_oem_error_shutdown'), (name, display_line)
        report_line=next(line.split('M300_NATIVE ',1)[1] for line in text.splitlines() if 'M300_NATIVE ' in line)
        bindings=json.loads(report_line)
        expected=dict(EXPECTED)
        # The M300 target guard is deliberate; still require its exact native
        # Heater backends, checked in-process without sending heater commands.
        thermal = next(json.loads(line.split('M300_CI_THERMAL_BINDINGS ',1)[1])
                       for line in text.splitlines() if 'M300_CI_THERMAL_BINDINGS ' in line)
        assert thermal['PASS'] and not thermal['targets_changed'], (name, thermal)
        for heater in ('extruder', 'heater_bed'):
            for method in ('set_temp', 'alter_target'):
                key=heater+'.'+method
                assert key in thermal['native_backends'], (name, key, thermal)
                expected[key]='extras.m300_temperature_policy.M300TemperaturePolicy._connect.<locals>.guarded'
        if cp.has_section('m300_print_control'):
            for key in ('G0','G1','SAVE_CONFIG','PID_CALIBRATE','PAUSE','RESUME'):
                expected[key+':native_backend']=EXPECTED[key]
            for key in ('G0','G1','SAVE_CONFIG','PID_CALIBRATE'):
                expected[key]='extras.m300_print_control.M300PrintControl._connect.<locals>.guarded'
            for key in ('G28','PAUSE','RESUME'):
                expected[key]='extras.m300_print_control.M300PrintControl.cmd_'+key
            expected['G28:m300_backend']=EXPECTED['G28']
        runtime = next(json.loads(line.split('M300_CI_RUNTIME_BINDINGS ', 1)[1])
                       for line in text.splitlines() if 'M300_CI_RUNTIME_BINDINGS ' in line)
        expected_commands = {'G0', 'G1', 'M109', 'M190', 'TEMPERATURE_WAIT'}
        if cp.has_section('gcode_arcs'):
            expected_commands.update(('G2', 'G3'))
        assert set(runtime) == expected_commands, (name, runtime)
        for key in ('G0', 'G1'):
            chain = runtime[key]
            downstream = ([expected[key], EXPECTED[key]] if cp.has_section('m300_print_control')
                          else [EXPECTED[key]])
            assert chain[1:] == downstream, (name, key, chain)
            expected[key] = chain[0]
        for key,owner in expected.items():
            assert bindings['owners'][key]==owner,(name,key,bindings['owners'][key],owner)
        if error:
            assert error in text,(name,'expected native refusal absent',text[-2000:])
            assert 'M300 requires fresh armed' not in text,name
        else:
            assert process.returncode==0,(name,text[-3000:])
            assert 'Traceback' not in text and 'Error on' not in text,(name,text[-2000:])
        assert 'Unknown command:' not in text, (name, 'undispatched G-code command', text[-4000:])
        if name == 'native_pad_mesh':
            assert 'M300_CI_FOOTER native upper rows and full message passed' in text
            status = next(json.loads(line.split('M300_PAD_MESH ', 1)[1])
                          for line in text.splitlines() if 'M300_PAD_MESH ' in line)
            assert len(status['probe_points']) == 25 and status['result'] is None
            assert 'has been saved to profile [m300_pads]' in text
            assert 'M300_CI_PAD_MESH profile load passed' in text
            assert 'M300_CI_PAD_MESH macro preview passed' in text
            assert 'Traceback' not in text
            snapshot=next(json.loads(line.split('M300_NATIVE_MESH_SNAPSHOT ',1)[1])
                          for line in text.splitlines() if 'M300_NATIVE_MESH_SNAPSHOT ' in line)
            assert snapshot['bed_mesh']['mesh_matrix']==[[]]
            (dest/'native_mesh_status.json').write_text(json.dumps(snapshot))
        if name.startswith('native_oem_error_'):
            view = next(json.loads(line.split('M300_ERRORS ',1)[1]) for line in text.splitlines()
                        if 'M300_ERRORS ' in line)
            assert view['catalogue_size'] == 21 and view['mcu_abi'] == 1, view
            if name == 'native_oem_error_catalog':
                assert view['current'] is None and not view['history'], view
                entries = [json.loads(line.split('M300_ERROR_VIEW ',1)[1]) for line in text.splitlines()
                           if 'M300_ERROR_VIEW ' in line]
                assert len(entries) == 21 and all(entry['catalogue'] for entry in entries)
                for code in (2,3,4,10,11,12,13,14,15,30,31,32,33,34,35,40,41,42,75,76,101):
                    assert any(e['code'] == code and e['label'] == 'Error #%03d' % code for e in entries)
            else:
                assert view['current']['code'] == 0 and view['current']['kind'] == 5, view
                assert view['current']['fatal'] is True, view
                assert 'Shutdown due to M112 command' in view['current']['reason'], view
        if name == 'native_pad_mesh_zero_margin':
            assert 'M300_CI_PAD_MESH zero-margin geometry passed' in text
            assert 'M300_CI_PAD_MESH zero-margin profile load passed' in text
            assert 'Traceback' not in text
        if name == 'native_pad_mesh_bounds':
            for message in ('contact rectangles passed','rectangle profile load passed',
                            'rectangle macro override passed'):
                assert 'M300_CI_PAD_MESH '+message in text
            assert 'Traceback' not in text
        if name == 'native_settings_information':
            views = [json.loads(line.split('M300_SETTINGS ', 1)[1]) for line in text.splitlines()
                        if 'M300_SETTINGS ' in line]
            view = views[-3]
            assert view['settings'] == dict(light_mode='WHITE', sound=False, sleep_mode='DISABLED',full_platform_preheat=False,
                                            sort_mode='NAME_CASE', language='EN',
                                            oled_brightness=8, led_brightness=5), view
            resources = next(json.loads(line.split('M300_CONFIG ', 1)[1])
                             for line in text.splitlines() if 'M300_CONFIG ' in line)
            assert resources['software_pwm_count'] == 7, resources
            displays = [json.loads(line.split('M300_DISPLAY ', 1)[1]) for line in text.splitlines()
                        if 'M300_DISPLAY ' in line]
            assert [d['sleep_enabled'] for d in displays] == [True, False, True], displays
            assert [d['brightness'] for d in displays] == [16, 8, 8], displays
            expected_release = json.loads(args.dictionary.read_text())['config']['M300_MCU_RELEASE']
            assert view['information']['mcu_release'] == expected_release
            assert views[-2]['settings'] == views[-1]['settings'], views[-2:]
            assert 'M300_INFORMATION ' in text
            assert 'https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper' in text
        if name in model_fixtures:
            result = next(json.loads(line.split('M300_CI_MODELS ', 1)[1])
                          for line in text.splitlines() if 'M300_CI_MODELS ' in line)
            filename, _, kind = model_fixtures[name]
            assert result['state'] == 'complete' and result['file_consumed'], (name, result)
            assert result['filename'] == filename and result['format'] == kind, result
            assert result['targets'] == [0., 0.], result
            assert result['explicit_resume'] == (kind == 'Z-code'), result
            assert result['explicit_reprint'] == (name == 'native_models_reprint'), result
            if name == 'native_models_reprint':
                assert result['replay_marks'] == ['ORIGINAL', 'ORIGINAL'], result
            elif kind=='G-code':
                assert result['position'][:3] == [155.,158.,5.],result
            else:
                assert result['position'][:2] == [300.,305.] and 14.<result['position'][2]<16.,result
                phases=result['control_phases']
                start=next(p['start'] for p in phases if p['phase']=='HEATING')
                assert start['mesh']==('m300_pads' if name.endswith('_mesh') else 'NONE'),result
                assert start['requested_mesh']=='AUTO',result
                names=[p['phase'] for p in phases]
                assert names.index('HEATING')<names.index('HOMING')<names.index('END_PARK'),result
                assert ('PLATFORM_SOAK' in names)==name.endswith('_soak'),result
        if name in ('native_print_lifecycle','native_print_cancel','native_print_cancel_soak'):
            result=next(json.loads(line.split('M300_CI_PRINT ',1)[1])
                        for line in text.splitlines() if 'M300_CI_PRINT ' in line)
            assert result['targets']==[0.,0.] and result['file_consumed'],result
            assert result['control']['state']=='IDLE' and not result['control']['paused'],result
            if name.endswith('cancel_soak'):
                assert result['state']=='cancelled' and result['marks']==[],result
                assert result['position'][:3]==[0.,0.,0.],result
            elif name.endswith('cancel'):
                assert result['state']=='cancelled' and result['marks']==['STARTED'],result
                assert result['position'][:2]==[300.,305.],result
            else:
                assert result['position'][:2]==[300.,305.],result
                assert result['state']=='complete',result
                assert result['marks']==['STARTED','RESUMED','CHANGED','ENDED'],result
                assert 'FILAMENT_READY' in result['actions'] and result['actions'].count('RESUME')==2,result
        if name == 'native_controls':
            calibration=next(json.loads(line[line.index('{'):]) for line in text.splitlines()
                             if 'calibration_api_version' in line and 'procedure_temperature' in line)
            filament=next(json.loads(line.split('M300_FILAMENT ',1)[1]) for line in text.splitlines()
                          if 'M300_FILAMENT ' in line)
            assert calibration['procedure_temperature'] == 260.
            assert filament['procedure_temperature'] == 240.
        if name == 'native_300_M220_150':
            view = next(json.loads(line.split('M300_MOTION ', 1)[1]) for line in text.splitlines()
                        if 'M300_MOTION ' in line)
            assert view['native_position'][:2] == [50., 50.], view
        if name in factory_cases:
            check_line = next(line.split('M300_CI_FACTORY ', 1)[1] for line in text.splitlines()
                              if 'M300_CI_FACTORY ' in line)
            assert json.loads(check_line)['native_steps_for_1mm'] == factory_cases[name][3]
        if name == 'normal_homing_xyz_FILEOUTPUT':
            views = [json.loads(line.split('M300_MOTION ', 1)[1]) for line in text.splitlines()
                     if 'M300_MOTION ' in line]
            assert len(views) == 2
            for view in views:
                assert view['state'] == 'COMPLETE' and view['homed_axes'] == 'xyz'
                assert abs(view['native_position'][2] - 5) < 1e-6
                assert view['z_home_hotend_target_c'] == 180
                assert view['failure_phase'] is None
                speeds = view['homing_speed_mm_s']
                assert speeds['native_rails']['z'] == {'seek': 4., 'retract': 4., 'second_seek': 2.}
                assert speeds['xy_to_contact'] == 50. and speeds['z_precision'] == .5
        if name == 'native_300_thermal_display_planning':
            view = next(json.loads(line.split('M300_MOTION ', 1)[1]) for line in text.splitlines()
                        if 'M300_MOTION ' in line)
            assert view['native_position'] == [50., 50., 5., 0.]
        results.append({'case':name,'PASS':True,'expected_native_refusal':error,
                        'synthetic_coordinates':synthetic,'physical_hardware':False,
                        'exit_code':process.returncode,
                        'protocol_bytes':(dest/'protocol.bin').stat().st_size,
                        'native_bindings':bindings['owners'],
                        'runtime_command_chains':runtime})
        results[-1]['synthetic_factory_record'] = name in factory_cases
    result={'status':'PASS_REAL_KLIPPY_NATIVE_CORE','cases':results,
            'FILEOUTPUT':True,'physical_UART':False,'MCU_executed':False,
            'FILEOUTPUT_native_cold_extrusion_check_disabled_by_upstream':True,
            'printer_motion_or_heating_qualified':False}
    (args.output/'REPORT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'cases':len(results),'physical_hardware':False}))

if __name__=='__main__':main()
