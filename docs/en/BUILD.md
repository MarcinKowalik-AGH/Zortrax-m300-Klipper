# Build and develop

## GitHub Actions

1. Commit changes to main, or run the workflow manually from Actions.
2. Open the run for the exact commit.
3. Check that the ARM build, host tests, real Klippy FILEOUTPUT and packaging
   steps succeeded.
4. Download the artifact under that run's Artifacts section. The top-level
   BUILD_PROVENANCE.json identifies the source commit; SHA256SUMS covers files.

The runner is Ubuntu 24.04 with GNU ARM/newlib and Python 3.12. Actual compiler,
linker and Python versions are included in TOOLCHAIN.json and build logs.
MCU tests compile native C register doubles; they do not measure F103 cycles.

The build helper checks the upstream ZIP SHA-256, pristine source hashes,
F103 configuration, 0x08008000 vector, memory boundaries, dictionary commands
and constants, local cooling and ownership capabilities. Packaging verifies
the newly compiled files against BUILD_REPORT.json before constructing M3B.

## Local equivalent

Install GNU Arm Embedded tools with newlib/nano, make, a native C compiler and
Python 3.12. In an isolated Python environment:

~~~bash
python ci/prepare_upstream.py
python -m pip install -r .ci/pristine/scripts/klippy-requirements.txt
python mcu/SOURCE_MCU/tools/build.py --archive mcu/SOURCE_MCU/UPSTREAM_KLIPPER_PINNED.zip --work .ci/arm-build --output dist/mcu --jobs 4
python ci/run_checks.py --dictionary dist/mcu/klipper.dict
bash ci/build_fluidd.sh
python ci/package_release.py --build dist/mcu --fluidd dist/fluidd
~~~

For an existing owned ARM build directory, add --fresh to the builder.
Unknown existing directories are protected from replacement. Downloaded
upstream, generated host trees and build results are ignored by Git.

## Editing

Edit runtime host files in host/klippy/extras, display settings in host/config,
and MCU changes in mcu/SOURCE_MCU. Update tests when behaviour changes.
The host update is assembled at build time, including its integrity manifest.
The canonical list of update files and expected host suite count are in PORT.json.

The optional factory-moon reproducer requires the privately held stock image.
It is not counted as an automatically executed public CI test.

R14.5 also validates factory ABI 1 and its response format in the fresh
MCU dictionary. Thirteen actual Klippy processes include synthetic HW04/HW05,
explicit configuration override and refusal of an erased record. The CI-only
identity fixture is not installed by the host update.

R16 also replays native XYZ homing with 180C, repeated Z, 300 mm/s/M220=150,
Z299/Z300 and concurrent thermal/fan/display requests in FILEOUTPUT.

### Experimental XY STEP DMA

Pass `--xy-step-dma-lab` to `mcu/SOURCE_MCU/tools/build.py` and use a separate
work and output directory. The build identifies itself as
`0.13.14.11-XY-STEP-DMA-CHAIN-LAB`. The register model can be run with
`python3 mcu/SOURCE_MCU/tools/test_xy_step_dma.py --upstream .ci/pristine`.

The lab build uses finite DMA transfers for non-inverted X and Y
constant-period blocks of at least 32 pulses, with a period of 352 to
720 core ticks and the stock 2 µs STEP setting. TIM2 and TIM3 generate update
and compare events that set and clear PB3 and PB4 through DMA1 channels
2/7 and 3/6, respectively. The GPIO pins stay in output mode. The existing
software scheduler handles the other blocks. On the first completed hardware
block per axis, `klippy.log` records `M300 XY STEP DMA completed first X block`
or the equivalent line for Y.

Adjacent eligible blocks in the same direction can rearm both DMA channels
without resetting the running timer. The new period governs the gap after
the preceding block's final rising edge. If the counter has passed the safe
rearm window, the regular stop/start handoff handles the next block. The
first successful chained boundary per axis is reported in `klippy.log`.

This is a lab image for the M300 Classic application slot. Qualification
requires checking pulse width, count and timing on the physical board and
repeating X, Y and diagonal moves with a position check after each speed.
