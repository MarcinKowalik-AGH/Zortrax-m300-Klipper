# MCU 1.0.9 — optional STM32 die temperature

For the Classic Zortrax M300 / STM32F103 only.

This version adds `M300_MCU_TEMPERATURE_ABI=1` and sets ADC16 acquisition to
239.5 cycles (about 53.2 us at 4.5 MHz). It preserves external hotend/bed sample
fields and keeps internal die readings outside their safety observer. It uses
the existing native ADC transport and does not enable debug memory reads.
The independent ADC2 fan thermostat is unchanged. Application starts at
0x08008000; the SD image contains no bootloader.

After the successful verified Actions build, download `M300_MCU_v1.0.9_SD.zip`
and its SHA256 checksum from `mcu-v1.0.9`. Verify the archive and extract
`M300APP.M3B` to the SD card root. With the printer idle, update the application
through the installed M300 bootloader, retaining the UART setting. Confirm
MCU 1.0.9 in the startup log / `ZORTRAX_INFO REFRESH=0`, then enable the
[optional host addon](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/main/docs/en/HOST_TEMPERATURE.md). Existing hosts work with this
firmware while the addon is disabled.

Software validation covers ADC channel/sample fields, ADC2 isolation, host
conversion and stale-data handling. Physical printer validation remains:
cold reading, warming trend and unchanged hotend/bed measurements.

Nominal sensor data: [ST DS5792](https://www.st.com/resource/en/datasheet/stm32f103re.pdf).
