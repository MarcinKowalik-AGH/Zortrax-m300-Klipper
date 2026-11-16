# M300 Classic RC14

Po nagrzaniu i ewentualnej stabilizacji stołu `START_PRINT` cofa filament
o 10 mm. Cofnięcie kończy się przed kontaktem Z. Po bazowaniu Klipper
wybiera siatkę, dojeżdża do początku czyszczenia na bezpiecznej wysokości
i podaje 6 mm filamentu. Następnie wykonuje dwie długie linie w Y i dwie w X
na jednej zadanej wysokości Z. Pierwszy odcinek X rusza z końca powrotnego
odcinka Y. Aktywna siatka koryguje fizyczne położenie Z. Po ostatniej linii
Klipper odsuwa Z i przekazuje wykonanie do pliku modelu. Samodzielne Home Z
i Bed Mesh korzystają z własnego cyklu pomiarowego.

W trybie Dynamic światło świeci stale na biało podczas drukowania modelu,
również przy zmianach celów grzałek. Przygotowanie, pauza i błędy mają
sygnalizację zgodną ze stanem drukarki.

## Zaktualizuj Klippera

Poczekaj na Ready, zakończ wydruk i procedury oraz wyłącz cele grzania.
Uruchom z konta Klippera:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py"
```

Jeśli drukarka ma już MCU 1.0.5, wystarczy aktualizacja hosta Klippera.
Pełna paczka zawiera `MCU/M300_SD.zip` do pierwszej instalacji. Fluidd
działa na porcie 4480. Osobne polecenie z opcjami
`--update-fluidd --port 4480` służy do jawnej naprawy strony.
[Pierwsza instalacja](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.14/docs/pl/FIRST_INSTALL.md) ·
[Instrukcja aktualizacji](https://github.com/MarcinKowalik-AGH/Zortrax-m300-Klipper/blob/v1.0.0-rc.14/docs/pl/INSTALL.md)

## Weryfikacja

Testy programowe sprawdzają kolejność startu, cztery linie czyszczące i
światło podczas drukowania modelu. Próba na drukarce pozostaje do
wykonania przy następnym nadzorowanym wydruku. Sprawdź cofnięcie przed
kontaktem Z, cztery linie i białe światło po rozpoczęciu druku modelu.
Ilustracje OLED z beta.20 pochodzą z historycznej wersji.
