"""Whole-file Z-code checks and the common native lifecycle contract.

All vectors are declared synthetic. Real Z-Suite corpus and physical print
acceptance cannot be inferred from these tests or a successful CRC alone.
"""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

import test_native_models as models
from payload.m300_binary import compile_m300, BinaryRejected
from payload.m300_zcode import crc8_d5, ZCodeError

ROOT=Path(__file__).resolve().parents[1]
LIMITS=dict(heater_limits=dict(hotend=[0.,300.],bed=[0.,130.]),
            axis_limits=dict(X=[0.,300.],Y=[0.,305.],Z=[0.,315.]))


def parts(data):
    records=[];offset=128
    while offset<len(data):
        end=offset+data[offset]+1;records.append(data[offset:end]);offset=end
    return bytearray(data[:128]),records


def record(op,payload=b''):
    body=bytes((len(payload)+2,op))+payload
    return body+bytes((crc8_d5(body),))


def rebuild(header,records):
    header=bytearray(header);struct.pack_into('<I',header,50,len(records))
    header[127]=crc8_d5(header[:127])
    return bytes(header)+b''.join(records)


class UnifiedZcodeTests(unittest.TestCase):
    def setUp(self):self.data=models.zcode('m300_stock_subset_synthetic')

    def compile(self,data):return compile_m300(data,native=True,**LIMITS)

    def test_native_output_uses_one_start_and_end_without_private_heat_sequence(self):
        result=self.compile(self.data);lines=result.gcode.decode().splitlines()
        self.assertEqual(sum(s.startswith('START_PRINT ') for s in lines),1)
        self.assertEqual(lines[-2:],['M400','END_PRINT'])
        self.assertIn('START_PRINT EXTRUDER_TEMP=220 BED_TEMP=80 MESH=AUTO',lines)
        for command in ('M104','M140','M109','M190','G28','TURN_OFF_HEATERS'):
            self.assertFalse(any(s.split(' ',1)[0]==command for s in lines),command)
        self.assertTrue(result.metadata['whole_file_validated'])
        self.assertFalse(result.metadata['executed'])
        self.assertFalse(result.metadata['physical_m300_zsuite_corpus_validated'])

    def test_every_supported_family_id_and_both_z_scales_keep_explicit_conversion(self):
        header,records=parts(self.data)
        for model in range(20,30):
            for scale in (400,800):
                with self.subTest(model=model,scale=scale):
                    h=bytearray(header);h[61]=model;struct.pack_into('<I',h,26,scale)
                    output=self.compile(rebuild(h,records)).gcode
                    self.assertIn(b'START_PRINT ',output)
                    # This declared fixture contains Z=8000 source units.
                    self.assertIn(b'Z20' if scale==400 else b'Z10',output)

    def test_other_printer_families_are_refused_even_with_a_valid_header_crc(self):
        header,records=parts(self.data)
        for model in (0,10,19,30,255):
            header[61]=model
            with self.subTest(model=model),self.assertRaisesRegex(ZCodeError,'model family'):
                self.compile(rebuild(header,records))

    def test_newer_firmware_and_wrong_scales_are_not_guessed(self):
        header,records=parts(self.data);header[58:61]=bytes((1,4,0))
        with self.assertRaisesRegex(BinaryRejected,'firmware is newer'):self.compile(rebuild(header,records))
        header,_=parts(self.data);struct.pack_into('<I',header,18,800)
        with self.assertRaisesRegex(BinaryRejected,'scales'):self.compile(rebuild(header,records))

    def test_truncated_corrupt_and_trailing_data_are_rejected(self):
        bad=bytearray(self.data);bad[-1]^=1
        for data in (self.data[:127],self.data[:-1],bytes(bad),self.data+b'\x00'):
            with self.subTest(size=len(data)),self.assertRaises(ZCodeError):self.compile(data)

    def test_unknown_final_opcode_is_rejected_before_any_partial_job_is_published(self):
        header,records=parts(self.data);bad=rebuild(header,records+[record(0x7f)])
        with self.assertRaisesRegex(BinaryRejected,'unsupported opcode'):self.compile(bad)
        with models.model_session(binary=bad) as h:
            models.prepare(h)
            self.assertEqual(h.models.get_status(h.now)['state'],'ERROR')
            self.assertIsNone(h.vsd.current_file);self.assertIsNone(h.models.preview)
            self.assertEqual((h.hotend.target,h.bed.target),(0.,0.))

    def test_configured_geometry_and_heater_limits_remain_authoritative(self):
        small=dict(LIMITS);small['axis_limits']=dict(LIMITS['axis_limits'],X=[0.,90.])
        with self.assertRaises(BinaryRejected):compile_m300(self.data,native=True,**small)
        small=dict(LIMITS);small['heater_limits']=dict(hotend=[0.,210.],bed=[0.,130.])
        with self.assertRaises(BinaryRejected):compile_m300(self.data,native=True,**small)

    def test_dual_material_and_source_record_count_mismatch_remain_rejected(self):
        header,records=parts(self.data);struct.pack_into('<I',header,77,100)
        with self.assertRaisesRegex(BinaryRejected,'dual-extruder'):self.compile(rebuild(header,records))
        header,records=parts(self.data);struct.pack_into('<I',header,50,len(records)+1)
        header[127]=crc8_d5(header[:127])
        with self.assertRaises(BinaryRejected):self.compile(bytes(header)+b''.join(records))

    def test_output_and_source_size_caps_apply_to_the_shared_wrapper_too(self):
        for kwargs in (dict(max_output_bytes=10),dict(max_bytes=len(self.data)-1),dict(max_records=1)):
            with self.subTest(kwargs=kwargs),self.assertRaises(BinaryRejected):
                compile_m300(self.data,native=True,**LIMITS,**kwargs)

    def test_offline_checker_reports_each_file_without_executing_commands(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'limits.json').write_text(json.dumps(LIMITS))
            (p/'good.zcode').write_bytes(self.data);(p/'bad.zcode').write_bytes(self.data[:-1])
            result=subprocess.run([sys.executable,str(ROOT/'check-zcode.py'),'--limits',str(p/'limits.json'),
                str(p/'good.zcode'),str(p/'bad.zcode')],capture_output=True,text=True)
            self.assertEqual(result.returncode,1,result.stderr);report=json.loads(result.stdout)
            self.assertFalse(report['all_passed'])
            self.assertEqual([r['status'] for r in report['files']],['PASS','REJECTED'])
            self.assertTrue(all(not r['executed'] and not r['physical_print_validated'] for r in report['files']))
            self.assertEqual((p/'good.zcode').read_bytes(),self.data)


if __name__=='__main__':unittest.main()
