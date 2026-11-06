# Hotend cooling: MCU R14.16 and native host

The upper fan, PE14, cools the hotend heatsink. The lower fan, PE13, is print
cooling: native M106/M107 and the slicer control it while connected. Normal
offline cooling keeps the lower fan off and controls the upper fan by measured
temperature. Heating PID remains native Klipper; the MCU independently
supervises the temperature envelope, heartbeat, heater/motor gates and fans.

| Valid hotend temperature | Upper fan, online and offline |
| --- | --- |
| At or above 50 C | On |
| Above 45 C and below 50 C | Retain the previous automatic state |
| At or below 45 C | Off |
| Missing, stale or invalid temperature | Protective cooling |

The heater target does not switch on the cold heatsink fan. G28 Z, G28 ALL,
Autocalibration and material heating therefore use this same thermostat.
An explicit cold fan test can still turn the upper fan on. A test cannot
switch it off when automatic cooling is required.

The host adapter binds the temperature-only callback before heater_fan Ready
registers its timer. It retains the existing heater_fan object, native Fan/PWM
queue, shutdown speed, one-second callback cadence and manual test wrappers.
It sends a new duty only when needed. No additional ADC, UART polling timer,
heater owner or fan output is created. The installer aligns `heater_temp` to
50 C and preserves pin ownership, PWM settings, PID, E and motion geometry.
`ZORTRAX_FANS_STATUS` reports the 50/45 C thresholds, 5 C hysteresis,
`hotend_auto_uses_target: false` and the current upper cooling requirement.

The MCU thermostat already existed before R14.16. It uses native ADC1
observations while available and independent ADC2 conversions without a host.
The fixed 12-bit conversion gives ON at raw314 (about 50.15 C) and OFF at
raw281 (about 44.88 C), the conservative quantization of nominal 50/45 C.
Startup is protective until the first complete valid sensor pair. A cold
first measurement releases the fans; hot startup cools the heatsink locally.

R14.16 fixes a specific offline handoff: ADC1 samples can expire before the
host heartbeat. The resulting ADC_STALE latch previously forced both fans
forever, even after ADC2 acquired a valid cold reading. Only a fresh,
in-range independent ADC2 pair may now run the local thermostat in this case.
Neither a later ADC1 sample nor an old ADC2 sample may release that bypass.
The shutdown/fault remains latched, and heaters and motion remain disabled.
Invalid or stale ADC2 readings, out-of-range sensors, connector/electrical
faults and other critical latches retain protective full cooling. The MCU
never clears its fault or restores heat/movement autonomously.

## Supervised acceptance

Install the matching host and flash `MCU/M300_R14_16_SD.zip` using the existing
SD bootloader procedure. Preserve the working 750000 baud configuration.

1. With a connected cold printer, read `ZORTRAX_MCU_STATUS` and
   `ZORTRAX_FANS_STATUS`. Confirm R14.16 and valid temperature telemetry.
2. Start normal supervised heating or homing. The automatic upper request
   stays off below 50 C, then turns on at the threshold. The lower fan should
   follow its native print request, normally zero during homing.
3. Turn off the heaters and observe the upper fan staying on through the
   45–50 C band and switching off at 45 C. An explicit fan-test request is
   separate from this automatic state.
4. With the printer cold and idle, verify an MCU start without Orange Pi.
   After valid local acquisition, both fans should be off. Hot offline
   cooling must keep the upper fan running until the lower threshold.

Read the existing MCU `local_cooling.mode`, `reason`, `sample_valid`,
`temperature`, `hotend_on` and `print_on` fields if bypass remains active.
An invalid or critical reason is not normal offline thermostat operation.
Software tests cover the register model and full host process; physical
temperature accuracy, fan airflow and actual disconnected behavior still
require printer observations.
