# Zortrax M300 — OrcaSlicer 0,20 mm

Pakiet `Zortrax_M300_Classic_0p20_18_filaments.orca_printer` zawiera **jeden preset drukarki**, **jeden proces 0,20 mm** oraz **18 presetów materiałów Zortrax**. Przygotowany pod **Klipper M300 Classic z Orange Pi**, a nie pod oryginalny interpreter Z-Code.

**Import**: w OrcaSlicer otwórz File → Import → Import Configs, wskaż pakiet i wybierz `Zortrax M300 0.4 nozzle`. Proces: `0.20mm Standard @Zortrax M300 0.4 nozzle`. Filamenty są rozpoznawalne po `@Zortrax M300`, aby nie nadpisywać profili Inventure.

**Ważne**: Z-PEEK i trzy Z-SUPPORT są wpisami katalogowymi oznaczonymi jako niezgodne z pracą w M300 Classic. Dla pozostałych, zwłaszcza spoza 7 oficjalnych filamentów M300, wymagane są testy na sprzęcie. W repo dostępny jest `VALIDATION_M300_0p20.md` z pełnym audytem każdego klucza i konfiguracji.
