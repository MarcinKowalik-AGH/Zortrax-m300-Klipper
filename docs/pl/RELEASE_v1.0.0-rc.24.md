# M300 Classic RC24 · Jasność OLED i powrót połączenia z Fluidd

Przy ustawianiu jasności OLED dodatkowy obrót poniżej pierwszego segmentu wybierał ukrytą pozycję Back. Ekran pokazywał wtedy zapisaną wcześniej jasność. Przy nastawie 8 wyglądało to jak skok z jednego kwadratu na połowę skali. W RC24 pokrętło zatrzymuje się na 1. Kliknięcie zapisuje widoczną wartość, a przytrzymanie wraca do wybranej pozycji w Settings. Te same granice obowiązują w edytorach jasności LED oraz czasu DIM i SLEEP.

Fluidd ponawia połączenie z Moonrakerem również po dłuższej przerwie. Ciche połączenie WebSocket sprawdza odczytem stanu serwera. Po odzyskaniu połączenia z tą samą drukarką odświeża stronę także w widoku urządzenia osadzonym w OrcaSlicerze. Przy niestabilnym połączeniu automatyczne przeładowanie może nastąpić raz na dwie minuty. Rozłączenie unieważnia okno poprzedniej procedury. Widok pobiera aktualny stan drukarki.

Na bezczynnej M300 w stanie Ready wykonaj w katalogu gałęzi orange-pi:

```bash
git pull --ff-only &&
sha256sum -c --quiet SHA256SUMS &&
python3 install-orange-pi.py &&
python3 install-orange-pi.py --update-fluidd --port 4480
```

Po instalacji otwórz Fluidd na porcie 4480 ponownie, aby wczytać nową obsługę połączeń. Poprawka korzysta z aplikacji MCU 1.0.8. Przy aktualizacji z RC23 wystarczą host i Fluidd. Plik `MCU/M300_SD.zip` służy również do pierwszej instalacji. Starsze ilustracje instrukcji pochodzą z beta.20.
