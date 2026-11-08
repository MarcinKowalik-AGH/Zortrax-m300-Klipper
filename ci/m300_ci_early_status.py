"""Exercise the real Moonraker query path before connect; FILEOUTPUT only."""
import json


class EarlyStatusFixture:
    def __init__(self,config):
        self.printer=config.get_printer()
        board=self.printer.load_object(config,'m300_mcu')
        if not board.get_mcu().is_fileoutput():
            raise config.error('Early status fixture requires FILEOUTPUT')
        self.printer.register_event_handler('klippy:mcu_identify',lambda:self.query('before_connect'))
        self.printer.register_event_handler('klippy:ready',lambda:self.query('ready'))

    def query(self,phase):
        printer=self.printer;service=printer.lookup_object('m300_maintenance')
        if phase=='before_connect':
            assert not service.ready
            assert getattr(service,'hotend',None) is None and getattr(service,'bed',None) is None
        else:assert service.ready
        helper=printer.lookup_object('webhooks')._endpoints['objects/query'].__self__
        objects={name:None for name,obj in printer.lookup_objects() if hasattr(obj,'get_status')}
        responses=[]
        helper.pending_queries.append((None,objects,responses.append,{}))
        helper._do_query(printer.get_reactor().monotonic())
        assert len(responses)==1
        status=responses[0]['params']['status']['m300_maintenance']
        assert status['ready']==(phase=='ready')
        assert status['target_hotend']==status['target_bed']==0.
        printer.lookup_object('gcode').respond_info('M300_CI_EARLY_STATUS '+json.dumps(dict(
            phase=phase,objects=len(objects),maintenance=status,physical_hardware=False)))


def load_config(config):return EarlyStatusFixture(config)
