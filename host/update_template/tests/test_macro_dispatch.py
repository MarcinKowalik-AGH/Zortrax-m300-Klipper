"""Exercise published macro names through the actual pinned G-code lexer."""
import configparser
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
import jinja2

import test_display
from payload.m300_procedures import M300Procedures
import m300_profile
from setup_fluidd import merge_groups

ROOT=Path(__file__).resolve().parents[1]
ENV=jinja2.Environment(variable_start_string='{',variable_end_string='}')
spec=importlib.util.spec_from_file_location('macro_native_gcode',ROOT/'tests/reference/native_gcode.py')
native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)


def dispatcher():
    printer=NS(get_start_args=lambda:{},register_event_handler=lambda *args:None,
        get_reactor=lambda:NS(mutex=lambda:None),config_error=RuntimeError,
        command_error=native.CommandError,is_shutdown=lambda:False)
    g=native.GCodeDispatch(printer)
    output=[];g.register_output_handler(output.append);g._handle_ready();output.clear()
    return g,printer,output


def templates():
    cp=configparser.RawConfigParser()
    cp.read(ROOT/'payload/m300_tests.cfg')
    return {name[12:]:cp.get(name,'gcode') for name in cp.sections() if name.startswith('gcode_macro ')}


class MacroDispatchTests(unittest.TestCase):
    def test_old_digit_in_middle_name_registers_but_cannot_be_dispatched(self):
        g,printer,output=dispatcher();called=[]
        g.register_command('TEST_M300_LEVEL',lambda cmd:called.append(True))
        g.run_script_from_command('TEST_M300_LEVEL')
        self.assertEqual(called,[])
        self.assertTrue(any('Unknown command:"TEST_M300"' in line for line in output))

    def test_all_published_macro_names_roundtrip_through_native_lexer(self):
        for path in (ROOT/'payload').glob('*.cfg'):
            cp=configparser.RawConfigParser();cp.read(path)
            for section in cp.sections():
                if not section.startswith('gcode_macro '):continue
                name=section[12:]
                with self.subTest(name=name):
                    g,printer,output=dispatcher();called=[]
                    g.register_command(name,lambda cmd:called.append(cmd.get_command()))
                    g.run_script_from_command(name)
                    self.assertEqual(called,[name]);self.assertEqual(output,[])

    def test_level_button_renders_and_reaches_shared_procedure_owner(self):
        g,printer,output=dispatcher();calls=[]
        p=M300Procedures.__new__(M300Procedures)
        p.printer=NS(lookup_object=lambda name:NS(start=lambda temp:calls.append(temp)))
        p.reactor=NS(NOW=0.,update_timer=lambda *args:None);p.timer='procedure'
        g.register_command('ZORTRAX_PROCEDURE_START',p.cmd_start)
        template=ENV.from_string(templates()['TEST_ZORTRAX_LEVEL'])
        g.register_command('TEST_ZORTRAX_LEVEL',lambda cmd:g.run_script_from_command(
            template.render(params=cmd.get_command_parameters())))
        g.run_script_from_command('TEST_ZORTRAX_LEVEL')
        self.assertEqual(calls,[180.]);self.assertEqual(output,[])

    def test_xy_button_renders_and_dispatches_all_seven_native_moves(self):
        g,printer,output=dispatcher();moves=[]
        for name in ('SAVE_GCODE_STATE','G90','M400','RESTORE_GCODE_STATE'):
            g.register_command(name,lambda cmd:None)
        g.register_command('G1',lambda cmd:moves.append(cmd.get_command_parameters()))
        toolhead=NS(homed_axes='xyz',axis_minimum=NS(x=0.,y=0.),axis_maximum=NS(x=300.,y=300.))
        def fail(message):raise RuntimeError(message)
        script=ENV.from_string(templates()['TEST_ZORTRAX_XY']).render(
            params={'SPEED':'300'},printer=NS(toolhead=toolhead),action_raise_error=fail)
        g.run_script_from_command(script)
        self.assertEqual(len(moves),7)
        self.assertEqual(float(moves[0]['F']),18000.)
        self.assertEqual(output,[])

    def test_status_button_dispatches_every_diagnostic_command(self):
        g,printer,output=dispatcher();calls=[]
        script=templates()['TEST_ZORTRAX_STATUS']
        names=[line.strip() for line in script.splitlines() if line.strip()]
        for name in names:g.register_command(name,lambda cmd:calls.append(cmd.get_command()))
        g.run_script_from_command(script)
        self.assertEqual(calls,names);self.assertEqual(output,[])

    def test_migration_renames_headers_preserves_bodies_and_is_reversible_by_installer(self):
        source='[gcode_macro TEST_M300_XY]\ndescription: My test\ngcode:\n    G1 X{params.X|default(50)}\n'
        result=m300_profile.convert_text(source)
        self.assertEqual(result,source.replace('[gcode_macro TEST_M300_XY]','[gcode_macro TEST_ZORTRAX_XY]'))
        self.assertEqual(m300_profile.convert_text(result),result)

    def test_fluidd_migration_keeps_hidden_and_color_preferences(self):
        before={'stored':[{'name':'TEST_M300_LEVEL','visible':False,'color':'red'}]}
        after,assigned=merge_groups(before,['TEST_ZORTRAX_LEVEL'])
        self.assertEqual(after['stored'][0]['name'],'TEST_ZORTRAX_LEVEL')
        self.assertFalse(after['stored'][0]['visible']);self.assertEqual(after['stored'][0]['color'],'red')
        self.assertEqual(assigned['TEST_ZORTRAX_LEVEL'],'TEST M300')
        self.assertEqual(before['stored'][0]['name'],'TEST_M300_LEVEL')


if __name__=='__main__':unittest.main()
