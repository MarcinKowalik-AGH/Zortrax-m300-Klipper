import hashlib
import os
from pathlib import Path
import struct
import tempfile
import unittest

from payload.m300_counter_backup import validate_backup


def image(active):
    result = bytearray(b'\xff' * 0x40000)
    struct.pack_into('<II', result, 0, 0x20005000, 0x08000101)
    struct.pack_into('<II', result, 0x8000, 0x20005000, 0x08008101)
    struct.pack_into('<I', result, 0x3f818, 0xaabb0401)
    result[0x3f81c:0x3f820] = bytes.fromhex('238dff87')
    struct.pack_into('<IB', result, 0x3f848, 0xaabb0103, 0xe5)
    struct.pack_into('<HHI', result, active + 2, 0xffff, 0, 286732)
    struct.pack_into('<H', result, active, 0)
    return result


class CounterBackupTests(unittest.TestCase):
    def validate(self, data, serial='Z238DFF87'):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'full-backup.bin'
            path.write_bytes(data)
            return validate_backup(path, serial)

    def test_both_normalized_bank_directions(self):
        for bank in (0x3e800, 0x3f000):
            backup = image(bank)
            self.assertEqual(self.validate(backup), hashlib.sha256(backup).hexdigest())

    def test_wrong_serial(self):
        with self.assertRaisesRegex(ValueError, 'factory serial'):
            self.validate(image(0x3e800), 'Z238DFF88')

    def test_wrong_size(self):
        for backup in (image(0x3e800)[:-1], image(0x3e800) + b'\0'):
            with self.assertRaisesRegex(ValueError, '262144 raw bytes'):
                self.validate(backup)
        with tempfile.TemporaryDirectory() as folder:
            fifo = Path(folder) / 'not-a-backup'
            os.mkfifo(fifo)
            with self.assertRaisesRegex(ValueError, 'regular file'):
                validate_backup(fifo, 'Z238DFF87')

    def test_requires_bootloader_and_application_vectors(self):
        for offset in (0, 0x8000):
            backup = image(0x3e800)
            backup[offset:offset + 8] = b'\xff' * 8
            with self.assertRaisesRegex(ValueError, 'vectors'):
                self.validate(backup)

    def test_rejects_dual_active_and_staged_peer(self):
        for offset in (0x3f000, 0x3f004):
            backup = image(0x3e800)
            backup[offset] = 0
            with self.assertRaisesRegex(ValueError, 'fully erased'):
                self.validate(backup)

    def test_rejects_bad_records_and_hardware(self):
        for offset in (0x3e806, 0x3e80c, 0x3f848):
            backup = image(0x3e800)
            backup[offset:offset + 4] = b'\xff' * 4 if offset == 0x3e806 else b'\0' * 4
            with self.assertRaises(ValueError):
                self.validate(backup)


if __name__ == '__main__':
    unittest.main()
