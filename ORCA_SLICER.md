# OrcaSlicer i M300 Classic

Profile drukarki, procesów, średnic dyszy i filamentów znajdują się w [repozytorium integracji OrcaSlicera](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Orca-Slicer). Wybierz profil M300 Classic odpowiadający założonej dyszy. Zakładka Device otwiera Fluidd pod adresem `http://<adres-hosta>:4480/`.

## Początek i koniec pliku

Sprawdź w profilu drukarki sekcje maszynowego G-code. Dla automatycznego wyboru zapisanej siatki początek zawiera jedno wywołanie:

```gcode
START_PRINT EXTRUDER_TEMP=[nozzle_temperature_initial_layer] BED_TEMP=[bed_temperature_initial_layer_single] MESH=AUTO
```

Koniec pliku wywołuje `END_PRINT`. START prowadzi grzanie, bazowanie, wybór siatki i linie czyszczące. Parametry w nawiasach kwadratowych rozwija slicer podczas generowania pliku. W konsoli operującej na drukarce podaje się wartości liczbowe. [Obsługa wydruku](docs/pl/PRINT_CONTROL.md) · [Podręcznik operatora (EN)](docs/en/USER_GUIDE.md).

Przy zmianie koloru wybierz `M600` lub **Change the material**. Gdy pojawi się potwierdzenie wypływu, w zakładce Device możesz użyć przycisków Extrude i Retract, potwierdzić czysty kolor i osobno wznowić wydruk. [Obsługa filamentu](docs/pl/MAINTENANCE_MATERIAL.md).
