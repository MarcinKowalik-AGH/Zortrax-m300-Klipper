# Third-party code and resources

Klipper and the M300 port retain their GPL notices; see LICENSE.
The pinned upstream source is fetched and verified at build time.

mcu/SOURCE_MCU/tools/test01_m3b.py is an offline MIT-licensed adaptation of
the user's M300 bootloader container tool. Its original and license are kept
under mcu/SOURCE_MCU/docs/boot_reference.

OEM sprite/font resources were extracted from the user's audited M300 1.3.1
firmware. Vendor ownership of the artwork is unchanged; no new artwork license
is asserted. The full factory firmware and machine dumps are not included.

The factory moon source image SHA-256 is
11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75.
The decoded 1,250-byte moon SHA-256 is
56bd4351a045e02e673b0c0d53953f47eae010529b8d3c58e65a83a02e1b7bd1.
Reference code under host/update_template/tests/reference is used for regression
checks and is not installed on the printer.
