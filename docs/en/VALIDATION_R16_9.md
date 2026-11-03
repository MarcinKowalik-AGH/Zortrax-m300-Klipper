# R16.9 native SD and Models validation

Models imports a checked copy through the existing read-only SD transport.
The operator starts the ready copy through native Klippy virtual SD. Both
text G-code and the audited Classic M300 Z-code subset use this path.
The legacy OEM job engine remains a separate diagnostic path.

| Layer | Evidence |
|---|---|
| Host regression | 299 tests, including 10 new Models tests |
| Public repository | 9 packaging and source contracts |
| MCU SD model | 28 modeled scenario groups, including SDSC/SDHC, card CRC, session, range, deadlines and shutdown |
| Native Klippy FILEOUTPUT | 16 cases, including complete G-code and converted Z-code prints |
| Model handoff | No native file or timer at preview. Explicit start uses the native worker, file name and print statistics. Both models reached their final coordinates and released the file. |
| Pause and end | The binary fixture paused and resumed via the explicit native RESUME command. Both tests finished with heater targets at zero. |
| Physical SD on the host | Real FAT16/FAT32 and long filename code above a simulated MCU transport. The OLED test navigates the SD root and a folder, imports G-code and starts the local copy. |
| Refusal paths | Bad CRC, foreign Inventure family, invalid text, stale listing, replaced card, import cancellation, lifecycle stop, native print busy and XYZ offsets. |

The accepted binary fixture is the project's synthetic Classic M300 sample.
The negative control is the Inventure converter's smoke output from the
earlier M300 audit. The two fixtures are recorded with SHA-256 in the test
package. Representative M300 Z-Suite exports and a physical printer run
remain separate acceptance work.

Use the actual card with a known small model after installing. Confirm
directory navigation, successful import, Back cancellation and the shared
native Print status. Verify the normal heating, homing and print sequence on
a supervised test. [Operator procedure](MODELS_SD.md)
