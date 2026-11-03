#!/usr/bin/env python3
"""Actual pinned Klippy processes, FILEOUTPUT only: no printer UART or MCU execution."""
import argparse
import configparser
import io
import json
from pathlib import Path
import subprocess
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import native_config

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
    files = native_config.read_tree(path)
    sections = []
    for text in files.values():
        for name, block in native_config.blocks(text)[1]:
            if not name.lower().startswith('include '):
                sections.append(block)
    saved = native_config.split_saved(files[Path(path).resolve()])[1]
    return '\n'.join(sections) + saved

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--dictionary',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
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
        'ZORTRAX_LANGUAGE\nZORTRAX_SETTINGS_STATUS\nZORTRAX_DISPLAY_STATUS\n'
        'ZORTRAX_INFORMATION REFRESH=0\nZORTRAX_INFO REFRESH=0\nZORTRAX_HELP\n'
        'ZORTRAX_SLEEP_MODE STATE=ENABLED\nZORTRAX_DISPLAY_STATUS\n')
    cases=[
        ('native_settings_information',settings_script,False,None),
        ('native_controls','ZORTRAX_NATIVE_STATUS\nZORTRAX_CALIBRATION_STATUS\nZORTRAX_FILAMENT_STATUS\nM104 S40\nM140 S40\nM106 S128\nM107\nTURN_OFF_HEATERS\nPID_SAVE\n',False,None),
        ('native_unhomed_xyz','ZORTRAX_NATIVE_STATUS\nG1 X1 F60\n',False,'Must home axis first'),
        ('native_e_planning_FILEOUTPUT','ZORTRAX_NATIVE_STATUS\nG1 E1 F60\n',False,None),
        # Coordinates below are deliberately synthetic FILEOUTPUT fixture data.
        # They are never installed and do not prove physical homing or motion.
        ('native_xyz_planning','ZORTRAX_NATIVE_STATUS\nSET_KINEMATIC_POSITION X=150 Y=150 Z=5\nG90\nG1 X50 F12000\nG1 X250 F12000\nG1 Y50 F12000\nG1 Y250 F12000\nG1 Z10 F300\nG1 Z5 F300\nM400\nSET_VELOCITY_LIMIT\n',True,None),
        ('native_axis_bounds','ZORTRAX_NATIVE_STATUS\nSET_KINEMATIC_POSITION X=150 Y=150 Z=5\nG1 X301 F12000\n',True,'Move out of range'),
        ('normal_homing_xyz_FILEOUTPUT','ZORTRAX_NATIVE_STATUS\nG28 X0 Y0\nG28 Z\nZORTRAX_MOTION_STATUS\nG28\nZORTRAX_MOTION_STATUS\n',False,None),
        ('native_300_M220_150','ZORTRAX_NATIVE_STATUS\nSET_KINEMATIC_POSITION X=150 Y=150 Z=5\nM220 S150\nTEST_ZORTRAX_XY SPEED=200\nM220 S100\nTEST_ZORTRAX_XY SPEED=300\nSET_VELOCITY_LIMIT ACCEL=3000\nTEST_ZORTRAX_XY SPEED=300\nSET_VELOCITY_LIMIT\nZORTRAX_MOTION_STATUS\n',True,None),
        ('native_z_usable_range','ZORTRAX_NATIVE_STATUS\nSET_KINEMATIC_POSITION X=150 Y=150 Z=5\nG1 Z299 F1500\nG1 Z300\nM400\n',True,None),
        ('native_300_thermal_display_planning','ZORTRAX_NATIVE_STATUS\nSET_KINEMATIC_POSITION X=150 Y=150 Z=5\nM104 S180\nM140 S60\nM106 S128\nTEST_ZORTRAX_XY SPEED=300\nZORTRAX_DISPLAY_STATUS\nTURN_OFF_HEATERS\nM107\nZORTRAX_MOTION_STATUS\n',True,None),
    ]
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
    for name,script,synthetic,error in cases:
        dest=args.output/name
        dest.mkdir(exist_ok=True)
        (dest/'gcodes').mkdir(exist_ok=True)
        cp=configparser.RawConfigParser()
        cp.read_string(base)
        for section in ('stepper_x', 'stepper_y', 'stepper_z', 'extruder'):
            assert cp.getfloat(section, 'step_pulse_duration') == .000002
        assert cp.getfloat('m300_motion', 'z_home_hotend_target') == 180
        assert cp.getfloat('m300_calibration', 'procedure_temperature') == 260
        assert cp.getfloat('m300_filament', 'procedure_temperature') == 240
        assert cp.getfloat('printer', 'max_velocity') >= 300
        cp.set('virtual_sdcard','path',str(dest/'gcodes'))
        cp.set('m300_nvm','path',str(dest/'settings.json'))
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
        command=[sys.executable,str(args.root/'klippy/klippy.py'),str(dest/'printer.cfg'),
                 '-i',str(dest/'input.gcode'),'-o',str(dest/'protocol.bin'),'-d',str(args.dictionary)]
        with (dest/'klippy.log').open('w') as log:
            process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=30)
        text=(dest/'klippy.log').read_text(errors='replace')
        if name == 'factory_erased_refused':
            assert error in text, (name, text[-3000:])
            assert "Configured MCU 'mcu'" not in text
            results.append({'case': name, 'PASS': True, 'startup_refused': True,
                            'synthetic_factory_record': True, 'physical_hardware': False})
            continue
        display_line=next(line.split('M300_DISPLAY ',1)[1] for line in text.splitlines() if 'M300_DISPLAY ' in line)
        assert json.loads(display_line)['connected'] is True, (name, display_line)
        report_line=next(line.split('M300_NATIVE ',1)[1] for line in text.splitlines() if 'M300_NATIVE ' in line)
        bindings=json.loads(report_line)
        for key,owner in EXPECTED.items():
            assert bindings['owners'][key]==owner,(name,key,bindings['owners'][key],owner)
        if error:
            assert error in text,(name,'expected native refusal absent',text[-2000:])
            assert 'M300 requires fresh armed' not in text,name
        else:
            assert process.returncode==0,(name,text[-3000:])
            assert 'Traceback' not in text and 'Error on' not in text,(name,text[-2000:])
        assert 'Unknown command:' not in text, (name, 'undispatched G-code command', text[-4000:])
        if name == 'native_settings_information':
            views = [json.loads(line.split('M300_SETTINGS ', 1)[1]) for line in text.splitlines()
                        if 'M300_SETTINGS ' in line]
            view = views[-2]
            assert view['settings'] == dict(light_mode='WHITE', sound=False, sleep_mode='DISABLED',
                                            sort_mode='NAME_CASE', language='EN'), view
            displays = [json.loads(line.split('M300_DISPLAY ', 1)[1]) for line in text.splitlines()
                        if 'M300_DISPLAY ' in line]
            assert [d['sleep_enabled'] for d in displays] == [True, False, True], displays
            assert view['information']['mcu_release'] == '0.13.14.5-FACTORY-Z-UART8'
            assert 'M300_INFORMATION ' in text
            assert 'https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper' in text
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
        if name == 'native_300_thermal_display_planning':
            view = next(json.loads(line.split('M300_MOTION ', 1)[1]) for line in text.splitlines()
                        if 'M300_MOTION ' in line)
            assert view['native_position'] == [50., 50., 5., 0.]
        results.append({'case':name,'PASS':True,'expected_native_refusal':error,
                        'synthetic_coordinates':synthetic,'physical_hardware':False,
                        'exit_code':process.returncode,
                        'protocol_bytes':(dest/'protocol.bin').stat().st_size,
                        'native_bindings':bindings['owners']})
        results[-1]['synthetic_factory_record'] = name in factory_cases
    result={'status':'PASS_REAL_KLIPPY_NATIVE_CORE','cases':results,
            'FILEOUTPUT':True,'physical_UART':False,'MCU_executed':False,
            'FILEOUTPUT_native_cold_extrusion_check_disabled_by_upstream':True,
            'printer_motion_or_heating_qualified':False}
    (args.output/'REPORT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'cases':len(results),'physical_hardware':False}))

if __name__=='__main__':main()
