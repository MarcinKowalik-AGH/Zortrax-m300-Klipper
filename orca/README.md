> Aktualny pakiet: **R2**, sprawdzony w silniku OrcaSlicer 2.3.2: 17 profili PASS G-code, PEEK tylko katalog. [Wyniki i ograniczenia](ORCA_RUNTIME_AUDIT_R2.md). Zastap poprzedni preset po imporcie. Nie wykonano testu GUI ani fizycznego wydruku.

# Zortrax M300 — OrcaSlicer 0,20 mm

Pakiet `Zortrax_M300_Classic_0p20_18_filaments.orca_printer` zawiera **jeden preset drukarki**, **jeden proces 0,20 mm** oraz **18 presetów materiałów Zortrax**. Przygotowany pod **Klipper M300 Classic z Orange Pi**, a nie pod oryginalny interpreter Z-Code.

**Import**: w OrcaSlicer otwórz File → Import → Import Configs, wskaż pakiet i wybierz `Zortrax M300 0.4 nozzle`. Proces: `0.20mm Standard @Zortrax M300 0.4 nozzle`. Filamenty są rozpoznawalne po `@Zortrax M300`, aby nie nadpisywać profili Inventure.

**Ważne**: Z-PEEK jest katalogowo obecny, lecz nie jest drukowalny (`filament_printable=0`); Z-SUPPORT są widoczne, ale nie mogą pełnić funkcji drugiego, niezależnego filamentu podporowego na jednogłowicowym M300. Dla pozostałych, zwłaszcza spoza 7 oficjalnych filamentów M300, wymagane są testy na sprzęcie. W repo dostępny jest `VALIDATION_M300_0p20.md` z pełnym audytem każdego klucza i konfiguracji.
