# Zachowanie — R15.7

[English](../en/BEHAVIOUR.md) · [Instalacja](INSTALL.md)

## Bezczynność wyświetlacza

| Warunek | Stan | Obraz |
|---|---|---|
| Mniej niż timeout od obsługi | AWAKE | Bieżący ekran, normalny kontrast |
| Timeout podczas pracy/pauzy/ruchu/grzania | DIM | Bieżący ekran, niski kontrast |
| Timeout podczas bezczynności | ENTERING_SLEEP | Oryginalny księżyc i Entering sleep mode |
| Potwierdzony komunikat przez notice_seconds | OFF | Wyłączona emisja OLED |
| Interakcja operatora | AWAKE | Odświeżony bieżący ekran |

Timer komunikatu rusza po potwierdzeniu klatki i kontrastu. Brak ACK nie jest
uznawany za udane pokazanie. Ponowna inicjalizacja transportu zeruje odliczanie.
Praca rozpoczęta w trakcie komunikatu przywraca jej widok przygaszony. Po
zakończeniu pracy bez nowej interakcji pojawia się komunikat, potem wygaszenie.

Obsługa operatora to świeże zdarzenie pokrętła lub zewnętrzne żądanie G-code
Moonraker, także odrzucone polecenie. Same odczyty obiektów, heartbeat, temperatury
i G-code odtwarzany wewnętrznie przez virtual_sdcard nie odświeżają czasu.
Automatyzacja wysyłająca gcode/script jest nierozróżnialna od operatora i wybudza.
Surowe wejście PTY nie jest przechwytywane; może użyć ZORTRAX_DISPLAY_WAKE.

Pierwszy gest na wygaszonym ekranie lub komunikacie jest zużywany w całości,
łącznie z długim przytrzymaniem i puszczeniem. Nie wybiera niewidocznej pozycji
ani nie udziela nowej zgody na ruch z enkodera. Puszczenie/STOP nadal dociera
do istniejącego wykonawcy. Po anulowaniu komunikatu niewidoczne akcje pozostają
zablokowane do potwierdzenia zwykłej klatki. Na przygaszonym, widocznym ekranie
klik działa normalnie.

## Wspólny transport

Używane są istniejące OledStream/FastOledStream, tokeny, okno DMA i budżet UART.
Zmiana kontrastu C1 oraz AE/AF następuje dopiero na granicy klatki, po ACK.
Wybudzenie przesyła aktualną klatkę przed AF. OFF zatrzymuje ukryte klatki,
ale zachowuje wejście pokrętła i istniejący heartbeat. Nie dodano właściciela SPI.
Nie zmieniono częstotliwości SPI/UART ani timerów i priorytetów MCU.

Brak ACK przechodzi do istniejącego reset_required; dodatek nie resetuje ani
nie uzbraja urządzeń. Przy shutdown/disconnect pozostawia ekran lokalnej
obsłudze MCU. Timer polityki działa raz na sekundę, podczas komunikatu co 0,1 s;
nie wykonuje renderowania w ścieżce każdego kroku silnika ani każdego G-code.

## Natywne menu

Przywrócono natywne grzanie, wyłączanie grzałek, M106 i ruchy względne z menu.
Polecenia trafiają przez zwykły mutex G-code, poza callbackiem ACK. Opóźniona
akcja traci ważność po zmianie generacji menu lub shutdown. SAVE/RESTORE
zachowuje tryb współrzędnych również po odrzuceniu ruchu.

Zachowano ABI i osobne bazowanie X/Y/XY/Z R15.5. Zaktualizowano listę akcji
M11, aby te pozycje były rozpoznawane. Przywrócono wcześniej istniejące kontrole
starego widoku filamentu i tożsamości pliku. Nie przywrócono całej starszej
gałęzi LAB ani dodatkowego właściciela ruchu/grzania.

## Uśpienie ekranu a uśpienie urządzeń

Dodatek nie wywołuje ZORTRAX_SLEEP/ZORTRAX_WAKE ani nie ustawia temperatur,
silników, wentylatorów i pozycji. Jeśli stary moduł maintenance zgłosi wejście
w SLEEP/SLEEPING, dodatek może pokazać komunikat; jego wybudzenie dotyczy tylko
obrazu. Nie przywraca działania ani zadanych temperatur sprzed uśpienia.

## Wybór wariantu Z

R15.7 wybiera skalę natywnego Z raz przy starcie z zachowanego ID3. M07, audyt
ruchu i OLED używają tej samej skali. Brak/uszkodzenie rekordu daje błąd startu;
z_profile=config jest jawnym wyborem operatora. Zobacz
[Warianty sprzętu](HARDWARE_VARIANTS.md).
