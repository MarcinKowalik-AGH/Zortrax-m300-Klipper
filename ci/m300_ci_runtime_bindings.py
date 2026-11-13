"""Inspect the runtime observers and existing guards on actual Klippy handlers."""
import json
import logging


def callback(handler):
    # Klipper registers an extended-parameter adapter for TEMPERATURE_WAIT.
    if handler.__module__ == 'gcode' and handler.__qualname__ == (
            'GCodeDispatch.register_command.<locals>.<lambda>'):
        captures = dict(zip(handler.__code__.co_freevars,
                            (cell.cell_contents for cell in handler.__closure__)))
        return captures['origfunc']
    return handler


def owner(handler):
    return handler.__module__ + '.' + handler.__qualname__


class RuntimeBindings:
    def __init__(self, config):
        self.printer = config.get_printer()
        if not self.printer.lookup_object('mcu').is_fileoutput():
            raise config.error('Runtime binding inspection requires FILEOUTPUT')
        self.printer.register_event_handler('klippy:ready', self.check)

    def check(self):
        printer = self.printer
        models = printer.lookup_object('m300_models')
        nvm = printer.lookup_object('m300_nvm')
        assert models.runtime is nvm
        control = printer.lookup_object('m300_print_control', None)
        gcode = printer.lookup_object('gcode')
        handlers = gcode.ready_gcode_handlers
        gcode_move = printer.lookup_object('gcode_move')
        heaters = printer.lookup_object('heaters')
        arcs = printer.lookup_object('gcode_arcs', None)
        expected = {
            'G0': (gcode_move.cmd_G1, 'deposition', 'watch'),
            'G1': (gcode_move.cmd_G1, 'deposition', 'watch'),
            'M109': (printer.lookup_object('extruder').cmd_M109, 'heater_waits', 'wait'),
            'M190': (printer.lookup_object('heater_bed').cmd_M190, 'heater_waits', 'wait'),
            'TEMPERATURE_WAIT': (heaters.cmd_TEMPERATURE_WAIT, 'heater_waits', 'wait'),
        }
        if arcs is not None:
            for name in ('G2', 'G3'):
                expected[name] = (getattr(arcs, 'cmd_' + name), 'deposition', 'watch')

        chains = {}
        for name, (native, method, local) in expected.items():
            observer = callback(handlers[name])
            assert owner(observer) == (
                f'extras.m300_models.M300Models._watch_{method}.<locals>.{local}'), name
            previous, = observer.__defaults__
            previous = callback(previous)
            chain = [owner(observer)]
            if control is not None and name in ('G0', 'G1'):
                assert owner(previous) == (
                    'extras.m300_print_control.M300PrintControl._connect.<locals>.guarded'), name
                original, guarded_name = previous.__defaults__
                assert guarded_name == name and original is control.command_backends[name], name
                chain.append(owner(previous))
                previous = callback(original)
            if name == 'TEMPERATURE_WAIT':
                assert owner(previous) == 'gcode.GCodeDispatch.register_mux_command.<locals>.<lambda>'
                captures = dict(zip(previous.__code__.co_freevars,
                                    (cell.cell_contents for cell in previous.__closure__)))
                assert captures == {'cmd': name, 'self': gcode}
                key, backends = gcode.mux_commands[name]
                assert key == 'SENSOR' and {'extruder', 'heater_bed'} <= backends.keys()
                assert all(backend == native for backend in backends.values())
                chain.append(owner(previous))
                previous = native
            assert previous == native, (name, owner(previous), owner(native))
            chains[name] = chain + [owner(native)]
        logging.info('M300_CI_RUNTIME_BINDINGS %s', json.dumps(chains, sort_keys=True))


def load_config(config):
    return RuntimeBindings(config)
