"""Native Models integration with a sector fixture at the MCU wire boundary."""
import base64
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace as NS
import unittest

from payload.m300_binary import compile_m300
from payload.m300_fat import _lfn_checksum
from payload.m300_models import M300Models, ModelError, _copy_open_native_file
from payload.m300_sd import M300SD, SDError, SNAPSHOT_BATCH_BYTES
from test_settings_information import session, browser

FIXTURES = json.loads((Path(__file__).parent / 'reference/models_zcode.json').read_text())


def zcode(name):
    record = FIXTURES[name]
    data = base64.b64decode(record['base64'], validate=True)
    assert hashlib.sha256(data).hexdigest() == record['sha256']
    return data


def fat_entry(short, cluster, size, directory=False):
    row = bytearray(32)
    row[:11] = short
    row[11] = 0x10 if directory else 0x20
    struct.pack_into('<HI', row, 26, cluster, size)
    return row


def file_rows(name, short, cluster, data):
    # Fixture names fit in a single VFAT long filename entry.
    encoded = (name + '\0').encode('utf-16-le').ljust(26, b'\xff')
    assert len(encoded) == 26
    lfn = bytearray(32)
    lfn[0], lfn[11], lfn[13] = 0x41, 0x0f, _lfn_checksum(short)
    lfn[1:11], lfn[14:26], lfn[28:32] = encoded[:10], encoded[10:22], encoded[22:]
    return lfn + fat_entry(short, cluster, len(data))


class CardImage:
    def __init__(self, binary, bits=16):
        self.text = b'; native test\r\nG90\r\nM105'
        self.cid = b'C' * 16
        self.csd = b'S' * 16
        self.bus = []
        self.sectors = {}
        self.before_read = None
        boot = bytearray(512)
        boot[:3] = b'\xeb\x3c\x90'
        boot[510:] = b'\x55\xaa'
        fat = bytearray(512)
        if bits == 16:
            reserved, root_lba, folder_cluster = 1, 17, 2
            folder_lba, self.blocks = 49, 4134
            struct.pack_into('<HBHBHH', boot, 11, 512, 1, reserved, 1, 512, self.blocks)
            struct.pack_into('<H', boot, 22, 16)
            fat_format, end = '<H', 0xffff
        else:
            reserved, root_lba, folder_cluster = 32, 544, 3
            folder_lba, self.blocks = 545, 66069
            struct.pack_into('<HBHB', boot, 11, 512, 1, reserved, 1)
            struct.pack_into('<II', boot, 32, self.blocks, 512)
            struct.pack_into('<I', boot, 44, 2)
            fat_format, end = '<I', 0x0fffffff
        for cluster in range(2, folder_cluster + 3):
            struct.pack_into(fat_format, fat, cluster * (bits // 8), end)
        root = (fat_entry(b'MODELS     ', folder_cluster, 0, True)
                + file_rows('part.zcode', b'PART    ZCO', folder_cluster + 2, binary))
        folder = file_rows('bench.gcode', b'BENCH   GCO', folder_cluster + 1, self.text)
        for sector, payload in ((0, boot), (reserved, fat), (root_lba, root),
                                (folder_lba, folder), (folder_lba + 1, self.text),
                                (folder_lba + 2, binary)):
            self.sectors[sector] = bytes(payload).ljust(512, b'\0')

    def request(self, card, command, args=(), timeout=None, offset=None, count=None):
        card._checkpoint()
        self.bus.append((command, tuple(args)))
        if command == 'open':
            return {'data': self.cid + self.csd, 'blocks': self.blocks}, 1
        if command == 'read':
            if self.before_read is not None:
                self.before_read(args[0])
            self.sector = self.sectors.get(args[0], bytes(512))
            return {'data': b''}, 2
        assert command == 'chunk' and 1 <= count <= 32
        return {'data': self.sector[offset:offset + count]}, 3


@contextmanager
def model_session(binary=None, bits=16):
    with session() as h:
        image = CardImage(binary if binary is not None else zcode('m300_stock_subset_synthetic'), bits)
        h.models_browser = browser(h)
        h.vsd = h.objects['virtual_sdcard']
        h.vsd.executor = NS(submit=lambda fn, *a, **kw: fn(*a, **kw), wrap_obj=lambda raw: raw)
        h.vsd.sdcard_dirname = str(h.files)
        h.vsd.current_file = h.vsd.work_timer = None
        h.vsd.print_stats = NS(set_current_file=lambda filename: h.events.append(('file', filename)))
        h.vsd._reset_file = lambda: setattr(h.vsd, 'current_file', None)
        def resume():
            h.vsd.work_timer = object()
            h.events.append(('native_worker',))
        h.vsd.do_resume = resume
        h.job.sd.v_sd = h.vsd
        h.objects['heaters'] = NS(lookup_heater=lambda key: h.hotend if key == 'extruder' else h.bed)
        mcu = h.board.get_mcu()
        mcu.alloc_command_queue = lambda: 1
        mcu.register_config_callback = lambda callback: None
        h.board.get_mcu = lambda: mcu
        h.config.getboolean = lambda name, default: True if name == 'sd_qualified' else default
        h.card = M300SD(h.config)
        h.objects['m300_sd'] = h.card
        h.card._ready()
        h.card._request = lambda *a, **kw: image.request(h.card, *a, **kw)
        h.models = M300Models(h.config)
        h.objects['m300_models'] = h.models
        h.models._ready()
        h.image = image
        try:
            yield h
        finally:
            h.models.invalidate()
            if h.vsd.current_file is not None:
                h.vsd.current_file.close()

def prepare(h, source='sd', directory='', name='part.zcode', run=True):
    listing = h.models_browser.list_files(source, directory)
    index = next(i for i, entry in enumerate(listing['files']) if entry['name'] == name)
    response = h.models_browser.native_preview(listing['generation'], index)
    if run:
        h.callbacks.pop()(h.now)
    return response['token']


class ModelsTests(unittest.TestCase):
    def test_orca_preheat_reorders_only_known_startup_in_both_native_paths(self):
        with model_session() as h:
            path = h.files / 'orca.gcode'
            for bed, wait, earlier, reorder in (
                    (80, b'M190 S80', b'M73 P0 R10\r\n', True),
                    (30, b'TEMPERATURE_WAIT SENSOR=heater_bed MINIMUM=29', b'', True),
                    (80, b'M190 S80', b'M109 S160\r\n', False),
                    (80, b'M190 S60', b'', False)):
                with self.subTest(bed=bed, wait=wait, earlier=earlier):
                    header = (b'; OrcaSlicer\r\n' + earlier +
                              b'; M300 Classic / native Klipper\r\nG90\r\nM83\r\n'
                              + b'M140 S%d\r\n' % bed)
                    after = b'G28\r\nM109 S220\r\nG90\r\nM83\r\nG92 E0\r\nG1 X100\r\n'
                    nozzle = b'M104 S180\r\n'
                    wait += b'\r\n'
                    source = header + wait + nozzle + after
                    expected = header + nozzle + wait + after if reorder else source
                    path.write_bytes(source)
                    with path.open('rb') as original:
                        raw, digest = _copy_open_native_file(original.fileno(), len(source))
                        with raw:
                            self.assertEqual(raw.read(), expected)
                    self.assertEqual(digest, hashlib.sha256(source).hexdigest())
                    token = prepare(h, source='host', name=path.name)
                    self.assertEqual(h.models.preview.stream.read().encode(), expected)
                    self.assertEqual(h.models.preview.source_sha256, digest)
                    self.assertEqual(h.models.preview.size, len(source))
                    h.models.cancel(token)
                    self.assertEqual(path.read_bytes(), source)

    def test_models_hides_windows_metadata_at_sd_root(self):
        with model_session() as h:
            original = h.card.list_files
            name = 'System Volume Information'
            h.card.list_files = lambda path, **kwargs: original(path, **kwargs) + [
                dict(name=name, path=name, size=0, directory=True, modified=0)]
            files = h.models_browser.list_files('sd')['files']
            self.assertNotIn(name, [entry['name'] for entry in files])
            self.assertIn('MODELS', [entry['name'] for entry in files])

    def test_card_import_fetches_only_the_last_sector_prefix(self):
        for bits, file_sector in ((16, 50), (32, 546)):
            with self.subTest(fat=bits), model_session(bits=bits) as h:
                stream, metadata = h.card.get_snapshot('MODELS/bench.gcode')
                with stream:
                    self.assertEqual(stream.read(), h.image.text)
                self.assertEqual(metadata['sha256'], hashlib.sha256(h.image.text).hexdigest())
                chunks = []
                for command, args in h.image.bus:
                    if command == 'read':
                        lba = args[0]
                    elif command == 'chunk' and lba == file_sector:
                        chunks.append(args[1:])
                self.assertEqual(chunks, [(0, len(h.image.text))])
                self.assertEqual([cmd for cmd, _ in h.image.bus].count('open'), 2)

    def test_card_import_batches_full_sectors_and_keeps_exact_snapshot(self):
        with model_session() as h:
            # FAT16 fixture with a 129-sector file and a 33-byte tail.
            data = bytes(range(256)) * (SNAPSHOT_BATCH_BYTES // 256) + bytes(range(33))
            first_cluster = 5
            first_lba = 49 + first_cluster - 2
            fat = bytearray(h.image.sectors[1])
            for offset in range(0, len(data), 512):
                index = offset // 512
                cluster = first_cluster + index
                more = offset + 512 < len(data)
                struct.pack_into('<H', fat, cluster * 2, cluster + 1 if more else 0xffff)
                h.image.sectors[first_lba + index] = data[offset:offset + 512].ljust(512, b'\0')
            h.image.sectors[1] = bytes(fat)
            h.image.sectors[49] = file_rows('bench.gcode', b'BENCH   GCO',
                                            first_cluster, data).ljust(512, b'\0')
            writes = []

            def submit(fn, *args):
                if fn.__name__ == 'write':
                    writes.append(len(args[0]))
                return fn(*args)

            h.card.executor = NS(submit=submit)
            stream, metadata = h.card.get_snapshot('MODELS/bench.gcode')
            with stream:
                self.assertEqual(stream.read(), data)
            self.assertEqual(metadata['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(writes, [SNAPSHOT_BATCH_BYTES, 33])
            self.assertEqual(h.card.bytes_copied, len(data))

    def test_card_import_discards_snapshot_cancelled_during_local_write(self):
        with model_session() as h:
            created = []

            def submit(fn, *args):
                result = fn(*args)
                if fn.__name__ == '_new_snapshot':
                    created.append(Path(result[1]))
                elif fn.__name__ == 'write':
                    h.card.cancel()
                return result

            h.card.executor = NS(submit=submit)
            with self.assertRaisesRegex(SDError, 'cancelled'):
                h.card.get_snapshot('MODELS/bench.gcode')
            self.assertEqual(len(created), 1)
            self.assertFalse(created[0].exists())
            self.assertFalse(h.card.busy)
            self.assertIsNone(h.vsd.current_file)

    def test_oled_models_opens_card_root_and_runs_gcode_from_folder(self):
        for bits in (16, 32):
            with self.subTest(fat=bits), model_session(bits=bits) as h:
                h.menu.page = 'zortrax'
                def press(label):
                    _, rows = h.menu.rows(h.now)
                    h.oled.selection = [row[0] for row in rows].index(label)
                    h.oled._select(h.now, tuple(action for _, action in rows))
                    self.assertFalse(h.menu.reason)
                press('Models')
                self.assertEqual(h.menu.rows(h.now)[0], 'SD:/')
                press('> MODELS')
                press('bench.gcode')
                self.assertEqual(h.menu.page, 'model_file')
                self.assertNotIn('Start printing', [r[0] for r in h.menu.rows(h.now)[1]])
                self.assertIsNone(h.vsd.current_file)
                h.callbacks.pop()(h.now)
                press('Start printing')
                self.assertEqual(h.menu.page, 'native_job')
                self.assertIn(('native_worker',), h.events)
                self.assertEqual(h.vsd.current_file.read().encode(), h.image.text + b'\n')
                self.assertEqual(h.vsd.current_file.name, 'sd:/MODELS/bench.gcode')
                self.assertEqual(h.vsd.file_size, len(h.image.text) + 1)

    def test_sd_zcode_uses_compiler_and_start_transfers_one_local_stream(self):
        with model_session() as h:
            token = prepare(h)
            self.assertEqual(h.models.get_status(h.now)['format'], 'Z-code')
            self.assertEqual(h.hotend.target, 0.)
            count = len(h.image.bus)
            h.image.sectors.clear()
            h.models.start(token)
            commands = h.vsd.current_file.read()
            self.assertIn('M140 S80\nM104 S220\nG28\nM190 S80\nM109 S220\n', commands)
            self.assertIn('G1 X100 Y100 Z10 F1800\n', commands)
            self.assertIn('\nPAUSE\n', commands)
            self.assertTrue(commands.endswith('M400\nTURN_OFF_HEATERS\nM107\n'))
            self.assertNotIn('START_PRINT', commands)
            self.assertEqual(len(h.image.bus), count)
            with self.assertRaises((ModelError, h.printer.command_error)):
                h.models.start(token)

    def test_corrupt_and_other_family_files_never_publish_a_stream(self):
        stock = zcode('m300_stock_subset_synthetic')
        bad = (stock[:-1] + bytes([stock[-1] ^ 1]), zcode('converter_production_smoke'))
        for data, reason in zip(bad, ('record CRC', 'Wrong model family')):
            with self.subTest(reason=reason), model_session(data) as h:
                token = prepare(h)
                view = h.models.get_status(h.now)
                self.assertEqual(view['state'], 'ERROR')
                self.assertIn(reason, view['error'])
                with self.assertRaisesRegex(ModelError, 'fully prepared'):
                    h.models.start(token)
                self.assertIsNone(h.vsd.current_file)

    def test_card_swap_after_listing_is_refused_before_reading_file_data(self):
        with model_session() as h:
            prepare(h, run=False)
            h.image.cid = b'X' * 16
            h.callbacks.pop()(h.now)
            self.assertIn('SD card or selected file changed', h.models.get_status(h.now)['error'])
            self.assertNotIn(('read', (51,)), h.image.bus)

    def test_cancel_during_card_read_revokes_pending_start(self):
        with model_session() as h:
            token = prepare(h, run=False)
            def cancel(lba):
                if lba == 51:
                    h.models.cancel(token)
            h.image.before_read = cancel
            h.callbacks.pop()(h.now)
            self.assertIsNone(h.models.preview)
            self.assertFalse(h.card.busy)
            self.assertFalse(h.models.get_status(h.now)['busy'])
            with self.assertRaises(ModelError):
                h.models.start(token)

    def test_qualified_physical_reader_declines_active_native_print(self):
        with model_session() as h:
            h.vsd.work_timer = object()
            with self.assertRaisesRegex(SDError, 'idle native print'):
                h.models_browser.list_files('sd')
            self.assertEqual(h.image.bus, [])

    def test_model_start_waits_for_native_idle_and_refuses_binary_xyz_offsets(self):
        with model_session() as h:
            token = prepare(h)
            h.vsd.current_file = NS()
            with self.assertRaisesRegex(ModelError, 'already owns'):
                h.models.start(token)
            h.vsd.current_file = None
            h.gmove.homing_position[2] = .1
            with self.assertRaisesRegex(ModelError, 'zero XYZ'):
                h.models.start(token)
            self.assertIsNone(h.vsd.current_file)

    def test_lifecycle_and_sort_change_cannot_publish_a_pending_selection(self):
        with model_session() as h:
            token = prepare(h, run=False)
            h.nvm.set_setting('sort_mode', 'SIZE')
            h.callbacks.pop()(h.now)
            self.assertIn('expired', h.models.get_status(h.now)['error'])
            new_token = prepare(h)
            self.assertNotEqual(token, new_token)
            old = h.models.preview.stream
            h.models.invalidate()
            self.assertTrue(old.closed)
            self.assertIsNone(h.vsd.current_file)

    def test_invalid_text_and_host_substitution_are_refused(self):
        with model_session() as h:
            path = h.files / 'file.gcode'
            path.write_bytes(b'G90\nG1 X1\0\n')
            prepare(h, 'host', name=path.name)
            self.assertIn('control byte', h.models.get_status(h.now)['error'])
            path.write_bytes(b'G90\n')
            prepare(h, 'host', name=path.name, run=False)
            path.write_bytes(b'G91\nG28\n')
            h.callbacks.pop()(h.now)
            self.assertIn('host file changed', h.models.get_status(h.now)['error'])

    def test_standard_legacy_compilation_is_unchanged(self):
        data = zcode('m300_stock_subset_synthetic')
        self.assertIn(b'START_PRINT EXTRUDER_TEMP=220 BED_TEMP=80\n', compile_m300(data).gcode)
        self.assertTrue(compile_m300(data).gcode.endswith(b'END_PRINT\n'))
