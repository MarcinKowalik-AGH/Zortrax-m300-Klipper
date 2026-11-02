# Pochodzenie kodu i grafiki

Kod zachowuje oznaczenia GPL portu M300; tekst licencji znajduje się w COPYING.
Księżyc jest dokładnym wyciągiem pikseli z dostarczonego firmware fabrycznego
M300 1.3.1 i wcześniej audytowanego atlasu OEM. Własność grafiki producenta
pozostaje niezmieniona; nie przypisano jej nowej licencji.

SHA-256 obrazu, adres deskryptora, suma rozkodowanej klatki i dowód wywołania
są w evidence/OEM_SLEEP_EVIDENCE.json. Dawne pliki w tests/reference służą
tylko testom zgodności i regresji; nie trafiają do drukarki.

Paczka zmienia m300_menu.py i m300_ui_m11_state.py oraz dodaje m300_display.py,
m300_display_stream.py, m300_display_oem.py i m300_display_moon.json.
Nie zastępuje transportu i renderera OLED, rdzenia Klippera, firmware MCU,
modułów ruchu i termiki.

R15.7 aktualizuje też m300_mcu, adaptery skali ruchu/kalibracji i menu.
Nowe m300_hardware i m300_factory w MCU realizują odczyt ID3 i wybór profilu
opisany w [Wariantach sprzętu](HARDWARE_VARIANTS.md). Powyższe stwierdzenie
o niezmienionym MCU i module ruchu dotyczy historycznej aktualizacji R15.6.
