#!/usr/bin/env python3
"""Actual pinned Klippy processes, FILEOUTPUT only: no printer UART or MCU execution."""
import argparse
import configparser
import io
import json
from pathlib import Path
import subprocess
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
    cases=[
        ('native_controls','ZORTRAX_NATIVE_STATUS\nM104 S40\nM140 S40\nM106 S128\nM107\nTURN_OFF_HEATERS\nPID_SAVE\n',False,None),
        ('native_unhomed_xyz','ZORTRAX_NATIVE_STATUS\nG1 X1 F60\n',False,'Must home axis first'),
        ('native_e_planning_FILEOUTPUT','ZORTRAX_NATIVE_STATUS\nG1 E1 F60\n',False,None),
        # Coordinates below are deliberately synthetic FILEOUTPUT fixture data.
        # They are never installed and do not prove physical homing or motion.
        ('native_xyz_planning','ZORTRAX_NATIVE_STATUS\nSET_KINEMATIC_POSITION X=150 Y=150 Z=5\nG90\nG1 X50 F12000\nG1 X250 F12000\nG1 Y50 F12000\nG1 Y250 F12000\nG1 Z10 F300\nG1 Z5 F300\nM400\nSET_VELOCITY_LIMIT\n',True,None),
        ('native_axis_bounds','ZORTRAX_NATIVE_STATUS\nSET_KINEMATIC_POSITION X=150 Y=150 Z=5\nG1 X301 F12000\n',True,'Move out of range'),
    ]
    results=[]
    for name,script,synthetic,error in cases:
        dest=args.output/name
        dest.mkdir(exist_ok=True)
        (dest/'gcodes').mkdir(exist_ok=True)
        cp=configparser.RawConfigParser()
        cp.read_string(base)
        cp.set('virtual_sdcard','path',str(dest/'gcodes'))
        cp.set('m300_nvm','path',str(dest/'settings.json'))
        if synthetic:
            if not cp.has_section('force_move'):cp.add_section('force_move')
            cp.set('force_move','enable_force_move','True')
        config=io.StringIO();cp.write(config)
        (dest/'printer.cfg').write_text(config.getvalue())
        (dest/'input.gcode').write_text('ZORTRAX_DISPLAY_STATUS\n' + script)
        command=[sys.executable,str(args.root/'klippy/klippy.py'),str(dest/'printer.cfg'),
                 '-i',str(dest/'input.gcode'),'-o',str(dest/'protocol.bin'),'-d',str(args.dictionary)]
        with (dest/'klippy.log').open('w') as log:
            process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=30)
        text=(dest/'klippy.log').read_text(errors='replace')
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
        results.append({'case':name,'PASS':True,'expected_native_refusal':error,
                        'synthetic_coordinates':synthetic,'physical_hardware':False,
                        'exit_code':process.returncode,
                        'protocol_bytes':(dest/'protocol.bin').stat().st_size,
                        'native_bindings':bindings['owners']})
    result={'status':'PASS_REAL_KLIPPY_NATIVE_CORE','cases':results,
            'FILEOUTPUT':True,'physical_UART':False,'MCU_executed':False,
            'FILEOUTPUT_native_cold_extrusion_check_disabled_by_upstream':True,
            'printer_motion_or_heating_qualified':False}
    (args.output/'REPORT.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'cases':len(results),'physical_hardware':False}))

if __name__=='__main__':main()
