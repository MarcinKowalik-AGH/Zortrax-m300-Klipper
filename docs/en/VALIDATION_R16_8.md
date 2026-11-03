# R16.8 menu validation

The regression suite covers the Zortrax root, Models browsing and preview,
Maintenance, Material, Settings and Information. Native Klippy FILEOUTPUT
exercises the installed configuration and dispatches the new Fluidd macros.
The regression suite retains the previous calibration, material, native
motion, heater, fan, OLED transport and recovery coverage.

| Area | Audit result |
|---|---|
| Models | Fixed the browser callback signature and restored preview validation. Expired selections fail before file access. Added case-sensitive sorting and allowed distinct host filenames that differ only by case. |
| Maintenance / Material | Preserved mandatory procedure instructions in the shared menu adapter. Existing heat, fan, platform, calibration and filament regressions run with the updated OLED renderer. |
| Settings | OLED and Fluidd use the same choices and state. Verified persistence, no writes for unchanged values, stale button rejection, buzzer stop, native print light indicators and the existing sleep policy. |
| Information | Verified live MCU and hardware fields, serial provenance, bounded history reads and GitHub Help. History I/O happens on request outside the renderer. |
| Performance | Ownership checks read state and busy directly. Repeated Settings/Information frames use a bounded cache. The benchmark separates CPU composition from printer transport. |

The OEM audit executed 11 firmware 1.3.1 Settings callbacks and compared 52
complete SSD1322 frames with the port compositor using stock labels. This
covers the font, cursor, checked marks, icon pixels and icon position. R16.8
uses the requested shorter labels, one English language choice and a printer
information submenu for the data available to Klipper. The audit is
reproducible with `ci/reproduce_settings_contract.py` and the private source
evidence. Its frame hashes are included in the self-contained tests. The
previous release's 110 procedure frames, 12 fan-menu frames and 20,002
quarter-turn vectors are retained.

**Software checks:** 288 host tests, 9 repository contracts, 18 check groups
and 14 actual Klippy FILEOUTPUT cases. The build report includes
`MENU_PERFORMANCE.json` with per-page render timings. Those numbers describe
the executor's CPU. Physical OLED latency, cooling, Z contact, filament
transport and platform motion still require the printer.

After installation, verify Ready and open each new page on the OLED and in
Fluidd. Change a setting on one surface and confirm its value on the other.
Restart Klipper and confirm the choice persists. Toggle sleep and check the
existing notice, display off and wake sequence. Verify Models ordering using
files with distinct dates, sizes and case. Check that Information identifies
the actual hardware and the source of print time.

The existing supervised printer procedure checks remain in
[the Maintenance and Material validation](VALIDATION_R16_7.md).
See [Settings and Information](SETTINGS_INFORMATION.md) and [installation](INSTALL.md).
