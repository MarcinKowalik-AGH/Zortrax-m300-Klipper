# Zortrax M300 Classic — port Klippera

[English](README.md) · [Kompilacja](docs/pl/BUILD.md) · [Instalacja](docs/pl/INSTALL.md) · [Stan i ograniczenia](docs/pl/STATUS.md)

Repozytorium źródeł dla **M300 Classic**, STM32F103 72 MHz, kinematyka Cartesian.
Aktualna baza: **MCU R14.5 + natywny host R15.7**, Klipper
`ee2c6fb6b00b2b5d097ef70d0868df7d74943b51`.

GitHub Actions wykonuje czystą kompilację GNU ARM, testy hosta i modeli
rejestrowych oraz dziewięć uruchomień rzeczywistego Klippy w FILEOUTPUT.
Artefakt do pobrania zawiera:

- BIN, ELF, słownik MCU, mapę, konfigurację kompilacji i opis pochodzenia.
- Sprawdzony kontener `M300APP.M3B` i ZIP na SD z aplikacją.
- Pasującą aktualizację **hosta Orange Pi R15.7**, testy i dokładne cofnięcie.
- Pełny zestaw źródeł hosta, raporty walidacji i sumy kontrolne.

Push do main ze zmianami źródeł lub CI uruchamia workflow. Dostępny jest też
przycisk **Actions → Build M300 STM32F103 and host R15.7 → Run workflow**.
Po zakończeniu pobierz `m300-r14_5-host-r15_7-<commit>` w sekcji Artifacts.

| Katalog | Zawartość |
|---|---|
| mcu/SOURCE_MCU | Overlay MCU, patcher przypiętego upstream i kompilator ARM |
| mcu/tests | Testy guard snapshot i natywnej kontroli grzania |
| host/klippy/extras | Główne źródła modułów i zasobów hosta M300 |
| host/update_template | Instalator i samodzielne testy regresji |
| host/config | Ustawienia samego wyświetlacza |
| ci | Składanie, walidacja i pakowanie artefaktów |
| tests/fixtures | Syntetyczne konfiguracje wyłącznie do FILEOUTPUT |
| docs/en, docs/pl | Dokumentacja rozdzielona na EN i PL |

Każdy plik runtime ma jedno główne źródło. CI składa z niego instalowalną
aktualizację; nie bazuje na ręcznie poprawianych archiwach ZIP. Upstream jest
pobierany z konkretnego commitu i sprawdzany SHA-256 przed patchowaniem.
Nie jest pobierana przypadkowa najnowsza wersja Klippera.

R15.6 przywraca natywne polecenia menu i rozpoznawanie osobnych akcji bazowania,
poprawia kontrast startowy i dodaje oryginalny księżyc z **Entering sleep mode**:
po pięciu minutach bezczynności komunikat przez dziesięć sekund potwierdzonego
wyświetlania, następnie wygaszenie. Podczas pracy ekran tylko przygasa.
Pierwszy niewidoczny gest wybudza bez wyboru opcji. Sterowanie urządzeniami
i idle_timeout pozostaje u dotychczasowych właścicieli.

R15.7 dodaje odczyt fabrycznej rewizji i automatyczny dobór Z=400/800,
wspólny dla M07 i statusu OLED. Wymaga pasującej aplikacji MCU R14.5.
Zobacz [Warianty sprzętu](docs/pl/HARDWARE_VARIANTS.md).
Paczka nie zawiera bootloadera ani zrzutu fabrycznego firmware. CI nie uruchamia
flashowania, UART, fizycznego ruchu ani grzania. Otwarte kwestie skali/zakresu Z
i pozostałych pomiarów opisuje STATUS.md.
