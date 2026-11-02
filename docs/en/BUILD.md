# Build and develop

[Polski](../pl/BUILD.md)

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
python ci/package_release.py --build dist/mcu
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
