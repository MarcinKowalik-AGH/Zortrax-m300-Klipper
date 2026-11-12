# M300 v1.0.0-rc.2 — pozostałe makro XY i aktualizacje Orange Pi

[Instrukcja główna](../../README_PL.md) · [Wspólny interfejs RC1](RC1_UI.md)

## Poprawka po rzeczywistym odczycie konfiguracji

12 listopada użytkownik odczytał z Moonrakera pozostawione `TEST_ZORTRAX_XY`.
Ta definicja ma `SPEED|default(200)`, stan `TEST_M300_XY_STATE` i końcowe
`RESTORE_GCODE_STATE ... MOVE=0`. RC1 znała inne sygnatury tego samego makra,
a tej brakowało. Dlatego zachowała je jako nierozpoznane i tylko ukryła.
Nie oznacza to błędu drukarki ani potrzeby ponownego skategoryzowania makra.

RC2 dodaje wyłącznie SHA-256 dokładnego znormalizowanego ciała:
`53be4a2ac5933a02df7321ed45f99ef9fe82d82b59faead042f1c472ecf3580f`.
Referencja znajduje się w testach, nie w aktywnej konfiguracji. Migracja usuwa
rozpoznaną definicję z printer.cfg lub include i odświeża zapisane preferencje
Fluidd. Własne dodatkowe polecenia, inny parametr lub dodatkowe opcje makra są
zachowane. Nie wykonuje makra XY, nie zmienia ruchu, homingu, temperatur, siatki,
purge ani ustawień kwalifikowanego Z. Korzysta z istniejącej kopii i rollbacku.

## Aktualizacja portu M300

Wyłącznie przy bezczynnej drukarce Ready, bez wydruku i bez pauzy:

```bash
git -C "$HOME/m300-orange-pi" pull --ff-only &&
python3 "$HOME/m300-orange-pi/install-orange-pi.py" --port 4480
```

Odśwież Fluidd przez Cmd+Shift+R. Lista makr odczytana z configfile nie powinna
już zawierać dokładnie tej definicji. Brak wpisu potwierdza usunięcie, nie samo
wyłączenie przełącznika. Instalator nie aktualizuje APT ani Moonrakera.
MCU pozostaje `0.13.14.19-TONED-OLED-UART8`; `MCU/M300_SD.zip` nie jest potrzebny
do tej aktualizacji. 65 ilustracji beta.20 pozostaje historycznym odniesieniem.

## Konkretny Moonraker z odczytu użytkownika

Porównano `9e676eba6b02661a4dfa3ec6e7ac3f3504498e6d` z
`b559b9a81161f958a43c2f527b6ad96f73310d5d`. Różnica to jeden commit i jeden
plik klippy_connection.py: iterowanie po przecięciu kluczy subskrypcji/statusu
zamiast sprawdzania każdego subskrybowanego obiektu. Filtr pól i wywołanie
send_status pozostają. Nie zmienia to UART ani firmware; ocena niskiego ryzyka
wynika z przeglądu kodu, nie z fizycznego testu drukarki. Ta ocena dotyczy tylko
podanego commita, nie przyszłych aktualizacji kanału dev. Aktualizuj Moonrakera
osobno po kopii konfiguracji i bazy; nie wybieraj Update All. Sam Moonraker nie
wymaga późniejszego ponownego nakładania portu M300.

Źródło: [dokładny diff Moonrakera](https://github.com/Arksine/moonraker/compare/9e676eba6b02661a4dfa3ec6e7ac3f3504498e6d...b559b9a81161f958a43c2f527b6ad96f73310d5d).

## Pakiety systemowe: wstrzymanie aktualizacji sprzętowych

Lista użytkownika zawiera jądro, DTB, U-Boot, BSP i firmware. Nie aktualizuj
całej tej grupy razem bez obrazu karty SD i późniejszej kontroli startu, sieci,
UART oraz nakładek. Zalecenie dotyczy działającej konfiguracji, nie twierdzenia,
że nowszy kernel jest wadliwy. Zamrożenie jest tymczasowym kompromisem: opóźnia
również poprawki bezpieczeństwa; zaplanuj kwalifikację aktualizacji sprzętowych.

Dla **dokładnych nazw z tego odczytu** można zastosować:

```bash
sudo apt-mark hold armbian-bsp-cli-orangepizero-current armbian-firmware linux-dtb-current-sunxi linux-image-current-sunxi linux-u-boot-orangepizero-current
apt-mark showhold
```

Pozostałe pozycje to apt, apt-utils, armbian-config, base-files, libapt-pkg7.0,
linux-libc-dev, tzdata, zlib1g i zlib1g-dev. linux-libc-dev to nagłówki interfejsu
dla programów, nie działający kernel. Same nazwy nie pozwalają ocenić wszystkich
skryptów i zależności konkretnych wersji; najpierw wykonaj symulację, nie używaj
--allow-change-held-packages ani wymuszonego --yes. Nie zalecamy bezterminowego
wyłączania wszystkich poprawek bezpieczeństwa. Nazwy orangepizero/sunxi opisują
zgłoszony zestaw pakietów; nie zastępują identyfikacji modelu fizycznej płytki.

Źródła: [Armbian — aktualizacje](https://docs.armbian.com/config/updates/),
[apt-mark](https://manpages.debian.org/trixie/apt/apt-mark.8.en.html).

## Klipper i walidacja

`klipper {}` w skróconym odczycie nie dowodzi aktualności ani czystego repozytorium:
może oznaczać brak wpisu lub brak wybranych pól. Baza Klippera projektu pozostaje
przypięta. Aktualizuj port M300 powyższym poleceniem; nie zakładaj, że aktualizacja
dowolnego upstream Klippera i późniejsze uruchomienie instalatora przywrócą zgodność.

Dodano siedem testów: dokładnej sygnatury, migracji w pliku głównym i include,
formatu z =/tabulatorami/CRLF, zachowania własnych zmian, SAVE_CONFIG i usuwania
nieaktualnych preferencji. Badane są idempotencja, dokładny rollback oraz migracja wersji modułu z RC1. Nie
wykonano aktualizacji systemu ani nowych testów sprzętowych na urządzeniu użytkownika.
