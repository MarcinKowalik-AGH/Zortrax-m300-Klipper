# Instalacja iteracji testowej R16.4

[English](../en/INSTALL.md) · [Funkcje i odbiór](FEATURES.md)

Dla M300 Classic z natywnym hostem R15.3/R15.5/R15.6/R15.7 i bootloaderem M300.
R16 wymaga MCU R14.5 dla odczytu wariantu Z. Jeśli R14.5 jest już wgrany,
nie wymaga ponownego programowania. Pełny artefakt Actions zawiera również
świeżo skompilowaną aplikację R14.5 dla starszych instalacji.

Rozpakuj artefakt i skopiuj z Maca znajdujący się w nim katalog hosta:

~~~bash
scp -r "$HOME/Downloads/M300_HOST_R16_4_NORMAL_UI" klipper@192.168.4.171:/home/klipper/
ssh klipper@192.168.4.171
cd ~/M300_HOST_R16_4_NORMAL_UI
python3 VERIFY.py
python3 -m unittest discover -s tests -v
python3 install.py
~~~

Oczekiwane: 171 testów OK i plan R16.4. Sprawdź listę plików: aktualizacja
zmienia dawną sekcję uruchomieniową na tryb native, ustawia homing Z przy 180C,
STEP 2 us, profil XY 300 mm/s i dodaje trzy pliki makr. Zachowuje PID-y,
kalibrację E oraz świadome wartości geometrii inne niż dawne Z30. Nieznane
lokalne edycje modułów runtime powodują odmowę; plan niczego nie zapisuje.
Prawidłowe obecne ustawienia ekranu pozostają.

Pomiędzy operacjami drukarki:

~~~bash
sudo systemctl stop klipper.service
python3 install.py --apply
sudo systemctl start klipper.service
~~~

Zachowaj ścieżkę RECEIPT.json. Jeżeli MCU jest starszy od R14.5, przy zatrzymanym
Klipperze wgraj MCU/M300APP.M3B przez sprawdzony bootloader/SD M300, przed
uruchomieniem nowego hosta. Aplikacja zaczyna się pod 0x08008000; nie zastępuje
rekordów fabrycznych ani bootloadera. ZIP aplikacji na SD: MCU/M300_R14_5_SD.zip.

Po uzyskaniu Ready utwórz grupy Fluidd:

~~~bash
python3 setup_fluidd.py
python3 setup_fluidd.py --apply
~~~

Odśwież przeglądarkę. Grupy: Klipper, ZORTRAX M300 i TEST M300. Skrypt używa
wyłącznie API bazy Fluidd w Moonrakerze i zachowuje pozostałe ustawienia UI.
Zwróconą kopię można przywrócić przez
`python3 setup_fluidd.py --rollback /DOKLADNA/KOPIA.json --apply`.

W konsoli sprawdź STATUS, ZORTRAX_HARDWARE_STATUS, ZORTRAX_MOTION_STATUS,
ZORTRAX_DISPLAY_STATUS i ZORTRAX_NATIVE_STATUS: tryb native, wykrytą skalę Z,
180C przy bazowaniu i 2 us w konfiguracji. Fizyczny odbiór opisuje FEATURES.md.
Timing przy dużej prędkości/pełnym obciążeniu pozostaje testem na drukarce.
Instalacja nie uruchamia automatycznie makr testowych.

Cofnięcie hosta/konfiguracji: zatrzymaj Klipper, wykonaj
`python3 install.py --rollback /DOKLADNA/SCIEZKA/RECEIPT.json` i uruchom usługę.
Receipt przywraca dokładne poprzednie pliki i chroni późniejsze edycje. Nie
zmienia MCU. HOST_SOURCE jest zgodną kopią źródeł, nie drugim instalatorem.
SHA256SUMS i BUILD_PROVENANCE.json identyfikują konkretny build Actions.

R16.4 dodaje bezpośrednią migrację znanego natywnego hosta R15.3, również
bez rozszerzenia wyświetlacza. Rzeczywiste sprawdzenie API i aktualizacja po
sumach są testowane na archiwalnych modułach R15.3. Zachowanie runtime/MCU
pozostaje jak w R16. Oczekiwany wynik: INSTALLED_M300_R16_4.

Jeżeli poprzedni instalator zgłosił `REFUSED: R15.5 motion and M11 presentation support required`,
nie zainstalował R16. Samo powodzenie setup_fluidd.py zmienia jedynie grupy makr.
R16.4 usuwa tę przeszkodę dla rozpoznanej bazy R15.3. Przed ruchem potwierdź
`INSTALLED_M300_R16_4` oraz w `ZORTRAX_MOTION_STATUS`: `normal_control=true`
i `z_home_hotend_target_c=180`. `G28 X Y` nie grzeje; `G28 Z` czeka na
natywną kontrolę nagrzania przed ruchem do kontaktu.

R16.4 aktualizuje także m300_lifecycle.py. Po instalacji ZORTRAX_LINK_STATUS
ma zgłaszać 0.13.16.2-LIFECYCLE-RECONNECT. Dla zwykłego restartu usługi/Orange Pi
dodano jedną próbę odzyskania starej sesji lub zatrzasku heartbeat. Odbiór i
przypadki wymagające jawnego restartu opisuje [Cykl połączenia](CONNECTION.md).

[Poziomowanie M07 w R16.4 — uruchomienie i odbiór](LEVELING.md)
