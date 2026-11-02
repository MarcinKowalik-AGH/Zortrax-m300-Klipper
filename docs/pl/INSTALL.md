# Instalacja MCU R14.5 i hosta R15.7

[English](../en/INSTALL.md) · [Warianty sprzętu](HARDWARE_VARIANTS.md)

Dla M300 Classic z dotychczasowym bootloaderem M300 i natywnym hostem
R15.5/R15.6. Automatyczny dobór Z wymaga **obu** elementów: aplikacji MCU R14.5
oraz hosta R15.7. Aktualizowana jest aplikacja, nie bootloader. Instalator
zachowuje liczby Z w printer.cfg, zapisane PID-y, kalibrację ekstrudera i obecne
ustawienia ekranu. Używana skala Z jest wybierana podczas startu.

## Przygotowanie hosta

Pobierz artefakt z udanego przebiegu Actions dla właściwego commitu i rozpakuj.
Z Maca skopiuj znajdujący się w nim katalog M300_HOST_R15_7_FACTORY_Z:

~~~bash
scp -r "$HOME/Downloads/M300_HOST_R15_7_FACTORY_Z" klipper@192.168.4.157:/home/klipper/
ssh klipper@192.168.4.157
cd ~/M300_HOST_R15_7_FACTORY_Z
python3 VERIFY.py
python3 -m unittest discover -s tests -v
python3 install.py
~~~

Oczekiwane: 92 testów OK i plan R15.7 z informacją o wymaganym MCU R14.5 dla
factory Z. Instalator odczytuje ścieżki z Moonrakera, z dotychczasowymi ścieżkami
M300 jako wariantem zapasowym. Nieznane lokalnie zmodyfikowane pliki runtime
powodują odmowę zamiast cichego nadpisania.

## Wgranie zgodnej pary

Pomiędzy operacjami drukarki:

1. Wykonaj `sudo systemctl stop klipper.service`.
2. Wgraj **MCU/M300APP.M3B** z tego artefaktu przez sprawdzoną procedurę
   aktualizacji bootloadera M300 z SD. MCU/M300_R14_5_SD.zip zawiera samą
   aplikację. Zachowaj stronę danych fabrycznych Flash i bootloader.
3. W katalogu aktualizacji hosta wykonaj `python3 install.py --apply`.
4. Wykonaj `sudo systemctl start klipper.service`.

Zachowaj ścieżkę zwróconego RECEIPT.json. Instalator nie uruchamia usługi ani
nie programuje MCU. Adres aplikacji pozostaje 0x08008000. ELF, mapa, słownik
i raport kompilacji dotyczą tego konkretnego buildu; nie mieszaj commitów.

## Sprawdzenie wariantu

We Fluidd wykonaj:

~~~gcode
STATUS
ZORTRAX_HARDWARE_STATUS
ZORTRAX_MCU_STATUS
ZORTRAX_MOTION_STATUS
~~~

Oczekiwany stan sprzętu: FACTORY_PROFILE_APPLIED. Dla zachowanego rekordu HW05:
hardware_label=HW05, stock/effective Z=400 i effective rotation=8.
HW04 wybiera 800 i rotation=4. Wartość configured rotation może być inna,
ponieważ wybór fabryczny nie przepisuje pliku. M07 ma używać tej samej skali.
Information na OLED pokazuje rewizję i używaną skalę Z. Przed pełnym zakresem
zmierz krótki ruch Z z poprawnie zbazowanej pozycji z prześwitem. CI nie
wykonało fizycznych operacji na żadnym z tych egzemplarzy.

Brak/uszkodzenie ID3 albo starszy MCU daje opisowy błąd startu. Dla świadomie
skonfigurowanej/przebudowanej mechaniki dostępne jest `[m300_mcu] z_profile: config`;
znaczenie opisują Warianty sprzętu. Nie wybieraj tego trybu przez zgadywanie śruby.

Zachowano zachowanie snu i menu R15.6. ZORTRAX_DISPLAY_STATUS,
ZORTRAX_MENU_STATUS i ZORTRAX_NATIVE_STATUS raportują dotychczasowych właścicieli.
Ustawienia ekranu są w ~/printer_data/config/m300_display.cfg.

## Cofnięcie

Zatrzymaj usługę, wykonaj `python3 install.py --rollback /DOKLADNA/SCIEZKA/RECEIPT.json`
i uruchom usługę. Późniejsze edycje plików są chronione. Cofnięcie przywraca
host i konfigurację; nie zmienia aplikacji MCU. HOST_SOURCE jest pełną kopią
zgodnych źródeł, a nie drugim instalatorem.
