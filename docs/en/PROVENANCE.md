# Source and asset provenance

Code follows the GPL notices of the M300 port; the GPL text is in COPYING.
The display moon is a pixel-exact extract from the user-provided M300 1.3.1
factory firmware and the previously audited OEM sprite atlas. Vendor ownership
of the artwork is unchanged; no new artwork license is asserted.

The source image SHA-256, descriptor address, decoded frame hash and call-site
evidence are in evidence/OEM_SLEEP_EVIDENCE.json. Reference fixtures under
tests/reference preserve earlier code solely for compatibility and regression
checks. They are not installed on the printer.

The new package changes m300_menu.py and m300_ui_m11_state.py and adds
m300_display.py, m300_display_stream.py, m300_display_oem.py and
m300_display_moon.json. Existing OLED transport/rendering, native Klipper core,
MCU firmware, motion and thermal modules are not replaced.

R15.7 additionally updates m300_mcu, motion/calibration scale adapters and
the menu. New m300_hardware and MCU m300_factory implement the ID3 read and
profile choice documented in [Hardware variants](HARDWARE_VARIANTS.md).
The historical statement above about unchanged MCU/motion applies to R15.6.
