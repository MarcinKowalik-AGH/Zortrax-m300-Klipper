# SPDX-License-Identifier: GPL-3.0-or-later
"""M13 optional Z-code admission and read-only SD diagnostics for M300 Classic.

No new opcode execution path or SPI driver. M02 owns the sole immutable file
snapshot and all heating/printing. M04 owns binary compilation and SPI1; M13
adds a testable user-level policy plus source-proof validation at that boundary.
"""
from .m300_temperature_policy import target_limit
import hashlib
import json
import os
import stat
from .m300_zcode_policy_state import prove,PolicyError,COMPATIBILITY
from .m300_job_sd import _open_source,FileRejected

class M300ZCodePolicy:
    def __init__(self,config):
        self.printer=config.get_printer()
        self.reactor=self.printer.get_reactor()
        self.job=self.printer.load_object(config,'m300_job')
        self.file=self.job.sd
        self.sd=self.printer.lookup_object('m300_sd',None)
        self.max_source_bytes=config.getint('max_source_bytes',16*1024*1024,
                                           minval=128,maxval=128*1024*1024)
        self.max_records=config.getint('max_records',1000000,minval=1,maxval=1000000)
        self.last_proof=None
        self.ready=False
        self.gcode=self.printer.lookup_object('gcode')
        self.gcode.register_command('ZORTRAX_ZCODE_STATUS',self.cmd_status,when_not_ready=True)
        self.gcode.register_command('ZORTRAX_ZCODE_INSPECT',self.cmd_inspect)
        self.gcode.register_command('ZORTRAX_ZCODE_SELECT',self.cmd_select)
        self.gcode.register_command('ZORTRAX_ZCODE_SD_CHECK',self.cmd_sd_check)
        self.printer.register_event_handler('klippy:ready',self._ready)
        for event in ('klippy:shutdown','klippy:disconnect','gcode:request_restart'):
            self.printer.register_event_handler(event,self.invalidate)

    def _ready(self):
        self.ready=True
        self.last_proof=None

    def invalidate(self,*args):
        self.ready=False
        self.last_proof=None

    def _validate_name(self,path):
        if not isinstance(path,str) or not path.lower().endswith('.zcode'):
            raise PolicyError('only classic M300 .zcode is admitted by M13')
        if path.startswith('sd:/'):
            raise PolicyError('physical SD inspection goes through M02 immutable import')
        if not path or len(path.encode('utf-8'))>255 or path.startswith('/') or '\\' in path or ':' in path:
            raise PolicyError('invalid filename')
        if any(x in ('','.','..') for x in path.split('/')) or any(ord(c)<32 for c in path):
            raise PolicyError('invalid path component')
        return path

    def _limits(self):
        heaters=self.printer.lookup_object('heaters')
        return {name:(heater.min_temp,target_limit(heater)) for name,heater in
                (('hotend',heaters.lookup_heater('extruder')),
                 ('bed',heaters.lookup_heater('heater_bed')))}

    def inspect_file(self,path):
        if not self.ready or self.printer.is_shutdown():
            raise PolicyError('M13 host is not ready')
        path=self._validate_name(path)
        source=None
        try:
            source,before=_open_source(self.file.root,path)
            if not 128 <= before.st_size <= self.max_source_bytes:
                raise PolicyError('binary file size outside M13 limit')
            data=source.read(self.max_source_bytes+1)
            after=os.fstat(source.fileno())
            identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            if identity(before)!=identity(after) or len(data)!=before.st_size:
                raise PolicyError('M13 binary source changed while inspecting')
            proof=prove(data,heater_limits=self._limits(),axis_limits=self.job._axis_bounds(),
                        max_bytes=self.max_source_bytes,max_records=self.max_records)
            self.last_proof=proof.public()
            return dict(self.last_proof)
        finally:
            if source is not None: source.close()

    def select_file(self,path):
        if not self.ready or self.printer.is_shutdown():
            raise PolicyError('M13 host is not ready')
        if not isinstance(path,str) or not path.lower().endswith('.zcode'):
            raise PolicyError('M13 select supports only .zcode')
        before=None
        if not path.startswith('sd:/'):
            before=self.inspect_file(path)
        # Already qualified M02 owns this entire pipeline: optional physical
        # SD snapshot, M04 byte-wise conversion, M02 syntax and safety preflight.
        prepared=self.file.select(path)
        meta=getattr(prepared,'source_metadata',{})
        try:
            if not getattr(prepared,'binary_source',False):
                raise PolicyError('M02 did not produce a binary-checked snapshot')
            if meta.get('profile') != 'M300_STOCK_1.3.1_SUBSET_V2_RECOVERED':
                raise PolicyError('M02 selected an unknown binary compilation profile')
            if before is not None and meta.get('source_sha256')!=before['source_sha256']:
                raise PolicyError('source mutated between inspection and M02 snapshot')
            if (meta.get('framing_and_crc_valid') is not True
                    or meta.get('whole_file_validated') is not True):
                raise PolicyError('M02 lacks a complete binary validity proof')
            self.last_proof={'source_sha256':meta.get('source_sha256'),
                             'profile':COMPATIBILITY,'source':path,
                             'snapshot_sha256':prepared.sha256,
                             'snapshot_identity':prepared.identity,
                             'executed':False,'physical':False}
            return dict(self.last_proof)
        except Exception:
            if self.file.selected is prepared:
                self.file.cancel()
            raise

    def sd_check(self,path='/'):
        if not self.ready or self.printer.is_shutdown():
            raise PolicyError('M13 host is not ready')
        if self.sd is None: raise PolicyError('SD provider is not configured')
        # M04 alone owns SPI1 and rejects FILEOUTPUT/unqualified cards.
        entries=self.sd.list_files(path)
        return {'path':path,'read_only':True,'entries':len(entries),
                'device_state':self.sd.get_status(self.reactor.monotonic()).get('state'),
                'spi_owner':'m300_sd'}

    def get_status(self,now):
        sd_status=self.sd.get_status(now) if self.sd is not None else {}
        return {'stage':'M13','model':'M300_CLASSIC','ready':self.ready,
                'profile':COMPATIBILITY,'source_limit':self.max_source_bytes,
                'max_records':self.max_records,'source_proof':dict(self.last_proof or {}),
                'sd_owner':'m300_sd', 'sd_qualified':sd_status.get('sd_qualified',False),
                'read_only':True,'owns_spi':False,'owns_motion':False,
                'executes_binary_directly':False,'zsuite_real_corpus_verified':False}

    def cmd_status(self,gcmd):
        gcmd.respond_info('ZORTRAX_ZCODE '+json.dumps(self.get_status(self.reactor.monotonic()),sort_keys=True))

    def cmd_inspect(self,gcmd):
        try: result=self.inspect_file(gcmd.get('FILENAME'))
        except (PolicyError,FileRejected,ValueError,OSError) as exc:
            raise gcmd.error('M13: '+str(exc))
        gcmd.respond_info('ZORTRAX_ZCODE_INSPECT '+json.dumps(result,sort_keys=True))

    def cmd_select(self,gcmd):
        try: result=self.select_file(gcmd.get('FILENAME'))
        except (PolicyError,FileRejected,ValueError,OSError) as exc:
            raise gcmd.error('M13: '+str(exc))
        gcmd.respond_info('ZORTRAX_ZCODE_SELECT '+json.dumps(result,sort_keys=True))

    def cmd_sd_check(self,gcmd):
        try: result=self.sd_check(gcmd.get('PATH','/'))
        except Exception as exc:
            raise gcmd.error('M13 SD: '+str(exc))
        gcmd.respond_info('ZORTRAX_ZCODE_SD '+json.dumps(result,sort_keys=True))


def load_config(config):
    return M300ZCodePolicy(config)
