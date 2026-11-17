# M300 Classic RC17

RC17 aktualizuje host Klippera na Orange Pi. Na drukarce z MCU 1.0.5 wystarcza aktualizacja hosta. Paczka pierwszej instalacji zawiera `MCU/M300_SD.zip`. Port Fluidd to 4480.

| Funkcja | Obsługa w RC17 |
|---|---|
| Druk z Orca | Aktywny plik zachowuje kontrolę nad START i END. Polecenie bazowania operatora w trakcie zadania zostaje odrzucone. |
| Wymiana filamentu | Jeśli brakuje miejsca na parkowanie po M600, głowica zachowuje XY. Operator może wznowić wydruk z pauzy. |
| Siatka | Wybierz zapisaną płytę przez `BED_MESH_PROFILE LOAD=nazwa`. `MESH=AUTO` sprawdza wybór przed ruchem i ładuje go po bazowaniu. Świadomy druk bez siatki wymaga `MESH=NONE`. |
| Gorąca dysza | Samodzielne Home Z i pomiar mesh cofają filament o 10 mm i przywracają 10 mm po powodzeniu. START wykonuje pojedyncze cofnięcie o 10 mm i podaje 6 mm przed liniami czyszczącymi. |
| Czas | Klipper sprawdza potwierdzenie rozliczonych minut przed kolejną synchronizacją. Zegar uwzględnia również pełny okrąg G2/G3 z ekstruzją. |
| Naprawa strony | Osobne polecenie `--update-fluidd --port 4480` atomowo wymienia katalog i weryfikuje rzeczywisty HTML, JavaScript i CSS przez HTTP. |

Aktualizację wykonuj przy bezczynnej drukarce. Zwykły instalator zachowuje działającą stronę i konfigurację nginx. Po aktualizacji sprawdź `PRINT_CONTROL_STATUS`, `ZORTRAX_HARDWARE_STATUS` i `ZORTRAX_INFO REFRESH=0`. Fizyczny odbiór RC17 obejmuje dwa zapisy ID0, pełne ponowne włączenie oraz cykl pauza, wymiana, wznowienie i koniec z OLED i Fluidd. Ilustracje OLED w podręczniku pochodzą z beta.20.

[Instrukcja aktualizacji](INSTALL.md) · [Pierwsza instalacja](FIRST_INSTALL.md) · [Rejestr odbiorów](ACCEPTANCE_REGISTER.md)
