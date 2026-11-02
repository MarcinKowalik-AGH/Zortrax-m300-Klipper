"""OEM procedure defaults with modeled authority and heater boundaries."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

import test_display
from payload.m300_filament import M300Filament


def filament():
    reactor=NS(monotonic=lambda:1.,NOW=0.,register_timer=lambda cb:cb,update_timer=Mock())
    board=NS(get_mcu=lambda:NS(register_config_callback=Mock()))
    job=NS(board=board,machine=NS(state='IDLE',token=7),m04_service_busy=lambda:False,
           _cleanup_pending=False,_resume_checking=False,_ops=[],_waiting=None,
           _executing=False,sd=NS(is_preparing=False),pause=Mock())
    printer=NS(get_reactor=lambda:reactor,command_error=RuntimeError,is_shutdown=lambda:False,
               lookup_object=lambda name:NS(register_command=Mock()),
               load_object=lambda config,name:job,register_event_handler=Mock())
    config=NS(get_printer=lambda:printer,getfloat=lambda name,default,**kw:default,
              getboolean=lambda name,default:True if name=='filament_qualified' else default,
              error=RuntimeError)
    f=M300Filament(config)
    f.toolhead=NS(get_extruder=lambda:NS(max_e_dist=50.))
    f.hotend=NS(min_extrude_temp=170.,max_temp=300.,set_temp=Mock())
    f._live=Mock();f._sensor=Mock()
    f._capture=Mock(side_effect=lambda:f.hotend.set_temp(f.target))
    return f


class ProcedureTemperatures(unittest.TestCase):
    def test_standalone_load_and_unload_use_240_without_manual_temp(self):
        for operation in ('LOAD','UNLOAD'):
            f=filament();f.start(operation)
            self.assertEqual(f.procedure_temperature,240.)
            self.assertEqual(f.target,240.)
            self.assertEqual(f.machine.state,'HEATING')
            f.hotend.set_temp.assert_called_once_with(240.)

    def test_raw_load_unload_commands_allow_omitted_or_explicit_temp(self):
        for name in ('cmd_load','cmd_unload'):
            for requested,expected in ((None,240.),(250.,250.)):
                f=filament()
                params={} if requested is None else {'TEMP':requested}
                cmd=NS(get_command_parameters=lambda:params,
                       get_float=lambda key,default=None:params.get(key,default),respond_info=Mock())
                getattr(f,name)(cmd)
                self.assertEqual(f.target,expected)
                f.hotend.set_temp.assert_called_once_with(expected)

    def test_factory_default_still_respects_the_native_heater_limit(self):
        f=filament();f.hotend.max_temp=235.
        with self.assertRaisesRegex(RuntimeError,'native extrusion/heater limits'):
            f.start('LOAD')
        self.assertEqual(f.machine.state,'IDLE')
        f.hotend.set_temp.assert_not_called()

    def test_m600_retains_paused_print_temperature_selection(self):
        f=filament();f.job.machine.state='PRINTING'
        f.cmd_m600(NS(get_command_parameters=lambda:{'M':'600'},respond_info=Mock()))
        self.assertEqual(f.machine.state,'WAIT_PAUSE')
        self.assertIsNone(f.target)
        f.job.pause.assert_called_once_with('M03 filament change')
        f.hotend.set_temp.assert_not_called()


if __name__=='__main__':unittest.main()
