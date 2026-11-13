# M300 RC8 — automatyczna synchronizacja czasu druku

Klipper wywołuje licznik MCU podczas normalnej pracy. Zlicza czas drukowania modelu, również dla wydruków anulowanych i przerwanych, i zapisuje go na Orange Pi. Po włączeniu synchronizacji Klipper przekazuje oczekujące pełne minuty, gdy drukarka jest bezczynna. MCU sprawdza warunki zapisu, odczytuje fabryczny rekord ID0, aktualizuje go z użyciem dwóch banków ustawień i zwraca wynik. Klipper ponownie odczytuje zapisaną wartość, uzgadnia ją z dziennikiem i zachowuje resztę sekund do następnego transferu.

Nowy zapis wymaga co najmniej jednej pełnej minuty oczekującego czasu. Krótszy czas pozostaje na Orange Pi do następnej synchronizacji.

## Aktualizacja

Zaktualizuj Orange Pi przy bezczynnej drukarce w stanie Ready:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Wgraj osobno aplikację MCU 1.0.4 z `MCU/M300_SD.zip`. Zachowaj sprawdzoną pełną kopię Flash tej płyty i istniejący wpis `factory_counter_backup:` w `[m300_mcu]`. Jeśli włączasz funkcję po raz pierwszy, dodaj ścieżkę do tej kopii. Synchronizacja działa bez restartu po spełnieniu warunków zapisu. Zgodne starsze firmware MCU nadal obsługuje licznik na Orange Pi. `ZORTRAX_HARDWARE_STATUS` pokazuje stan synchronizacji i banków, a `ZORTRAX_INFO REFRESH=0` zwraca minuty w MCU, sekundy na hoście i czas łączny. Ilustracje OLED z beta.20 są materiałem historycznym. [Aktualizacja MCU i odczyt licznika](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.8/docs/pl/MCU_FIRMWARE_1.0.4.md).

## Weryfikacja

Użytkownik potwierdził uruchomienie fabrycznego firmware’u 1.3.1 po wgraniu przez posiadany bootloader. Próba sprzętowa RC8 dotyczy automatycznego zapisu ID0 i zachowania po przerwaniu zapisu Flash. Klipper wznawia przerwany transfer banków na podstawie dziennika transakcji. [Rejestr odbiorów](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.8/docs/pl/ACCEPTANCE_REGISTER.md).
