# M300 Classic RC16

| Polecenie | Ruch drukarki |
|---|---|
| `PAUSE`, `M25`, `M601` | Po dokończeniu ruchów głowica pozostaje w bieżącym XY. Stół opuszcza się domyślnie o 5 mm w granicach skoku. Silniki trzymają pozycję. |
| `RESUME` | Klipper przywraca temperatury i pozycję przerwania, po czym kontynuuje ten sam plik. |
| `M600` lub wymiana wybrana z menu pauzy | Głowica dojeżdża do punktu serwisowego na wysokości uzyskanego prześwitu. Wymiana rozpoczyna się po zatrzymaniu głowicy. |
| `END_PRINT` z Orca | Stół opuszcza się o 300 mm lub do skonfigurowanego limitu Z. Następnie głowica parkuje w prawym tylnym rogu (domyślnie X300 Y305). Po zakończeniu ruchów, wyłączeniu celów grzania i nawiewu modelu oraz odczytaniu końca pliku OLED pokazuje **PRINTING DONE**. |

Przy końcowej pozycji Z250 i limicie Z300 stół zjedzie o 50 mm.
Jeżeli zostało mniej niż wymagany prześwit (domyślnie 5 mm), stół wykorzysta dostępny ruch, a głowica pozostanie w bieżącym XY.
Opcja **Stop the print** w menu pauzy wywołuje `CANCEL_PRINT` i oznacza anulowanie zadania.

## Aktualizacja Orange Pi

Po zakończeniu bieżącego wydruku i aktywnych procedur, przy wyłączonych celach grzania i stanie Ready, uruchom jako użytkownik Klippera

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

W konsoli Fluidd wpisz `PRINT_CONTROL_STATUS`. Oczekiwana rewizja to `0.13.16.41-END-PARK`.
Użyj istniejącego Fluidd na porcie 4480. Opcja `--update-fluidd --port 4480` służy do osobnej naprawy strony.
W działającej instalacji z MCU 1.0.5 wystarcza aktualizacja hosta. Paczka pierwszej instalacji zawiera `MCU/M300_SD.zip`.
[Pierwsza instalacja](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.16/docs/pl/FIRST_INSTALL.md) · [Aktualizacja](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.16/docs/pl/INSTALL.md)

Testy programowe obejmują pauzę i wznowienie z aktywną siatką, parkowanie do wymiany filamentu, niski i wysoki model, wolną oś Z oraz anulowanie w trakcie końcowego ruchu. Próba RC16 na fizycznej drukarce czeka na potwierdzenie. Ilustracje OLED w podręczniku pochodzą z beta.20.
